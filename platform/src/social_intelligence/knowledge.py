"""Small, deterministic helpers for the repository's OKF v0.2 bundle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable

import yaml


OKF_VERSION = "0.2"
CATALOG_FILENAME = "catalog.json"
RESERVED_MARKDOWN = frozenset({"index.md", "log.md"})
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class OkfDocument:
    path: Path
    metadata: dict[str, Any]
    body: str


def _parse_iso(value: object, field_name: str) -> None:
    if isinstance(value, (date, datetime)):
        return
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date or datetime")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field_name} must be an ISO date or datetime") from error


def load_okf_document(path: Path) -> OkfDocument:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return OkfDocument(path=path, metadata={}, body=text)
    try:
        _, frontmatter, body = text.split("---\n", 2)
    except ValueError as error:
        raise ValueError(f"{path}: malformed YAML frontmatter") from error
    metadata = yaml.safe_load(frontmatter) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return OkfDocument(path=path, metadata=metadata, body=body)


def iter_okf_documents(bundle: Path) -> Iterable[OkfDocument]:
    for path in sorted(bundle.rglob("*.md")):
        yield load_okf_document(path)


def build_catalog(bundle: Path) -> dict[str, Any]:
    concepts: list[dict[str, Any]] = []
    for document in iter_okf_documents(bundle):
        relative = document.path.relative_to(bundle).as_posix()
        if document.path.name in RESERVED_MARKDOWN:
            continue
        metadata = document.metadata
        concepts.append(
            {
                "path": relative,
                "type": metadata.get("type"),
                "title": metadata.get("title", document.path.stem.replace("-", " ").title()),
                "description": metadata.get("description", ""),
                "status": metadata.get("status", "active"),
                "tags": sorted(metadata.get("tags", [])),
            }
        )
    return {
        "okf_version": OKF_VERSION,
        "bundle": bundle.name,
        "concept_count": len(concepts),
        "concepts": concepts,
    }


def render_catalog(bundle: Path) -> str:
    return json.dumps(build_catalog(bundle), indent=2, sort_keys=True) + "\n"


def write_catalog(bundle: Path) -> Path:
    output = bundle / CATALOG_FILENAME
    output.write_text(render_catalog(bundle), encoding="utf-8")
    return output


def validate_okf_bundle(bundle: Path) -> list[str]:
    errors: list[str] = []
    root_index = bundle / "index.md"
    if not root_index.exists():
        errors.append("index.md: root index is required")
        return errors

    try:
        root = load_okf_document(root_index)
    except ValueError as error:
        return [str(error)]
    if str(root.metadata.get("okf_version")) != OKF_VERSION:
        errors.append(f"index.md: okf_version must be {OKF_VERSION}")

    for document in iter_okf_documents(bundle):
        relative = document.path.relative_to(bundle).as_posix()
        metadata = document.metadata
        if document.path.name not in RESERVED_MARKDOWN:
            if not metadata.get("type"):
                errors.append(f"{relative}: type is required")
            if not metadata.get("title"):
                errors.append(f"{relative}: title is required by this bundle")

        sources = metadata.get("sources", [])
        if not isinstance(sources, list):
            errors.append(f"{relative}: sources must be a list")
        else:
            for index, source in enumerate(sources):
                if not isinstance(source, dict) or not source.get("resource"):
                    errors.append(f"{relative}: sources[{index}].resource is required")

        generated = metadata.get("generated")
        if generated is not None:
            if not isinstance(generated, dict) or not generated.get("by") or not generated.get("at"):
                errors.append(f"{relative}: generated requires by and at")
            else:
                try:
                    _parse_iso(generated["at"], f"{relative}: generated.at")
                except ValueError as error:
                    errors.append(str(error))

        verified = metadata.get("verified", [])
        if not isinstance(verified, list):
            errors.append(f"{relative}: verified must be a list")
        else:
            for index, verification in enumerate(verified):
                if not isinstance(verification, dict) or not verification.get("by") or not verification.get("at"):
                    errors.append(f"{relative}: verified[{index}] requires by and at")
                    continue
                try:
                    _parse_iso(verification["at"], f"{relative}: verified[{index}].at")
                except ValueError as error:
                    errors.append(str(error))

        if "stale_after" in metadata:
            try:
                _parse_iso(metadata["stale_after"], f"{relative}: stale_after")
            except ValueError as error:
                errors.append(str(error))

        if metadata.get("type") == "Attested Computation":
            for field_name in ("runtime", "parameters", "computation", "executor", "attester"):
                if not metadata.get(field_name):
                    errors.append(f"{relative}: {field_name} is required for Attested Computation")
            executor = metadata.get("executor", {})
            attester = metadata.get("attester", {})
            if isinstance(executor, dict):
                if not executor.get("resource") or not executor.get("receipt"):
                    errors.append(f"{relative}: executor requires resource and receipt")
            if isinstance(attester, dict) and not attester.get("resource"):
                errors.append(f"{relative}: attester.resource is required")

        for target in MARKDOWN_LINK.findall(document.body):
            clean_target = target.split("#", 1)[0].strip()
            if not clean_target or "://" in clean_target or clean_target.startswith("mailto:"):
                continue
            resolved = (
                bundle / clean_target.lstrip("/")
                if clean_target.startswith("/")
                else document.path.parent / clean_target
            ).resolve()
            if not resolved.exists():
                errors.append(f"{relative}: broken local link {target}")

    catalog = bundle / CATALOG_FILENAME
    if not catalog.exists():
        errors.append(f"{CATALOG_FILENAME}: generated catalog is required")
    elif catalog.read_text(encoding="utf-8") != render_catalog(bundle):
        errors.append(f"{CATALOG_FILENAME}: out of date; run build_okf_bundle.py")
    return errors
