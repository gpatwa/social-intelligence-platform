"""Independent receipt attester for the canonical opportunity score."""

from __future__ import annotations

from hashlib import sha256
import inspect
from typing import Any, Mapping

from social_intelligence.decisioning import opportunity_score


def attest(receipt: Mapping[str, Any]) -> bool:
    inputs = receipt.get("inputs")
    if not isinstance(inputs, Mapping):
        return False
    expected_priority, expected_confidence = opportunity_score(
        inputs.get("signal_score"),
        inputs.get("evidence_count"),
        inputs.get("product_fit"),
        inputs.get("commercial_fit"),
        inputs.get("risk_penalty", 0.0),
    )
    implementation_sha = sha256(inspect.getsource(opportunity_score).encode("utf-8")).hexdigest()
    return (
        receipt.get("priority_score") == expected_priority
        and receipt.get("confidence_score") == expected_confidence
        and receipt.get("implementation_sha256") == implementation_sha
    )
