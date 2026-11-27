-- 映刻 MySQL 完整建表脚本；由 SQLAlchemy 元数据生成。
-- 包含业务、登录会话及演示/生产分析表。已有数据库请使用注释同步命令，勿重复执行 CREATE TABLE。
SET NAMES utf8mb4;

CREATE TABLE event_outbox (
	event_id VARCHAR(64) NOT NULL COMMENT '事件唯一标识；相同标识只允许相同业务载荷',
	payload JSON NOT NULL COMMENT '完整事件 JSON，包含用户、视频、行为及秒级时间戳',
	created_at DOUBLE NOT NULL COMMENT '事件写入时记录的时间；Unix 时间戳，单位秒',
	delivered_at DOUBLE COMMENT '已投递或无需投递的标记时间，单位秒；空值表示待投递',
	attempts INTEGER NOT NULL COMMENT '持久化投递尝试次数，包含成功和失败',
	last_error TEXT COMMENT '最近投递错误摘要；成功后清空',
	PRIMARY KEY (event_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='业务事务内持久化的待投递事件及投递状态表' COLLATE utf8mb4_bin;

CREATE INDEX ix_outbox_pending ON event_outbox (delivered_at, created_at, event_id);

CREATE TABLE model_versions (
	id VARCHAR(64) NOT NULL COMMENT '模型版本唯一标识',
	algorithm VARCHAR(64) NOT NULL COMMENT '模型算法标识：als、fm 或 two_tower',
	artifact_path TEXT NOT NULL COMMENT '持久化模型制品文件路径；不存储模型二进制内容',
	metrics JSON NOT NULL COMMENT '训练状态、配置、评估指标、损失与校验信息 JSON',
	created_at DOUBLE NOT NULL COMMENT '训练任务创建时间；Unix 时间戳，单位秒',
	active BOOL NOT NULL COMMENT '是否为该算法当前启用的模型版本',
	PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='推荐模型训练任务、评估与版本元数据表' COLLATE utf8mb4_bin;


CREATE TABLE users (
	id VARCHAR(64) NOT NULL COMMENT '用户或创作者唯一标识',
	name VARCHAR(128) NOT NULL COMMENT '展示昵称',
	avatar VARCHAR(256) NOT NULL COMMENT '头像标记或头像地址',
	PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='用户与创作者公开资料表' COLLATE utf8mb4_bin;


CREATE TABLE accounts (
	user_id VARCHAR(64) NOT NULL COMMENT '账号所属用户标识，关联用户资料',
	username VARCHAR(64) NOT NULL COMMENT '规范化登录名；去除首尾空格并转为小写，唯一',
	password_hash VARCHAR(255) NOT NULL COMMENT '密码的 PBKDF2 摘要，包含算法、迭代次数、盐与派生密钥',
	created_at DOUBLE NOT NULL COMMENT '账号创建时间；Unix 时间戳，单位秒',
	last_login_at DOUBLE NOT NULL COMMENT '最近登录时间；Unix 时间戳，单位秒',
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='账号登录凭据表；与公开用户资料分离' COLLATE utf8mb4_bin;

CREATE UNIQUE INDEX ux_accounts_username ON accounts (username);

CREATE TABLE auth_sessions (
	token_hash VARCHAR(64) NOT NULL COMMENT '会话令牌的 SHA-256 十六进制摘要；不保存原始令牌',
	user_id VARCHAR(64) NOT NULL COMMENT '登录用户标识',
	created_at DOUBLE NOT NULL COMMENT '会话创建时间；Unix 秒级时间戳',
	expires_at DOUBLE NOT NULL COMMENT '会话过期时间；Unix 秒级时间戳',
	last_seen_at DOUBLE NOT NULL COMMENT '最近会话验证时间；Unix 秒级时间戳',
	user_agent VARCHAR(255) NOT NULL COMMENT '登录客户端的用户代理信息，最长 255 字符',
	PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='不透明 Bearer 登录会话表；仅保存令牌摘要' COLLATE utf8mb4_bin;

CREATE INDEX ix_auth_sessions_expiry ON auth_sessions (expires_at);
CREATE INDEX ix_auth_sessions_user ON auth_sessions (user_id);

CREATE TABLE follows (
	user_id VARCHAR(64) NOT NULL COMMENT '发起关注的用户标识',
	creator_id VARCHAR(64) NOT NULL COMMENT '被关注的创作者标识',
	active BOOL NOT NULL COMMENT '是否正在关注；取消关注时置为假',
	PRIMARY KEY (user_id, creator_id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(creator_id) REFERENCES users (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='用户关注创作者的当前状态表' COLLATE utf8mb4_bin;


CREATE TABLE videos (
	id VARCHAR(64) NOT NULL COMMENT '视频唯一标识',
	author_id VARCHAR(64) NOT NULL COMMENT '作者标识，关联用户资料',
	title VARCHAR(256) NOT NULL COMMENT '视频标题',
	category VARCHAR(64) NOT NULL COMMENT '内容类别',
	tags VARCHAR(512) NOT NULL COMMENT '视频标签文本',
	description TEXT NOT NULL COMMENT '视频内容描述',
	video_url TEXT NOT NULL COMMENT '视频播放地址；可为本地媒体接口路径',
	cover TEXT NOT NULL COMMENT '视频封面地址',
	duration INTEGER NOT NULL COMMENT '视频实际时长，单位秒',
	created_at DOUBLE NOT NULL COMMENT '发布时间；Unix 时间戳，单位秒',
	base_likes INTEGER NOT NULL COMMENT '演示初始点赞数量；不等同于真实用户点赞',
	published BOOL NOT NULL COMMENT '是否已发布；未发布视频不进入公开视频目录',
	PRIMARY KEY (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='视频目录与发布状态表' COLLATE utf8mb4_bin;


CREATE TABLE video_interactions (
	user_id VARCHAR(64) NOT NULL COMMENT '用户标识',
	item_id VARCHAR(64) NOT NULL COMMENT '视频标识',
	kind VARCHAR(16) NOT NULL COMMENT '互动类型：like 点赞或 favorite 收藏',
	active BOOL NOT NULL COMMENT '互动是否有效；取消操作保留记录并置为假',
	PRIMARY KEY (user_id, item_id, kind),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(item_id) REFERENCES videos (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='用户对视频的点赞与收藏当前状态表' COLLATE utf8mb4_bin;

CREATE INDEX ix_video_likes ON video_interactions (item_id, kind, active);

CREATE TABLE events (
	event_id VARCHAR(64) NOT NULL COMMENT '行为事件唯一标识；用于业务幂等与流处理去重',
	user_id VARCHAR(64) NOT NULL COMMENT '触发行为的用户标识',
	item_id VARCHAR(64) NOT NULL COMMENT '行为对应的视频标识',
	action VARCHAR(16) NOT NULL COMMENT '行为类型：观看、完播、点赞及取消、收藏及取消、关注及取消、跳过',
	ts_ms BIGINT NOT NULL COMMENT '事件发生时间；Unix 时间戳，单位毫秒',
	weight DOUBLE NOT NULL COMMENT '行为权重；正值增加偏好，取消或跳过可为负值',
	PRIMARY KEY (event_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='演示模式去重行为明细表' COLLATE utf8mb4_bin;

CREATE INDEX ix_events_time ON events (ts_ms, event_id);

CREATE TABLE item_hotness (
	item_id VARCHAR(64) NOT NULL COMMENT '视频标识；与窗口起点共同组成主键',
	window_start DATETIME(3) NOT NULL COMMENT '一分钟事件时间窗口起点；按 UTC 存储，精确到毫秒',
	window_end DATETIME(3) NOT NULL COMMENT '一分钟事件时间窗口终点；右边界不包含在窗口内',
	score DOUBLE NOT NULL COMMENT '窗口内经过时间衰减的行为权重总和',
	interactions BIGINT NOT NULL COMMENT '窗口内去重行为事件数量',
	PRIMARY KEY (item_id, window_start)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='演示模式预留的一分钟窗口热度表；demo 不执行窗口作业' COLLATE utf8mb4_bin;


CREATE TABLE stream_events (
	event_id VARCHAR(64) NOT NULL COMMENT '行为事件唯一标识；用于业务幂等与流处理去重',
	user_id VARCHAR(64) NOT NULL COMMENT '触发行为的用户标识',
	item_id VARCHAR(64) NOT NULL COMMENT '行为对应的视频标识',
	action VARCHAR(16) NOT NULL COMMENT '行为类型：观看、完播、点赞及取消、收藏及取消、关注及取消、跳过',
	ts_ms BIGINT NOT NULL COMMENT '事件发生时间；Unix 时间戳，单位毫秒',
	weight DOUBLE NOT NULL COMMENT '行为权重；正值增加偏好，取消或跳过可为负值',
	PRIMARY KEY (event_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='Flink 实时作业输出的去重行为明细表' COLLATE utf8mb4_bin;

CREATE INDEX ix_stream_events_time ON stream_events (ts_ms, event_id);

CREATE TABLE stream_item_hotness (
	item_id VARCHAR(64) NOT NULL COMMENT '视频标识；与窗口起点共同组成主键',
	window_start DATETIME(3) NOT NULL COMMENT '一分钟事件时间窗口起点；按 UTC 存储，精确到毫秒',
	window_end DATETIME(3) NOT NULL COMMENT '一分钟事件时间窗口终点；右边界不包含在窗口内',
	score DOUBLE NOT NULL COMMENT '窗口内经过时间衰减的行为权重总和',
	interactions BIGINT NOT NULL COMMENT '窗口内去重行为事件数量',
	PRIMARY KEY (item_id, window_start)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='Flink 一分钟事件时间窗口输出的视频热度表' COLLATE utf8mb4_bin;


CREATE TABLE stream_user_item_features (
	user_id VARCHAR(64) NOT NULL COMMENT '用户标识；与视频标识共同组成主键',
	item_id VARCHAR(64) NOT NULL COMMENT '视频标识；与用户标识共同组成主键',
	preference DOUBLE NOT NULL COMMENT '累计行为权重；推荐算法读取时将负偏好截断为零',
	interactions BIGINT NOT NULL COMMENT '累计去重行为事件数量，包含正负反馈',
	last_ts BIGINT NOT NULL COMMENT '最近行为发生时间；Unix 时间戳，单位毫秒',
	PRIMARY KEY (user_id, item_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='Flink 连续聚合输出的用户视频偏好特征表' COLLATE utf8mb4_bin;

CREATE INDEX ix_stream_features_updated ON stream_user_item_features (last_ts);

CREATE TABLE user_item_features (
	user_id VARCHAR(64) NOT NULL COMMENT '用户标识；与视频标识共同组成主键',
	item_id VARCHAR(64) NOT NULL COMMENT '视频标识；与用户标识共同组成主键',
	preference DOUBLE NOT NULL COMMENT '累计行为权重；推荐算法读取时将负偏好截断为零',
	interactions BIGINT NOT NULL COMMENT '累计去重行为事件数量，包含正负反馈',
	last_ts BIGINT NOT NULL COMMENT '最近行为发生时间；Unix 时间戳，单位毫秒',
	PRIMARY KEY (user_id, item_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='演示模式用户视频累计偏好特征表' COLLATE utf8mb4_bin;

CREATE INDEX ix_features_updated ON user_item_features (last_ts);
