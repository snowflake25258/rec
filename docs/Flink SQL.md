# Flink SQL

## 1、sql命令行

```sql
# 1、启动会话集群
yarn-session.sh -d

# 2、进入sql命令行
sql-client.sh

SET 'sql-client.execution.result-mode' = 'table';
SET 'sql-client.execution.result-mode' = 'tableau';


# 3、创建动态表（source表） -- 有界流表
CREATE TABLE students (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'filesystem',           -- 必选：指定连接器类型
  'path' = 'hdfs://master:9000/data/students',  -- 必选：指定路径
  'format' = 'csv',                     -- 必选：文件系统连接器指定 format
  'csv.field-delimiter' = ',' -- 字段分隔符
);

# 4、创建sink表
-- 向sink表中写入数据，最终数据会写入到mysql中
CREATE TABLE clazz_num (
  clazz STRING,
  num BIGINT,
  PRIMARY KEY (clazz) NOT ENFORCED
) WITH (
  'connector' = 'jdbc',
  'url' = 'jdbc:mysql://master:3306/bigdata',
  'table-name' = 'clazz_num',
  'username' = 'root',
  'password' = '123456'
);

-- 在mysql中创建表
CREATE TABLE clazz_num (
  clazz varchar(255),
  num BIGINT,
  PRIMARY KEY (clazz) 
);

#  flink 处理模式
# 流处理模式（实时计算）
# 1、输出连续的结果，以插入，更新，删除的形式输出
# 2、每一条数据处理一次，每一条数据都会输出一个结果
# 3、流处理模式主要用于处理无界流，可以处理有界流
SET 'execution.runtime-mode' = 'streaming'; 

# 批处理模式（相当于mr和spark，离线计算）
# 1、输出最终结果
# 2、底层是mapreduce，经过map和reduce过程之后输出最终结果
# 3、只能用于处理有界流
SET 'execution.runtime-mode' = 'batch'; 

insert into clazz_num
select clazz,count(1) as num
from students
group by clazz;
```

## 2、连接器

### 1、datagen

```sql
-- 生产随机数据的数据源---无界流
CREATE TABLE students_datagen (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'datagen',
  'rows-per-second'='5',-- 每秒生成5条数据
  'fields.id.length'='10',
  'fields.name.length'='2',
  'fields.sex.length'='1',
  'fields.clazz.length'='4',
  'fields.age.min'='1',
  'fields.age.max'='100'
);

select * from students_datagen;
```

### 2、hdfs

#### 1、hdfs source

```sql
-- 创建source表--有界流
CREATE TABLE students_batch (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'filesystem',           -- 必选：指定连接器类型
  'path' = 'hdfs://master:9000/data/students',  -- 必选：指定路径
  'format' = 'csv',                     -- 必选：文件系统连接器指定 format
  'csv.field-delimiter' = ',' -- 字段分隔符
);

-- 创建source表-- 无界流
CREATE TABLE students_stream (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'filesystem',           -- 必选：指定连接器类型
  'path' = 'hdfs://master:9000/data/students',  -- 必选：指定路径
  'format' = 'csv',                     -- 必选：文件系统连接器指定 format
  'csv.field-delimiter' = ',', -- 字段分隔符
  'source.monitor-interval' = '5000'  -- 每隔5秒扫描目录下新的文件
);
select * from students_stream
# 上传新的文件
hdfs dfs -put a.csv /data/students
```

#### 2、hdfs sink

```sql
CREATE TABLE clazz_num_hdfs (
  clazz STRING,
  num BIGINT
) WITH (
  'connector' = 'filesystem',           -- 必选：指定连接器类型
  'path' = 'hdfs://master:9000/data/clazz_num',  -- 必选：指定路径
  'format' = 'json'                     -- 必选：文件系统连接器指定 format
);

-- 1、批处理模式写入hdfs
SET 'execution.runtime-mode' = 'batch'; 

-- 追加写入
insert into clazz_num_hdfs
select clazz,count(1) as num
from students_batch
group by clazz;
-- 覆盖写入
insert overwrite clazz_num_hdfs
select clazz,count(1) as num
from students_batch
group by clazz;


-- 2、流处理模式写入hdfs
SET 'execution.runtime-mode' = 'streaming'; 

-- 将更新更改的结果表写入hdfs
-- canal-json:变更的数据格式
-- {"data":[{"clazz":"理科四班","num":91}],"type":"DELETE"}
-- {"data":[{"clazz":"理科四班","num":92}],"type":"INSERT"}
CREATE TABLE clazz_num_hdfs_canal (
  clazz STRING,
  num BIGINT
) WITH (
  'connector' = 'filesystem',           -- 必选：指定连接器类型
  'path' = 'hdfs://master:9000/data/clazz_num_hdfs_canal',  -- 必选：指定路径
  'format' = 'canal-json'                     -- 必选：文件系统连接器指定 format
);

insert into clazz_num_hdfs_canal
select clazz,count(1) as num
from students_batch
group by clazz;

-- 将仅插入的结果写入hdfs
CREATE TABLE students_yiban (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'filesystem',           -- 必选：指定连接器类型
  'path' = 'hdfs://master:9000/data/students_yiban',  -- 必选：指定路径
  'format' = 'json'                     -- 必选：文件系统连接器指定 format
);

insert into students_yiban
select *
from students_batch
where clazz='文科一班';
```

