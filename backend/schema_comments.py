"""统一管理 MySQL 表、字段的中文数据字典，以及已有表的注释同步。

注释挂载在 SQLAlchemy 元数据上，供 create_all 和静态 SQL 使用。
已有表不会因 create_all 自动更新，因此初始化命令还需显式同步注释。
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import MetaData, Table, inspect, literal
from sqlalchemy.engine import Connection, Engine

# 复用字段字典，保证 demo 与 production 的同构分析表含义一致。
EVENT_COLUMNS = {
    'event_id': '行为事件唯一标识；用于业务幂等与流处理去重',
    'user_id': '触发行为的用户标识',
    'item_id': '行为对应的视频标识',
    'action': '行为类型：观看、完播、点赞及取消、收藏及取消、关注及取消、跳过',
    'ts_ms': '事件发生时间；Unix 时间戳，单位毫秒',
    'weight': '行为权重；正值增加偏好，取消或跳过可为负值',
}
FEATURE_COLUMNS = {
    'user_id': '用户标识；与视频标识共同组成主键',
    'item_id': '视频标识；与用户标识共同组成主键',
    'preference': '累计行为权重；推荐算法读取时将负偏好截断为零',
    'interactions': '累计去重行为事件数量，包含正负反馈',
    'last_ts': '最近行为发生时间；Unix 时间戳，单位毫秒',
}
HOTNESS_COLUMNS = {
    'item_id': '视频标识；与窗口起点共同组成主键',
    'window_start': '一分钟事件时间窗口起点；按 UTC 存储，精确到毫秒',
    'window_end': '一分钟事件时间窗口终点；右边界不包含在窗口内',
    'score': '窗口内经过时间衰减的行为权重总和',
    'interactions': '窗口内去重行为事件数量',
}
TABLE_COMMENTS: dict[str, tuple[str, dict[str, str]]] = {
    'users': ('用户与创作者公开资料表', {
        'id': '用户或创作者唯一标识', 'name': '展示昵称', 'avatar': '头像标记或头像地址',
    }),
    'videos': ('视频目录与发布状态表', {
        'id': '视频唯一标识', 'author_id': '作者标识，关联用户资料',
        'title': '视频标题', 'category': '内容类别', 'tags': '视频标签文本',
        'description': '视频内容描述', 'video_url': '视频播放地址；可为本地媒体接口路径',
        'cover': '视频封面地址', 'duration': '视频实际时长，单位秒',
        'created_at': '发布时间；Unix 时间戳，单位秒',
        'base_likes': '演示初始点赞数量；不等同于真实用户点赞',
        'published': '是否已发布；未发布视频不进入公开视频目录',
    }),
    'video_interactions': ('用户对视频的点赞与收藏当前状态表', {
        'user_id': '用户标识', 'item_id': '视频标识',
        'kind': '互动类型：like 点赞或 favorite 收藏',
        'active': '互动是否有效；取消操作保留记录并置为假',
    }),
    'follows': ('用户关注创作者的当前状态表', {
        'user_id': '发起关注的用户标识', 'creator_id': '被关注的创作者标识',
        'active': '是否正在关注；取消关注时置为假',
    }),
    'event_outbox': ('业务事务内持久化的待投递事件及投递状态表', {
        'event_id': '事件唯一标识；相同标识只允许相同业务载荷',
        'payload': '完整事件 JSON，包含用户、视频、行为及秒级时间戳',
        'created_at': '事件写入时记录的时间；Unix 时间戳，单位秒',
        'delivered_at': '已投递或无需投递的标记时间，单位秒；空值表示待投递',
        'attempts': '持久化投递尝试次数，包含成功和失败',
        'last_error': '最近投递错误摘要；成功后清空',
    }),
    'model_versions': ('推荐模型训练任务、评估与版本元数据表', {
        'id': '模型版本唯一标识', 'algorithm': '模型算法标识：als、fm 或 two_tower',
        'artifact_path': '持久化模型制品文件路径；不存储模型二进制内容',
        'metrics': '训练状态、配置、评估指标、损失与校验信息 JSON',
        'created_at': '训练任务创建时间；Unix 时间戳，单位秒',
        'active': '是否为该算法当前启用的模型版本',
    }),
    'accounts': ('账号登录凭据表；与公开用户资料分离', {
        'user_id': '账号所属用户标识，关联用户资料',
        'username': '规范化登录名；去除首尾空格并转为小写，唯一',
        'password_hash': '密码的 PBKDF2 摘要，包含算法、迭代次数、盐与派生密钥',
        'created_at': '账号创建时间；Unix 时间戳，单位秒',
        'last_login_at': '最近登录时间；Unix 时间戳，单位秒',
    }),
    'auth_sessions': ('不透明 Bearer 登录会话表；仅保存令牌摘要', {
        'token_hash': '会话令牌的 SHA-256 十六进制摘要；不保存原始令牌',
        'user_id': '登录用户标识', 'created_at': '会话创建时间；Unix 秒级时间戳',
        'expires_at': '会话过期时间；Unix 秒级时间戳',
        'last_seen_at': '最近会话验证时间；Unix 秒级时间戳',
        'user_agent': '登录客户端的用户代理信息，最长 255 字符',
    }),
    'events': ('演示模式去重行为明细表', EVENT_COLUMNS),
    'user_item_features': ('演示模式用户视频累计偏好特征表', FEATURE_COLUMNS),
    'item_hotness': ('演示模式预留的一分钟窗口热度表；demo 不执行窗口作业', HOTNESS_COLUMNS),
    'stream_events': ('Flink 实时作业输出的去重行为明细表', EVENT_COLUMNS),
    'stream_user_item_features': ('Flink 连续聚合输出的用户视频偏好特征表', FEATURE_COLUMNS),
    'stream_item_hotness': ('Flink 一分钟事件时间窗口输出的视频热度表', HOTNESS_COLUMNS),
}


def apply_comments(metadata: MetaData) -> None:
    """为已声明的每张表和每个字段设置注释；新增字段未写字典时直接报错。"""
    for table in metadata.tables.values():
        description, columns = TABLE_COMMENTS[table.name]
        table.comment = description
        for column in table.columns:
            column.comment = columns[column.name]


# SHOW CREATE TABLE 的字段定义可能含 SQL 转义或双单引号，不能简单按引号截断。
COMMENT_CLAUSE = re.compile(
    r"`(?:``|[^`])*`|'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.|\"\")*\""
    r"|(?P<comment>\s+COMMENT\s+'(?:[^'\\]|\\.|'')*')", re.IGNORECASE)


def replace_column_comment(definition: str, comment_sql: str) -> str:
    """保留服务器返回的完整字段定义，仅替换 COMMENT，避免丢失默认值等属性。"""
    # 先识别字符串与标识符，避免误删 DEFAULT 'COMMENT ...' 中的普通文本。
    definition = COMMENT_CLAUSE.sub(
        lambda match: '' if match.group('comment') else match.group(),
        definition.rstrip().removesuffix(','))
    return definition + ' COMMENT ' + comment_sql


def comment_sql(connection: Connection, table: Table) -> str | None:
    """仅为存在差异的表生成一条 ALTER；相同注释再次执行不会触发 DDL。

    采用 SHOW CREATE TABLE 原始列定义，而不是用 ORM 类型覆盖已有列。
    因此兼容历史表的类型、可空性、默认值及 ON UPDATE 等实际属性。
    """
    inspector = inspect(connection)
    existing = {column['name']: column for column in inspector.get_columns(table.name)}
    quote = connection.dialect.identifier_preparer.quote_identifier
    sql_literal = lambda value: str(literal(value).compile(
        dialect=connection.dialect, compile_kwargs={'literal_binds': True}))
    changes: list[str] = []
    if inspector.get_table_comment(table.name).get('text') != table.comment:
        changes.append('COMMENT = ' + sql_literal(table.comment))
    missing = set(table.columns.keys()) - existing.keys()
    if missing:
        raise ValueError(f'{table.name} 缺少字段，不能同步注释：{sorted(missing)}')
    different = [column for column in table.columns
                 if existing[column.name].get('comment') != column.comment]
    if different:
        ddl = connection.exec_driver_sql(f'SHOW CREATE TABLE {quote(table.name)}').one()[1]
        definitions = {line.strip().split('`', 2)[1]: line.strip()
                       for line in ddl.splitlines() if line.lstrip().startswith('`')}
        for column in different:
            definition = definitions[column.name]
            changes.append('MODIFY COLUMN ' + replace_column_comment(definition, sql_literal(column.comment)))
    return f'ALTER TABLE {quote(table.name)} ' + ', '.join(changes) if changes else None


def sync_mysql_comments(engine: Engine, metadatas: Iterable[MetaData]) -> int:
    """同步既有 MySQL 表注释，返回实际 ALTER 表数量；不创建数据库、不更新业务行。

    MySQL DDL 会隐式提交，逐表执行，失败后可重试；不能依赖事务回滚所有 ALTER。
    MODIFY 仍可能获取元数据锁，建议在低流量时执行。
    """
    if engine.dialect.name != 'mysql':
        raise ValueError('注释同步仅支持 MySQL')
    changed = 0
    with engine.connect() as connection:
        for metadata in metadatas:
            for table in metadata.sorted_tables:
                statement = comment_sql(connection, table)
                if statement:
                    connection.exec_driver_sql(statement)
                    changed += 1
    return changed
