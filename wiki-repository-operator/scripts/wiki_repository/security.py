from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
import time
from pathlib import Path

from .errors import ConfirmationRequired, OperatorError

_TOKEN_PATTERN = re.compile(r"wkp_[A-Za-z0-9_-]{8,}")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_PLAN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_SAFE_TOKEN_KEYS = {
    "token_configured",
    "token_expires_at",
    "token_id",
    "token_prefix",
    "token_replaced",
    "token_scopes",
    "personal_access_token_id",
    "personal_access_token_scopes",
}
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "private_token",
    "access_token",
    "refresh_token",
    "api_key",
    "token_encrypted",
    "webhook_secret",
}


def is_sensitive_key(value) -> bool:
    key = str(value or "").strip().lower()
    if key in _SAFE_TOKEN_KEYS:
        return False
    return key in _SENSITIVE_KEYS or key == "token" or key.endswith("_token") or key.endswith("_secret")


def redact(value):
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _JWT_PATTERN.sub("<jwt-redacted>", _TOKEN_PATTERN.sub("wkp_<redacted>", value))
    return value


def contains_sensitive_fields(value) -> bool:
    if isinstance(value, dict):
        return any(is_sensitive_key(key) or contains_sensitive_fields(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_sensitive_fields(item) for item in value)
    return False


class SafetyGate:
    def __init__(self, store, ttl_seconds=600):
        self.store = store
        self.ttl_seconds = ttl_seconds

    def authorize(
        self,
        *,
        operation,
        endpoint,
        risk,
        scope,
        method,
        path,
        query,
        body,
        display_body=None,
        confirmation_id=None,
        confirmation_text=None,
        required_text=None,
    ):
        if risk == "read":
            return
        fingerprint = operation_fingerprint(
            operation=operation,
            endpoint=endpoint,
            method=method,
            path=path,
            query=query,
            body=body,
        )
        expected_text = required_text or (
            f"CONFIRM {operation}" if risk == "critical" else None
        )
        if not confirmation_id:
            plan = self._create_plan(
                operation=operation,
                endpoint=endpoint,
                risk=risk,
                scope=scope,
                method=method,
                path=path,
                query=query,
                body=body if display_body is None else display_body,
                fingerprint=fingerprint,
                confirmation_text=expected_text,
            )
            raise ConfirmationRequired(plan)

        plan = self._read_plan(confirmation_id)
        now = int(time.time())
        if plan.get("expires_at_epoch", 0) < now:
            self._delete_plan(confirmation_id)
            raise OperatorError("确认计划已过期，请重新生成", code="confirmation_expired", exit_code=3)
        if not hmac.compare_digest(str(plan.get("fingerprint", "")), fingerprint):
            raise OperatorError("命令或参数与确认计划不一致，请重新生成", code="confirmation_mismatch", exit_code=3)
        stored_text = plan.get("confirmation_text")
        if stored_text and not hmac.compare_digest(str(confirmation_text or ""), str(stored_text)):
            raise OperatorError(
                "高风险确认短语不匹配",
                code="confirmation_text_mismatch",
                exit_code=3,
                details={"expected_confirmation_text": stored_text},
            )
        self._delete_plan(confirmation_id)

    def _create_plan(self, **values):
        self._ensure_plans_dir()
        self._cleanup_expired()
        now = int(time.time())
        plan_id = secrets.token_urlsafe(18)
        plan = {
            "id": plan_id,
            "operation": values["operation"],
            "target_server": values["endpoint"],
            "risk": values["risk"],
            "required_scope": values["scope"],
            "request": {
                "method": values["method"],
                "path": values["path"],
                "query": redact(values["query"]),
                "body": redact(values["body"]),
            },
            "created_at_epoch": now,
            "expires_at_epoch": now + self.ttl_seconds,
            "fingerprint": values["fingerprint"],
            "confirmation_text": values["confirmation_text"],
        }
        self._atomic_write(self.store.plans_dir / f"{plan_id}.json", plan)
        public_plan = {key: value for key, value in plan.items() if key != "fingerprint"}
        public_plan["next_step"] = f"请向用户展示本计划；确认后原命令增加 --confirm {plan_id}"
        if values["confirmation_text"]:
            public_plan["next_step"] += " 并增加 --confirm-text 后跟精确确认短语"
        return public_plan

    def _read_plan(self, plan_id):
        path = self._plan_path(plan_id)
        try:
            info = path.lstat()
        except FileNotFoundError as error:
            raise OperatorError("确认计划不存在或已使用", code="confirmation_not_found", exit_code=3) from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise OperatorError("确认计划文件不安全", code="unsafe_confirmation_plan", exit_code=3)
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise OperatorError("确认计划文件权限不安全", code="unsafe_confirmation_plan", exit_code=3)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise OperatorError("确认计划文件损坏", code="invalid_confirmation_plan", exit_code=3) from error

    def _delete_plan(self, plan_id):
        self._plan_path(plan_id).unlink(missing_ok=True)

    def _plan_path(self, plan_id) -> Path:
        if not _PLAN_ID_PATTERN.fullmatch(str(plan_id or "")):
            raise OperatorError("确认计划编号无效", code="invalid_confirmation_id", exit_code=3)
        return self.store.plans_dir / f"{plan_id}.json"

    def _ensure_plans_dir(self):
        self.store.ensure()
        path = self.store.plans_dir
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
                raise OperatorError("确认计划目录不安全", code="unsafe_confirmation_directory")
            os.chmod(path, 0o700)
        else:
            path.mkdir(mode=0o700)

    def _cleanup_expired(self):
        now = int(time.time())
        for path in self.store.plans_dir.glob("*.json"):
            if not _PLAN_ID_PATTERN.fullmatch(path.stem):
                continue
            try:
                plan = json.loads(path.read_text(encoding="utf-8"))
                if plan.get("expires_at_epoch", 0) < now:
                    path.unlink(missing_ok=True)
            except (OSError, json.JSONDecodeError):
                continue

    def _atomic_write(self, path, value):
        descriptor, temporary_name = tempfile.mkstemp(prefix=".plan.", dir=self.store.plans_dir)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def operation_fingerprint(*, operation, endpoint, method, path, query, body):
    canonical = {
        "operation": operation,
        "endpoint": endpoint,
        "method": method.upper(),
        "path": path,
        "query": _fingerprint_value(query),
        "body": _fingerprint_value(body),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _fingerprint_value(value):
    if isinstance(value, dict):
        return {
            str(key): "<sensitive>" if is_sensitive_key(key) else _fingerprint_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_fingerprint_value(item) for item in value]
    if isinstance(value, tuple):
        return [_fingerprint_value(item) for item in value]
    return value