### 3、mysql

#### 1、mysql source

```sql
-- 1、mysql source --- 有界流
CREATE TABLE clazz_num_jdbc (
  clazz STRING,
  num BIGINT,
  PRIMARY KEY (clazz) NOT ENFORCED
) WITH (
  'connector' = 'jdbc',
  'url' = 'jdbc:mysql://master:3306/bigdata',
  'table-name' = 'clazz_num',
  'username' = 'root',
  'password' = '123456'
);

select * from clazz_num_jdbc;

-- 2、flink cdc -- 无界流,更新更改的流（+I,-U,+U,-D）
-- 读取数据的方式，先全表扫描，在监控binlog读取更改的数据
-- 通过监控mysql的binlog日志文件实现实时读取增加，删除，更新的数据
CREATE TABLE clazz_num_cdc (
  clazz STRING,
  num BIGINT,
  PRIMARY KEY (clazz) NOT ENFORCED
) WITH (
  'connector' = 'mysql-cdc', -- 只能用于读取数据
  'hostname' = 'master',
  'port' = '3306',
  'username' = 'root',
  'password' = '123456',
  'database-name' = 'bigdata',
  'table-name' = 'clazz_num'
);

select * from clazz_num_cdc;
```

#### 2、mysql sink

```sql
-- 创建mysql sink表
CREATE TABLE students_jdbc (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'jdbc',
  'url' = 'jdbc:mysql://master:3306/bigdata',
  'table-name' = 'students',
  'username' = 'root',
  'password' = '123456'
);

-- 在mysql中创建表
CREATE TABLE students (
  id varchar(255),
  name varchar(255),
  age INT,
  sex varchar(255),
  clazz varchar(255)
) ;

 -- 1、将仅插入的结果流写入mysql
insert into students_jdbc
select * from students_batch;


-- 2、将更新的结果流写入mysql,mysql的表需要有主键，flink会按照主键进行更新

CREATE TABLE sex_num (
  sex STRING,
  num BIGINT,
  PRIMARY KEY (sex) NOT ENFORCED
) WITH (
  'connector' = 'jdbc',
  'url' = 'jdbc:mysql://master:3306/bigdata',
  'table-name' = 'sex_num',
  'username' = 'root',
  'password' = '123456'
);

CREATE TABLE sex_num (
  sex varchar(255),
  num BIGINT,
  PRIMARY KEY (sex) 
) ;

insert into sex_num
select sex,count(1) as num
from students_batch
group by sex;
```

### 3、doris

> doris是OLAP:分析型数据库, doris为什么快,列式存储，按列压缩可以得到跟高的压缩比，提高读取的效率，向量化计算，排序，索引，分区，分桶
>
> mysql是OLTP:事物型数据库

```sql
# 解决doris版本冲突问题
# 下载新的连接器包flink-doris-connector-1.18-26.3.0.jar
# 将新的包上传到flink的lib目录下/usr/local/soft/flink-1.18.1/lib
# 删除旧的flink-doris-connector-1.18-24.1.0.jar
# 重启flink的会话集群
yarn application -list
yarn application -kill application_1793874687606_0002
yarn-session.sh -d
# flink sql命令后也要退出重新进
```

#### 1、doris sink

```sql
-- 创建sink表
CREATE TABLE students_doris (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING,
  PRIMARY KEY (id) NOT ENFORCED
) 
WITH (
  'connector' = 'doris',
  'fenodes' = 'master:8034',
  'benodes' = 'master:8041',
  'table.identifier' = 'bigdata.students',
  'username' = 'root',
  'password' = '123456',
  'sink.label-prefix' = 'doris_label'
);


-- 在doris中创建表
CREATE TABLE IF NOT EXISTS students
(
  id varchar(20),
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
)
UNIQUE KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1"
);

insert into students_doris
select * from students_batch;
```

#### 2、doris source

```sql
select * from students_doris;
```

### 4、print

```sql
CREATE TABLE print_table (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
 'connector' = 'print'
);

insert into print_table
select * from students_datagen;
```

### 5、BlackHole

> 用于高性能测试

```sql
CREATE TABLE blackhole_table (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'blackhole'
);

insert into blackhole_table
select * from students_datagen;
```

### 6、kafka

#### 1、kafka source

