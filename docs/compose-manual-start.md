# Compose 按依赖逐个服务启动指南

本文对应项目根目录的 `compose.yaml`，由你手动逐条执行命令。每次只启动一个服务，确认就绪后再进入下一步。

## 1. 启动顺序与依赖

| 顺序 | 服务 | 前置条件 | 完成标准 |
| --- | --- | --- | --- |
| 1 | mysql-init | 已有 MySQL 可从容器访问 | 初始化容器退出码为 0 |
| 2 | kafka | Docker 可用，9092 端口空闲 | Kafka 健康状态为 healthy |
| 3 | kafka-init | Kafka healthy | Topic 创建任务退出码为 0 |
| 4 | jobmanager | 8081 端口空闲 | Flink REST API 可访问 |
| 5 | taskmanager | JobManager 就绪 | Worker 已注册且有可用 slot |
| 6 | flink-submit | MySQL 初始化、Topic 和 Flink Worker 就绪 | 提交容器退出码为 0，推荐作业 RUNNING |
| 7 | app | 上述步骤完成，8000 端口空闲 | 应用健康接口返回 status=ok |

`mysql-init`、`kafka-init` 和 `flink-submit` 是一次性任务，成功后显示 `Exited (0)` 属于正常情况。其他服务应持续运行。

所有启动命令都带 `--no-deps`，避免 Compose 自动同时启动依赖。`--build` 仅用于需要构建项目镜像的服务；镜像已经准备好且代码未变时，可以改为 `--no-build`。

## 2. 启动前准备

在项目根目录执行：

```bash
cd /Users/qx/code/rec
docker compose version
docker info
docker compose config --quiet
```

最后一条命令只验证配置，不输出解析后的数据库密码。

确认根目录已有 `.env`，配置 `MYSQL_PORT`、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`。Compose 使用已有 MySQL，不会启动新的 MySQL 容器或创建测试库。

容器通过 `MYSQL_DOCKER_HOST` 连接 MySQL，未设置时默认 `host.docker.internal`；容器里的 `localhost` 指向容器自己。已有 MySQL 需要允许来自容器网络的连接。

本指南会启动一套独立的容器 Kafka/Flink。你已有的 `master:9092` 和 `master:8081` 不属于这套 Compose；若它们占用当前机器的 9092、8081 端口，需先解决端口占用，或修改 Compose 的宿主机端口映射。宿主机已有 API 也可能占用 8000。不要让两个 Flink 作业写同一组 `stream_*` 表。

可查看本机端口占用：

```bash
lsof -nP -iTCP:9092 -sTCP:LISTEN
lsof -nP -iTCP:8081 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:3306 -sTCP:LISTEN

netstat -aon | findstr "8080"
```

无输出通常表示对应端口没有监听进程。

## 3. 启动并初始化 MySQL

```bash
# 启动mysql
docker compose up -d --no-deps mysql
# 查看服务
docker ps
# 初始化表
docker compose up -d --no-deps --build mysql-init
# 查看初始化日志
docker compose logs -f mysql-init
```

连接失败时先检查 `.env`、MySQL 可访问性及账号权限，不继续启动后续服务。

## 4. 启动 Kafka

```bash
# 启动kafka
docker compose up -d --no-deps kafka
# 查看日志
docker compose logs --tail 60 kafka
```

等待输出 `running healthy`。如果还显示 `starting`，稍后重新执行最后一条检查命令。

## 5. 创建 Kafka Topic

```bash
docker compose up -d --no-deps kafka-init
docker compose logs -f kafka-init
```

确认 `exited 0`，再查看 Topic：

```bash
# 不进入容器执行命令
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic rec-events

# 进入容器
docker compose exec  kafka /bin/bash 
# 执行命令
/opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic rec-events
```

默认 Topic 是 `rec-events`，3 个分区、副本数 1。初始化命令使用 `--if-not-exists`，已有 Topic 时不会重复创建。容器内部使用 `kafka:9092` 通信。

## 6. 启动 Flink JobManager

Flink 镜像统一使用 Flink/PyFlink 1.18.1、Kafka SQL Connector 3.1.0-1.18、JDBC Connector 3.1.2-1.18。ARM64 安装 `pemja` 时需要源码编译，Dockerfile 从 Java 8 JDK 镜像复制完整 JDK，并安装 C 编译器和 Python 开发头文件。不要只修改 PyFlink 版本而保留 1.20 的连接器。

该步骤只构建镜像，不启动服务。镜像安装阶段会执行 `pip check` 和 PyFlink UDF 导入检查。app 构建日志中的 `CANCELED` 可能是其他并行镜像失败导致，不一定是应用自身安装错误。

```bash
docker compose up -d --no-deps --build jobmanager
docker compose logs --tail 60 jobmanager
docker ps
http://localhost:8081
docker compose exec -T jobmanager curl -fsS --max-time 5 http://localhost:8081/overview
```

REST 接口返回 JSON 后继续。此时还未启动 TaskManager，`taskmanagers` 为 0 属于正常情况。

默认 Flink 页面：[http://127.0.0.1:8081](http://127.0.0.1:8081)。若修改了宿主机映射端口，使用修改后的端口访问。

## 7. 启动 Flink TaskManager

```bash
docker compose up -d --no-deps --build taskmanager
# 停止某个服务
docker compose down taskmanager
docker compose logs --tail 60 taskmanager
docker compose exec -T jobmanager curl -fsS --max-time 5 http://localhost:8081/overview
```

确认返回 JSON 中：

- `taskmanagers` 至少为 1。
- 首次提交作业前，`slots-available` 大于 0，当前配置通常为 4。

注册尚未完成时，稍后重复检查；不要只凭容器显示 Running 就提交作业。若已有推荐作业占用 slot，先按下一节检查，避免重复提交。

## 8. 启动应用（前后端服务）

```bash
docker compose up -d --no-deps --build app
docker compose down app
docker compose logs --tail 80 app
```

健康接口返回 `status: ok`、`mode: production` 后，打开：

- 应用：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

首次使用注册账号，再进行播放、点赞、收藏等交互。应用健康接口仅表示应用可用，完整实时链路还需通过上一节的作业与 checkpoint 检查。

## 9、在kafka中查看事件数据

```shell
docker compose exec  kafka /bin/bash 

