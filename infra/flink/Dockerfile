FROM flink:1.20.1-scala_2.12-java17
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip curl && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir apache-flink==1.20.1
RUN curl -fSL --retry 3 https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar -o /opt/flink/lib/flink-sql-connector-kafka.jar \
 && curl -fSL --retry 3 https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-jdbc/3.3.0-1.20/flink-connector-jdbc-3.3.0-1.20.jar -o /opt/flink/lib/flink-connector-jdbc.jar \
 && curl -fSL --retry 3 https://repo.maven.apache.org/maven2/com/mysql/mysql-connector-j/8.4.0/mysql-connector-j-8.4.0.jar -o /opt/flink/lib/mysql-connector-j.jar
RUN mkdir -p /opt/flink/checkpoints && chown -R flink:flink /opt/flink/checkpoints
ENV PYTHONPATH=/opt/flink/jobs
ENV PYFLINK_CLIENT_EXECUTABLE=python3
ENV PYFLINK_PYTHON=python3
USER flink