```sql
-- 创建kafka source表 -- 无界流
CREATE TABLE words (
    word STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'students',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'earliest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

select * from words;

select word,count(1) as num
from words
group by word;

kafka-console-producer.sh --broker-list master:9092 --topic students

# {"car":"皖BUXJH7","city_code":"340100","county_code":"340111","card":117276031841010,"camera_id":"00120","orientation":"南","road_id":34937242,"time":1614731542,"speed":67.41}

# group-offsets：从 Zookeeper/Kafka 中某个指定的消费组已提交的偏移量开始。
# earliest-offset：从可能的最早偏移量开始。
# latest-offset：从最末尾偏移量开始。
# timestamp：从用户为每个 partition 指定的时间戳开始。
# specific-offsets：从用户为每个 partition 指定的偏移量开始。

-- 消费最新的数据
CREATE TABLE cars (
  car STRING,
  city_code STRING,
  county_code STRING,
  card BIGINT,
  camera_id STRING,
  orientation STRING,
  road_id BIGINT,
  `time` BIGINT,
  speed DOUBLE
) WITH (
  'connector' = 'kafka',
  'topic' = 'cars',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json',
  'json.ignore-parse-errors' = 'true'
);

-- 指定时间消费
CREATE TABLE cars (
  car STRING,
  city_code STRING,
  county_code STRING,
  card BIGINT,
  camera_id STRING,
  orientation STRING,
  road_id BIGINT,
  `time` BIGINT,
  speed DOUBLE,
  `event_time` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp'-- 数据进入kafka的时间
) WITH (
  'connector' = 'kafka',
  'topic' = 'cars',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'timestamp',
  'scan.startup.timestamp-millis' = '1794033642684',-- 指定消费数据的时间
  'format' = 'json',
  'json.ignore-parse-errors' = 'true'
);

select car,road_id,`time`,event_time from cars;
```

#### 2、kafka sink

```sql
-- 创建sink表
CREATE TABLE students (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'students_json',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'format' = 'json'
);

insert into students
select * from students_batch;

kafka-console-consumer.sh --bootstrap-server master:9092 --from-beginning --topic students_json
```

## 3、并行度

```sql
# 设置并行度
# flink任务在运行时，一个并行度占用一个slot
SET 'parallelism.default' = '2';

CREATE TABLE clazz_num_print (
  clazz STRING,
  num BIGINT
) WITH (
 'connector' = 'print'
);

insert into clazz_num_print
select clazz,count(1) as num
from students_datagen
group by clazz;
```

## 4、SQL语法

### 1、Hint

```sql
CREATE TABLE cars (
  car STRING,
  city_code STRING,
  county_code STRING,
  card BIGINT,
  camera_id STRING,
  orientation STRING,
  road_id BIGINT,
  `time` BIGINT,
  speed DOUBLE
) WITH (
  'connector' = 'kafka',
  'topic' = 'cars',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json',
  'json.ignore-parse-errors' = 'true'
);

-- 在当前查询中动态修改表的参数
select * from cars /*+ OPTIONS('scan.startup.mode'='earliest-offset') */;
```

### 2、with

```sql
-- 当一个sql逻辑被多次使用时，可以将这段逻辑放到with子句中，减少代码量
with tmp as (
  select * from cars
)
select * from tmp;
```

### 3、distinct

```sql
select distinct * from cars;

CREATE TABLE students_datagen (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'datagen',
  'rows-per-second'='5',-- 每秒生成5条数据
  'fields.id.length'='10',
  'fields.name.length'='2',
  'fields.sex.length'='1',
  'fields.clazz.length'='4',
  'fields.age.min'='1',
  'fields.age.max'='100'
);

CREATE TABLE blackhole_table (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'blackhole'
);

-- flink流处理模式中，distinct会将数据保存到状态中，会导致状态越来越大，时间长了之后内存会溢出
insert into blackhole_table
select distinct * from students_datagen /*+ OPTIONS('rows-per-second'='50000') */;


-- 2、使用row_number()
-- row_number只需要将主键一个字段保存到状态中，可以减少内存的占用
insert into blackhole_table
select id,name,age,sex,clazz from (
  select 
    *,
    row_number() over(partition by id order by PROCTIME()) as r
  from students_datagen /*+ OPTIONS('rows-per-second'='50000') */
) as a
where r = 1;

-- 设置taskmasger的启动内存
yarn-session.sh -tm 4G -d
```

### 4、窗口表值函数（TVFs）

#### 1、滚动窗口

> 每隔一段时间进行最近一段时间的数据，比如每隔一个小时计算最近一个小时的数据

```sql
CREATE TABLE cars_proctime (
  car STRING,
  city_code STRING,
  county_code STRING,
  card BIGINT,
  camera_id STRING,
  orientation STRING,
  road_id BIGINT,
  `time` BIGINT,
  speed DOUBLE,
  proctime as PROCTIME()  -- 处理时间,数据被flink处理的时候的时间
) WITH (
  'connector' = 'kafka',
  'topic' = 'cars',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json',
  'json.ignore-parse-errors' = 'true'
);

select car,proctime from cars_proctime;

-- TUMBLE:滚动窗口函数，在原表的基础增加了window_start,window_end,window_time
SELECT car,proctime, window_start,window_end,window_time  FROM 
TABLE(
   TUMBLE(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '1' MINUTES)
);

-- 实时统计每个城市每分钟的车流量
SELECT city_code,window_start,window_end,count(1) as flow
FROM 
  TABLE(
     TUMBLE(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '1' MINUTES)
  )
group by city_code,window_start,window_end;

-- 实时统计每个道路每分钟的车流量和平均车速
SELECT road_id,window_start,window_end,count(1) as flow,avg(speed) as avg_speed
FROM 
  TABLE(
     TUMBLE(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '1' MINUTES)
  )
group by road_id,window_start,window_end;
```

