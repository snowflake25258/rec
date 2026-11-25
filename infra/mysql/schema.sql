-- Unified MySQL schema; runtime SQLAlchemy metadata is authoritative.


CREATE TABLE event_outbox (
	event_id VARCHAR(64) NOT NULL, 
	payload JSON NOT NULL, 
	created_at DOUBLE NOT NULL, 
	delivered_at DOUBLE, 
	attempts INTEGER NOT NULL, 
	last_error TEXT, 
	PRIMARY KEY (event_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_outbox_pending ON event_outbox (delivered_at, created_at, event_id);


CREATE TABLE model_versions (
	id VARCHAR(64) NOT NULL, 
	algorithm VARCHAR(64) NOT NULL, 
	artifact_path TEXT NOT NULL, 
	metrics JSON NOT NULL, 
	created_at DOUBLE NOT NULL, 
	active BOOL NOT NULL, 
	PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;


CREATE TABLE users (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	avatar VARCHAR(256) NOT NULL, 
	PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;


CREATE TABLE follows (
	user_id VARCHAR(64) NOT NULL, 
	creator_id VARCHAR(64) NOT NULL, 
	active BOOL NOT NULL, 
	PRIMARY KEY (user_id, creator_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(creator_id) REFERENCES users (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;


CREATE TABLE videos (
	id VARCHAR(64) NOT NULL, 
	author_id VARCHAR(64) NOT NULL, 
	title VARCHAR(256) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	tags VARCHAR(512) NOT NULL, 
	description TEXT NOT NULL, 
	video_url TEXT NOT NULL, 
	cover TEXT NOT NULL, 
	duration INTEGER NOT NULL, 
	created_at DOUBLE NOT NULL, 
	base_likes INTEGER NOT NULL, 
	published BOOL NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(author_id) REFERENCES users (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;


CREATE TABLE video_interactions (
	user_id VARCHAR(64) NOT NULL, 
	item_id VARCHAR(64) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	active BOOL NOT NULL, 
	PRIMARY KEY (user_id, item_id, kind), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(item_id) REFERENCES videos (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_video_likes ON video_interactions (item_id, kind, active);


CREATE TABLE events (
	event_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	item_id VARCHAR(64) NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	ts_ms BIGINT NOT NULL, 
	weight DOUBLE NOT NULL, 
	PRIMARY KEY (event_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_events_time ON events (ts_ms, event_id);


CREATE TABLE item_hotness (
	item_id VARCHAR(64) NOT NULL, 
	window_start DATETIME(3) NOT NULL, 
	window_end DATETIME(3) NOT NULL, 
	score DOUBLE NOT NULL, 
	interactions BIGINT NOT NULL, 
	PRIMARY KEY (item_id, window_start)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;


CREATE TABLE stream_events (
	event_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	item_id VARCHAR(64) NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	ts_ms BIGINT NOT NULL, 
	weight DOUBLE NOT NULL, 
	PRIMARY KEY (event_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_stream_events_time ON stream_events (ts_ms, event_id);


CREATE TABLE stream_item_hotness (
	item_id VARCHAR(64) NOT NULL, 
	window_start DATETIME(3) NOT NULL, 
	window_end DATETIME(3) NOT NULL, 
	score DOUBLE NOT NULL, 
	interactions BIGINT NOT NULL, 
	PRIMARY KEY (item_id, window_start)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;


CREATE TABLE stream_user_item_features (
	user_id VARCHAR(64) NOT NULL, 
	item_id VARCHAR(64) NOT NULL, 
	preference DOUBLE NOT NULL, 
	interactions BIGINT NOT NULL, 
	last_ts BIGINT NOT NULL, 
	PRIMARY KEY (user_id, item_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_stream_features_updated ON stream_user_item_features (last_ts);


CREATE TABLE user_item_features (
	user_id VARCHAR(64) NOT NULL, 
	item_id VARCHAR(64) NOT NULL, 
	preference DOUBLE NOT NULL, 
	interactions BIGINT NOT NULL, 
	last_ts BIGINT NOT NULL, 
	PRIMARY KEY (user_id, item_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_features_updated ON user_item_features (last_ts);


CREATE TABLE accounts (
	user_id VARCHAR(64) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	created_at DOUBLE NOT NULL, 
	last_login_at DOUBLE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE UNIQUE INDEX ux_accounts_username ON accounts (username);


CREATE TABLE auth_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	created_at DOUBLE NOT NULL, 
	expires_at DOUBLE NOT NULL, 
	last_seen_at DOUBLE NOT NULL, 
	user_agent VARCHAR(255) NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin

;

CREATE INDEX ix_auth_sessions_user ON auth_sessions (user_id);
CREATE INDEX ix_auth_sessions_expiry ON auth_sessions (expires_at);