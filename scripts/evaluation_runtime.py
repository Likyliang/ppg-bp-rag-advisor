from __future__ import annotations

import argparse
from typing import Optional

from app.services.config_loader import load_yaml_config


MAX_ALLOWED_CONCURRENCY = 5
DEFAULT_CONCURRENCY = 1


def resolve_max_concurrency(requested: Optional[int] = None) -> int:
    """Return a safe experiment concurrency, capped at 5 by project policy."""
    configured = (
        load_yaml_config("config/settings.yaml")
        .get("evaluation", {})
        .get("max_concurrency", DEFAULT_CONCURRENCY)
    )
    value = requested if requested is not None else configured
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_CONCURRENCY
    return max(1, min(value, MAX_ALLOWED_CONCURRENCY))


def add_concurrency_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=None,
        help=f"Maximum parallel experiment workers; capped at {MAX_ALLOWED_CONCURRENCY}.",
    )
