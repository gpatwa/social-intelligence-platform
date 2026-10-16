"""Authenticated, idempotent, append-only persistence for reviewed pilot records.

The compile-only modules (``recommendation_review`` and ``campaign_intelligence``)
produce validated artifacts. This module is the single write boundary for them.
It never trusts a caller-supplied artifact: it authenticates the caller,
authorizes the tenant, re-derives the deterministic record ID, re-checks the
governance invariants (citations, human attribution, aggregate-only data,
non-causal, non-mutating) and verifies that the referenced review or experiment
already exists in the same tenant before appending exactly one row.

Replays with an identical artifact are acknowledged without a second write. A
replay of the same idempotency key with different content is a conflict. Nothing
here calls an ad platform, exports an audience, or changes spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import hmac
import json
import os
import re
from typing import Any, Callable, Mapping, Protocol

from .campaign_intelligence import EXPERIMENT_VERSION, MEASUREMENT_VERSION
from .recommendation_review import OUTCOME_VERSION, REVIEW_STATUSES, REVIEW_VERSION

IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
APPROVED_STATUSES = frozenset({"APPROVED_FOR_HANDOFF", "EDITED_FOR_HANDOFF"})

REVIEWS = "decision_recommendation_reviews"
OUTCOMES = "decision_recommendation_outcomes"
EXPERIMENTS = "decision_campaign_experiments"
MEASUREMENTS = "decision_campaign_measurements"

PRINCIPALS_ENV = "SOCIAL_INTELLIGENCE_APPEND_PRINCIPALS"
TOKEN_ENV = "SOCIAL_INTELLIGENCE_APPEND_TOKEN"


class AuthenticationError(PermissionError):
    """The caller could not be identified."""


class ConflictError(ValueError):
    """The idempotency key was already used for different content."""


@dataclass(frozen=True)
class Principal:
    actor_id: str
    tenants: frozenset[str]

    def authorize(self, tenant_id: str) -> None:
        if tenant_id not in self.tenants:
            raise PermissionError("Principal is not authorized for this tenant")


class PrincipalAuthenticator:
    """Bearer-token authentication over SHA-256 token digests (never raw tokens)."""

    def __init__(self, principals: Mapping[str, Principal]) -> None:
        self._principals = dict(principals)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "PrincipalAuthenticator":
        """Parse ``[{"actor_id", "tenants", "token_sha256"}]`` from the environment.

        The variable holds digests only; generate one with
        ``printf %s "$TOKEN" | shasum -a 256``.
        """
        raw = (environ if environ is not None else os.environ).get(PRINCIPALS_ENV, "").strip()
        if not raw:
            raise RuntimeError(f"{PRINCIPALS_ENV} is required; the append boundary fails closed")
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{PRINCIPALS_ENV} must be valid JSON") from error
        if not isinstance(entries, list) or not entries:
            raise RuntimeError(f"{PRINCIPALS_ENV} must be a non-empty JSON list")
        principals: dict[str, Principal] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError(f"{PRINCIPALS_ENV} entries must be objects")
            digest = str(entry.get("token_sha256", "")).lower()
            actor = str(entry.get("actor_id", ""))
            tenants = entry.get("tenants")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise RuntimeError("token_sha256 must be a 64-character hex SHA-256 digest")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", actor):
                raise RuntimeError("actor_id must be an opaque identifier, not an email address")
            if not isinstance(tenants, list) or not tenants or not all(isinstance(t, str) and t for t in tenants):
                raise RuntimeError("tenants must be a non-empty list of tenant IDs")
            principals[digest] = Principal(actor, frozenset(tenants))
        return cls(principals)

    def authenticate(self, token: str | None) -> Principal:
        candidate = sha256((token or "").encode("utf-8")).hexdigest()
        match: Principal | None = None
        for digest, principal in self._principals.items():  # constant-time over all entries
            if hmac.compare_digest(digest, candidate):
                match = principal
        if not token or match is None:
            raise AuthenticationError("Invalid or missing append credential")
        return match


class RecordStore(Protocol):
    def get(self, table: str, record_id: str) -> Mapping[str, Any] | None: ...

    def insert_if_absent(self, table: str, id_column: str, row: Mapping[str, Any]) -> None: ...


class InMemoryRecordStore:
    """Reference store for tests and offline staging rehearsals."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = {}

    def get(self, table: str, record_id: str) -> Mapping[str, Any] | None:
        row = self.tables.get(table, {}).get(record_id)
        return dict(row) if row is not None else None

    def insert_if_absent(self, table: str, id_column: str, row: Mapping[str, Any]) -> None:
        self.tables.setdefault(table, {}).setdefault(str(row[id_column]), dict(row))


