import importlib.util
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import json
from pathlib import Path
import tempfile
import unittest

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from social_intelligence.contracts import SocialEventEnvelope
from social_intelligence.decisioning import opportunity_score
from social_intelligence.knowledge import (
    OKF_VERSION,
    build_catalog,
    load_okf_document,
    render_catalog,
    validate_okf_bundle,
)


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = PLATFORM_ROOT / "knowledge" / "social-intelligence"
CONTRACTS = PLATFORM_ROOT / "contracts"


class ContractRegistryTests(unittest.TestCase):
    def test_json_schemas_are_versioned_and_machine_readable(self):
        schemas = sorted((CONTRACTS / "json-schema").glob("*.json"))
        self.assertGreaterEqual(len(schemas), 7)
        for path in schemas:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
            self.assertIn("$id", schema)
            self.assertIn("title", schema)
            self.assertEqual(schema["type"], "object")
            Draft202012Validator.check_schema(schema)

    def test_openapi_contract_exposes_only_governed_mvp_operations(self):
        path = CONTRACTS / "openapi" / "social-intelligence-api-v1.yaml"
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(contract["openapi"], "3.1.0")
        self.assertEqual(
            set(contract["paths"]),
            {
                "/health",
                "/opportunities",
                "/opportunities/{opportunity_id}",
                "/recommendations",
                "/agent-stack/recommendations",
                "/evidence/ranked",
                "/internal-pilots/plan",
                "/recommendation-contexts/compile",
                "/recommendation-reranks",
                "/recommendation-reviews",
                "/recommendation-outcomes",
            },
        )
        self.assertNotIn("approveRecommendation", str(contract))

    def test_cloud_event_adapter_conforms_to_published_schema(self):
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in (CONTRACTS / "json-schema").glob("*.json")
        }
        registry = Registry()
        for schema in schemas.values():
            registry = registry.with_resource(
                schema["$id"], Resource.from_contents(schema)
            )
        validator = Draft202012Validator(
            schemas["cloud-event-social-event-v1.json"], registry=registry
        )
        observed_at = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        event = SocialEventEnvelope.create(
            tenant_id="demo",
            source_id="youtube-sf",
            platform="youtube",
            event_type="social.post.observed",
            source_object_id="video-1",
            occurred_at=observed_at,
            collected_at=observed_at,
            payload={"title": "Launch"},
        )
        validator.validate(event.to_cloudevent())


class OkfBundleTests(unittest.TestCase):
    def test_bundle_is_valid_and_catalog_is_deterministic(self):
        self.assertEqual(validate_okf_bundle(BUNDLE), [])
        catalog = json.loads((BUNDLE / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["okf_version"], OKF_VERSION)
        self.assertEqual(catalog, build_catalog(BUNDLE))
        self.assertEqual(
            (BUNDLE / "catalog.json").read_text(encoding="utf-8"),
            render_catalog(BUNDLE),
        )

    def test_validator_rejects_a_concept_without_type(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "index.md").write_text(
                '---\nokf_version: "0.2"\n---\n# Test\n', encoding="utf-8"
            )
            (bundle / "concept.md").write_text(
                "---\ntitle: Missing type\n---\n# Concept\n", encoding="utf-8"
            )
            (bundle / "catalog.json").write_text(
                render_catalog(bundle), encoding="utf-8"
            )
            errors = validate_okf_bundle(bundle)
            self.assertTrue(any("type is required" in error for error in errors))

    def test_computation_document_points_to_canonical_runtime(self):
        document = load_okf_document(
            BUNDLE / "computations" / "opportunity-score.md"
        )
        self.assertEqual(document.metadata["type"], "Attested Computation")
        self.assertEqual(
            document.metadata["executor"]["resource"],
            "../../../src/social_intelligence/decisioning.py",
        )
        self.assertIn("opportunity_score", document.body)

    def test_attester_recomputes_receipt_without_an_llm(self):
        path = BUNDLE / "references" / "attesters" / "opportunity_score.py"
        spec = importlib.util.spec_from_file_location("okf_opportunity_attester", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        inputs = {
            "signal_score": 80,
            "evidence_count": 20,
            "product_fit": 0.8,
            "commercial_fit": 0.7,
            "risk_penalty": 5,
        }
        priority, confidence = opportunity_score(**inputs)
        receipt = {
            "inputs": inputs,
            "priority_score": priority,
            "confidence_score": confidence,
            "implementation_sha256": sha256(
                inspect.getsource(opportunity_score).encode("utf-8")
            ).hexdigest(),
        }
        self.assertTrue(module.attest(receipt))
        receipt["priority_score"] += 1
        self.assertFalse(module.attest(receipt))


if __name__ == "__main__":
    unittest.main()
