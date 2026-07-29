from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.admin.models import ApiMetric, utcnow


def record_metric(
    db: Session,
    *,
    route_name: str,
    method: str,
    status_code: int,
    latency_ms: float,
    generation_mode: str = "",
    retrieval_backend: str = "",
    safety_fallback: bool = False,
) -> None:
    db.add(
        ApiMetric(
            route_name=route_name[:120],
            method=method[:12],
            status_code=status_code,
            latency_ms=latency_ms,
            generation_mode=generation_mode or None,
            retrieval_backend=retrieval_backend or None,
            safety_fallback=safety_fallback,
        )
    )
    db.commit()


def prune_metrics(db: Session, retention_days: int = 30) -> int:
    cutoff = utcnow() - timedelta(days=max(1, retention_days))
    result = db.execute(delete(ApiMetric).where(ApiMetric.created_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)


def metrics_summary(db: Session, hours: int = 24) -> Dict[str, Any]:
    cutoff = utcnow() - timedelta(hours=max(1, min(hours, 24 * 30)))
    rows = db.scalars(select(ApiMetric).where(ApiMetric.created_at >= cutoff)).all()
    latencies = sorted(row.latency_ms for row in rows)

    def percentile(values: List[float], p: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, math.ceil(len(values) * p) - 1))
        return round(values[index], 2)

    by_route: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "errors": 0, "latencies": []})
    for row in rows:
        item = by_route[row.route_name]
        item["count"] += 1
        item["errors"] += int(row.status_code >= 400)
        item["latencies"].append(row.latency_ms)
    routes = []
    for route, item in sorted(by_route.items(), key=lambda pair: pair[1]["count"], reverse=True):
        routes.append(
            {
                "route": route,
                "count": item["count"],
                "error_count": item["errors"],
                "p95_ms": percentile(sorted(item["latencies"]), 0.95),
            }
        )
    return {
        "window_hours": hours,
        "request_count": len(rows),
        "error_count": sum(1 for row in rows if row.status_code >= 400),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "safety_fallback_count": sum(1 for row in rows if row.safety_fallback),
        "generation_modes": dict(Counter(row.generation_mode for row in rows if row.generation_mode)),
        "retrieval_backends": dict(Counter(row.retrieval_backend for row in rows if row.retrieval_backend)),
        "routes": routes,
        "privacy_note": "仅保存路由、状态、延迟和运行模式；不保存测量输入、用户画像或对话正文。",
    }
