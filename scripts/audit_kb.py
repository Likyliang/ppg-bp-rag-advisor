from __future__ import annotations

import json

from app.services.config_loader import resolve_project_path
from app.services.kb_audit import audit_knowledge_base


def main() -> None:
    result = audit_knowledge_base()
    out_path = resolve_project_path("knowledge_base/processed/kb_audit_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