TIMESTAMP_COLUMNS = frozenset({"reviewed_at", "observed_at", "planned_start_at", "planned_end_at", "received_at"})


class DatabricksSqlRecordStore:
    """Append-only Delta writer using parameterized, insert-if-absent MERGE.

    Not exercised against a live workspace in this repository's tests; the SQL
    shape is unit-tested with a fake cursor. Verify against staging before use.
    """

    def __init__(self, connection: Any, *, catalog: str, schema: str) -> None:
        for name, value in (("catalog", catalog), ("schema", schema)):
            if not IDENTIFIER.fullmatch(value):
                raise ValueError(f"{name} must be a simple SQL identifier")
        self._connection = connection
        self._namespace = f"`{catalog}`.`{schema}`"

    @classmethod
    def from_environment(cls) -> "DatabricksSqlRecordStore":
        try:
            from databricks import sql
        except ImportError as error:  # pragma: no cover - optional dependency
            raise RuntimeError("Install the databricks extra to use the Databricks record store") from error
        host = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "").strip()
        http_path = os.environ.get("DATABRICKS_HTTP_PATH", "").strip()
        token = os.environ.get("DATABRICKS_TOKEN", "").strip()
        if not all((host, http_path, token)):
            raise RuntimeError("DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, and DATABRICKS_TOKEN are required")
        return cls(
            sql.connect(server_hostname=host, http_path=http_path, access_token=token),
            catalog=os.environ.get("SOCIAL_INTELLIGENCE_CATALOG", "dev"),
            schema=os.environ.get("SOCIAL_INTELLIGENCE_SCHEMA", "social_intelligence_dev"),
        )

    def _table(self, table: str) -> str:
        if table not in TABLE_ID_COLUMNS:
            raise ValueError("unknown record table")
        return f"{self._namespace}.`{table}`"

    def _query(self, statement: str, params: Mapping[str, Any]) -> list[tuple[Any, ...]]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(statement, dict(params))
            return list(cursor.fetchall()) if cursor.description else []
        finally:
            cursor.close()

    def get(self, table: str, record_id: str) -> Mapping[str, Any] | None:
        id_column = TABLE_ID_COLUMNS[table]
        cursor = self._connection.cursor()
        try:
            cursor.execute(f"SELECT * FROM {self._table(table)} WHERE `{id_column}` = :record_id LIMIT 1", {"record_id": record_id})
            rows = cursor.fetchall()
            if not rows:
                return None
            row = dict(zip([str(column[0]) for column in cursor.description], rows[0]))
        finally:
            cursor.close()
        return {key: (value.isoformat() if isinstance(value, datetime) else value) for key, value in row.items()}

    def insert_if_absent(self, table: str, id_column: str, row: Mapping[str, Any]) -> None:
        columns = list(row)
        if not all(IDENTIFIER.fullmatch(column) for column in columns):
            raise ValueError("invalid column name")
        values = ", ".join(
            f"CAST(:{c} AS TIMESTAMP)" if c in TIMESTAMP_COLUMNS else f":{c}" for c in columns
        )
        names = ", ".join(f"`{c}`" for c in columns)
        self._query(
            f"MERGE INTO {self._table(table)} AS target "
            f"USING (SELECT :{id_column} AS `{id_column}`) AS incoming "
            f"ON target.`{id_column}` = incoming.`{id_column}` "
            f"WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({values})",
            row,
        )