#### 2、滑动窗口

```sql
-- 每隔1分钟计算最近1分钟的数据，当滑动时间等于窗口大小时，滑动窗口就是滚动窗口
SELECT car,proctime, window_start,window_end,window_time FROM 
TABLE(
    HOP(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '1' MINUTES, INTERVAL '2' MINUTES)
);


-- 每隔1分钟计算最近15分钟到了的车流量和平均车速
SELECT road_id,window_start,window_end,count(1) as flow,avg(speed) as avg_speed
FROM 
  TABLE(
     HOP(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '1' MINUTES,INTERVAL '15' MINUTES)
  )
group by road_id,window_start,window_end;
```

#### 3、累计窗口

```sql
-- 每隔2分钟累计一次，累计到10分钟，再重新累计
-- 在10分钟内，每隔2分钟计算一次
SELECT car,proctime, window_start,window_end,window_time FROM TABLE(
    CUMULATE(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '2' MINUTES, INTERVAL '10' MINUTES)
);

SELECT road_id,window_start,window_end,count(1) as flow,avg(speed) as avg_speed
FROM 
  TABLE(
     CUMULATE(TABLE cars_proctime, DESCRIPTOR(proctime), INTERVAL '2' MINUTES, INTERVAL '10' MINUTES)
  )
group by road_id,window_start,window_end;
```

#### 4、会话窗口

> 如果苏剧一直有，就不计算，如果一段时间没有数据会将前面的数据放到一个窗口中进行计算

```sql
CREATE TABLE words (
  word STRING,
  proctime as PROCTIME()  -- 处理时间,数据被flink处理的时候的时间
) WITH (
  'connector' = 'kafka',
  'topic' = 'words',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.field-delimiter' = '\t' ,
  'csv.ignore-parse-errors' = 'true'
);

select 
  word,
  SESSION_START(proctime, INTERVAL '1' MINUTES) as win_start,
  SESSION_END(proctime, INTERVAL '1' MINUTES) as win_end,
  count(1) as num
from words
group by 
  word,
  SESSION(proctime, INTERVAL '1' MINUTES);

kafka-console-producer.sh --broker-list master:9092 --topic words
```

### 5、事件时间

```sql
CREATE TABLE cars_eventtime (
  car STRING,
  city_code STRING,
  county_code STRING,
  card BIGINT,
  camera_id STRING,
  orientation STRING,
  road_id BIGINT,
  `time` BIGINT,
  speed DOUBLE,
  eventtime as TO_TIMESTAMP(FROM_UNIXTIME(`time`)), -- 将时间戳转化成flink的时间类型
  proctime as PROCTIME(),  -- 处理时间,数据被flink处理的时候的时间
  WATERMARK FOR eventtime AS eventtime - INTERVAL '5' SECOND -- 告诉flink哪一个字段是事件时间字段
) WITH (
  'connector' = 'kafka',
  'topic' = 'cars',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json',
  'json.ignore-parse-errors' = 'true'
);

-- 每隔1分钟计算最近1分钟的数据，当滑动时间等于窗口大小时，滑动窗口就是滚动窗口
SELECT car,eventtime,proctime, window_start,window_end,window_time FROM 
TABLE(
    HOP(TABLE cars_eventtime, DESCRIPTOR(eventtime), INTERVAL '1' MINUTES, INTERVAL '2' MINUTES)
);


-- 每隔1分钟计算最近15分钟到了的车流量和平均车速
SELECT road_id,window_start,window_end,count(1) as flow,avg(speed) as avg_speed
FROM 
  TABLE(
     HOP(TABLE cars_eventtime, DESCRIPTOR(eventtime), INTERVAL '1' MINUTES,INTERVAL '15' MINUTES)
  )
group by road_id,window_start,window_end;


-- 事件时间存在的问题
-- 1、如果数据乱序可能会导致数据丢失
CREATE TABLE words_eventtime (
  word STRING,
  eventtime TIMESTAMP(3), -- 事件时间
  -- 定义水位线生成的策略，水位线减去5秒，避免数据乱序导致数据丢失
  WATERMARK FOR eventtime AS eventtime - INTERVAL '5' SECOND 
) WITH (
  'connector' = 'kafka',
  'topic' = 'words_eventtime',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.field-delimiter' = ',' ,
  'csv.ignore-parse-errors' = 'true'
);

-- 每隔5秒统计单词的数量
SELECT word,window_start,window_end,count(1) as num
FROM 
  TABLE(
     TUMBLE(TABLE words_eventtime, DESCRIPTOR(eventtime), INTERVAL '5' SECOND)
  )
group by word,window_start,window_end;

kafka-console-producer.sh --broker-list master:9092 --topic words_eventtime
flink,2026-10-01 16:20:02
flink,2026-10-01 16:20:03
flink,2026-10-01 16:20:06
flink,2026-10-01 16:20:04
flink,2026-10-01 16:20:07
flink,2026-10-01 16:20:09
flink,2026-10-01 16:20:11
flink,2026-10-01 16:20:15
```

