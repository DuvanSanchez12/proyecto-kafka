# ---------------------------------------------------------------------------
# Imagen de Spark para BrandPulse.
#
# Se parte de la imagen oficial (ya trae Spark + Java 17 + Python 3) y se
# agregan tres cosas:
#   1. un virtualenv con psycopg2 (los executors lo usan para escribir);
#   2. los conectores Kafka de Spark, copiados a $SPARK_HOME/jars para que
#      esten en el classpath del driver Y de los workers sin -‑jars;
#   3. el codigo del job en /opt/app/jobs.
# ---------------------------------------------------------------------------
FROM apache/spark:3.5.1-scala2.12-java17-python3-ubuntu

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ARG SPARK_VERSION=3.5.1
ARG SCALA=2.12
ARG KAFKA_CLIENTS=3.4.1
ARG COMMONS_POOL=2.11.0
ARG MAVEN=https://repo1.maven.org/maven2

RUN set -eux; \
    curl -fsSL -o "$SPARK_HOME/jars/spark-sql-kafka-0-10_${SCALA}-${SPARK_VERSION}.jar" \
      "$MAVEN/org/apache/spark/spark-sql-kafka-0-10_${SCALA}/${SPARK_VERSION}/spark-sql-kafka-0-10_${SCALA}-${SPARK_VERSION}.jar"; \
    curl -fsSL -o "$SPARK_HOME/jars/spark-token-provider-kafka-0-10_${SCALA}-${SPARK_VERSION}.jar" \
      "$MAVEN/org/apache/spark/spark-token-provider-kafka-0-10_${SCALA}/${SPARK_VERSION}/spark-token-provider-kafka-0-10_${SCALA}-${SPARK_VERSION}.jar"; \
    curl -fsSL -o "$SPARK_HOME/jars/kafka-clients-${KAFKA_CLIENTS}.jar" \
      "$MAVEN/org/apache/kafka/kafka-clients/${KAFKA_CLIENTS}/kafka-clients-${KAFKA_CLIENTS}.jar"; \
    curl -fsSL -o "$SPARK_HOME/jars/commons-pool2-${COMMONS_POOL}.jar" \
      "$MAVEN/org/apache/commons/commons-pool2/${COMMONS_POOL}/commons-pool2-${COMMONS_POOL}.jar"

COPY jobs /opt/app/jobs

ENV PYSPARK_PYTHON=/opt/venv/bin/python \
    PYSPARK_DRIVER_PYTHON=/opt/venv/bin/python \
    PYTHONPATH=/opt/app \
    SPARK_HOME=/opt/spark

WORKDIR /opt/app
