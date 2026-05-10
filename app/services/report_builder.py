from __future__ import annotations

from app.schemas.report import HealthReport


def report_to_json(report: HealthReport) -> dict:
    return report.model_dump(by_alias=True)


def report_to_markdown(report: HealthReport) -> str:
    return report.markdown_report
