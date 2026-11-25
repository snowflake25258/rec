-- Flink SQL Client pipeline. Submit with:
--   sql-client.sh -f pipeline.rendered.sql --pyFiles udfs.py --pyExecutable python3
SET 'sql-client.execution.result-mode' = 'tableau';
SET 'execution.runtime-mode' = 'streaming';
SET 'parallelism.default' = '1';
SET 'table.exec.source.idle-timeout' = '10 s';
SET 'table.local-time-zone' = 'UTC';

CREATE FUNCTION behavior_weight AS 'udfs.behavior_weight' LANGUAGE PYTHON;
CREATE FUNCTION time_decay AS 'udfs.time_decay' LANGUAGE PYTHON;

CREATE TABLE kafka_events (
    event_id STRING, user_id STRING, item_id STRING, action STRING, ts_ms BIGINT,
    event_time AS TO_TIMESTAMP_LTZ(ts_ms, 3),
    proc_time AS PROCTIME(),
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka', 'topic' = '${KAFKA_TOPIC}',
    'properties.bootstrap.servers' = '${KAFKA_BOOTSTRAP_SERVERS}',
    'properties.group.id' = 'yingke-realtime-v1',
    'scan.startup.mode' = 'earliest-offset', 'format' = 'json',
    'json.fail-on-missing-field' = 'true', 'json.ignore-parse-errors' = 'false'
);

CREATE VIEW valid_events AS
SELECT event_id, user_id, item_id, action, ts_ms, event_time, proc_time
FROM kafka_events
WHERE event_id IS NOT NULL AND user_id IS NOT NULL AND item_id IS NOT NULL
AND ts_ms > 0 AND action IN ('view','complete','like','unlike','favorite','unfavorite','follow','unfollow','skip');

CREATE VIEW unique_events AS
SELECT event_id, user_id, item_id, action, ts_ms, event_time
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY proc_time ASC) AS rn
    FROM valid_events
) WHERE rn = 1;

CREATE TABLE mysql_events (
    event_id STRING, user_id STRING, item_id STRING, action STRING, ts_ms BIGINT, weight DOUBLE,
    PRIMARY KEY (event_id) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = '${MYSQL_JDBC_URL}', 'table-name' = 'stream_events',
    'driver' = 'com.mysql.cj.jdbc.Driver',
    'username' = '${MYSQL_USER}', 'password' = '${MYSQL_PASSWORD}',
    'sink.buffer-flush.max-rows' = '100', 'sink.buffer-flush.interval' = '1s',
    'sink.max-retries' = '3'
);

CREATE TABLE mysql_user_item (
    user_id STRING, item_id STRING, preference DOUBLE, interactions BIGINT, last_ts BIGINT,
    PRIMARY KEY (user_id, item_id) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = '${MYSQL_JDBC_URL}', 'table-name' = 'stream_user_item_features',
    'driver' = 'com.mysql.cj.jdbc.Driver',
    'username' = '${MYSQL_USER}', 'password' = '${MYSQL_PASSWORD}',
    'sink.buffer-flush.max-rows' = '100', 'sink.buffer-flush.interval' = '1s',
    'sink.max-retries' = '3'
);

CREATE TABLE mysql_hotness (
    item_id STRING, window_start TIMESTAMP(3), window_end TIMESTAMP(3), score DOUBLE, interactions BIGINT,
    PRIMARY KEY (item_id, window_start) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = '${MYSQL_JDBC_URL}', 'table-name' = 'stream_item_hotness',
    'driver' = 'com.mysql.cj.jdbc.Driver',
    'username' = '${MYSQL_USER}', 'password' = '${MYSQL_PASSWORD}',
    'sink.buffer-flush.max-rows' = '100', 'sink.buffer-flush.interval' = '1s',
    'sink.max-retries' = '3'
);

SET 'pipeline.name' = 'yingke-realtime-recommendations';

EXECUTE STATEMENT SET
BEGIN
INSERT INTO mysql_events
SELECT event_id, user_id, item_id, action, ts_ms, behavior_weight(action) FROM unique_events;


INSERT INTO mysql_user_item
SELECT user_id, item_id, SUM(behavior_weight(action)), COUNT(*), MAX(ts_ms)
FROM unique_events GROUP BY user_id, item_id;

INSERT INTO mysql_hotness
SELECT item_id, window_start, window_end,
    SUM(time_decay(behavior_weight(action), CAST(TIMESTAMPDIFF(SECOND, CAST(event_time AS TIMESTAMP(3)), window_end) AS DOUBLE) / 3600.0)),
    COUNT(*)
FROM TABLE(TUMBLE(TABLE unique_events, DESCRIPTOR(event_time), INTERVAL '1' MINUTE))
GROUP BY item_id, window_start, window_end;
END;
