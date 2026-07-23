from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import portalocker
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import ConfigDraft, ConfigRevision, utcnow
from app.admin.audit import redact_sensitive_text
from app.schemas.conversation import ConversationProfile
from app.services.config_loader import clear_config_caches, resolve_project_path
from app.services.source_catalog import ALLOWED_USES


CONFIG_SPECS: Dict[str, Dict[str, Any]] = {
    "settings": {
        "path": "config/settings.yaml",
        "risk": "normal",
        "read_by": "报告模式、检索器、向量后端与评估运行时",
    },
    "screening_rules": {
        "path": "config/screening_rules.yaml",
        "risk": "high",
        "read_by": "筛查建议引擎与生成器",
    },
    "safety_terms": {
        "path": "config/safety_terms.yaml",
        "risk": "high",
        "read_by": "安全审查、随访、规则引擎与生成器",
    },
    "bp_thresholds": {
        "path": "config/bp_thresholds.yaml",
        "risk": "high",
        "read_by": "信号质量、血压参考范围与急症规则",
    },
    "advisor_questions": {
        "path": "config/advisor_questions.yaml",
        "risk": "high",
        "read_by": "随访渐进式问题选择",
    },
    "field_mapping": {
        "path": "config/field_mapping.yaml",
        "risk": "normal",
        "read_by": "输入字段别名归一化",
    },
}

_REGRESSION_TESTS = {
    "settings": ["tests/test_retriever_quality.py", "tests/test_report_fixtures.py"],
    "screening_rules": ["tests/test_screening.py", "tests/test_safety.py", "tests/test_report_fixtures.py"],
    "safety_terms": ["tests/test_safety.py", "tests/test_advisor.py", "tests/test_report_fixtures.py"],
    "bp_thresholds": ["tests/test_rule_engine.py", "tests/test_safety.py", "tests/test_report_fixtures.py"],
    "advisor_questions": ["tests/test_advisor.py"],
    "field_mapping": ["tests/test_normalizer.py", "tests/test_schema.py"],
}

