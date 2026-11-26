#!/usr/bin/env bash
set -euo pipefail
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
export MYSQL_HOST="${MYSQL_HOST:-host.docker.internal}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-yingke}"
export MYSQL_USER="${MYSQL_USER:-root}"
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
export KAFKA_TOPIC="${KAFKA_TOPIC:-rec-events}"
PYTHON="${FLINK_PYTHON:-python3}"
# SQL Client 在提交容器里生成作业图，checkpoint 配置必须在这里显式传给客户端，
# 否则作业图里没有 checkpointing（集群端配置只对集群里跑的作业生效）。
CHECKPOINT_ARGS=(
  -Dexecution.checkpointing.interval=10s
  -Dexecution.checkpointing.mode=EXACTLY_ONCE
  -Dexecution.checkpointing.timeout=10min
  -Dexecution.checkpointing.max-concurrent-checkpoints=1
  -Dexecution.checkpointing.min-pause=0
  -Dexecution.checkpointing.externalized-checkpoint-retention=RETAIN_ON_CANCELLATION
  -Dexecution.checkpointing.unaligned=false
  -Dstate.backend=hashmap
  -Dstate.checkpoints.dir=file:///opt/flink/checkpoints
  -Dstate.savepoints.dir=file:///opt/flink/checkpoints/savepoints
)
for attempt in $(seq 1 60); do
  if curl -sf http://jobmanager:8081/overview | grep -q '"slots-available":[1-9]'; then
    python3 /opt/flink/jobs/render_sql.py /opt/flink/jobs/pipeline.sql /tmp/yingke-pipeline.sql
    exec /opt/flink/bin/sql-client.sh \
      -Drest.address=jobmanager \
      -Drest.port=8081 \
      -Dexecution.runtime-mode=streaming \
      "${CHECKPOINT_ARGS[@]}" \
      -f /tmp/yingke-pipeline.sql \
      --pyFiles /opt/flink/jobs/udfs.py \
      --pyExecutable "$PYTHON"
  fi
  sleep 2
done
echo 'JobManager not ready' >&2
exit 1