### 6、order by 

```sql
-- 计算代价
-- 在flink的流处理模式中，如果按照普通字段排序，每来一条新的数据都需要重新和前面所有的数据计算新的顺序，计算代价太大了，所以在flink流处理模式中禁止使用普通字段排序
select * from cars_proctime order by speed;
-- 只能按照时间字段升序排序
select * from cars_proctime order by proctime;


-- 特殊情况，在排序之后取limit
-- 加limit起到的作用，避免计算的代价越来越大
SET 'sql-client.execution.result-mode' = 'table';
select car,speed from cars_proctime order by speed desc limit 10;
```

### 7、over函数

#### 1、row_number

```sql
CREATE TABLE cars_proctime (
  car STRING,
  city_code STRING,
  county_code STRING,
  card BIGINT,
  camera_id STRING,
  orientation STRING,
  road_id BIGINT,
  `time` BIGINT,
  speed DOUBLE,
  proctime as PROCTIME()  -- 处理时间,数据被flink处理的时候的时间
) WITH (
  'connector' = 'kafka',
  'topic' = 'cars',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json',
  'json.ignore-parse-errors' = 'true'
);

-- 计算代价
-- 在flink的流处理模式中，如果按照普通字段排序，每来一条新的数据都需要重新和前面所有的数据计算新的顺序，计算代价太大了，所以在flink流处理模式中禁止使用普通字段排序
select 
car,city_code,speed,proctime,
row_number() over(partition by city_code order by speed desc) as r
from cars_proctime;

-- 增加限制，可以按照普通字段排序
select * from(
  select 
  car,city_code,speed,proctime,
  row_number() over(partition by city_code order by speed desc) as r
  from cars_proctime
)
where r <= 10;
```

#### 2、sum

```sql
-- sum over,1、有排序时，是累计求和，2、没有排序时，是全局求和
-- 流处理模式中不能使用全局求和，只能使用累计求和，而且必须是时间字段

select 
car,city_code,speed,proctime,
sum(speed) over(partition by city_code order by proctime) as sum_speed
from cars_proctime;
```

#### 3、lag

```sql
-- 流处理模式只能使用lag，不能使用lead
select 
car,city_code,speed,proctime,
lag(speed,1) over(partition by car order by proctime) as lag_speed
from cars_proctime;

select 
car,city_code,speed,proctime,
lead(speed,1) over(partition by car order by proctime) as lag_speed
from cars_proctime;
```

### 8、join

#### 1、Regular Joins

> 常规join，分为内关联，左关联，又关联，全关联

```sql
CREATE TABLE students_kafka (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'students',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);
kafka-console-producer.sh --broker-list master:9092 --topic students
1500100001,施笑槐,22,女,文科六班
1500100002,吕金鹏,24,男,文科六班
1500100003,单乐蕊,22,女,理科六班
1500100004,葛德曜,24,男,理科三班
1500100005,宣谷芹,22,女,理科五班

CREATE TABLE scores_kafka (
  sid STRING,
  cid STRING,
  score DOUBLE
) WITH (
  'connector' = 'kafka',
  'topic' = 'scores',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

kafka-console-producer.sh --broker-list master:9092 --topic scores
1500100001,1000001,98
1500100001,1000002,5
1500100001,1000003,137
1500100001,1000004,29
1500100001,1000005,85
1500100001,1000006,52
1500100002,1000001,139


-- 使用常规的关联方式，flink会将两个表的数据一直保存在内存中，内会越来越大，不会稳定
select a.id,a.name,b.cid,b.score from 
students_kafka as a
left join 
scores_kafka as b
on a.id=b.sid;
```

#### 2、Interval Joins 

> 用于双流join，两个无界流join

```sql
CREATE TABLE students_kafka_proctime (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING,
  proctime as PROCTIME()
) WITH (
  'connector' = 'kafka',
  'topic' = 'students',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);
kafka-console-producer.sh --broker-list master:9092 --topic students
1500100001,施笑槐,22,女,文科六班
1500100002,吕金鹏,24,男,文科六班
1500100003,单乐蕊,22,女,理科六班
1500100004,葛德曜,24,男,理科三班
1500100005,宣谷芹,22,女,理科五班

CREATE TABLE scores_kafka_proctime (
  sid STRING,
  cid STRING,
  score DOUBLE,
  proctime as PROCTIME()
) WITH (
  'connector' = 'kafka',
  'topic' = 'scores',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

kafka-console-producer.sh --broker-list master:9092 --topic scores
1500100001,1000001,98
1500100001,1000002,5
1500100001,1000003,137
1500100001,1000004,29
1500100001,1000005,85
1500100001,1000006,52
1500100002,1000001,139


-- AND a.proctime BETWEEN b.proctime - INTERVAL '10' SECOND AND b.proctime;
-- a表数据的时间(12:10,10) 需要在 b表数据时间减去10秒(12:10:03) 到 b表数据时间(12:10:13) 的范围内
-- 内存中只需要保留最近10秒的数据，状态不会越来越大
SELECT a.id,a.name,b.cid,b.score
FROM students_kafka_proctime a, scores_kafka_proctime b
WHERE a.id = b.sid
AND a.proctime BETWEEN b.proctime - INTERVAL '10' SECOND AND b.proctime;
```

