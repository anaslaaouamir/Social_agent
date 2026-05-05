"""
Spark Structured Streaming — traitement temps réel des événements sociaux.
Lance avec : spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.8 stream_processor.py
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, avg, sum as spark_sum,
    to_timestamp, current_timestamp, expr, udf, struct, to_json
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType,
    IntegerType, BooleanType, TimestampType, ArrayType
)

KAFKA_SERVERS = "kafka:9092"
CHECKPOINT_DIR = "/tmp/spark-checkpoints"
POSTGRES_URL = "jdbc:postgresql://postgres:5432/social_agent"
POSTGRES_PROPS = {
    "user": "agent",
    "password": "agentpass",
    "driver": "org.postgresql.Driver",
}

# ─── Schémas des événements ───────────────────────────────────────────────────

COMMENT_SCHEMA = StructType([
    StructField("comment_id", StringType()),
    StructField("post_id", StringType()),
    StructField("platform", StringType()),
    StructField("account_id", StringType()),
    StructField("text", StringType()),
    StructField("author", StringType()),
    StructField("timestamp", StringType()),
    StructField("likes_count", IntegerType()),
    StructField("is_reply", BooleanType()),
])

NLP_RESULT_SCHEMA = StructType([
    StructField("comment_id", StringType()),
    StructField("is_spam", BooleanType()),
    StructField("spam_score", DoubleType()),
    StructField("is_toxic", BooleanType()),
    StructField("toxic_score", DoubleType()),
    StructField("sentiment", StringType()),
    StructField("sentiment_score", DoubleType()),
    StructField("topic_id", IntegerType()),
    StructField("topic_label", StringType()),
    StructField("language", StringType()),
])

ENGAGEMENT_SCHEMA = StructType([
    StructField("post_id", StringType()),
    StructField("platform", StringType()),
    StructField("account_id", StringType()),
    StructField("likes_count", IntegerType()),
    StructField("comments_count", IntegerType()),
    StructField("shares_count", IntegerType()),
    StructField("reach", IntegerType()),
    StructField("timestamp", StringType()),
])


def create_spark_session() -> SparkSession:
    return (
        SparkSession.builder
        .appName("SocialAgentStreaming")
        .master("spark://spark-master:7077")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.8,"
            "org.postgresql:postgresql:42.7.3"
        )
        .getOrCreate()
    )


def read_kafka_stream(spark: SparkSession, topic: str):
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("subscribe", topic)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
        .select(
            col("key").cast("string"),
            col("value").cast("string"),
            col("timestamp").alias("kafka_timestamp"),
            col("partition"),
            col("offset"),
        )
    )


def process_comments_stream(spark: SparkSession):
    """
    Stream: social.comments.raw + social.nlp.results
    → Agrégations par fenêtre 5min : sentiment distribution, toxic rate
    → Alertes si toxic_rate > 20%
    """
    # Stream des commentaires bruts
    raw_comments = (
        read_kafka_stream(spark, "social.comments.raw")
        .select(from_json(col("value"), COMMENT_SCHEMA).alias("c"), col("kafka_timestamp"))
        .select("c.*", "kafka_timestamp")
        .withColumn("event_time", to_timestamp(col("timestamp")))
    )

    # Stream des résultats NLP
    nlp_results = (
        read_kafka_stream(spark, "social.nlp.results")
        .select(from_json(col("value"), NLP_RESULT_SCHEMA).alias("n"), col("kafka_timestamp"))
        .select("n.*")
    )

    # Join commentaires + NLP sur comment_id (watermark 10min)
    joined = (
        raw_comments
        .withWatermark("event_time", "10 minutes")
        .join(
            nlp_results,
            "comment_id",
            "left",
        )
    )

    # Agrégation par fenêtre glissante de 5 minutes
    windowed_sentiment = (
        joined
        .withWatermark("event_time", "10 minutes")
        .groupBy(
            window(col("event_time"), "5 minutes", "1 minute"),
            col("platform"),
            col("account_id"),
            col("sentiment"),
        )
        .agg(
            count("*").alias("comment_count"),
            avg("sentiment_score").alias("avg_sentiment_score"),
            avg("spam_score").alias("avg_spam_score"),
            avg("toxic_score").alias("avg_toxic_score"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("platform"),
            col("account_id"),
            col("sentiment"),
            col("comment_count"),
            col("avg_sentiment_score"),
            col("avg_spam_score"),
            col("avg_toxic_score"),
        )
    )

    # Output vers Kafka (pour Grafana via Kafka datasource ou webhook)
    query_sentiment = (
        windowed_sentiment
        .select(to_json(struct("*")).alias("value"))
        .writeStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("topic", "social.analytics.sentiment_window")
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/sentiment_window")
        .outputMode("update")
        .start()
    )

    return query_sentiment


def process_engagement_stream(spark: SparkSession):
    """
    Stream: social.engagement.metrics
    → Agrégations rolling 1h par compte/plateforme
    → Détection anomalie si engagement chute > 50%
    """
    engagement = (
        read_kafka_stream(spark, "social.engagement.metrics")
        .select(from_json(col("value"), ENGAGEMENT_SCHEMA).alias("e"), col("kafka_timestamp"))
        .select("e.*", "kafka_timestamp")
        .withColumn("event_time", to_timestamp(col("timestamp")))
    )

    # Rolling 1h par compte
    rolling_engagement = (
        engagement
        .withWatermark("event_time", "2 hours")
        .groupBy(
            window(col("event_time"), "1 hour", "15 minutes"),
            col("platform"),
            col("account_id"),
        )
        .agg(
            spark_sum("likes_count").alias("total_likes"),
            spark_sum("comments_count").alias("total_comments"),
            spark_sum("shares_count").alias("total_shares"),
            avg("reach").alias("avg_reach"),
            count("post_id").alias("post_count"),
        )
        .withColumn(
            "engagement_rate",
            (col("total_likes") + col("total_comments") * 2 + col("total_shares") * 3)
            / (col("avg_reach") + expr("1")),
        )
    )

    query_engagement = (
        rolling_engagement
        .select(to_json(struct("*")).alias("value"))
        .writeStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("topic", "social.analytics.engagement_window")
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/engagement_window")
        .outputMode("update")
        .start()
    )

    return query_engagement


def process_alert_detection(spark: SparkSession):
    """
    Détection d'alertes temps réel depuis le stream NLP.
    Si toxic_rate > 0.2 sur 5min → émet une alerte dans social.alerts
    """
    nlp_results = (
        read_kafka_stream(spark, "social.nlp.results")
        .select(from_json(col("value"), NLP_RESULT_SCHEMA).alias("n"), col("kafka_timestamp"))
        .select("n.*", col("kafka_timestamp").alias("event_time"))
    )

    toxic_rate = (
        nlp_results
        .withWatermark("event_time", "10 minutes")
        .groupBy(window(col("event_time"), "5 minutes"))
        .agg(
            avg("toxic_score").alias("avg_toxic_score"),
            avg("spam_score").alias("avg_spam_score"),
            count("*").alias("total_processed"),
        )
        .filter(col("avg_toxic_score") > 0.2)
        .select(
            to_json(struct(
                col("window.start").alias("detected_at"),
                col("avg_toxic_score"),
                col("avg_spam_score"),
                col("total_processed"),
                expr("'HIGH'").alias("severity"),
                expr("'Toxic content spike detected in last 5 minutes'").alias("message"),
            )).alias("value")
        )
    )

    return (
        toxic_rate
        .writeStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("topic", "social.alerts")
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/alert_detection")
        .outputMode("update")
        .start()
    )


if __name__ == "__main__":
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    q1 = process_comments_stream(spark)
    q2 = process_engagement_stream(spark)
    q3 = process_alert_detection(spark)

    # Attendre que tous les streams tournent
    spark.streams.awaitAnyTermination()
