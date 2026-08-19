"""Read-only projection providers and atomic snapshot export for MCP."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .mcp_service import SocialIntelligenceDataProvider


PROJECTION_FILES = {
    "opportunities": "opportunities.json",
    "evidence": "evidence.json",
    "metrics": "metrics.json",
    "pipeline_status": "pipeline_status.json",
}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SqlProjectionProvider(SocialIntelligenceDataProvider):
    """Provider backed by four governed SQL projection views.

    The executor is injected so the contract can be tested without a cloud
    account. Production constructors below use the provider-native connectors.
    User input never becomes SQL; only configured, validated identifiers do.
    """

    def __init__(
        self,
        executor: Callable[[str], Sequence[Mapping[str, Any]]],
        *,
        catalog: str,
        schema: str,
        views: Mapping[str, str] | None = None,
    ) -> None:
        self.executor = executor
        self.catalog = self._identifier(catalog, "catalog")
        self.schema = self._identifier(schema, "schema")
        configured = dict(views or {})
        self.views = {
            name: self._identifier(configured.get(name, f"mcp_{name}"), f"{name} view")
            for name in PROJECTION_FILES
        }

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if not IDENTIFIER.fullmatch(str(value)):
            raise ValueError(f"{name} must be a simple SQL identifier")
        return str(value)

    def _read(self, name: str) -> Sequence[Mapping[str, Any]]:
        table = f"`{self.catalog}`.`{self.schema}`.`{self.views[name]}`"
        rows = self.executor(f"SELECT * FROM {table} LIMIT 1000")
        if not all(isinstance(row, Mapping) for row in rows):
            raise RuntimeError(f"SQL projection {name} returned invalid rows")
        return rows

    def opportunities(self) -> Sequence[Mapping[str, Any]]:
        return self._read("opportunities")

    def evidence(self) -> Sequence[Mapping[str, Any]]:
        return self._read("evidence")

    def metrics(self) -> Sequence[Mapping[str, Any]]:
        return self._read("metrics")

    def pipeline_status(self) -> Sequence[Mapping[str, Any]]:
        return self._read("pipeline_status")


def _connector_executor(connection: Any) -> Callable[[str], Sequence[Mapping[str, Any]]]:
    def execute(query: str) -> Sequence[Mapping[str, Any]]:
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            columns = [str(column[0]) for column in cursor.description or ()]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    return execute


def databricks_provider_from_environment() -> SqlProjectionProvider:
    try:
        from databricks import sql
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise RuntimeError(
            "Install the databricks SQL extra before selecting the Databricks MCP provider"
        ) from error
    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "").strip()
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", "").strip()
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    if not all((host, http_path, token)):
        raise RuntimeError(
            "DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, and DATABRICKS_TOKEN are required"
        )
    connection = sql.connect(server_hostname=host, http_path=http_path, access_token=token)
    return SqlProjectionProvider(
        _connector_executor(connection),
        catalog=os.environ.get("SOCIAL_INTELLIGENCE_CATALOG", "dev"),
        schema=os.environ.get("SOCIAL_INTELLIGENCE_SCHEMA", "social_intelligence_dev"),
    )


def snowflake_provider_from_environment() -> SqlProjectionProvider:
    try:
        import snowflake.connector
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise RuntimeError(
            "Install the snowflake SQL extra before selecting the Snowflake MCP provider"
        ) from error
    account = os.environ.get("SNOWFLAKE_ACCOUNT", "").strip()
    user = os.environ.get("SNOWFLAKE_USER", "").strip()
    password = os.environ.get("SNOWFLAKE_PASSWORD", "").strip()
    if not all((account, user, password)):
        raise RuntimeError("SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD are required")
    connection = snowflake.connector.connect(
        account=account,
        user=user,
        password=password,
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "SOCIAL_INTELLIGENCE_BA"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "SOCIAL_INTELLIGENCE"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "ANALYTICS"),
    )
    return SqlProjectionProvider(
        _connector_executor(connection),
        catalog=os.environ.get("SNOWFLAKE_DATABASE", "SOCIAL_INTELLIGENCE"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "ANALYTICS"),
        views={
            "opportunities": "GOLD_OPPORTUNITIES",
            "evidence": "MCP_EVIDENCE",
            "metrics": "MCP_METRICS",
            "pipeline_status": "MCP_PIPELINE_STATUS",
        },
    )


def write_projection_snapshots(
    provider: SocialIntelligenceDataProvider, root: Path
) -> None:
    """Export read projections atomically for Free Edition or local MCP hosts."""
    root.mkdir(parents=True, exist_ok=True)
    rows_by_name = {
        "opportunities": provider.opportunities(),
        "evidence": provider.evidence(),
        "metrics": provider.metrics(),
        "pipeline_status": provider.pipeline_status(),
    }
    for name, rows in rows_by_name.items():
        payload = json.dumps({"items": list(rows)}, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=root, prefix=f".{name}.", delete=False
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        temporary_path.replace(root / PROJECTION_FILES[name])


def provider_from_environment() -> SocialIntelligenceDataProvider:
    mode = os.environ.get("SOCIAL_INTELLIGENCE_MCP_PROVIDER", "empty").strip().lower()
    if mode == "snapshot":
        directory = os.environ.get("SOCIAL_INTELLIGENCE_MCP_SNAPSHOT_DIR", "").strip()
        if not directory:
            raise RuntimeError("SOCIAL_INTELLIGENCE_MCP_SNAPSHOT_DIR is required for snapshot mode")
        from .mcp_service import SnapshotDataProvider

        return SnapshotDataProvider(Path(directory).expanduser())
    if mode == "databricks":
        return databricks_provider_from_environment()
    if mode == "snowflake":
        return snowflake_provider_from_environment()
    if mode in ("", "empty"):
        from .mcp_service import InMemoryDataProvider

        return InMemoryDataProvider()
    raise RuntimeError(f"Unsupported MCP provider: {mode}")
