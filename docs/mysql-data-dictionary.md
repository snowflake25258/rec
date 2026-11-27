# MySQL 中文数据字典

时间单位以每个字段的说明为准。业务与会话时间为 Unix 秒，事件与特征时间为 Unix 毫秒。
模型与视频二进制保存在持久化目录，MySQL 保存路径与元数据。

## event_outbox：业务事务内持久化的待投递事件及投递状态表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| event_id | VARCHAR(64) | 否 | 事件唯一标识；相同标识只允许相同业务载荷 |
| payload | JSON | 否 | 完整事件 JSON，包含用户、视频、行为及秒级时间戳 |
| created_at | DOUBLE | 否 | 事件写入时记录的时间；Unix 时间戳，单位秒 |
| delivered_at | DOUBLE | 是 | 已投递或无需投递的标记时间，单位秒；空值表示待投递 |
| attempts | INTEGER | 否 | 持久化投递尝试次数，包含成功和失败 |
| last_error | TEXT | 是 | 最近投递错误摘要；成功后清空 |

主键：event_id。

## model_versions：推荐模型训练任务、评估与版本元数据表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| id | VARCHAR(64) | 否 | 模型版本唯一标识 |
| algorithm | VARCHAR(64) | 否 | 模型算法标识：als、fm 或 two_tower |
| artifact_path | TEXT | 否 | 持久化模型制品文件路径；不存储模型二进制内容 |
| metrics | JSON | 否 | 训练状态、配置、评估指标、损失与校验信息 JSON |
| created_at | DOUBLE | 否 | 训练任务创建时间；Unix 时间戳，单位秒 |
| active | BOOL | 否 | 是否为该算法当前启用的模型版本 |

主键：id。

## users：用户与创作者公开资料表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| id | VARCHAR(64) | 否 | 用户或创作者唯一标识 |
| name | VARCHAR(128) | 否 | 展示昵称 |
| avatar | VARCHAR(256) | 否 | 头像标记或头像地址 |

主键：id。

## accounts：账号登录凭据表；与公开用户资料分离

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| user_id | VARCHAR(64) | 否 | 账号所属用户标识，关联用户资料 |
| username | VARCHAR(64) | 否 | 规范化登录名；去除首尾空格并转为小写，唯一 |
| password_hash | VARCHAR(255) | 否 | 密码的 PBKDF2 摘要，包含算法、迭代次数、盐与派生密钥 |
| created_at | DOUBLE | 否 | 账号创建时间；Unix 时间戳，单位秒 |
| last_login_at | DOUBLE | 否 | 最近登录时间；Unix 时间戳，单位秒 |

主键：user_id。

## auth_sessions：不透明 Bearer 登录会话表；仅保存令牌摘要

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| token_hash | VARCHAR(64) | 否 | 会话令牌的 SHA-256 十六进制摘要；不保存原始令牌 |
| user_id | VARCHAR(64) | 否 | 登录用户标识 |
| created_at | DOUBLE | 否 | 会话创建时间；Unix 秒级时间戳 |
| expires_at | DOUBLE | 否 | 会话过期时间；Unix 秒级时间戳 |
| last_seen_at | DOUBLE | 否 | 最近会话验证时间；Unix 秒级时间戳 |
| user_agent | VARCHAR(255) | 否 | 登录客户端的用户代理信息，最长 255 字符 |

主键：token_hash。

## follows：用户关注创作者的当前状态表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| user_id | VARCHAR(64) | 否 | 发起关注的用户标识 |
| creator_id | VARCHAR(64) | 否 | 被关注的创作者标识 |
| active | BOOL | 否 | 是否正在关注；取消关注时置为假 |

主键：user_id、creator_id。

## videos：视频目录与发布状态表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| id | VARCHAR(64) | 否 | 视频唯一标识 |
| author_id | VARCHAR(64) | 否 | 作者标识，关联用户资料 |
| title | VARCHAR(256) | 否 | 视频标题 |
| category | VARCHAR(64) | 否 | 内容类别 |
| tags | VARCHAR(512) | 否 | 视频标签文本 |
| description | TEXT | 否 | 视频内容描述 |
| video_url | TEXT | 否 | 视频播放地址；可为本地媒体接口路径 |
| cover | TEXT | 否 | 视频封面地址 |
| duration | INTEGER | 否 | 视频实际时长，单位秒 |
| created_at | DOUBLE | 否 | 发布时间；Unix 时间戳，单位秒 |
| base_likes | INTEGER | 否 | 演示初始点赞数量；不等同于真实用户点赞 |
| published | BOOL | 否 | 是否已发布；未发布视频不进入公开视频目录 |