# --- artifact specifications -------------------------------------------------

TABLE_ID_COLUMNS = {REVIEWS: "review_id", OUTCOMES: "outcome_id", EXPERIMENTS: "experiment_id", MEASUREMENTS: "measurement_id"}

# Exact top-level keys each compiler emits. Unknown keys are rejected so nothing
# identity-like or provider-specific can ride along with an artifact.
ARTIFACT_KEYS = {
    "review": frozenset({
        "review_id", "schema_version", "review_version", "tenant_id", "rerank_id", "context_id", "decision_id",
        "decision", "status", "reviewer_id", "decision_reason", "reviewer_note", "reviewed_at", "idempotency_key",
        "selected_candidate_id", "selected_candidate_rank", "evidence_ids", "edited_brief", "handoff",
        "approval_required", "causality_claim", "mutation",
    }),
    "outcome": frozenset({
        "outcome_id", "schema_version", "outcome_version", "tenant_id", "review_id", "rerank_id", "context_id",
        "decision_id", "candidate_id", "metric_name", "observed_value", "baseline_value", "unit",
        "measurement_window_days", "measurement_source", "observed_at", "reported_by", "idempotency_key",
        "confidence", "attribution", "causality_claim", "mutation",
    }),
    "experiment": frozenset({
        "experiment_id", "schema_version", "experiment_version", "tenant_id", "review_id", "rerank_id", "context_id",
        "decision_id", "candidate_id", "campaign_name", "channel", "business_objective", "primary_metric",
        "control_definition", "treatment_definition", "comparison_method", "target_lift_pct", "planned_start_at",
        "planned_end_at", "created_by", "idempotency_key", "status", "activation", "data_policy",
        "approval_required", "causality_claim", "mutation",
    }),
    "measurement": frozenset({
        "measurement_id", "schema_version", "measurement_version", "tenant_id", "experiment_id", "review_id",
        "candidate_id", "comparison_method", "primary_metric", "control", "treatment",
        "observed_conversion_rate_lift_pct", "result", "confidence", "measurement_window_days", "measurement_source",
        "reported_by", "observed_at", "idempotency_key", "ranking_feedback", "data_policy", "attribution",
        "causality_claim", "mutation",
    }),
}
ARM_KEYS = frozenset({"impressions", "conversions", "value", "spend", "conversion_rate"})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(artifact: Mapping[str, Any], key: str) -> str:
    value = artifact.get(key)
    _require(isinstance(value, str) and bool(value.strip()), f"{key} is required")
    return value


def _digest(*parts: str) -> str:
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def _common(artifact: Mapping[str, Any], kind: str, version_key: str, version: str) -> str:
    _require(isinstance(artifact, Mapping), "artifact must be a JSON object")
    unknown = sorted(set(artifact) - ARTIFACT_KEYS[kind])
    _require(not unknown, f"artifact contains unsupported fields: {', '.join(unknown)}")
    _require(artifact.get(version_key) == version, f"artifact must be {version}")
    _require(artifact.get("mutation") == "none", "artifact must be non-mutating")
    _require(artifact.get("causality_claim") == "none", "artifact must not claim causality")
    return _text(artifact, "tenant_id")


def _referenced(store: RecordStore, table: str, record_id: str, tenant_id: str, what: str) -> Mapping[str, Any]:
    row = store.get(table, record_id)
    _require(row is not None and row.get("tenant_id") == tenant_id, f"referenced {what} is not stored for this tenant")
    return row  # type: ignore[return-value]


def _approved_review(store: RecordStore, review_id: str, tenant_id: str) -> Mapping[str, Any]:
    review = _referenced(store, REVIEWS, review_id, tenant_id, "review")
    _require(review.get("status") in APPROVED_STATUSES, "referenced review is not approved for handoff")
    return review


@dataclass(frozen=True)
class _Prepared:
    table: str
    id_column: str
    row: dict[str, Any]


