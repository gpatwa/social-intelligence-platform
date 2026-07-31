# Databricks notebook source
"""Create a deterministic, realistic social-media landing dataset for the MVP."""

from datetime import datetime, timedelta, timezone
import json
import random
import re

from pyspark.sql import functions as F
from pyspark.sql import types as T


dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("lookback_hours", "72")
dbutils.widgets.text("tenant_id", "demo")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
lookback_hours = int(dbutils.widgets.get("lookback_hours"))
tenant_id = dbutils.widgets.get("tenant_id")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")
if not 24 <= lookback_hours <= 720:
    raise ValueError("lookback_hours must be between 24 and 720")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", tenant_id):
    raise ValueError(f"Unsafe tenant identifier: {tenant_id!r}")

namespace = f"`{catalog}`.`{schema}`"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {namespace}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {namespace}.`raw_social`")
# The generator is a demo-only source, so each run starts the raw data plane
# clean. A real connector keeps both event tables and checkpoints for replay.
spark.sql(f"DROP TABLE IF EXISTS {namespace}.`bronze_social_events`")
spark.sql(f"DROP TABLE IF EXISTS {namespace}.`bronze_dead_letter_events`")
spark.sql(f"DROP TABLE IF EXISTS {namespace}.`bronze_social_posts`")

landing_path = f"/Volumes/{catalog}/{schema}/raw_social/events"
checkpoint_path = f"/Volumes/{catalog}/{schema}/raw_social/checkpoints/events"
dbutils.fs.rm(landing_path, recurse=True)
dbutils.fs.rm(checkpoint_path, recurse=True)

random.seed(20260710)
generation_time = datetime.now(timezone.utc)
end_time = generation_time.replace(minute=0, second=0, microsecond=0)
# Generate complete hourly buckets only. This prevents demo events from being
# timestamped in the future when a run starts early in the current hour.
start_time = end_time - timedelta(hours=lookback_hours)
platforms = ["youtube", "reddit", "tiktok"]
regions = ["US-CA", "US-NY", "US-TX", "GB-LND", "CA-ON"]

rows = []
sequence = 0


def add_post(
    hour_index: int,
    topic: str,
    text: str,
    hashtags: list[str],
    sentiment: str,
    base_views: int,
    audio_id: str | None = None,
    brand: str | None = None,
) -> None:
    global sequence
    sequence += 1
    created_at = start_time + timedelta(hours=hour_index, minutes=random.randint(0, 55))
    # Collection time describes connector activity, not source publication time.
    # A production initial sync may collect historical posts in one fresh batch.
    collected_at = generation_time
    platform = platforms[(sequence + hour_index) % len(platforms)]
    views = max(50, int(base_views * random.uniform(0.75, 1.35)))
    positive_factor = 1.25 if sentiment == "positive" else 0.75 if sentiment == "negative" else 1.0
    likes = int(views * random.uniform(0.035, 0.09) * positive_factor)
    comments = int(views * random.uniform(0.006, 0.018))
    shares = int(views * random.uniform(0.004, 0.022) * positive_factor)
    saves = int(views * random.uniform(0.003, 0.015))
    author_id = f"creator_{(sequence * 17 + hour_index * 7) % 240:03d}"
    source = {
        "demo": True,
        "topic_seed": topic,
        "sentiment_seed": sentiment,
        "generator_version": "1.0",
    }
    rows.append(
        (
            f"{platform}_{sequence:07d}",
            platform,
            author_id,
            random.randint(300, 250_000),
            text,
            hashtags,
            audio_id,
            created_at,
            collected_at,
            views,
            likes,
            comments,
            shares,
            saves,
            "en",
            regions[(sequence + hour_index * 3) % len(regions)],
            brand,
            json.dumps(source, sort_keys=True),
        )
    )


