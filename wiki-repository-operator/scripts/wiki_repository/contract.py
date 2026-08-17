from __future__ import annotations

import re
from dataclasses import dataclass

from .actions import ACTIONS


_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_PATH_PARAMETER = re.compile(r"\{[^{}]+\}")


@dataclass(frozen=True)
class ManualOperation:
    command: str
    method: str
    path: str
    scope: str
    risk: str
    body_required: bool = False


# These API operations use dedicated handlers because they stream, transfer files,
# validate secrets, or participate in bootstrap/discovery rather than the generic
# JSON action handler.
MANUAL_OPERATIONS = (
    ManualOperation("doctor", "GET", "/health", "", "read"),
    ManualOperation("auth.status", "GET", "/auth/me", "", "read"),
    ManualOperation("repo.download", "GET", "/repositories/{repositoryId}/archive", "wiki:read", "read"),
    ManualOperation("repo.preview-dir", "POST", "/repositories/{repositoryId}/imports/preview", "wiki:write", "medium", body_required=True),
    ManualOperation("knowledge.ask-stream", "POST", "/projects/{projectId}/ask/stream", "wiki:read", "read", body_required=True),
    ManualOperation("gitlab.validate", "POST", "/integrations/gitlab/settings/validate", "integrations:manage", "medium", body_required=True),
    ManualOperation("gitlab.apply", "PUT", "/integrations/gitlab/settings", "integrations:manage", "critical", body_required=True),
    ManualOperation("jira.validate", "POST", "/integrations/jira/token/validate", "integrations:manage", "medium", body_required=True),
    ManualOperation("jira.apply", "PUT", "/integrations/jira/token", "integrations:manage", "critical", body_required=True),
    ManualOperation("jira.clear", "DELETE", "/integrations/jira/token", "integrations:manage", "critical"),
)


# Web-password login is deliberately outside the Agent boundary. The operator uses
# personal access tokens and must never collect a user's Webmanager password.
EXCLUDED_OPERATIONS = {
    ("POST", "/auth/login"): "interactive web login is replaced by personal access tokens",
}


def audit_openapi(specification):
    api_operations = _read_openapi_operations(specification)
    supported_operations = _supported_operations()
    excluded_operations = {
        _operation_key(method, path): {"method": method, "path": path, "reason": reason}
        for (method, path), reason in EXCLUDED_OPERATIONS.items()
    }

    api_keys = set(api_operations)
    supported_keys = set(supported_operations)
    excluded_keys = set(excluded_operations)
    unsupported_keys = api_keys - supported_keys - excluded_keys
    unavailable_keys = supported_keys - api_keys
    metadata_mismatches = []

    for key in sorted(api_keys & supported_keys):
        api = api_operations[key]
        local = supported_operations[key]
        for field, api_field in (
            ("risk", "x-risk-level"),
            ("scope", "x-required-scope"),
            ("body_required", "request-body-required"),
        ):
            default = False if field == "body_required" else ""
            local_value = local[field] if local[field] is not None else default
            api_value = api.get(api_field)
            if api_value is None:
                api_value = default
            if local_value != api_value:
                metadata_mismatches.append({
                    "command": local["command"],
                    "method": api["method"],
                    "path": api["path"],
                    "field": field,
                    "operator": local_value,
                    "api": api_value,
                })

    ignored = [
        excluded_operations[key]
        for key in sorted(api_keys & excluded_keys)
    ]
    unsupported = [
        {"method": api_operations[key]["method"], "path": api_operations[key]["path"]}
        for key in sorted(unsupported_keys)
    ]
    unavailable = [
        {
            "command": supported_operations[key]["command"],
            "method": supported_operations[key]["method"],
            "path": supported_operations[key]["path"],
        }
        for key in sorted(unavailable_keys)
    ]
    covered_count = len(api_keys & supported_keys)
    managed_count = len(api_keys - excluded_keys)
    compatible = not unsupported and not unavailable and not metadata_mismatches

    return {
        "compatible": compatible,
        "api_operation_count": len(api_keys),
        "managed_api_operation_count": managed_count,
        "covered_api_operation_count": covered_count,
        "operator_command_count": len(supported_keys),
        "excluded_operations": ignored,
        "unsupported_operations": unsupported,
        "unavailable_commands": unavailable,
        "metadata_mismatches": metadata_mismatches,
    }


def _supported_operations():
    operations = {}
    for action in ACTIONS:
        _add_supported_operation(
            operations,
            command=f"{action.group}.{action.name}",
            method=action.method,
            path=action.path,
            scope=action.scope,
            risk=action.risk,
            body_required=action.body_required,
        )
    for operation in MANUAL_OPERATIONS:
        _add_supported_operation(
            operations,
            command=operation.command,
            method=operation.method,
            path=operation.path,
            scope=operation.scope,
            risk=operation.risk,
            body_required=operation.body_required,
        )
    return operations


def _add_supported_operation(operations, *, command, method, path, scope, risk, body_required):
    key = _operation_key(method, path)
    if key in operations:
        raise ValueError(f"duplicate operator route: {method} {path}")
    operations[key] = {
        "command": command,
        "method": method,
        "path": path,
        "scope": scope,
        "risk": risk,
        "body_required": body_required,
    }


def _read_openapi_operations(specification):
    paths = specification.get("paths") if isinstance(specification, dict) else None
    if not isinstance(paths, dict):
        return {}
    operations = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            normalized_method = str(method).upper()
            if normalized_method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            key = _operation_key(normalized_method, path)
            operations[key] = {
                "method": normalized_method,
                "path": path,
                "x-risk-level": operation.get("x-risk-level"),
                "x-required-scope": operation.get("x-required-scope"),
                "request-body-required": bool(
                    isinstance(operation.get("requestBody"), dict)
                    and operation["requestBody"].get("required")
                ),
            }
    return operations


def _operation_key(method, path):
    return str(method).upper(), _PATH_PARAMETER.sub("{}", str(path))