def _prepare_review(a: Mapping[str, Any], principal: Principal, store: RecordStore, now: str) -> _Prepared:
    tenant = _common(a, "review", "review_version", REVIEW_VERSION)
    _require(a.get("review_id") == _digest(REVIEW_VERSION, tenant, _text(a, "rerank_id"), _text(a, "idempotency_key")), "review_id does not match its idempotency inputs")
    decision, status = _text(a, "decision"), _text(a, "status")
    _require(REVIEW_STATUSES.get(decision) == status, "decision and status are inconsistent")
    _require(a.get("reviewer_id") == principal.actor_id, "reviewer_id must equal the authenticated actor")
    handoff = a.get("handoff")
    _require(isinstance(handoff, Mapping) and handoff.get("external_action_permitted") is False, "review must keep the manual-handoff boundary")
    evidence = a.get("evidence_ids")
    _require(isinstance(evidence, list) and all(isinstance(i, str) and i for i in evidence), "evidence_ids must be a list of IDs")
    if status in APPROVED_STATUSES:
        _require(bool(evidence) and bool(a.get("selected_candidate_id")), "approved reviews require a selected candidate with evidence citations")
    return _Prepared(REVIEWS, "review_id", {
        "review_id": a["review_id"], "tenant_id": tenant, "rerank_id": a["rerank_id"], "context_id": a["context_id"],
        "decision_id": a["decision_id"], "decision": decision, "status": status, "reviewer_id": a["reviewer_id"],
        "decision_reason": a["decision_reason"], "reviewer_note": a.get("reviewer_note"),
        "selected_candidate_id": a.get("selected_candidate_id"), "selected_candidate_rank": a.get("selected_candidate_rank"),
        "evidence_ids_json": json.dumps(evidence), "edited_brief": a.get("edited_brief"),
        "handoff_state": handoff["state"], "idempotency_key": a["idempotency_key"],
        "reviewed_at": a["reviewed_at"], "received_at": now,
    })


def _prepare_outcome(a: Mapping[str, Any], principal: Principal, store: RecordStore, now: str) -> _Prepared:
    tenant = _common(a, "outcome", "outcome_version", OUTCOME_VERSION)
    expected = _digest(OUTCOME_VERSION, tenant, _text(a, "review_id"), _text(a, "metric_name"), _text(a, "idempotency_key"))
    _require(a.get("outcome_id") == expected, "outcome_id does not match its idempotency inputs")
    _require(a.get("attribution") == "OBSERVATIONAL_ONLY", "outcomes must be observational only")
    _require(a.get("reported_by") == principal.actor_id, "reported_by must equal the authenticated actor")
    review = _approved_review(store, a["review_id"], tenant)
    _require(review.get("selected_candidate_id") == a.get("candidate_id"), "outcome candidate must match the approved review")
    return _Prepared(OUTCOMES, "outcome_id", {
        "outcome_id": a["outcome_id"], "tenant_id": tenant, "review_id": a["review_id"], "rerank_id": a["rerank_id"],
        "context_id": a["context_id"], "decision_id": a["decision_id"], "candidate_id": a["candidate_id"],
        "metric_name": a["metric_name"], "observed_value": a["observed_value"], "baseline_value": a.get("baseline_value"),
        "unit": a["unit"], "measurement_window_days": a["measurement_window_days"],
        "measurement_source": a["measurement_source"], "observed_at": a["observed_at"], "reported_by": a["reported_by"],
        "idempotency_key": a["idempotency_key"], "confidence": a["confidence"], "attribution": a["attribution"],
        "received_at": now,
    })


