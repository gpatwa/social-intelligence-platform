"""Idempotent, append-only loader for pilot topic labels.

Labels are the gold set the pilot topic rules are scored on, so the loader is
strict about three things: who labelled (``labeller_id``), whether that was a
human or a model (``label_source``, always explicit, never defaulted), and that a
reload never silently changes a stored label. A label is keyed by tenant,
platform, post and labeller, so a second labeller can label the same post.

Only identifiers and the label are stored. Titles, authors, URLs and view counts
in the source CSV are read for nothing and never persisted.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping, Sequence

from .record_append import PILOT_LABELS, ConflictError, RecordStore
from .record_append import _same_content as same_content

LABEL_VERSION = "pilot-label-v1"

# The pilot taxonomy plus the two labels the review process also uses:
# ``off_topic`` (not about the pilot subject) and ``cost``/``design_patterns``,
# which are not ranked in v1 but must stay labelable so held-out data can show
# whether they deserve to be added.
TOPIC_LABELS = frozenset({
    "framework", "evals", "reliability", "mcp", "governance_security",
    "build_vs_buy", "cost", "design_patterns", "other", "off_topic",
})
OFF_TOPIC = "off_topic"
FITS = frozenset({"high", "medium", "low"})
LABEL_SOURCES = frozenset({"human", "model"})
PLATFORMS = frozenset({"youtube", "x"})

TENANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
LABELLER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")  # opaque id, not an email
POST_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.:-]{0,127}")  # YouTube video ids may start with - or _
NOTE_LIMIT = 300
REQUIRED_COLUMNS = ("post_id", "topic_label", "audience_fit")


class LabelFileError(ValueError):
    """The CSV or its options cannot be loaded; nothing was written."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems[:8]) + (f" (+{len(self.problems) - 8} more)" if len(self.problems) > 8 else ""))


@dataclass(frozen=True)
class PilotLabel:
    label_id: str
    tenant_id: str
    platform: str
    post_id: str
    labeller_id: str
    label_source: str
    topic_label: str
    on_topic: bool
    audience_fit: str
    note: str | None
    labelled_at: str

    def to_row(self) -> dict[str, Any]:
        return {
            "label_id": self.label_id, "tenant_id": self.tenant_id, "platform": self.platform,
            "post_id": self.post_id, "labeller_id": self.labeller_id, "label_source": self.label_source,
            "topic_label": self.topic_label, "on_topic": self.on_topic, "audience_fit": self.audience_fit,
            "note": self.note, "labelled_at": self.labelled_at,
        }


def label_id(tenant_id: str, platform: str, post_id: str, labeller_id: str) -> str:
    return sha256("|".join((LABEL_VERSION, tenant_id, platform, post_id, labeller_id)).encode("utf-8")).hexdigest()


def parse_labels(
    text: str,
    *,
    tenant_id: str,
    platform: str,
    labeller_id: str,
    label_source: str,
    labelled_on: date,
) -> list[PilotLabel]:
    """Validate the options and every row; raise ``LabelFileError`` listing all problems."""
    problems: list[str] = []
    if not TENANT.fullmatch(tenant_id):
        problems.append("tenant_id must be a simple identifier")
    if platform not in PLATFORMS:
        problems.append(f"platform must be one of: {', '.join(sorted(PLATFORMS))}")
    if not LABELLER.fullmatch(labeller_id) or "@" in labeller_id:
        problems.append("labeller_id must be an opaque identifier, not an email address")
    if label_source not in LABEL_SOURCES:
        problems.append(f"label_source must be one of: {', '.join(sorted(LABEL_SOURCES))}")
    if labelled_on > datetime.now(timezone.utc).date():
        problems.append("labelled_on cannot be in the future")
    if problems:
        raise LabelFileError(problems)

    reader = csv.DictReader(io.StringIO(text))
    # The labelled sample files head the label column "topic_label (a|b|c)" before labelling.
    fieldnames = [(name or "").split(" (")[0].strip() for name in (reader.fieldnames or [])]
    reader.fieldnames = fieldnames
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise LabelFileError([f"missing column(s): {', '.join(missing)}"])

    labelled_at = datetime(labelled_on.year, labelled_on.month, labelled_on.day, tzinfo=timezone.utc).isoformat()
    labels: list[PilotLabel] = []
    seen: dict[str, int] = {}
    for line, row in enumerate(reader, start=2):
        post_id = (row.get("post_id") or "").strip()
        topic = (row.get("topic_label") or "").strip()
        fit = (row.get("audience_fit") or "").strip().lower()
        note = (row.get("note") or "").strip() or None
        where = f"line {line}"
        if not POST_ID.fullmatch(post_id):
            problems.append(f"{where}: post_id is missing or malformed")
            continue
        if post_id in seen:
            problems.append(f"{where}: post_id {post_id} repeats line {seen[post_id]}")
            continue
        seen[post_id] = line
        if topic not in TOPIC_LABELS:
            problems.append(f"{where}: topic_label {topic!r} is not in the label vocabulary")
        if fit not in FITS:
            problems.append(f"{where}: audience_fit {fit!r} must be high, medium or low")
        if note is not None and len(note) > NOTE_LIMIT:
            problems.append(f"{where}: note is longer than {NOTE_LIMIT} characters")
        if topic in TOPIC_LABELS and fit in FITS:
            labels.append(PilotLabel(
                label_id=label_id(tenant_id, platform, post_id, labeller_id), tenant_id=tenant_id,
                platform=platform, post_id=post_id, labeller_id=labeller_id, label_source=label_source,
                topic_label=topic, on_topic=topic != OFF_TOPIC, audience_fit=fit, note=note, labelled_at=labelled_at,
            ))
    if not labels and not problems:
        problems.append("the file contains no labelled rows")
    if problems:
        raise LabelFileError(problems)
    return labels


@dataclass
class LoadResult:
    inserted: int = 0
    duplicates: int = 0
    dry_run: bool = False
    table: str = PILOT_LABELS
    label_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "inserted": self.inserted, "duplicates": self.duplicates, "dry_run": self.dry_run}


def load_labels(
    labels: Sequence[PilotLabel],
    store: RecordStore,
    *,
    dry_run: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> LoadResult:
    """Insert labels that are absent, skip identical ones, refuse changed ones.

    Every label is checked before any is written, so a conflict leaves the table
    untouched. ``received_at`` is assigned here and excluded from the comparison,
    which is what makes a reload of the same file change nothing.
    """
    pending: list[PilotLabel] = []
    result = LoadResult(dry_run=dry_run)
    conflicts: list[str] = []
    for label in labels:
        stored = store.get(PILOT_LABELS, label.label_id)
        if stored is None:
            pending.append(label)
        elif same_content(stored, label.to_row()):
            result.duplicates += 1
        else:
            conflicts.append(label.post_id)
    if conflicts:
        shown = ", ".join(conflicts[:5]) + (" ..." if len(conflicts) > 5 else "")
        raise ConflictError(
            f"{len(conflicts)} label(s) already stored with different content (post_id: {shown}); "
            "labels are append-only, so a correction needs a new labeller_id or an explicit migration"
        )
    now = clock().isoformat()
    for label in pending:
        if not dry_run:
            store.insert_if_absent(PILOT_LABELS, "label_id", {**label.to_row(), "received_at": now})
        result.inserted += 1
        result.label_ids.append(label.label_id)
    return result