#### 3、Temporal Joins 

> 用于流表关联时态表

```sql
CREATE TABLE orders (
    order_id    STRING,
    price       DECIMAL(32,2),
    currency    STRING,
    order_time  TIMESTAMP(3),
    WATERMARK FOR order_time AS order_time
) WITH (
 'connector' = 'kafka',
  'topic' = 'orders',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);
kafka-console-producer.sh --broker-list master:9092 --topic orders
001,100,CNY,2026-11-08 15:10:12
002,10,CNY,2026-11-08 15:10:16
003,20,CNY,2026-11-08 15:10:21

CREATE TABLE currency_rates (
    currency STRING,
    conversion_rate DECIMAL(32, 2),
    update_time TIMESTAMP(3) ,
    WATERMARK FOR update_time AS update_time,
    PRIMARY KEY(currency) NOT ENFORCED
) WITH (
  'connector' = 'kafka',
   'topic' = 'currency_rates',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'earliest-offset',
  'format' = 'canal-json'
);

insert into currency_rates
values
('CNY',0.15,TIMESTAMP '2026-11-08 15:10:10'),
('CNY',0.16,TIMESTAMP '2026-11-08 15:10:15'),
('CNY',0.17,TIMESTAMP '2026-11-08 15:10:20');
kafka-console-consumer.sh --bootstrap-server master:9092 --from-beginning --topic currency_rates


-- 如果使用常规的关联方式，会关联获取到最新的汇率
select 
a.order_id,a.price,a.order_time,b.conversion_rate,b.update_time
from 
orders as a
join
currency_rates as b
on a.currency=b.currency;

-- 改用时态表join
-- FOR SYSTEM_TIME AS OF a.order_time: 使用a表的时间到b表中查询对应时间段的数据
select 
a.order_id,a.price,a.order_time,b.conversion_rate,b.update_time
from 
orders as a
left join
currency_rates FOR SYSTEM_TIME AS OF a.order_time as b
on a.currency=b.currency;
```

#### 4、Lookup Join

> 用于流表关联维表，无界流关联有界流

```sql
-- 有界流
CREATE TABLE students_mysql (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING
) WITH (
	'connector' = 'jdbc',
  'url' = 'jdbc:mysql://master:3306/bigdata',
  'table-name' = 'students',
  'username' = 'root',
  'password' = '123456'
);

-- 无界流
CREATE TABLE scores_kafka (
  sid STRING,
  cid STRING,
  score DOUBLE,
  proctime as PROCTIME()
) WITH (
  'connector' = 'kafka',
  'topic' = 'scores',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

kafka-console-producer.sh --broker-list master:9092 --topic scores
1500100001,1000001,98
1500100001,1000002,5
1500100001,1000003,137
1500100001,1000004,29
1500100001,1000005,85
1500100001,1000006,52
1500100002,1000001,139

-- 常规关联方式
-- 问题：
-- 1、有界流的表只会在任务启动的时候读取一次，不能读取到后面更新的数据
-- 2、flink会将两个表的数据一直保存在状态中，状态会越来越大
select b.id,b.name,a.cid,a.score  from 
scores_kafka as a
left join 
students_mysql as b
on a.sid=b.id;

-- lookup join（查找join）
-- FOR SYSTEM_TIME AS OF a.proctime :使用a表最新时间到b表中查询最新的数据
-- 分数表每来一条新的数据都会到学生表的数据库中查询
select b.id,b.name,a.cid,a.score  from 
scores_kafka as a
left join 
students_mysql FOR SYSTEM_TIME AS OF a.proctime as b
on a.sid=b.id;
```

#### 5、window join

> 也可以用于双流join

```sql
CREATE TABLE students_kafka_eventtime (
  id STRING,
  name STRING,
  age INT,
  sex STRING,
  clazz STRING,
  eventtime TIMESTAMP(3),
  WATERMARK FOR eventtime AS eventtime
) WITH (
  'connector' = 'kafka',
  'topic' = 'students',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);
kafka-console-producer.sh --broker-list master:9092 --topic students
1500100001,施笑槐,22,女,文科六班,2026-10-10 10:10:04
1500100002,吕金鹏,24,男,文科六班,2026-10-10 10:11:05

CREATE TABLE scores_kafka_eventtime (
  sid STRING,
  cid STRING,
  score DOUBLE,
  eventtime TIMESTAMP(3),
  WATERMARK FOR eventtime AS eventtime
) WITH (
  'connector' = 'kafka',
  'topic' = 'scores',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

kafka-console-producer.sh --broker-list master:9092 --topic scores
1500100001,1000001,98,2026-10-10 10:10:04
1500100001,1000002,5,2026-10-10 10:11:05

-- 在1分钟内进行关联，flink内存中只需要保留1分钟的数据，状态不会越来越大
select a.id,a.name,b.cid,b.score,a.window_start,a.window_end from 
  (
  select * from 
    TABLE(
     TUMBLE(TABLE students_kafka_eventtime, DESCRIPTOR(eventtime), INTERVAL '1' MINUTES)
  )
  ) as a
 join
  (
  select * from 
    TABLE(
     TUMBLE(TABLE scores_kafka_eventtime, DESCRIPTOR(eventtime), INTERVAL '1' MINUTES)
  )
  ) as b
on a.id=b.sid
and a.window_start=b.window_start and a.window_end=b.window_end;
```