def _prepare_experiment(a: Mapping[str, Any], principal: Principal, store: RecordStore, now: str) -> _Prepared:
    tenant = _common(a, "experiment", "experiment_version", EXPERIMENT_VERSION)
    expected = _digest(EXPERIMENT_VERSION, tenant, _text(a, "review_id"), _text(a, "idempotency_key"))
    _require(a.get("experiment_id") == expected, "experiment_id does not match its idempotency inputs")
    _require(a.get("created_by") == principal.actor_id, "created_by must equal the authenticated actor")
    _require(a.get("status") == "DRAFT" and a.get("data_policy") == "AGGREGATE_METRICS_ONLY_NO_PII", "experiment must be a DRAFT aggregate-only brief")
    activation = a.get("activation")
    _require(
        isinstance(activation, Mapping) and all(activation.get(k) is False for k in ("external_action_permitted", "audience_export_permitted", "spend_permitted")),
        "experiment must not permit external action, audience export, or spend",
    )
    review = _approved_review(store, a["review_id"], tenant)
    _require(review.get("selected_candidate_id") == a.get("candidate_id"), "experiment candidate must match the approved review")
    return _Prepared(EXPERIMENTS, "experiment_id", {
        **{k: a[k] for k in (
            "experiment_id", "tenant_id", "review_id", "rerank_id", "context_id", "decision_id", "candidate_id",
            "campaign_name", "channel", "business_objective", "primary_metric", "control_definition",
            "treatment_definition", "comparison_method", "target_lift_pct", "planned_start_at", "planned_end_at",
            "created_by", "idempotency_key", "status", "data_policy",
        )},
        "received_at": now,
    })


def _prepare_measurement(a: Mapping[str, Any], principal: Principal, store: RecordStore, now: str) -> _Prepared:
    tenant = _common(a, "measurement", "measurement_version", MEASUREMENT_VERSION)
    expected = _digest(MEASUREMENT_VERSION, tenant, _text(a, "experiment_id"), _text(a, "idempotency_key"))
    _require(a.get("measurement_id") == expected, "measurement_id does not match its idempotency inputs")
    _require(a.get("reported_by") == principal.actor_id, "reported_by must equal the authenticated actor")
    _require(a.get("data_policy") == "AGGREGATE_METRICS_ONLY_NO_PII", "measurement must be aggregate-only")
    experiment = _referenced(store, EXPERIMENTS, a["experiment_id"], tenant, "experiment")
    for key in ("review_id", "candidate_id", "comparison_method", "primary_metric"):
        _require(experiment.get(key) == a.get(key), f"measurement {key} must match its experiment")
    arms = {}
    for name in ("control", "treatment"):
        arm = a.get(name)
        _require(isinstance(arm, Mapping) and set(arm) == ARM_KEYS, f"{name} must contain only aggregate arm metrics")
        for key in ("impressions", "conversions"):
            _require(isinstance(arm[key], int) and not isinstance(arm[key], bool) and arm[key] >= 0, f"{name}.{key} must be a non-negative integer")
        for key in ("value", "spend"):
            _require(isinstance(arm[key], (int, float)) and not isinstance(arm[key], bool) and arm[key] >= 0, f"{name}.{key} must be non-negative")
        _require(arm["impressions"] > 0 and arm["conversions"] <= arm["impressions"], f"{name} impressions and conversions are inconsistent")
        arms[name] = arm
    control, treatment = arms["control"], arms["treatment"]
    c_rate, t_rate = round(control["conversions"] / control["impressions"], 8), round(treatment["conversions"] / treatment["impressions"], 8)
    _require(control["conversion_rate"] == c_rate and treatment["conversion_rate"] == t_rate, "conversion rates do not match the counts")
    lift = round(100 * (t_rate - c_rate) / c_rate, 2) if c_rate else None
    _require(a.get("observed_conversion_rate_lift_pct") == lift, "observed lift does not match the counts")
    adequate = min(control["impressions"], treatment["impressions"]) >= 1000 and min(control["conversions"], treatment["conversions"]) >= 25
    target = float(experiment["target_lift_pct"])
    result = "INSUFFICIENT_DATA" if not adequate else ("POSITIVE" if lift is not None and lift >= target else "NEGATIVE" if lift is not None and lift < 0 else "INCONCLUSIVE")
    _require(a.get("result") == result, "result does not match the v1 quality gate")
    feedback = a.get("ranking_feedback")
    _require(isinstance(feedback, Mapping) and feedback.get("eligible_for_offline_reranking") is (adequate and lift is not None), "feedback eligibility does not match the v1 quality gate")
    attribution = "OBSERVATIONAL_ONLY" if a["comparison_method"] == "PRE_POST" else "COMPARATIVE_OBSERVED"
    _require(a.get("attribution") == attribution, "attribution does not match the comparison method")
    return _Prepared(MEASUREMENTS, "measurement_id", {
        "measurement_id": a["measurement_id"], "tenant_id": tenant, "experiment_id": a["experiment_id"],
        "review_id": a["review_id"], "candidate_id": a["candidate_id"], "comparison_method": a["comparison_method"],
        "primary_metric": a["primary_metric"],
        "control_impressions": control["impressions"], "control_conversions": control["conversions"],
        "control_value": float(control["value"]), "control_spend": float(control["spend"]),
        "treatment_impressions": treatment["impressions"], "treatment_conversions": treatment["conversions"],
        "treatment_value": float(treatment["value"]), "treatment_spend": float(treatment["spend"]),
        "observed_conversion_rate_lift_pct": lift, "result": result, "confidence": a["confidence"],
        "measurement_window_days": a["measurement_window_days"], "measurement_source": a["measurement_source"],
        "reported_by": a["reported_by"], "observed_at": a["observed_at"], "idempotency_key": a["idempotency_key"],
        "feedback_eligible": bool(feedback["eligible_for_offline_reranking"]), "attribution": a["attribution"],
        "data_policy": a["data_policy"], "received_at": now,
    })


