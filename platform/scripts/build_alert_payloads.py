"""Emit portable Alerts V2 REST payloads for a configured workspace."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "alerts"
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
ALERT_EMAIL = os.getenv("SOCIAL_INTELLIGENCE_ALERT_EMAIL", "")
PARENT_PATH = os.getenv(
    "DATABRICKS_PARENT_PATH",
    f"/Users/{ALERT_EMAIL}" if ALERT_EMAIL else "",
)
TENANT_ID = os.getenv("SOCIAL_INTELLIGENCE_TENANT_ID", "demo")
CATALOG = os.getenv("SOCIAL_INTELLIGENCE_CATALOG", "dev")
SCHEMA = os.getenv("SOCIAL_INTELLIGENCE_SCHEMA", "social_intelligence_dev")

if not WAREHOUSE_ID or not PARENT_PATH:
    raise SystemExit(
        "Set DATABRICKS_WAREHOUSE_ID and DATABRICKS_PARENT_PATH before "
        "building alert payloads."
    )
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", WAREHOUSE_ID):
    raise SystemExit("DATABRICKS_WAREHOUSE_ID contains unsupported characters.")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", TENANT_ID):
    raise SystemExit("SOCIAL_INTELLIGENCE_TENANT_ID is invalid.")
for identifier in (CATALOG, SCHEMA):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise SystemExit("Catalog and schema names must be SQL identifiers.")


def load(name: str) -> dict:
    return json.loads((CONFIG / name).read_text())


alerts = [
    {
        "display_name": "Social Intelligence: Emerging Trend",
        "query_text": f"SELECT MAX(trend_score) AS alert_value FROM {CATALOG}.{SCHEMA}.gold_trend_snapshot WHERE tenant_id = '{TENANT_ID}'",
        "evaluation": load("trend_score_evaluation.json"),
        "schedule": load("daily_0800.json"),
        "custom_summary": "Emerging social trend detected",
        "custom_description": "A social topic exceeded the configured trend-score threshold. Review the Emerging Trends dashboard page.",
    },
    {
        "display_name": "Social Intelligence: Brand Risk",
        "query_text": f"SELECT COALESCE(SUM(high_risk_mentions), 0) AS alert_value FROM {CATALOG}.{SCHEMA}.gold_brand_daily WHERE tenant_id = '{TENANT_ID}' AND metric_date = (SELECT MAX(metric_date) FROM {CATALOG}.{SCHEMA}.gold_brand_daily WHERE tenant_id = '{TENANT_ID}')",
        "evaluation": load("brand_risk_evaluation.json"),
        "schedule": load("daily_0805.json"),
        "custom_summary": "High-risk brand conversation detected",
        "custom_description": "High-risk brand mentions were detected. Review Brand Health and Risk & Operations.",
    },
    {
        "display_name": "Social Intelligence: Source Freshness",
        "query_text": f"SELECT MAX(freshness_minutes) AS alert_value FROM {CATALOG}.{SCHEMA}.gold_source_health WHERE tenant_id = '{TENANT_ID}' AND enabled",
        "evaluation": load("freshness_evaluation.json"),
        "schedule": load("daily_0810.json"),
        "custom_summary": "Social data may be stale",
        "custom_description": "No recent social posts were found within the freshness threshold. Check the pipeline and source provider.",
    },
]

output_dir = Path(sys.argv[1])
output_dir.mkdir(parents=True, exist_ok=True)
for index, alert in enumerate(alerts, start=1):
    alert["warehouse_id"] = WAREHOUSE_ID
    alert["parent_path"] = PARENT_PATH
    if ALERT_EMAIL:
        alert["evaluation"]["notification"]["subscriptions"] = [
            {"user_email": ALERT_EMAIL}
        ]
    (output_dir / f"{index:02d}_alert.json").write_text(json.dumps(alert, indent=2) + "\n")