### 9、模式检测（CEP)

#### 1、案例1

```sql
-- 对于一个账户，如果出现小于 $1 美元的交易后紧跟着一个大于 $500 的交易
CREATE TABLE transactions (
  id STRING,
  price DOUBLE,
  eventtime TIMESTAMP(3),
  WATERMARK FOR eventtime AS eventtime
) WITH (
  'connector' = 'kafka',
  'topic' = 'transactions',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

kafka-console-producer.sh --broker-list master:9092 --topic transactions
001,100,2026-11-09 10:10:10
001,0.5,2026-11-09 10:10:11
001,600,2026-11-09 10:10:13
001,400,2026-11-09 10:10:20
001,0.4,2026-11-09 10:10:21
001,100,2026-11-09 10:10:22
001,1000,2026-11-09 10:10:24

-- 使用lag实现
select * from(
  select *,
  lag(price,1) over(partition by id order by eventtime) lag_price
  from transactions
) as a
where price>500 and lag_price<1;


-- 使用cep实现: flink通过定义的规则和条件在数据流上进行匹配，当数据满足了规则和条件之后将满足的数据返回
-- 对于一个账户，如果出现小于 $1 美元的交易后紧跟着一个大于 $500 的交易
select * from transactions
    MATCH_RECOGNIZE (
      PARTITION BY id -- 分组
      ORDER BY eventtime -- 排序，只能按照时间升序排序
      MEASURES -- 定义匹配成功之后返回的字段
        A.price as a_price,
        A.eventtime as a_eventtime,
        B.price as b_price,
        B.eventtime as b_eventtime
      PATTERN (A B) -- 定义规则
      DEFINE -- 定义条件
         A as price<1,
         B as price>500
    ) AS T;
  
-- 对于一个账户，如果连续3次出现小于 $1 美元的交易后紧跟着一个大于 $500 的交易
select * from transactions
    MATCH_RECOGNIZE (
      PARTITION BY id -- 分组
      ORDER BY eventtime -- 排序，只能按照时间升序排序
      MEASURES -- 定义匹配成功之后返回的字段
        FIRST(A.price) as a_price, -- 获取第一个a
        AVG(A.price) as avg_price, -- 聚合计算
        SUM(A.price) as sum_price, -- 聚合计算
        FIRST(A.eventtime) as a_eventtime, -- 获取第一个a
        B.price as b_price,
        B.eventtime as b_eventtime
      PATTERN (A{3} B) -- 定义规则
      DEFINE -- 定义条件
         A as price<1,
         B as price>500
    ) AS T;
001,100,2026-11-09 10:10:09
001,0.5,2026-11-09 10:10:10
001,0.2,2026-11-09 10:10:11
001,0.1,2026-11-09 10:10:12
001,600,2026-11-09 10:10:13
001,400,2026-11-09 10:10:20
001,0.4,2026-11-09 10:10:21
001,100,2026-11-09 10:10:22
001,1000,2026-11-09 10:10:24

-- 对于一个账户，如果连续3次出现小于 $1 美元的交易后紧跟着一个大于 $500 的交易,需要在10秒内完成
select * from transactions
    MATCH_RECOGNIZE (
      PARTITION BY id -- 分组
      ORDER BY eventtime -- 排序，只能按照时间升序排序
      MEASURES -- 定义匹配成功之后返回的字段
        FIRST(A.price) as a_price, -- 获取第一个a
        AVG(A.price) as avg_price, -- 聚合计算
        SUM(A.price) as sum_price, -- 聚合计算
        FIRST(A.eventtime) as a_eventtime, -- 获取第一个a
        B.price as b_price,
        B.eventtime as b_eventtime
      PATTERN (A{3} B) WITHIN INTERVAL '5' SECOND -- 定义规则
      DEFINE -- 定义条件
         A as price<1,
         B as price>500
    ) AS T;
001,100,2026-11-09 10:10:09
001,0.5,2026-11-09 10:10:10
001,0.2,2026-11-09 10:10:11
001,0.1,2026-11-09 10:10:12
001,600,2026-11-09 10:10:13
001,400,2026-11-09 10:10:20
001,0.4,2026-11-09 10:10:21
001,0.2,2026-11-09 10:10:22
001,0.1,2026-11-09 10:10:28
001,1000,2026-11-09 10:10:30
001,1000,2026-11-09 10:10:31
```