主键：id。

## video_interactions：用户对视频的点赞与收藏当前状态表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| user_id | VARCHAR(64) | 否 | 用户标识 |
| item_id | VARCHAR(64) | 否 | 视频标识 |
| kind | VARCHAR(16) | 否 | 互动类型：like 点赞或 favorite 收藏 |
| active | BOOL | 否 | 互动是否有效；取消操作保留记录并置为假 |

主键：user_id、item_id、kind。

## events：演示模式去重行为明细表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| event_id | VARCHAR(64) | 否 | 行为事件唯一标识；用于业务幂等与流处理去重 |
| user_id | VARCHAR(64) | 否 | 触发行为的用户标识 |
| item_id | VARCHAR(64) | 否 | 行为对应的视频标识 |
| action | VARCHAR(16) | 否 | 行为类型：观看、完播、点赞及取消、收藏及取消、关注及取消、跳过 |
| ts_ms | BIGINT | 否 | 事件发生时间；Unix 时间戳，单位毫秒 |
| weight | DOUBLE | 否 | 行为权重；正值增加偏好，取消或跳过可为负值 |

主键：event_id。

## item_hotness：演示模式预留的一分钟窗口热度表；demo 不执行窗口作业

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| item_id | VARCHAR(64) | 否 | 视频标识；与窗口起点共同组成主键 |
| window_start | DATETIME(3) | 否 | 一分钟事件时间窗口起点；按 UTC 存储，精确到毫秒 |
| window_end | DATETIME(3) | 否 | 一分钟事件时间窗口终点；右边界不包含在窗口内 |
| score | DOUBLE | 否 | 窗口内经过时间衰减的行为权重总和 |
| interactions | BIGINT | 否 | 窗口内去重行为事件数量 |

主键：item_id、window_start。

## stream_events：Flink 实时作业输出的去重行为明细表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| event_id | VARCHAR(64) | 否 | 行为事件唯一标识；用于业务幂等与流处理去重 |
| user_id | VARCHAR(64) | 否 | 触发行为的用户标识 |
| item_id | VARCHAR(64) | 否 | 行为对应的视频标识 |
| action | VARCHAR(16) | 否 | 行为类型：观看、完播、点赞及取消、收藏及取消、关注及取消、跳过 |
| ts_ms | BIGINT | 否 | 事件发生时间；Unix 时间戳，单位毫秒 |
| weight | DOUBLE | 否 | 行为权重；正值增加偏好，取消或跳过可为负值 |

主键：event_id。

## stream_item_hotness：Flink 一分钟事件时间窗口输出的视频热度表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| item_id | VARCHAR(64) | 否 | 视频标识；与窗口起点共同组成主键 |
| window_start | DATETIME(3) | 否 | 一分钟事件时间窗口起点；按 UTC 存储，精确到毫秒 |
| window_end | DATETIME(3) | 否 | 一分钟事件时间窗口终点；右边界不包含在窗口内 |
| score | DOUBLE | 否 | 窗口内经过时间衰减的行为权重总和 |
| interactions | BIGINT | 否 | 窗口内去重行为事件数量 |

主键：item_id、window_start。

## stream_user_item_features：Flink 连续聚合输出的用户视频偏好特征表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| user_id | VARCHAR(64) | 否 | 用户标识；与视频标识共同组成主键 |
| item_id | VARCHAR(64) | 否 | 视频标识；与用户标识共同组成主键 |
| preference | DOUBLE | 否 | 累计行为权重；推荐算法读取时将负偏好截断为零 |
| interactions | BIGINT | 否 | 累计去重行为事件数量，包含正负反馈 |
| last_ts | BIGINT | 否 | 最近行为发生时间；Unix 时间戳，单位毫秒 |

主键：user_id、item_id。

## user_item_features：演示模式用户视频累计偏好特征表

| 字段 | 类型 | 可空 | 中文说明 |
| --- | --- | --- | --- |
| user_id | VARCHAR(64) | 否 | 用户标识；与视频标识共同组成主键 |
| item_id | VARCHAR(64) | 否 | 视频标识；与用户标识共同组成主键 |
| preference | DOUBLE | 否 | 累计行为权重；推荐算法读取时将负偏好截断为零 |
| interactions | BIGINT | 否 | 累计去重行为事件数量，包含正负反馈 |
| last_ts | BIGINT | 否 | 最近行为发生时间；Unix 时间戳，单位毫秒 |

主键：user_id、item_id。

