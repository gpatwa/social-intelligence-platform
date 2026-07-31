import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.connectors.checkpoint import (
    ConnectorCheckpoint,
    JsonCheckpointStore,
)
from social_intelligence.connectors.quota import (
    QuotaController,
    QuotaExceeded,
    QuotaLedger,
    QuotaPolicy,
)
from social_intelligence.connectors.retry import RetryPolicy


class CheckpointTests(unittest.TestCase):
    def test_missing_checkpoint_starts_empty_and_save_is_replayable(self):
        now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(Path(directory) / "youtube.json")
            self.assertEqual(store.load().cursors, {})

            checkpoint = ConnectorCheckpoint(
                cursors={"rule-a": "2026-07-31T12:00:00Z"},
                quota={"quota_day": "2026-07-31", "search_calls": 1},
                metadata={"events": 3},
                updated_at=now,
            )
            store.save(checkpoint)
            loaded = store.load()

            self.assertEqual(loaded.cursors, checkpoint.cursors)
            self.assertEqual(loaded.quota["search_calls"], 1)
            self.assertEqual(loaded.metadata["events"], 3)
            self.assertEqual(loaded.updated_at, now)

    def test_unknown_checkpoint_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported checkpoint schema"):
            ConnectorCheckpoint.from_dict(
                {"schema_version": 99, "updated_at": "2026-07-31T12:00:00Z"}
            )


class QuotaTests(unittest.TestCase):
    def test_reserve_is_enforced_before_the_request(self):
        observed = []
        policy = QuotaPolicy(
            search_daily_limit=3,
            search_reserve=1,
            core_daily_limit=10,
            core_reserve=1,
        )
        controller = QuotaController(
            policy,
            QuotaLedger(quota_day="2026-07-31", search_calls=1),
            on_change=lambda ledger: observed.append(ledger.to_mapping()),
        )
        controller.consume("search", 1, "search.list")
        with self.assertRaisesRegex(QuotaExceeded, "Quota reserve reached"):
            controller.consume("search", 1, "search.list")
        self.assertEqual(observed[-1]["search_calls"], 2)

    def test_ledger_resets_on_the_provider_quota_day(self):
        now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        ledger = QuotaLedger.from_mapping(
            {
                "quota_day": "2026-07-30",
                "search_calls": 90,
                "core_units": 8_000,
            },
            now,
            "America/Los_Angeles",
        )
        self.assertEqual(ledger.search_calls, 0)
        self.assertEqual(ledger.core_units, 0)


class RetryTests(unittest.TestCase):
    def test_transient_operation_uses_bounded_exponential_backoff(self):
        attempts = []
        delays = []

        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise RuntimeError("transient")
            return "ok"

        result = RetryPolicy(
            max_attempts=3,
            base_delay_seconds=1,
            max_delay_seconds=10,
            jitter_ratio=0,
        ).run(
            operation,
            lambda error: str(error) == "transient",
            sleeper=delays.append,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, [1, 2, 3])
        self.assertEqual(delays, [1, 2])

    def test_permanent_operation_is_not_retried(self):
        attempts = []

        def operation():
            attempts.append(1)
            raise ValueError("permanent")

        with self.assertRaisesRegex(ValueError, "permanent"):
            RetryPolicy(max_attempts=4).run(operation, lambda error: False)
        self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
