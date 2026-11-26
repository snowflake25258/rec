FROM eclipse-temurin:8-jdk-jammy AS jdk

FROM flink:1.18.1-scala_2.12-java8
USER root
# The Flink runtime contains a JRE. ARM64 pemja needs JNI headers and a compiler.
COPY --from=jdk /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-dev build-essential curl && rm -rf /var/lib/apt/lists/*
RUN pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
RUN test -f "$JAVA_HOME/include/jni.h" && test -f "$JAVA_HOME/include/linux/jni_md.h" \
 && python3 -m pip install --no-cache-dir 'numpy<1.25' 'pandas<2' 'pyarrow<12' 'Cython<3' apache-flink==1.18.1 \
 && python3 -m pip check \
 && python3 -c 'import pemja; from pyflink.table import DataTypes; from pyflink.table.udf import udf'
RUN curl -fSL --retry 3 https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.1.0-1.18/flink-sql-connector-kafka-3.1.0-1.18.jar -o /opt/flink/lib/flink-sql-connector-kafka.jar \
 && curl -fSL --retry 3 https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-jdbc/3.1.2-1.18/flink-connector-jdbc-3.1.2-1.18.jar -o /opt/flink/lib/flink-connector-jdbc.jar \
 && curl -fSL --retry 3 https://repo.maven.apache.org/maven2/com/mysql/mysql-connector-j/8.4.0/mysql-connector-j-8.4.0.jar -o /opt/flink/lib/mysql-connector-j.jar
RUN mkdir -p /opt/flink/checkpoints && chown -R flink:flink /opt/flink/checkpoints
ENV PYTHONPATH=/opt/flink/jobs
ENV PYFLINK_CLIENT_EXECUTABLE=python3
ENV PYFLINK_PYTHON=python3
USER flink