#### 2、案例2

```sql
CREATE TABLE ticker (
  symbol STRING,
  price DOUBLE,
  tax DOUBLE,
  rowtime TIMESTAMP(3),
  WATERMARK FOR rowtime AS rowtime
) WITH (
  'connector' = 'kafka',
  'topic' = 'ticker',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);
kafka-console-producer.sh --broker-list master:9092 --topic ticker
ACME,12,1,2026-11-09 10:00:00
ACME,17,2,2026-11-09 10:00:01
ACME,19,1,2026-11-09 10:00:02
ACME,21,3,2026-11-09 10:00:03
ACME,25,2,2026-11-09 10:00:04
ACME,18,1,2026-11-09 10:00:05
ACME,15,1,2026-11-09 10:00:06
ACME,14,2,2026-11-09 10:00:07
ACME,24,2,2026-11-09 10:00:08
ACME,25,2,2026-11-09 10:00:09
ACME,19,1,2026-11-09 10:00:10

-- 找出一个单一股票价格不断下降的时期
select * from ticker
    MATCH_RECOGNIZE (
      PARTITION BY symbol -- 分组
      ORDER BY rowtime -- 排序，只能按照时间升序排序
      MEASURES -- 定义匹配成功之后返回的字段
        A.price as a_price,
        B.price as b_price,
        C.price as c_price,
        A.rowtime as a_rowtime,
        B.rowtime as b_rowtime,
        C.rowtime as c_rowtime
      AFTER MATCH SKIP PAST LAST ROW -- 在当前匹配的最后一行之后的下一行继续模式匹配。
      PATTERN (A B+ C) -- 定义规则
      DEFINE -- 定义条件
         B as (LAST(price,1) is null and B.price<A.price) or  B.price < LAST(price,1),
         C as C.price>B.price
    ) AS T;
```

## 5、checkpoint(快照)

> flink通过checkpoint定时将计算的状态保存到hdfs，如果任务执行失败，可以计算hdfs中保存的状态恢复任务，保证中间结果不丢失

### 1、开启checkpoint功能

vim  flink-conf.yaml 

```shell
execution.checkpointing.interval: 10000
execution.checkpointing.externalized-checkpoint-retention: RETAIN_ON_CANCELLATION
execution.checkpointing.max-concurrent-checkpoints: 1
execution.checkpointing.min-pause: 0
execution.checkpointing.mode: EXACTLY_ONCE
execution.checkpointing.timeout: 10min
execution.checkpointing.tolerable-failed-checkpoints: 0
execution.checkpointing.unaligned: false
state.backend: hashmap
state.checkpoints.dir: hdfs://master:9000/flink/checkpoints
state.savepoints.dir: hdfs://master:9000/flink/savepoints
```

### 2、编写代码

vim word_count.sql

```sql
CREATE TABLE words (
    word STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'lines',
  'properties.bootstrap.servers' = 'master:9092',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'earliest-offset',
  'format' = 'csv',
  'csv.ignore-parse-errors' = 'true'
);

CREATE TABLE print_table (
  word STRING,
  num BIGINT
) WITH (
 'connector' = 'print'
);

-- 失败重启时增加
-- SET 'execution.savepoint.path' = 'hdfs://master:9000/flink/checkpoints/c56e7c3dcf8352a285dfd954084c6258/chk-23';

insert into print_table
select word,count(1) as num
from words
group by word;
```

### 3、提交任务

```shell
# 第一次直接提交任务，会从头消费数据计算结果
# 如果任务中途失败了，就不能直接提交，
sql-client.sh -f word_count.sql

# 失败重启的方式
# 需要计算之前的checkpoint恢复任务
# 到hdfs查找任务快照的目录
hdfs dfs -ls /flink/checkpoints/c56e7c3dcf8352a285dfd954084c6258
# 需要从下面这个地址恢复任务
hdfs://master:9000/flink/checkpoints/c56e7c3dcf8352a285dfd954084c6258/chk-23

# 在word_count.sql文件中增加参数,放到insert语句的前面
SET 'execution.savepoint.path' = 'hdfs://master:9000/flink/checkpoints/c56e7c3dcf8352a285dfd954084c6258/chk-23';

sql-client.sh -f word_count.sql
```

### 4、生成数据

```sql
kafka-console-producer.sh --broker-list master:9092 --topic lines
```

## 6、自定义函数

### 1、编写自定义函数

vim upper.py

```text
from pyflink.table.udf import  udf

# 编写自定义函数
@udf(result_type='STRING')
def upper(s:str):
  return s.upper()
```

### 2、注册自定义函数

```shell
# pyExecutable需要根据服务器环境修改
sql-client.sh --pyFiles upper.py --pyExecutable /opt/miniconda3/envs/flink_env/bin/python3

# 创建自定义函数
CREATE FUNCTION python_upper AS 'upper.upper' LANGUAGE  PYTHON;

# 测试
select python_upper('shujia');
```



