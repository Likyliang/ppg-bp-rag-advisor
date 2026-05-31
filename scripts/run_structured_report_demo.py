from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

from app.agents.workflow import generate_report, preview_rules
from app.services.config_loader import resolve_project_path


DEFAULT_MINIAPP_PAYLOAD: Dict[str, Any] = {
    "module": "CHS-BloodPressure",
    "SBP": 146,
    "DBP": 92,
    "HR": 82,
    "quality_score": 0.86,
    "quality": "good",
    "conf": 0.72,
    "duration": 30,
    "sensor_source": "camera_finger",
    "model_version": "miniapp-bp-v1.0-demo",
    "age": 46,
    "sex": "male",
    "diabetes": False,
    "kidney_disease": False,
    "cvd_history": False,
    "pregnancy": False,
    "antihypertensive_medication": False,
    "symptoms": {
        "chest_pain": False,
        "shortness_of_breath": False,
        "numbness_or_weakness": False,
        "vision_change": False,
        "speech_difficulty": False,
        "severe_headache": False,
    },
    "locale": "zh-CN",
    "guideline_region": "CN",
    "user_question": "这个小程序估算结果需要注意什么？",
}


def _read_payload(input_path: str = None) -> Dict[str, Any]:
    if not input_path:
        return dict(DEFAULT_MINIAPP_PAYLOAD)
    if input_path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(resolve_project_path(input_path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a demo report from mini-app style structured PPG BP data.")
    parser.add_argument("--input", help="JSON payload path. Use '-' to read JSON from stdin. Defaults to an embedded demo payload.")
    parser.add_argument("--output-dir", default="outputs/structured_report_demo")
    parser.add_argument("--prefix", default=None, help="Output filename prefix. Defaults to timestamped structured_report.")
    args = parser.parse_args()

    payload = _read_payload(args.input)
    rules = preview_rules(payload)
    report = generate_report(payload)

    out_dir = resolve_project_path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or f"structured_report_{int(time.time())}"
    json_path = out_dir / f"{prefix}.json"
    markdown_path = out_dir / f"{prefix}.md"
    rules_path = out_dir / f"{prefix}.rules.json"

    json_path.write_text(json.dumps(report.model_dump(by_alias=True), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(report.markdown_report, encoding="utf-8")
    rules_path.write_text(json.dumps(rules.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "input_mode": "default_demo" if not args.input else "json_input",
                "estimated_bp_category": report.risk_assessment.estimated_bp_category,
                "risk_level": report.risk_assessment.risk_level,
                "urgency_level": report.risk_assessment.urgency_level,
                "emergency": report.safety_alert.emergency,
                "evidence_count": len(report.retrieved_evidence),
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "rules_path": str(rules_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
