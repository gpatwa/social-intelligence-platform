"""Generate the serialized AI/BI dashboard definition for the MVP.

The resulting JSON is accepted by the Lakeview (AI/BI Dashboard) API. It uses
only the Gold tables created by the workflow and intentionally keeps the first
dashboard compact and explainable.
"""

from __future__ import annotations

import json
import re
import sys


def dataset(name: str, sql: str) -> dict:
    return {
        "name": name,
        "displayName": name.replace("_", " ").title(),
        "queryLines": [sql],
        "catalog": catalog,
        "schema": schema,
    }


def query(dataset_name: str, fields: list[tuple[str, str]]) -> dict:
    return {
        "name": "main_query",
        "query": {
            "datasetName": dataset_name,
            "fields": [{"name": name, "expression": expression} for name, expression in fields],
            "disaggregated": False,
        },
    }


def counter(name: str, dataset_name: str, field: str, title: str, x: int) -> dict:
    return {
        "widget": {
            "name": name,
            "queries": [query(dataset_name, [(field, f"`{field}`")])],
            "spec": {
                "encodings": {"target": {"displayName": title, "fieldName": field}},
                "version": 2,
                "widgetType": "counter",
            },
        },
        "position": {"x": x, "y": 0, "width": 3, "height": 2},
    }


def bar(
    name: str,
    dataset_name: str,
    x_field: str,
    y_expression: str,
    y_name: str,
    title: str,
    *,
    y: int = 2,
) -> dict:
    return {
        "widget": {
            "name": name,
            "queries": [query(dataset_name, [(x_field, f"`{x_field}`"), (y_name, y_expression)])],
            "spec": {
                "encodings": {
                    "x": {"displayName": x_field.replace("_", " ").title(), "fieldName": x_field, "axis": {"hideTitle": True}},
                    "y": {
                        "displayName": title,
                        "fieldName": y_name,
                        "axis": {"title": title},
                        "scale": {"type": "quantitative"},
                    },
                },
                "version": 3,
                "widgetType": "bar",
            },
        },
        "position": {"x": 0, "y": y, "width": 12, "height": 6},
    }


def page(name: str, display_name: str, layout: list[dict]) -> dict:
    return {"name": name, "displayName": display_name, "layout": layout}


tenant_id = sys.argv[1] if len(sys.argv) > 1 else "demo"
catalog = sys.argv[2] if len(sys.argv) > 2 else "dev"
schema = sys.argv[3] if len(sys.argv) > 3 else "social_intelligence_dev"
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", tenant_id):
    raise SystemExit(f"Unsafe tenant identifier: {tenant_id!r}")
for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise SystemExit(f"Unsafe catalog or schema identifier: {identifier!r}")
tenant_predicate = f" WHERE tenant_id = '{tenant_id}'"


dashboard = {
    "datasets": [
        dataset(
            "executive_kpis",
            "SELECT posts_24h, creators_24h, views_24h, engagements_24h, "
            "positive_share_24h, negative_share_24h, high_risk_mentions_24h, active_topics_24h "
            f"FROM gold_executive_kpis{tenant_predicate}",
        ),
        dataset(
            "trend_snapshot",
            "SELECT topic, trend_score, velocity_z, acceleration_pct, post_count, creator_count, "
            f"positive_share, negative_share FROM gold_trend_snapshot{tenant_predicate}",
        ),
        dataset(
            "challenge_snapshot",
            "SELECT challenge_name, challenge_score, participation_count, participant_growth_pct, "
            f"unique_creators, geography_count, platform_count FROM gold_challenge_snapshot{tenant_predicate}",
        ),
        dataset(
            "brand_daily",
            "SELECT metric_date, brand, mentions, negative_share, net_sentiment, high_risk_mentions "
            f"FROM gold_brand_daily{tenant_predicate}",
        ),
        dataset(
            "risk_topics",
            "SELECT topic, SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS high_risk_mentions "
            f"FROM silver_social_posts{tenant_predicate} GROUP BY topic",
        ),
        dataset(
            "signal_feed",
            "SELECT signal_type, signal_key, score, severity, evidence_count "
            f"FROM gold_signal_feed{tenant_predicate}",
        ),
        dataset(
            "source_health",
            "SELECT platform, delivered_events, rejected_events, duplicate_deliveries, "
            f"freshness_minutes, health_status FROM gold_source_health{tenant_predicate}",
        ),
    ],
    "pages": [
        page(
            "executive_pulse",
            "Executive Pulse",
            [
                counter("posts_24h", "executive_kpis", "posts_24h", "Posts (24h)", 0),
                counter("views_24h", "executive_kpis", "views_24h", "Views (24h)", 3),
                counter("engagements_24h", "executive_kpis", "engagements_24h", "Engagements (24h)", 6),
                counter("risk_24h", "executive_kpis", "high_risk_mentions_24h", "High-risk mentions", 9),
            ],
        ),
        page(
            "emerging_trends",
            "Emerging Trends",
            [bar("trend_scores", "trend_snapshot", "topic", "MAX(`trend_score`)", "trend_score", "Trend score")],
        ),
        page(
            "challenges",
            "Challenges",
            [bar("challenge_scores", "challenge_snapshot", "challenge_name", "MAX(`challenge_score`)", "challenge_score", "Challenge score")],
        ),
        page(
            "brand_health",
            "Brand Health",
            [bar("negative_sentiment", "brand_daily", "metric_date", "AVG(`negative_share`)", "negative_share", "Negative share")],
        ),
        page(
            "risk_operations",
            "Risk & Operations",
            [
                bar(
                    "risk_by_topic",
                    "risk_topics",
                    "topic",
                    "SUM(`high_risk_mentions`)",
                    "high_risk_mentions",
                    "High-risk mentions",
                ),
                bar(
                    "source_delivery",
                    "source_health",
                    "platform",
                    "SUM(`delivered_events`)",
                    "delivered_events",
                    "Delivered events",
                    y=8,
                ),
                bar(
                    "signal_scores",
                    "signal_feed",
                    "signal_key",
                    "MAX(`score`)",
                    "score",
                    "Signal score",
                    y=14,
                ),
            ],
        ),
    ],
}

json.dump(dashboard, sys.stdout, separators=(",", ":"))
sys.stdout.write("\n")
