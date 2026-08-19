import json
import tempfile
import unittest
from pathlib import Path
from social_intelligence.mcp_provider import SqlProjectionProvider, write_projection_snapshots

class ProviderTests(unittest.TestCase):
    def test_sql_identifiers_are_validated_and_snapshot_export_is_atomic(self):
        queries = []
        provider = SqlProjectionProvider(lambda query: (queries.append(query) or [{"tenant_id":"acme"}]), catalog="dev", schema="analytics")
        self.assertEqual(provider.metrics()[0]["tenant_id"], "acme")
        self.assertIn("SELECT * FROM `dev`.`analytics`", queries[0])
        with tempfile.TemporaryDirectory() as directory:
            write_projection_snapshots(provider, Path(directory))
            self.assertEqual(json.loads((Path(directory)/"metrics.json").read_text())["items"], [{"tenant_id":"acme"}])
    def test_invalid_sql_identifier_is_rejected(self):
        with self.assertRaises(ValueError): SqlProjectionProvider(lambda _: [], catalog="dev;drop", schema="analytics")

if __name__ == "__main__": unittest.main()
