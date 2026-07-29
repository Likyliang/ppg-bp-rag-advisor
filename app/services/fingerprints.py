from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from app.services.config_loader import resolve_project_path


def combine_fingerprints(values: dict) -> str:
    normalized = {str(key): str(value or "") for key, value in sorted(values.items())}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    file_path = resolve_project_path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint_paths(paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for path_string in sorted(set(str(path) for path in paths)):
        path = resolve_project_path(path_string)
        digest.update(path_string.encode("utf-8"))
        if path.is_file():
            digest.update(sha256_file(path_string).encode("ascii"))
        elif path.is_dir():
            for child in sorted(p for p in path.rglob("*") if p.is_file()):
                relative = str(child.relative_to(path))
                digest.update(relative.encode("utf-8"))
                child_digest = hashlib.sha256(child.read_bytes()).hexdigest()
                digest.update(child_digest.encode("ascii"))
        else:
            digest.update(b"missing")
    return digest.hexdigest()


def catalog_fingerprint() -> str:
    return fingerprint_paths(
        [
            "knowledge_base/sources/source_catalog.yaml",
            "knowledge_base/sources/source_catalog_extra.yaml",
        ]
    )


def config_fingerprint() -> str:
    return fingerprint_paths(
        [
            "config/settings.yaml",
            "config/screening_rules.yaml",
            "config/safety_terms.yaml",
            "config/bp_thresholds.yaml",
            "config/advisor_questions.yaml",
            "config/field_mapping.yaml",
        ]
    )
