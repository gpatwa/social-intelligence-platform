import contextlib
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from social_intelligence.pilot_labels import (
    LabelFileError,
    PilotLabel,
    label_id,
    load_labels,
    parse_labels,
)
from social_intelligence.pilot_labels_cli import main as cli_main
from social_intelligence.record_append import (
    PILOT_LABELS,
    ConflictError,
    DatabricksSqlRecordStore,
    InMemoryRecordStore,
)

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
DAY = date(2026, 11, 4)

CSV = """post_id,author,title,views,url,topic_label,audience_fit,note
vid-001,Some Channel,Title one,0,https://example.test/1,evals,high,Checks agent evals
vid-002,Other Channel,"Title, two",0,https://example.test/2,off_topic,low,
vid-003,Third,Title three,0,https://example.test/3,governance_security,medium,
"""


def parse(text=CSV, **overrides):
    options = dict(tenant_id="demo", platform="youtube", labeller_id="owner_01", label_source="human", labelled_on=DAY)
    options.update(overrides)
    return parse_labels(text, **options)


class ParseTests(unittest.TestCase):
    def test_parses_rows_and_stores_no_post_text(self):
        labels = parse()
        self.assertEqual([l.post_id for l in labels], ["vid-001", "vid-002", "vid-003"])
        self.assertEqual([l.on_topic for l in labels], [True, False, True])
        self.assertEqual(labels[0].note, "Checks agent evals")
        self.assertIsNone(labels[1].note)
        self.assertEqual(labels[0].labelled_at, "2026-11-04T00:00:00+00:00")
        row = labels[0].to_row()
        for forbidden in ("title", "author", "url", "views"):
            self.assertNotIn(forbidden, row)

    def test_label_id_is_deterministic_and_includes_tenant_and_labeller(self):
        first = label_id("demo", "youtube", "vid-001", "owner_01")
        self.assertEqual(first, label_id("demo", "youtube", "vid-001", "owner_01"))
        self.assertNotEqual(first, label_id("other-tenant", "youtube", "vid-001", "owner_01"))
        self.assertNotEqual(first, label_id("demo", "youtube", "vid-001", "second_01"))

    def test_youtube_ids_that_start_with_a_dash_or_underscore_are_accepted(self):
        text = "post_id,topic_label,audience_fit\n-abc_123,evals,high\n_xyz-789,mcp,low\n"
        self.assertEqual([l.post_id for l in parse(text)], ["-abc_123", "_xyz-789"])

    def test_unlabelled_header_from_the_blank_template_is_accepted(self):
        text = "post_id,topic_label (framework|evals|other),audience_fit\nvid-001,evals,high\n"
        self.assertEqual(len(parse(text)), 1)

    def test_every_problem_is_reported_and_nothing_is_returned(self):
        text = (
            "post_id,topic_label,audience_fit,note\n"
            "vid-001,evals,high,\n"
            "vid-001,evals,high,\n"        # duplicate post
            "vid-002,,high,\n"             # unlabelled
            "vid-003,bogus,high,\n"        # not in vocabulary
            "vid-004,evals,great,\n"       # bad fit
            f"vid-005,evals,low,{'x' * 301}\n"
        )
        with self.assertRaises(LabelFileError) as raised:
            parse(text)
        joined = " | ".join(raised.exception.problems)
        for expected in ("repeats line 2", "'bogus'", "'great'", "longer than 300", "line 4"):
            self.assertIn(expected, joined)

    def test_options_are_validated(self):
        for overrides in (
            {"label_source": "robot"}, {"platform": "github"}, {"labeller_id": "me@example.com"},
            {"tenant_id": "bad tenant"}, {"labelled_on": date(2099, 1, 1)},
        ):
            with self.assertRaises(LabelFileError, msg=str(overrides)):
                parse(**overrides)

    def test_missing_columns_and_empty_files_are_rejected(self):
        with self.assertRaises(LabelFileError):
            parse("post_id,topic_label\nvid-001,evals\n")
        with self.assertRaises(LabelFileError):
            parse("post_id,topic_label,audience_fit\n")


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryRecordStore()

    def load(self, labels=None, **kwargs):
        return load_labels(labels or parse(), self.store, clock=lambda: NOW, **kwargs)

    def test_reloading_the_same_file_changes_nothing(self):
        first = self.load()
        self.assertEqual((first.inserted, first.duplicates), (3, 0))
        before = json.dumps(self.store.tables, sort_keys=True, default=str)
        later = load_labels(parse(), self.store, clock=lambda: datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assertEqual((later.inserted, later.duplicates), (0, 3))
        self.assertEqual(json.dumps(self.store.tables, sort_keys=True, default=str), before)

    def test_changed_label_is_refused_and_writes_nothing(self):
        self.load()
        changed = CSV.replace("vid-001,Some Channel,Title one,0,https://example.test/1,evals,high",
                              "vid-001,Some Channel,Title one,0,https://example.test/1,framework,high")
        extra = changed + "vid-004,X,New,0,https://example.test/4,mcp,high,\n"
        snapshot = json.dumps(self.store.tables, sort_keys=True, default=str)
        with self.assertRaisesRegex(ConflictError, "vid-001"):
            self.load(parse(extra))
        self.assertEqual(json.dumps(self.store.tables, sort_keys=True, default=str), snapshot)
        self.assertEqual(len(self.store.tables[PILOT_LABELS]), 3)  # the new vid-004 was not inserted either

    def test_dry_run_counts_but_writes_nothing(self):
        result = self.load(dry_run=True)
        self.assertEqual((result.inserted, result.duplicates, result.dry_run), (3, 0, True))
        self.assertEqual(self.store.tables, {})

    def test_a_second_labeller_can_label_the_same_posts(self):
        self.load()
        second = self.load(parse(labeller_id="second_01", label_source="human"))
        self.assertEqual(second.inserted, 3)
        self.assertEqual(len(self.store.tables[PILOT_LABELS]), 6)

    def test_model_and_human_labels_stay_distinguishable(self):
        self.load(parse(label_source="model", labeller_id="model_run_01"))
        sources = {row["label_source"] for row in self.store.tables[PILOT_LABELS].values()}
        self.assertEqual(sources, {"model"})

    def test_other_tenants_labels_do_not_collide(self):
        self.load()
        other = self.load(parse(tenant_id="tenant-b"))
        self.assertEqual(other.inserted, 3)

    def test_received_at_is_set_by_the_writer(self):
        self.load()
        self.assertTrue(all(row["received_at"] == NOW.isoformat() for row in self.store.tables[PILOT_LABELS].values()))


class FakeCursor:
    def __init__(self, log):
        self.log, self.description = log, None

    def execute(self, statement, params=None):
        self.log.append((statement, params))

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.log = []

    def cursor(self):
        return FakeCursor(self.log)


class StoreAndCliTests(unittest.TestCase):
    def test_databricks_store_writes_the_label_table_with_parameters_only(self):
        connection = FakeConnection()
        store = DatabricksSqlRecordStore(connection, catalog="dev", schema="social_intelligence_dev")
        load_labels(parse(), store, clock=lambda: NOW)
        merges = [statement for statement, _ in connection.log if statement.startswith("MERGE")]
        self.assertEqual(len(merges), 3)
        self.assertIn("`dev`.`social_intelligence_dev`.`reviewed_pilot_topic`", merges[0])
        self.assertIn("CAST(:labelled_at AS TIMESTAMP)", merges[0])
        self.assertNotIn("vid-001", merges[0])  # values are bound parameters, never inlined

    def run_cli(self, *extra):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.csv"
            path.write_text(CSV, encoding="utf-8")
            argv = [str(path), "--tenant", "demo", "--platform", "youtube", "--labeller", "owner_01",
                    "--labelled-on", "2026-11-04", *extra]
            with mock.patch("social_intelligence.pilot_labels_cli.DatabricksSqlRecordStore.from_environment",
                            return_value=InMemoryRecordStore()), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return cli_main(argv)

    def test_cli_requires_an_explicit_label_source(self):
        with self.assertRaises(SystemExit):
            self.run_cli()
        self.assertEqual(self.run_cli("--label-source", "human", "--dry-run"), 0)

    def test_cli_rejects_a_bad_file_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("post_id,topic_label,audience_fit\nvid-001,bogus,high\n", encoding="utf-8")
            argv = [str(path), "--tenant", "demo", "--platform", "youtube", "--labeller", "owner_01",
                    "--label-source", "human", "--labelled-on", "2026-11-04"]
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli_main(argv), 2)


class TableDefinitionTests(unittest.TestCase):
    """Static guards: Spark is unavailable in unit tests."""

    def test_table_is_tenant_scoped_append_only_and_keyed_by_labeller(self):
        source = (NOTEBOOKS / "00_initialize_platform.py").read_text(encoding="utf-8")
        start = source.index("`reviewed_pilot_topic` (")
        ddl = source[start: source.index(")\n    USING DELTA", start)]
        for column in ("label_id STRING NOT NULL", "tenant_id STRING NOT NULL", "platform STRING NOT NULL",
                       "post_id STRING NOT NULL", "labeller_id STRING NOT NULL", "label_source STRING NOT NULL",
                       "on_topic BOOLEAN NOT NULL", "labelled_at TIMESTAMP NOT NULL"):
            self.assertIn(column, ddl)
        for stored_text in ("title", "author", "url", "content_text"):
            self.assertNotRegex(ddl, rf"\b{stored_text}\b")

    def test_cli_is_registered(self):
        pyproject = (NOTEBOOKS.parent / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('social-intelligence-pilot-labels = "social_intelligence.pilot_labels_cli:main"', pyproject)


if __name__ == "__main__":
    unittest.main()
