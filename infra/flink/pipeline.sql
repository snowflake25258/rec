-- Flink SQL Client pipeline. Submit with:
--   sql-client.sh -f pipeline.rendered.sql --pyFiles udfs.py --pyExecutable python3
-- 实时链路：Kafka JSON 事件 -> 校验 -> event_id 去重 -> 三路 MySQL JDBC 输出。
-- 三条 INSERT 归属一个 Statement Set，共用一个 Job ID 和 checkpoint/savepoint。
SET 'sql-client.execution.result-mode' = 'tableau';
SET 'execution.runtime-mode' = 'streaming';
SET 'parallelism.default' = '1';
-- 空闲 Kafka 分区不阻塞其他分区的 watermark；全部输入空闲时仍不能保证窗口立即输出。
SET 'table.exec.source.idle-timeout' = '10 s';
SET 'table.local-time-zone' = 'UTC';

CREATE FUNCTION behavior_weight AS 'udfs.behavior_weight' LANGUAGE PYTHON;
CREATE FUNCTION time_decay AS 'udfs.time_decay' LANGUAGE PYTHON;

-- 创建source表--kafka-- 无界流额
CREATE TABLE kafka_events (
    event_id STRING COMMENT '事件唯一标识，用于流内去重',
    user_id STRING COMMENT '行为所属用户标识',
    item_id STRING COMMENT '视频标识',
    action STRING COMMENT '观看、完播、点赞、收藏、关注、取消或跳过',
    ts_ms BIGINT COMMENT '事件发生时间，Unix 毫秒时间戳',
    -- event_time 决定窗口归属；proc_time 只决定同一事件首次到达的顺序。
    event_time AS TO_TIMESTAMP_LTZ(ts_ms, 3),
    proc_time AS PROCTIME(),
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = '${KAFKA_TOPIC}',
    'properties.bootstrap.servers' = '${KAFKA_BOOTSTRAP_SERVERS}',
    'properties.group.id' = 'yingke-realtime-v1',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json',
    'json.fail-on-missing-field' = 'true',
    'json.ignore-parse-errors' = 'false'
);

-- 1、对数据进行清洗过滤(ETL)
CREATE VIEW valid_events AS
SELECT event_id, user_id, item_id, action, ts_ms, event_time, proc_time
FROM kafka_events
WHERE event_id IS NOT NULL AND user_id IS NOT NULL AND item_id IS NOT NULL
AND ts_ms > 0 AND action IN ('view','complete','like','unlike','favorite','unfavorite','follow','unfollow','skip');

-- 2、取重
-- Outbox 至少一次投递可能重复发送，保留每个 event_id 首次到达的事件。
-- 此处没有设置去重状态 TTL，长期运行时需关注状态规模；恢复时必须保留相应状态。
CREATE VIEW unique_events AS
SELECT event_id, user_id, item_id, action, ts_ms, event_time
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY proc_time ASC) AS rn
    FROM valid_events
) WHERE rn = 1;

-- 创建sink表，权重明细表
CREATE TABLE mysql_events (
    event_id STRING COMMENT '事件唯一标识，对应 MySQL 主键',
    user_id STRING COMMENT '用户标识',
    item_id STRING COMMENT '视频标识',
    action STRING COMMENT '行为类型',
    ts_ms BIGINT COMMENT '事件发生时间，单位毫秒',
    weight DOUBLE COMMENT '行为权重，取消操作可为负数',
    -- NOT ENFORCED 表示 Flink 信任唯一性；物理表主键由 MySQL 建表脚本创建。
    PRIMARY KEY (event_id) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = '${MYSQL_JDBC_URL}', 'table-name' = 'stream_events',
    'driver' = 'com.mysql.cj.jdbc.Driver',
    'username' = '${MYSQL_USER}', 'password' = '${MYSQL_PASSWORD}',
    'sink.buffer-flush.max-rows' = '100', 'sink.buffer-flush.interval' = '1s',
    'sink.max-retries' = '3'
);

