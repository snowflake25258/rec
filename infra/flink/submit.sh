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
for attempt in $(seq 1 60); do
  if curl -sf http://jobmanager:8081/overview | grep -q '"slots-available":[1-9]'; then
    python3 /opt/flink/jobs/render_sql.py /opt/flink/jobs/pipeline.sql /tmp/yingke-pipeline.sql
    exec /opt/flink/bin/sql-client.sh \
      -Drest.address=jobmanager \
      -Drest.port=8081 \
      -Dexecution.runtime-mode=streaming \
      -f /tmp/yingke-pipeline.sql \
      --pyFiles /opt/flink/jobs/udfs.py \
      --pyExecutable "$PYTHON"
  fi
  sleep 2
done
echo 'JobManager not ready' >&2
exit 1