_FIXED_PREVIEW_CASES = [
    {"case_id": "reference_normal", "estimated_sbp": 118, "estimated_dbp": 76, "signal_quality_score": 0.9},
    {"case_id": "reference_high", "estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.9},
    {
        "case_id": "emergency_symptom",
        "estimated_sbp": 185,
        "estimated_dbp": 122,
        "signal_quality_score": 0.9,
        "symptoms": {"chest_pain": True},
    },
]


class ConfigConflictError(RuntimeError):
    pass


class ConfigValidationError(RuntimeError):
    pass


_PROTECTED_CONFIG_KEY = re.compile(
    r"(?i)(?:^|[_-])(?:api[_-]?key|secret|token|password|cookie|authorization|credential)(?:$|[_-])"
)


def _credential_issues(value: Any, path: str = "config") -> List[str]:
    issues: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if _PROTECTED_CONFIG_KEY.search(str(key)):
                issues.append(f"{child} 禁止保存凭证字段")
            issues.extend(_credential_issues(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_credential_issues(item, f"{path}[{index}]"))
    elif isinstance(value, str) and redact_sensitive_text(value) != value:
        issues.append(f"{path} 禁止保存凭证值")
    return issues


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path_for(key: str) -> Path:
    if key not in CONFIG_SPECS:
        raise KeyError(key)
    return resolve_project_path(CONFIG_SPECS[key]["path"])


def _current_text(key: str) -> str:
    path = _path_for(key)
    return path.read_text(encoding="utf-8") if path.exists() else "{}\n"


def current_revision(key: str) -> str:
    return _sha256(_current_text(key))


def _dump(content: Dict[str, Any]) -> str:
    return yaml.safe_dump(content, allow_unicode=True, sort_keys=False, width=4096)


def list_configs() -> List[Dict[str, Any]]:
    result = []
    for key, spec in CONFIG_SPECS.items():
        text = _current_text(key)
        try:
            content = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            content = {}
        result.append(
            {
                "key": key,
                "path": spec["path"],
                "risk_level": spec["risk"],
                "read_by": spec["read_by"],
                "revision": _sha256(text),
                "content": content,
            }
        )
    return result


def create_config_draft(
    db: Session,
    key: str,
    content: Dict[str, Any],
    user_id: str,
    reason: Optional[str] = None,
) -> ConfigDraft:
    if key not in CONFIG_SPECS:
        raise KeyError(key)
    credential_issues = _credential_issues(content)
    if credential_issues:
        raise ConfigValidationError("；".join(credential_issues))
    text = _dump(content)
    before = _current_text(key).splitlines(keepends=True)
    after = text.splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(before, after, fromfile=CONFIG_SPECS[key]["path"], tofile=f"draft/{key}")
    )
    draft = ConfigDraft(
        config_key=key,
        base_revision=current_revision(key),
        content_text=text,
        risk_level=CONFIG_SPECS[key]["risk"],
        status="draft",
        diff_text=diff,
        reason=reason,
        created_by=user_id,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def _validate_regex_list(content: Dict[str, Any], key: str, errors: List[str]) -> None:
    values = content.get(key)
    if not isinstance(values, list) or not values:
        errors.append(f"{key} 必须是非空列表")
        return
    for index, value in enumerate(values):
        try:
            re.compile(str(value))
        except re.error as exc:
            errors.append(f"{key}[{index}] 正则无效: {exc}")


def _structural_validation(key: str, content: Dict[str, Any]) -> List[str]:
    errors: List[str] = _credential_issues(content)
    if not isinstance(content, dict) or not content:
        return ["配置必须是非空对象"]

    def number(value: Any, label: str) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            errors.append(f"{label} 必须为数字")
            return None

    if key == "settings":
        retrieval = content.get("retrieval") or {}
        for field in ("top_k", "keyword_weight", "vector_weight", "per_source_cap"):
            if field not in retrieval:
                errors.append(f"retrieval.{field} 缺失")
        top_k = number(retrieval.get("top_k"), "retrieval.top_k")
        if top_k is not None and top_k <= 0:
            errors.append("retrieval.top_k 必须大于 0")
        keyword_weight = number(retrieval.get("keyword_weight"), "retrieval.keyword_weight")
        vector_weight = number(retrieval.get("vector_weight"), "retrieval.vector_weight")
        if (keyword_weight is not None and keyword_weight < 0) or (vector_weight is not None and vector_weight < 0):
            errors.append("检索融合权重不能为负数")
        safety = content.get("safety") or {}
        for invariant in ("require_ppg_limitation", "require_disclaimer", "block_diagnosis", "block_medication_changes"):
            if safety.get(invariant) is not True:
                errors.append(f"核心安全开关 safety.{invariant} 不能关闭")
    elif key == "safety_terms":
        for field in ("diagnostic_patterns", "device_overclaim_patterns", "medication_change_patterns", "screening_overreach_patterns"):
            _validate_regex_list(content, field, errors)
        required = set(content.get("required_disclaimer_terms") or [])
        invariant_terms = {"仅供个人健康趋势参考", "不能替代医生诊断", "不能替代规范血压测量"}
        if not invariant_terms.issubset(required):
            errors.append("免责声明核心术语不得删除")
        for field in ("screening_required_hedge_cues", "screening_required_referral_cues", "emergency_false_reassurance_patterns"):
            if not content.get(field):
                errors.append(f"{field} 不能为空")
    elif key == "bp_thresholds":
        emergency = content.get("emergency") or {}
        if not isinstance(emergency.get("sbp_gte"), (int, float)) or not isinstance(emergency.get("dbp_gte"), (int, float)):
            errors.append("急症 SBP/DBP 阈值必须为数字")
        if not emergency.get("symptoms"):
            errors.append("急症症状列表不能为空")
        quality = content.get("quality") or {}
        for field, value in quality.items():
            if field.endswith(("_score_lt", "_artifact_gte", "_coverage_lt", "confidence_lt")):
                parsed = number(value, f"quality.{field}")
                if parsed is not None and not 0 <= parsed <= 1:
                    errors.append(f"quality.{field} 必须位于 0..1")
        poor_signal = number(quality.get("poor_signal_score_lt"), "quality.poor_signal_score_lt")
        fair_signal = number(quality.get("fair_signal_score_lt"), "quality.fair_signal_score_lt")
        if poor_signal is not None and fair_signal is not None and poor_signal >= fair_signal:
            errors.append("quality.poor_signal_score_lt 必须小于 fair_signal_score_lt")
        moderate_motion = number(quality.get("moderate_motion_artifact_gte"), "quality.moderate_motion_artifact_gte")
        high_motion = number(quality.get("high_motion_artifact_gte"), "quality.high_motion_artifact_gte")
        if moderate_motion is not None and high_motion is not None and moderate_motion >= high_motion:
            errors.append("中度运动伪影阈值必须小于高度运动伪影阈值")
        aha = content.get("AHA") or {}
        try:
            normal = aha["normal"]
            elevated = aha["elevated"]
            stage1 = aha["stage_1_reference_range"]
            stage2 = aha["stage_2_reference_range"]
            severe = aha["severe_range"]
            sbp_edges = [normal["sbp_lt"], elevated["sbp_range"][0], elevated["sbp_range"][1], stage1["sbp_range"][0], stage1["sbp_range"][1], stage2["sbp_gte"], severe["sbp_gte"]]
            if not all(float(left) <= float(right) for left, right in zip(sbp_edges, sbp_edges[1:])):
                errors.append("AHA 收缩压分层阈值顺序冲突")
            dbp_edges = [normal["dbp_lt"], stage1["dbp_range"][0], stage1["dbp_range"][1], stage2["dbp_gte"], severe["dbp_gte"]]
            if not all(float(left) <= float(right) for left, right in zip(dbp_edges, dbp_edges[1:])):
                errors.append("AHA 舒张压分层阈值顺序冲突")
            if float(emergency["sbp_gte"]) != float(severe["sbp_gte"]) or float(emergency["dbp_gte"]) != float(severe["dbp_gte"]):
                errors.append("急症阈值必须与 severe_range 保持一致")
        except (KeyError, TypeError, ValueError, IndexError):
            errors.append("AHA 血压分层结构不完整")
        cn = content.get("CN") or {}
        try:
            home, office = cn["home_bp_high_reference"], cn["office_bp_high_reference"]
            if float(home["sbp_gte"]) > float(office["sbp_gte"]) or float(home["dbp_gte"]) > float(office["dbp_gte"]):
                errors.append("中国家庭血压参考阈值不能高于诊室参考阈值")
        except (KeyError, TypeError, ValueError):
            errors.append("CN 血压参考结构不完整")
    elif key == "screening_rules":
        if content.get("enabled") is not True:
            errors.append("筛查规则总开关不能通过后台关闭")
        if not content.get("required_hedge_cues") or not content.get("required_referral_cues"):
            errors.append("筛查建议必须保留对冲措辞和就医指引")
        ids = []
        for index, item in enumerate(content.get("conditions") or []):
            if not isinstance(item, dict):
                errors.append(f"conditions[{index}] 必须是对象")
                continue
            ids.append(item.get("id"))
            if item.get("confidence") not in {"low", "moderate"}:
                errors.append(f"{item.get('id')} 置信度只能为 low/moderate")
            if not item.get("screening_action") or not item.get("rationale_template"):
                errors.append(f"{item.get('id')} 缺少解释或排查行动")
            # A condition may use its own id as an internal routing intent;
            # every other value must come from the governed source vocabulary.
            invalid_uses = set(item.get("allowed_uses") or []) - (set(ALLOWED_USES) | {str(item.get("id") or "")})
            if invalid_uses:
                errors.append(f"{item.get('id')} 使用非法 allowed_uses: {sorted(invalid_uses)}")
            if not item.get("triggers") or not item.get("requires"):
                errors.append(f"{item.get('id')} 缺少 triggers/requires 安全门控")
        if not ids or len(ids) != len(set(ids)):
            errors.append("筛查规则 id 不能为空或重复")
    elif key == "advisor_questions":
        ids = []
        profile_fields = set(ConversationProfile.model_fields)
        for index, item in enumerate(content.get("questions") or []):
            if not isinstance(item, dict):
                errors.append(f"questions[{index}] 必须是对象")
                continue
            ids.append(item.get("id"))
            if not item.get("text") or not item.get("why") or not item.get("options"):
                errors.append(f"{item.get('id')} 必须包含 text/why/options")
            for option in item.get("options") or []:
                unknown = set((option.get("profile") or {}).keys()) - profile_fields
                if unknown:
                    errors.append(f"{item.get('id')} 使用未知画像字段: {sorted(unknown)}")
        if not ids or len(ids) != len(set(ids)):
            errors.append("随访问题 id 不能为空或重复")
    elif key == "field_mapping":
        alias_owners: Dict[str, str] = {}
        collisions = set()
        for field, spec in content.items():
            aliases = spec.get("aliases") if isinstance(spec, dict) else None
            if not isinstance(aliases, list) or not aliases:
                errors.append(f"{field}.aliases 必须是非空列表")
            else:
                for alias in aliases:
                    normalized = str(alias).lower()
                    previous = alias_owners.setdefault(normalized, str(field))
                    if previous != str(field):
                        collisions.add(normalized)
        if collisions:
            errors.append(f"字段别名跨字段冲突: {sorted(collisions)[:10]}")
    return errors


def _regression_gate(key: str, content: Dict[str, Any]) -> Dict[str, Any]:
    env = os.environ.copy()
    # Candidate configuration checks run in a disposable workspace and must not
    # inherit credentials from the service process.  The gate only needs normal
    # process/runtime variables plus the explicit deterministic settings below.
    sensitive_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE", "AUTHORIZATION")
    for name in list(env):
        if any(marker in name.upper() for marker in sensitive_markers):
            env.pop(name, None)
    env["APP_ENV"] = "quality_gate"
    env["APP_CONFIG_OVERRIDES_JSON"] = json.dumps({CONFIG_SPECS[key]["path"]: content}, ensure_ascii=False)
    env["REPORT_MODE"] = "template_only"
    env["LLM_PROVIDER"] = "mock"
    env["RETRIEVAL_EMBEDDING_BACKEND"] = "hashing"
    env["ADMIN_AUTH_DISABLED"] = "1"
    preview = _fixed_case_preview(env)
    if not preview.get("passed"):
        return {"passed": False, "fixture_preview": preview, "error_code": "fixture_preview_failed"}
    command = [sys.executable, "-m", "pytest", "-q", *_REGRESSION_TESTS[key]]
    try:
        result = subprocess.run(
            command,
            cwd=resolve_project_path("."),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "error_code": "timeout", "output_tail": "候选配置回归测试超时"}
    output = result.stdout[-6000:].replace(str(resolve_project_path(".")), "<project>")
    response = {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "output_tail": output,
        "fixture_preview": preview,
    }
    if response["passed"] and CONFIG_SPECS[key]["risk"] == "high":
        try:
            strict = _isolated_strict_quality_gate(env)
        except Exception:
            strict = {"passed": False, "error_code": "isolation_error", "output_tail": "无法创建隔离质量门环境"}
        response["strict_quality_gate"] = strict
        response["passed"] = bool(strict.get("passed"))
    return response


def _fixed_case_preview(env: Dict[str, str]) -> Dict[str, Any]:
    script = (
        "import json; "
        "from app.agents.workflow import preview_rules; "
        f"cases={_FIXED_PREVIEW_CASES!r}; "
        "rows=[]; "
        "[(lambda r, c: rows.append({'case_id': c['case_id'], "
        "'quality_usable': r.quality.is_usable, 'category': r.estimated_bp_category, "
        "'emergency': r.emergency, 'retrieval_intents': r.retrieval_intents}))(preview_rules(c), c) for c in cases]; "
        "print(json.dumps(rows, ensure_ascii=False))"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=resolve_project_path("."),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "error_code": "timeout"}
    if result.returncode != 0:
        return {"passed": False, "error_code": f"exit_{result.returncode}"}
    try:
        rows = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError, TypeError):
        return {"passed": False, "error_code": "invalid_output"}
    return {"passed": True, "cases": rows}


def _isolated_strict_quality_gate(env: Dict[str, str]) -> Dict[str, Any]:
    """Run the full stop gate in a credential-free temporary project copy."""

    project = resolve_project_path(".")
    excluded_names = {
        ".git", ".venv", ".env", ".pytest_cache", "__pycache__", "node_modules",
        "var", "outputs", "vector_store", "library", "demo_literature",
    }

    def ignore(_directory: str, names: List[str]) -> List[str]:
        return [name for name in names if name in excluded_names or name.endswith((".db", ".sqlite", ".sqlite3", ".pdf"))]

    with tempfile.TemporaryDirectory(prefix="ppg-config-gate-") as temp_dir:
        workspace = Path(temp_dir) / "project"
        shutil.copytree(project, workspace, ignore=ignore)
        try:
            result = subprocess.run(
                [sys.executable, "scripts/run_quality_gate.py", "--strict-stop"],
                cwd=workspace,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "error_code": "timeout", "output_tail": "隔离严格质量门超时"}
    output = result.stdout[-6000:].replace(str(project), "<project>").replace(temp_dir, "<isolated>")
    return {"passed": result.returncode == 0, "returncode": result.returncode, "output_tail": output}


def validate_config_draft(db: Session, draft: ConfigDraft, *, run_regression: bool = True) -> Dict[str, Any]:
    try:
        content = yaml.safe_load(draft.content_text) or {}
    except yaml.YAMLError as exc:
        result = {"passed": False, "errors": [f"YAML 无法解析: {exc}"]}
    else:
        errors = _structural_validation(draft.config_key, content)
        regression = {"passed": True, "skipped": True}
        if not errors and run_regression:
            regression = _regression_gate(draft.config_key, content)
        result = {
            "passed": not errors and bool(regression.get("passed")),
            "errors": errors,
            "regression": regression,
            "validated_revision": draft.base_revision,
        }
    draft.validation_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
    draft.status = "validated" if result.get("passed") else "invalid"
    draft.updated_at = utcnow()
    db.commit()
    return result


def _record_revision(
    db: Session,
    *,
    key: str,
    text: str,
    previous: Optional[str],
    user_id: str,
    reason: str,
    validation: Dict[str, Any],
) -> ConfigRevision:
    revision = _sha256(text)
    existing = db.scalar(
        select(ConfigRevision).where(ConfigRevision.config_key == key, ConfigRevision.revision == revision)
    )
    if existing is not None:
        return existing
    row = ConfigRevision(
        config_key=key,
        revision=revision,
        previous_revision=previous,
        content_text=text,
        published_by=user_id,
        reason=reason,
        validation_json=json.dumps(validation, ensure_ascii=False, sort_keys=True),
    )
    db.add(row)
    db.flush()
    return row


def _atomic_write(key: str, text: str, expected_revision: str) -> None:
    path = _path_for(key)
    lock_path = resolve_project_path(f"var/locks/config-{key}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(str(lock_path), timeout=10):
        current = _current_text(key)
        if _sha256(current) != expected_revision:
            raise ConfigConflictError("配置已被其他操作修改，请刷新后重新创建草稿")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(str(temp_path), str(path))


def publish_config_draft(
    db: Session,
    draft: ConfigDraft,
    *,
    user_id: str,
    reason: str,
    expected_revision: str,
    confirmation: str,
) -> Dict[str, Any]:
    if confirmation != draft.config_key:
        raise ConfigValidationError(f"确认文本必须为 {draft.config_key}")
    if draft.status != "validated":
        raise ConfigValidationError("草稿尚未通过校验")
    validation = json.loads(draft.validation_json or "{}")
    if not validation.get("passed"):
        raise ConfigValidationError("草稿校验未通过")
    if draft.risk_level == "high":
        regression = validation.get("regression") or {}
        strict = regression.get("strict_quality_gate") or {}
        if regression.get("skipped") or not regression.get("passed") or not strict.get("passed"):
            raise ConfigValidationError("高风险配置必须通过隔离回归与严格质量门，不能跳过验证")
    if expected_revision != draft.base_revision:
        raise ConfigConflictError("请求 revision 与草稿基线不一致")
    before = _current_text(draft.config_key)
    before_revision = _sha256(before)
    if before_revision != expected_revision:
        raise ConfigConflictError("当前配置已变化")
    _record_revision(
        db,
        key=draft.config_key,
        text=before,
        previous=None,
        user_id=user_id,
        reason="自动发布前快照",
        validation={"snapshot": True},
    )
    _atomic_write(draft.config_key, draft.content_text, expected_revision)
    new_revision = _sha256(draft.content_text)
    _record_revision(
        db,
        key=draft.config_key,
        text=draft.content_text,
        previous=before_revision,
        user_id=user_id,
        reason=reason,
        validation=validation,
    )
    draft.status = "published"
    draft.reason = reason
    draft.updated_at = utcnow()
    db.commit()
    clear_config_caches()
    return {"config_key": draft.config_key, "revision": new_revision, "previous_revision": before_revision}


def rollback_config_revision(
    db: Session,
    revision_row: ConfigRevision,
    *,
    user_id: str,
    reason: str,
    expected_current_revision: Optional[str] = None,
) -> Dict[str, Any]:
    key = revision_row.config_key
    try:
        target = yaml.safe_load(revision_row.content_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"目标版本 YAML 无法解析: {exc}") from exc
    errors = _structural_validation(key, target)
    if errors:
        raise ConfigValidationError("目标版本不再满足安全约束: " + "; ".join(errors))
    regression: Dict[str, Any] = {"passed": True, "skipped": True}
    if CONFIG_SPECS[key]["risk"] == "high":
        regression = _regression_gate(key, target)
        if not regression.get("passed"):
            raise ConfigValidationError("高风险配置回滚未通过隔离回归与严格质量门")
    before = _current_text(key)
    before_revision = _sha256(before)
    if expected_current_revision is not None and before_revision != expected_current_revision:
        raise ConfigConflictError("配置在回滚任务排队后发生变化，请重新确认目标版本")
    _record_revision(
        db,
        key=key,
        text=before,
        previous=None,
        user_id=user_id,
        reason="自动回滚前快照",
        validation={"snapshot": True},
    )
    _atomic_write(key, revision_row.content_text, before_revision)
    new_revision = _sha256(revision_row.content_text)
    _record_revision(
        db,
        key=key,
        text=revision_row.content_text,
        previous=before_revision,
        user_id=user_id,
        reason=f"回滚: {reason}",
        validation={"rollback_to": revision_row.revision, "regression": regression},
    )
    db.commit()
    clear_config_caches()
    return {"config_key": key, "revision": new_revision, "previous_revision": before_revision}


def draft_dict(draft: ConfigDraft) -> Dict[str, Any]:
    return {
        "id": draft.id,
        "config_key": draft.config_key,
        "base_revision": draft.base_revision,
        "content": yaml.safe_load(draft.content_text) or {},
        "risk_level": draft.risk_level,
        "status": draft.status,
        "validation": json.loads(draft.validation_json or "{}"),
        "diff": draft.diff_text,
        "reason": draft.reason,
        "created_by": draft.created_by,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def revision_dict(row: ConfigRevision) -> Dict[str, Any]:
    return {
        "id": row.id,
        "config_key": row.config_key,
        "revision": row.revision,
        "previous_revision": row.previous_revision,
        "published_by": row.published_by,
        "reason": row.reason,
        "validation": json.loads(row.validation_json or "{}"),
        "created_at": row.created_at.isoformat(),
    }