PREPARERS: dict[str, Callable[[Mapping[str, Any], Principal, RecordStore, str], _Prepared]] = {
    "review": _prepare_review,
    "outcome": _prepare_outcome,
    "experiment": _prepare_experiment,
    "measurement": _prepare_measurement,
}


def append_record(
    kind: str,
    artifact: Mapping[str, Any],
    *,
    token: str | None,
    authenticator: PrincipalAuthenticator,
    store: RecordStore,
    dry_run: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Validate and append one artifact. Returns ``{"status": APPENDED|DUPLICATE|VALID}``."""
    principal = authenticator.authenticate(token)
    if kind not in PREPARERS:
        raise ValueError(f"kind must be one of: {', '.join(sorted(PREPARERS))}")
    _require(isinstance(artifact, Mapping), "artifact must be a JSON object")
    principal.authorize(str(artifact.get("tenant_id", "")))
    try:
        prepared = PREPARERS[kind](artifact, principal, store, clock().isoformat())
    except KeyError as error:
        raise ValueError(f"artifact is missing required field {error.args[0]}") from error
    record_id = str(prepared.row[prepared.id_column])
    existing = store.get(prepared.table, record_id)
    if existing is not None:
        if not _same_content(existing, prepared.row):
            raise ConflictError("idempotency key was already used for different content")
        return {"status": "DUPLICATE", "kind": kind, "record_id": record_id, "table": prepared.table}
    if dry_run:
        return {"status": "VALID", "kind": kind, "record_id": record_id, "table": prepared.table}
    store.insert_if_absent(prepared.table, prepared.id_column, prepared.row)
    stored = store.get(prepared.table, record_id)  # a concurrent writer with different content must not pass silently
    if stored is not None and not _same_content(stored, prepared.row):
        raise ConflictError("idempotency key was concurrently used for different content")
    return {"status": "APPENDED", "kind": kind, "record_id": record_id, "table": prepared.table}


def _normalize(key: str, value: Any) -> Any:
    """Compare timestamps by instant and numbers by value so stores may return their own types."""
    if key in TIMESTAMP_COLUMNS and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _same_content(stored: Mapping[str, Any], written: Mapping[str, Any]) -> bool:
    """True when every column we write matches the stored row.

    Only the written columns are compared (a store may add columns of its own),
    and ``received_at`` is excluded because the writer assigns it per attempt.
    """
    return all(
        key in stored and _normalize(key, stored[key]) == _normalize(key, value)
        for key, value in written.items()
        if key != "received_at"
    )