for hour in range(lookback_hours):
    # Stable topics form the baseline and should not dominate the emerging list.
    for _ in range(4):
        add_post(
            hour,
            "lifestyle",
            "A simple morning routine and daily inspiration",
            ["DailyMoments", "Lifestyle"],
            "positive",
            1_200,
        )
    for _ in range(3):
        add_post(
            hour,
            "product_tips",
            "Acme product tips, setup ideas, and a useful tutorial",
            ["AcmeTips", "HowTo"],
            "positive",
            1_000,
            brand="Acme",
        )

    # A challenge appears late and accelerates across creators and platforms.
    challenge_start = int(lookback_hours * 0.55)
    if hour >= challenge_start:
        challenge_age = hour - challenge_start
        challenge_posts = min(22, 2 + challenge_age // 2)
        for participant in range(challenge_posts):
            add_post(
                hour,
                "glow_up_challenge",
                f"Trying the glow up transformation challenge, participant {participant}",
                ["GlowUpChallenge", "TryThis"],
                "positive",
                1_500 + challenge_age * 140,
                audio_id="audio_glow_2026",
            )

    # A sharp brand-risk event appears only in the final portion of the window.
    issue_start = int(lookback_hours * 0.82)
    if hour >= issue_start:
        issue_age = hour - issue_start
        for report in range(3 + issue_age):
            add_post(
                hour,
                "battery_issue",
                f"Acme battery problem: overheating and poor charging report {report}",
                ["AcmeBattery", "ProductIssue"],
                "negative",
                900 + issue_age * 110,
                brand="Acme",
            )

post_schema = T.StructType(
    [
        T.StructField("post_id", T.StringType(), False),
        T.StructField("platform", T.StringType(), False),
        T.StructField("author_id", T.StringType(), False),
        T.StructField("author_followers", T.LongType(), False),
        T.StructField("content_text", T.StringType(), False),
        T.StructField("hashtags", T.ArrayType(T.StringType()), False),
        T.StructField("audio_id", T.StringType(), True),
        T.StructField("created_at", T.TimestampType(), False),
        T.StructField("collected_at", T.TimestampType(), False),
        T.StructField("views", T.LongType(), False),
        T.StructField("likes", T.LongType(), False),
        T.StructField("comments", T.LongType(), False),
        T.StructField("shares", T.LongType(), False),
        T.StructField("saves", T.LongType(), False),
        T.StructField("language", T.StringType(), False),
        T.StructField("geography", T.StringType(), False),
        T.StructField("brand", T.StringType(), True),
        T.StructField("source_payload", T.StringType(), False),
    ]
)

demo_df = spark.createDataFrame(rows, schema=post_schema)

# The demo connector emits the same versioned envelope expected from production
# webhook, streaming, and polling adapters. The raw payload stays source-shaped
# so it can be replayed after mapping or enrichment logic changes.
payload_columns = [F.col(field.name) for field in post_schema.fields]
identity = F.concat_ws(
    "|",
    F.lit(tenant_id),
    F.col("platform"),
    F.col("post_id"),
    F.lit("social.post.observed"),
    F.date_format(F.col("created_at"), "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"),
)
event_df = demo_df.select(
    F.sha2(F.concat(F.lit("delivery|"), identity), 256).alias("event_id"),
    F.lit("1.0").alias("schema_version"),
    F.lit(tenant_id).alias("tenant_id"),
    F.concat(F.lit("demo-"), F.col("platform")).alias("source_id"),
    "platform",
    F.lit("social.post.observed").alias("event_type"),
    F.col("post_id").alias("source_object_id"),
    F.col("created_at").alias("occurred_at"),
    "collected_at",
    F.sha2(identity, 256).alias("idempotency_key"),
    F.lit(f"demo-{end_time.strftime('%Y%m%d%H%M%S')}").alias("correlation_id"),
    F.to_json(F.struct(*payload_columns)).alias("payload"),
    F.create_map(
        F.lit("connector_type"),
        F.lit("demo_generator"),
        F.lit("delivery_mode"),
        F.lit("batch"),
    ).alias("attributes"),
)
event_df.coalesce(8).write.mode("overwrite").json(landing_path)

print(f"Generated {event_df.count():,} canonical events from {start_time.isoformat()} to {end_time.isoformat()}")
print(f"Event landing path: {landing_path}")