/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server 127.0.0.1:9092 --from-beginning --topic rec-events
```

## 9 提交 Flink 推荐作业

在flink验证数据读取

```sql
# 进入flink容器内
docker compose exec  jobmanager /bin/bash 
# 进入sql命令行
/opt/flink/bin/sql-client.sh
# 创建表
CREATE TABLE kafka_events (
    event_id STRING, 
    user_id STRING, 
    item_id STRING, 
    action STRING, 
    ts_ms BIGINT,
    event_time AS TO_TIMESTAMP_LTZ(ts_ms, 3),
    proc_time AS PROCTIME(),
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka', 
  'topic' = 'rec-events',
  'properties.bootstrap.servers' = 'kafka:9092',
  'properties.group.id' = 'yingke-realtime-v1',
  'scan.startup.mode' = 'earliest-offset', 
  'format' = 'json',
  'json.fail-on-missing-field' = 'true', 
  'json.ignore-parse-errors' = 'false'
);
SET 'sql-client.execution.result-mode' = 'tableau';
select * from kafka_events;
```

先检查是否已有同名作业：

```bash
docker compose exec -T jobmanager curl -fsS --max-time 5 http://localhost:8081/jobs/overview
```

如果已经存在名称为 `yingke-realtime-recommendations`、状态为 `RUNNING` 的作业，跳过提交。处于启动或恢复过程中的同名作业，先等待并排查，不重复提交。

首次启动、没有该作业时执行：

```bash
# 提交任务
docker compose up -d --no-deps --build flink-submit
docker compose logs -f flink-submit
```

提交容器应为 `exited 0`，但这仅表示提交过程成功，还需要检查作业：

```bash
docker compose exec -T jobmanager curl -fsS --max-time 5 http://localhost:8081/jobs/overview
```

确认同名作业的 `state` 为 `RUNNING`，记录其 `jid`。Python UDF Worker 首次启动可能需要几十秒。

还可以在 Flink 页面查看最近完成的 checkpoint。若需要命令行检查，把下面的 `实际作业ID` 替换为刚记录的 `jid`：

```bash
docker compose exec -T jobmanager curl -fsS --max-time 5 http://localhost:8081/jobs/实际作业ID/checkpoints
```

SQL 通过一个 Statement Set 向 `stream_events`、`stream_user_item_features`、`stream_item_hotness` 写入结果。窗口热度依赖 watermark 推进，不会在刚提交后立即出现。

已有状态需要恢复时，不要用全新提交代替 checkpoint/savepoint 恢复，也不要删除 Kafka 数据或特征表。本节仅用于首次提交；恢复操作参考 README 的实时作业说明。

## 10. 查看全局状态与排错

```bash
docker compose ps -a
docker compose logs --tail 100 mysql-init
docker compose logs --tail 100 kafka
docker compose logs --tail 100 jobmanager
docker compose logs --tail 100 taskmanager
docker compose logs --tail 100 flink-submit
docker compose logs --tail 100 app
```

| 现象 | 优先检查 |
| --- | --- |
| mysql-init 非 0 退出 | MySQL 地址、容器网络、账号权限 |
| Kafka 无法启动 | 9092 占用与 Kafka 日志 |
| Topic 初始化失败 | Kafka 是否 healthy、Topic 名是否匹配 |
| TaskManager 未注册 | JobManager REST、RPC 和 Worker 日志 |
| flink-submit 非 0 退出 | 可用 slot、连接器、UDF、MySQL 连接 |
| 推荐作业 FAILED | Flink 异常日志、checkpoint 与 JDBC 错误 |
| app 无法启动 | 8000 占用、数据库连接、应用日志 |
| 视频无法播放 | `runtime/media/videos/` 文件与只读挂载 |

出现失败时停在当前步骤，排查后仅重试对应服务；尤其不要盲目重复提交 Flink 作业。

## 11. 停止服务并保留数据

先通过 Flink 的 savepoint 流程保存需要保留的作业状态，再停止组件。单纯停止容器不会自动生成 savepoint。

```bash
docker compose stop app
docker compose stop taskmanager
docker compose stop jobmanager
docker compose stop kafka
```

以上命令保留容器与数据卷。不要使用 `docker compose down -v`，该参数会删除 Kafka、checkpoint 和应用持久卷。外部 MySQL 始终由你单独管理。