-- 权重累加表
CREATE TABLE mysql_user_item (
    user_id STRING COMMENT '用户标识，联合主键之一',
    item_id STRING COMMENT '视频标识，联合主键之一',
    preference DOUBLE COMMENT '去重事件的累计偏好权重',
    interactions BIGINT COMMENT '累计去重事件数',
    last_ts BIGINT COMMENT '最近事件的毫秒时间戳',
    PRIMARY KEY (user_id, item_id) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = '${MYSQL_JDBC_URL}', 'table-name' = 'stream_user_item_features',
    'driver' = 'com.mysql.cj.jdbc.Driver',
    'username' = '${MYSQL_USER}', 'password' = '${MYSQL_PASSWORD}',
    'sink.buffer-flush.max-rows' = '100', 'sink.buffer-flush.interval' = '1s',
    'sink.max-retries' = '3'
);

-- 按窗口计算偏好表
CREATE TABLE mysql_hotness (
    item_id STRING COMMENT '视频标识，联合主键之一',
    window_start TIMESTAMP(3) COMMENT '一分钟事件窗口起点，UTC',
    window_end TIMESTAMP(3) COMMENT '窗口终点，不包含右边界',
    score DOUBLE COMMENT '窗口内时间衰减权重总和',
    interactions BIGINT COMMENT '窗口内去重事件数',
    PRIMARY KEY (item_id, window_start) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = '${MYSQL_JDBC_URL}',
    'table-name' = 'stream_item_hotness',
    'driver' = 'com.mysql.cj.jdbc.Driver',
    'username' = '${MYSQL_USER}',
    'password' = '${MYSQL_PASSWORD}',
    'sink.buffer-flush.max-rows' = '100',
     'sink.buffer-flush.interval' = '1s',
    'sink.max-retries' = '3'
);

SET 'pipeline.name' = 'yingke-realtime-recommendations';

-- EXECUTE STATEMENT SET :在一个任务中执行一组sql
-- 3、计算结果
EXECUTE STATEMENT SET
BEGIN

-- 明细通过 event_id 主键 upsert；JDBC sink 为至少一次，不是跨表 XA 事务。
INSERT INTO mysql_events
SELECT
    event_id,
    user_id,
    item_id,
    action,
    ts_ms,
    behavior_weight(action)
FROM unique_events;


-- 连续 GROUP BY 会不断输出更新后的绝对值；MySQL 覆盖聚合值而非再次累加。
INSERT INTO mysql_user_item
SELECT
    user_id,
    item_id,
    round(SUM(behavior_weight(action)),2),
    COUNT(*),
    MAX(ts_ms)
FROM
    unique_events
GROUP BY
    user_id, item_id;

-- 按事件时间一分钟滚动窗口，衰减间隔取事件时刻到窗口终点的小时差。
-- 当前 Trending 推荐从最近事件另算衰减，此窗口表用于窗口分析。
-- Flink 1.20.1 对「视图 + 时间属性」有 planner 回归：TABLE(TUMBLE(TABLE unique_events, ...))
-- 会抛 "belongs to a different planner than is currently being used"，
-- 因此窗口直接建在物理表 kafka_events 上，并把 above 的过滤条件下推。
-- 代价：热度聚合不具备 event_id 去重（重复投递会短暂高估）；明细与特征仍然去重。
INSERT INTO mysql_hotness
SELECT
    item_id,
    window_start,
    window_end,
    round(SUM(time_decay(behavior_weight(action), CAST(TIMESTAMPDIFF(SECOND, CAST(event_time AS TIMESTAMP(3)), window_end) AS DOUBLE) / 3600.0)),2),
    COUNT(*)
FROM
    TABLE(TUMBLE(TABLE kafka_events, DESCRIPTOR(event_time), INTERVAL '1' MINUTE))
WHERE
    event_id IS NOT NULL AND user_id IS NOT NULL AND item_id IS NOT NULL
    AND ts_ms > 0
    AND action IN ('view','complete','like','unlike','favorite','unfavorite','follow','unfollow','skip')
GROUP BY
    item_id,
    window_start,
    window_end;

END;
