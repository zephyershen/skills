from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

from . import __version__
from .actions import ACTIONS
from .archives import create_directory_zip, extract_zip_safely
from .client import PlatformClient
from .config import (
    DEFAULT_ORIGIN,
    TOKEN_ENV,
    URL_ENV,
    CredentialStore,
    masked_token,
    normalize_server,
    validate_token,
)
from .contract import audit_openapi
from .dependencies import ensure_wiki_skill_once
from .errors import ApiError, ConfirmationRequired, OperatorError
from .security import SafetyGate, contains_sensitive_fields, is_sensitive_key, redact

MAX_INPUT_BYTES = 2 * 1024 * 1024
_PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)\}")
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise OperatorError(message, code="invalid_arguments", exit_code=2)


def build_parser():
    parser = SafeArgumentParser(
        prog="wiki-platform",
        description="安全操作 Wiki Repository 平台的 Agent CLI",
    )
    parser.add_argument("--pretty", action="store_true", help="缩进输出 JSON")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时秒数，默认 30")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    top = parser.add_subparsers(dest="group", required=True)

    doctor = top.add_parser("doctor", help="检查服务、API 契约和令牌")
    doctor.set_defaults(_handler="doctor")

    groups = {}
    for group_name in sorted({action.group for action in ACTIONS}):
        group_parser = top.add_parser(group_name, help=f"{group_name} 操作")
        groups[group_name] = group_parser.add_subparsers(dest="command", required=True)
    for action in ACTIONS:
        command = groups[action.group].add_parser(action.name, help=action.summary)
        command.set_defaults(_handler="action", _action_spec=action)
        add_path_arguments(command, action.path)
        command.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="查询参数，可重复")
        if action.method != "GET":
            add_json_input(command, required=action.body_required)
        if action.response_secret:
            command.add_argument("--save-token", required=True, metavar="PATH", help="把新令牌写入权限 600 的新文件")
        if action.risk != "read":
            add_confirmation(command)

    add_repo_specials(groups["repo"])
    add_knowledge_specials(groups["knowledge"])
    add_gitlab_specials(groups["gitlab"])
    add_jira_specials(groups["jira"])
    add_server_commands(top)
    add_auth_commands(top)
    add_resolve_commands(top)
    add_raw_commands(top)
    return parser


def add_server_commands(top):
    parser = top.add_parser("server", help="查看或更换平台地址")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="显示当前平台地址")
    show.set_defaults(_handler="server_show")
    set_command = commands.add_parser("set", help="验证后保存新地址；只写 IP 时自动使用 4004")
    set_command.add_argument("address")
    set_command.set_defaults(_handler="server_set")
    reset = commands.add_parser("reset", help="恢复默认生产地址")
    reset.set_defaults(_handler="server_reset")


def add_auth_commands(top):
    parser = top.add_parser("auth", help="配置个人访问令牌")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="验证当前令牌")
    status.set_defaults(_handler="auth_status")
    set_token = commands.add_parser("set-token", help="从标准输入验证并保存 wkp_ 令牌")
    set_token.add_argument("--stdin", action="store_true", required=True)
    set_token.set_defaults(_handler="auth_set_token")
    clear = commands.add_parser("clear", help="删除本机保存的令牌")
    clear.set_defaults(_handler="auth_clear")


def add_resolve_commands(top):
    parser = top.add_parser("resolve", help="按名称安全解析平台对象")
    commands = parser.add_subparsers(dest="command", required=True)
    project = commands.add_parser("project", help="解析 Wiki Group")
    project.add_argument("query")
    project.set_defaults(_handler="resolve", _resolve_kind="project")
    repository = commands.add_parser("repository", help="在一个 Group 中解析 Wiki")
    repository.add_argument("query")
    repository.add_argument("--project-id", required=True, type=positive_id)
    repository.set_defaults(_handler="resolve", _resolve_kind="repository")
    person = commands.add_parser("person", help="解析 Wiki 平台人员")
    person.add_argument("query")
    person.set_defaults(_handler="resolve", _resolve_kind="person")


def add_raw_commands(top):
    parser = top.add_parser("raw", help="只读调用未来新增的 API")
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("get", help="仅允许 GET /api 下的相对路径")
    get.add_argument("path")
    get.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    get.set_defaults(_handler="raw_get")


def add_repo_specials(commands):
    preview = commands.add_parser("preview-dir", help="把本地目录打包并上传为变更预览")
    preview.add_argument("--repository-id", required=True, type=positive_id)
    preview.add_argument("--directory", required=True)
    preview.add_argument("--branch")
    add_confirmation(preview)
    preview.set_defaults(_handler="repo_preview")

    download = commands.add_parser("download", help="下载固定提交版本的 Wiki ZIP")
    download.add_argument("--repository-id", required=True, type=positive_id)
    download.add_argument("--revision")
    download.add_argument("--output", required=True)
    download.add_argument("--overwrite", action="store_true")
    add_confirmation(download)
    download.set_defaults(_handler="repo_download")

    extract = commands.add_parser("extract", help="安全解压已下载的 Wiki ZIP 到新目录")
    extract.add_argument("--archive", required=True)
    extract.add_argument("--destination", required=True)
    extract.set_defaults(_handler="repo_extract")


def add_knowledge_specials(commands):
    stream = commands.add_parser("ask-stream", help="以 JSON Lines 输出流式 Wiki 问答事件")
    stream.add_argument("--project-id", required=True, type=positive_id)
    add_json_input(stream, required=True)
    stream.set_defaults(_handler="ask_stream")


def add_gitlab_specials(commands):
    for name, handler, help_text in (
        ("validate", "gitlab_validate", "只验证 GitLab 设置，不保存"),
        ("apply", "gitlab_apply", "验证后保存并热切换 GitLab 设置"),
    ):
        parser = commands.add_parser(name, help=help_text)
        parser.add_argument("--base-url", required=True)
        parser.add_argument("--connect-ip", default="")
        add_secret_source(parser, required=False)
        if name == "apply":
            add_confirmation(parser)
        parser.set_defaults(_handler=handler)


def add_jira_specials(commands):
    validate = commands.add_parser("validate", help="只验证 Jira Token，不保存")
    add_secret_source(validate, required=True)
    validate.set_defaults(_handler="jira_validate")
    apply = commands.add_parser("apply", help="验证后保存 Jira Token")
    add_secret_source(apply, required=True)
    add_confirmation(apply)
    apply.set_defaults(_handler="jira_apply")
    clear = commands.add_parser("clear", help="解除全局 Jira 绑定")
    add_confirmation(clear)
    clear.set_defaults(_handler="jira_clear")


def add_path_arguments(parser, path):
    for name in _PLACEHOLDER.findall(path):
        option = f"--{camel_to_kebab(name)}"
        if name == "kind":
            parser.add_argument(option, required=True, choices=["project", "namespace", "repository"])
        elif name == "changeRequestId" or name == "tokenId":
            parser.add_argument(option, required=True)
        else:
            parser.add_argument(option, required=True, type=positive_id)


def add_json_input(parser, required=False):
    values = parser.add_mutually_exclusive_group(required=required)
    values.add_argument("--json", dest="json_value", metavar="JSON", help="非敏感 JSON 请求体")
    values.add_argument("--json-file", metavar="PATH", help="从文件读取非敏感 JSON 请求体")


def add_secret_source(parser, *, required):
    values = parser.add_mutually_exclusive_group(required=required)
    values.add_argument("--secret-stdin", action="store_true", help="从标准输入读取 Token")
    values.add_argument("--secret-env", metavar="ENV_NAME", help="从指定环境变量读取 Token")
    values.add_argument("--secret-file", metavar="PATH", help="从权限为 600 的文件读取 Token")


def add_confirmation(parser):
    parser.add_argument("--confirm", metavar="PLAN_ID", help="执行已向用户展示并确认的计划")
    parser.add_argument("--confirm-text", metavar="TEXT", help="关键操作需要的精确确认短语")


def run(args, store):
    endpoint, endpoint_source = store.endpoint()
    handler = getattr(args, "_handler", None)
    token = None
    token_source = "missing"
    token_error = None
    try:
        token, token_source = store.token()
    except OperatorError as error:
        token_error = error
        if handler not in {"doctor", "server_show", "server_set", "server_reset", "auth_set_token", "auth_clear"}:
            raise
    client = PlatformClient(endpoint, token, timeout=args.timeout)
    gate = SafetyGate(store)
    if handler == "doctor":
        return "doctor", doctor(client, token_source, token_error=token_error)
    if handler == "server_show":
        return "server.show", {
            "origin": endpoint.origin,
            "api_url": endpoint.api_url,
            "source": endpoint_source,
            "environment_override": URL_ENV if os.environ.get(URL_ENV) else None,
        }
    if handler in {"server_set", "server_reset"}:
        return handle_server(args, store, reset=handler == "server_reset")
    if handler == "auth_status":
        return "auth.status", auth_status(client, token, token_source)
    if handler == "auth_set_token":
        return "auth.set-token", auth_set_token(client, store)
    if handler == "auth_clear":
        removed = store.clear_token()
        return "auth.clear", {
            "stored_token_removed": removed,
            "environment_token_still_active": bool(os.environ.get(TOKEN_ENV)),
        }
    if handler == "resolve":
        return f"resolve.{args._resolve_kind}", resolve_object(client, args)
    if handler == "raw_get":
        return "raw.get", raw_get(client, args)
    if handler == "repo_preview":
        return "repo.preview-dir", repo_preview(client, gate, endpoint, args)
    if handler == "repo_download":
        path = f"/repositories/{args.repository_id}/archive"
        if args.overwrite:
            gate.authorize(
                operation="repo.download-overwrite",
                endpoint=endpoint.origin,
                risk="high",
                scope="wiki:read",
                method="GET",
                path=path,
                query={"revision": args.revision},
                body={"output": str(Path(args.output).expanduser().absolute()), "overwrite": True},
                confirmation_id=args.confirm,
                confirmation_text=args.confirm_text,
            )
        return "repo.download", client.download(
            path,
            args.output,
            query={"revision": args.revision},
            overwrite=args.overwrite,
        )
    if handler == "repo_extract":
        return "repo.extract", extract_zip_safely(args.archive, args.destination)
    if handler == "ask_stream":
        body = parse_json_input(args, required=True)
        return "knowledge.ask-stream", stream_events(client, args.project_id, body)
    if handler in {"gitlab_validate", "gitlab_apply"}:
        return handle_gitlab(client, gate, store, endpoint, args, apply=handler == "gitlab_apply")
    if handler in {"jira_validate", "jira_apply", "jira_clear"}:
        return handle_jira(client, gate, store, endpoint, args, handler)
    if handler == "action":
        return handle_action(client, gate, endpoint, args)
    raise OperatorError("未识别的命令", code="invalid_command")


def handle_action(client, gate, endpoint, args):
    action = args._action_spec
    path = render_path(action.path, args)
    query = parse_query(args.param)
    body = parse_json_input(args, required=action.body_required) if action.method != "GET" else None
    body = bind_archive_target(client, action, args, body)
    required_text = action.confirmation_text
    if required_text:
        format_values = {
            name: getattr(args, camel_to_snake(name))
            for name in _PLACEHOLDER.findall(required_text)
        }
        required_text = required_text.format(**format_values)
    gate_body = body
    if action.response_secret:
        gate_body = {
            "request": body,
            "save_token": str(Path(args.save_token).expanduser().absolute()),
        }
    gate.authorize(
        operation=f"{action.group}.{action.name}",
        endpoint=endpoint.origin,
        risk=action.risk,
        scope=action.scope or None,
        method=action.method,
        path=path,
        query=query,
        body=gate_body,
        confirmation_id=getattr(args, "confirm", None),
        confirmation_text=getattr(args, "confirm_text", None),
        required_text=required_text,
    )
    result = client.api(
        action.method,
        path,
        query=query,
        body=body,
        retry=action.risk == "read",
        redact_response=not action.response_secret,
    )
    if action.response_secret:
        if not isinstance(result, dict) or not result.get("token"):
            raise ApiError("平台未返回新令牌", status=502, code="missing_created_token")
        token = result.pop("token")
        saved_to = write_new_secret_file(args.save_token, validate_token(token))
        result["token_saved_to"] = saved_to
        result["token"] = "<stored-not-shown>"
    return f"{action.group}.{action.name}", redact(result)


def bind_archive_target(client, action, args, body):
    operation = f"{action.group}.{action.name}"
    if operation in {"workspace.group-archive", "workspace.wiki-archive"}:
        workspace = client.api(
            "GET",
            f"/projects/{args.project_id}/workspace",
            query={"reconcile": "false"},
            retry=True,
        )
        if operation == "workspace.group-archive":
            items = workspace.get("namespaces", []) if isinstance(workspace, dict) else []
            target_id = args.namespace_id
            path_key = "full_path"
        else:
            items = workspace.get("repositories", []) if isinstance(workspace, dict) else []
            target_id = args.repository_id
            path_key = "path_with_namespace"
        target = next(
            (
                item for item in items
                if isinstance(item, dict) and positive_object_id(item.get("id")) == target_id
            ),
            None,
        )
        full_path = target.get(path_key) if isinstance(target, dict) else None
    elif operation == "archives.restore":
        result = client.api("GET", "/archives", retry=True)
        items = result.get("items", []) if isinstance(result, dict) else []
        target = next(
            (
                item for item in items
                if isinstance(item, dict)
                and str(item.get("kind")) == str(args.kind)
                and positive_object_id(item.get("id")) == args.id
            ),
            None,
        )
        full_path = target.get("full_path") if isinstance(target, dict) else None
    else:
        return body

    full_path = str(full_path or "").strip()
    if not full_path:
        raise OperatorError(
            "目标已不存在或当前账号不可见，请重新读取资源列表",
            code="archive_target_not_found",
            exit_code=6,
        )
    output = dict(body or {})
    supplied = output.get("expected_full_path")
    if supplied is not None and str(supplied) != full_path:
        raise OperatorError(
            "目标路径已变化，请使用当前列表重新生成确认计划",
            code="archive_target_changed",
            exit_code=3,
            details={"current_full_path": full_path},
        )
    output["expected_full_path"] = full_path
    return output


def positive_object_id(value):
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        return None
    return identifier if identifier > 0 else None


def handle_server(args, store, *, reset):
    if os.environ.get(URL_ENV):
        raise OperatorError(
            f"当前由 {URL_ENV} 覆盖平台地址，请先移除该环境变量再保存",
            code="server_environment_override",
        )
    candidate = normalize_server(DEFAULT_ORIGIN if reset else args.address)
    discovery = discover(PlatformClient(candidate, timeout=args.timeout))
    store.save_endpoint(candidate)
    return ("server.reset" if reset else "server.set"), {
        "origin": candidate.origin,
        "api_url": candidate.api_url,
        "verified": discovery,
    }


def auth_status(client, token, token_source):
    if not token:
        return {"configured": False, "source": token_source, "message": "请先在网页创建个人访问令牌"}
    profile = client.api("GET", "/auth/me")
    return {
        "configured": True,
        "source": token_source,
        "token_prefix": masked_token(token),
        "profile": profile,
    }


def auth_set_token(client, store):
    if sys.stdin.isatty():
        raise OperatorError("请通过管道或重定向把令牌传入标准输入", code="token_stdin_required", exit_code=4)
    raw = sys.stdin.read(513)
    if len(raw) > 512:
        raise OperatorError("令牌输入过长", code="invalid_token", exit_code=4)
    token = validate_token(raw)
    profile = client.api("GET", "/auth/me", token_override=token)
    store.save_token(token)
    return {"saved": True, "token_prefix": masked_token(token), "profile": profile}


def doctor(client, token_source, *, token_error=None):
    checks = {}
    openapi_specification = None
    for name, operation in (
        ("service", lambda: client.public("/service/meta")),
        ("health", lambda: client.public("/health", base="api")),
        ("openapi", lambda: client.public("/openapi.json", base="api")),
    ):
        try:
            value = operation()
            validate_discovery_component(name, value)
            checks[name] = {"ok": True, "result": summarize_discovery(name, value)}
            if name == "openapi":
                openapi_specification = value
        except OperatorError as error:
            checks[name] = {"ok": False, "error": error.code, "message": str(error)}
    if openapi_specification is not None:
        contract = audit_openapi(openapi_specification)
        checks["operator_contract"] = {"ok": contract["compatible"], "result": contract}
    else:
        checks["operator_contract"] = {
            "ok": False,
            "error": "openapi_unavailable",
            "message": "无法核对 Operator 命令与平台 API 契约",
        }
    try:
        if token_error:
            checks["authentication"] = {
                "ok": False,
                "source": token_source,
                "error": token_error.code,
                "message": str(token_error),
            }
        elif client.token:
            profile = client.api("GET", "/auth/me")
            checks["authentication"] = {"ok": True, "source": token_source, "profile": profile}
        else:
            checks["authentication"] = {"ok": False, "source": token_source, "message": "尚未配置个人访问令牌"}
    except OperatorError as error:
        checks["authentication"] = {"ok": False, "error": error.code, "message": str(error)}
    return {
        "ready": all(checks[name]["ok"] for name in ("service", "health", "openapi", "operator_contract", "authentication")),
        "server": client.endpoint.origin,
        "checks": checks,
    }


def discover(client):
    meta = client.public("/service/meta")
    validate_discovery_component("service", meta)
    openapi = client.public("/openapi.json", base="api")
    validate_discovery_component("openapi", openapi)
    health = client.public("/health", base="api")
    validate_discovery_component("health", health)
    return {
        "service_key": meta.get("service_key"),
        "service_version": meta.get("version"),
        "api_version": meta.get("api_version") or openapi.get("info", {}).get("version"),
        "readiness": health.get("readiness"),
    }


def validate_discovery_component(name, value):
    if not isinstance(value, dict):
        raise OperatorError("平台发现响应格式无效", code="wrong_service")
    if name == "service" and value.get("service_key") != "kg-platform":
        raise OperatorError("目标不是 Wiki Repository 平台", code="wrong_service")
    if name == "health" and value.get("readiness") != "ready":
        raise OperatorError("目标平台核心服务尚未就绪", code="service_not_ready")
    if name == "openapi":
        if value.get("info", {}).get("title") != "Wiki Repository Platform API":
            raise OperatorError("目标没有返回预期的 Wiki API 契约", code="wrong_service")
        version = str(value.get("info", {}).get("version") or "")
        if not version.startswith("4."):
            raise OperatorError(
                f"目标 API 版本 {version or 'unknown'} 与 Skill 需要的 4.x 不兼容",
                code="unsupported_api_version",
            )


def summarize_discovery(name, value):
    if name == "service":
        return {key: value.get(key) for key in ("service_key", "service_name", "version", "api_version")}
    if name == "health":
        return {key: value.get(key) for key in ("status", "readiness", "components")}
    return {"openapi": value.get("openapi"), "title": value.get("info", {}).get("title"), "version": value.get("info", {}).get("version")}


def resolve_object(client, args):
    if args._resolve_kind == "project":
        value = client.api("GET", "/projects")
    elif args._resolve_kind == "repository":
        value = client.api("GET", f"/projects/{args.project_id}/workspace")
    else:
        value = client.api("GET", "/personnel")
    candidates = collect_named_objects(value, args._resolve_kind)
    ranked = rank_candidates(candidates, args.query)
    if not ranked:
        raise OperatorError("没有找到匹配对象", code="object_not_found", exit_code=6)
    best_score = ranked[0][0]
    best = [item for score, item in ranked if score == best_score]
    if len(best) != 1:
        raise OperatorError(
            "名称不唯一，请使用更完整的名称或直接使用 ID",
            code="ambiguous_object",
            exit_code=6,
            details={"candidates": best[:20]},
        )
    return {"resolved": best[0], "matches_considered": len(ranked)}


def raw_get(client, args):
    parsed = urlsplit(args.path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not parsed.path.startswith("/"):
        raise OperatorError("raw get 只接受 /api 下不带查询参数的相对路径", code="unsafe_raw_path")
    if any(part == ".." for part in parsed.path.split("/")):
        raise OperatorError("raw get 路径不能包含 ..", code="unsafe_raw_path")
    return client.api("GET", parsed.path, query=parse_query(args.param), retry=True)


def repo_preview(client, gate, endpoint, args):
    archive, stats = create_directory_zip(args.directory)
    try:
        digest = sha256_file(archive)
        path = f"/repositories/{args.repository_id}/imports/preview"
        body = {
            "directory": str(Path(args.directory).expanduser().absolute()),
            "branch": args.branch,
            "manifest": {**stats, "sha256": digest},
        }
        gate.authorize(
            operation="repo.preview-dir",
            endpoint=endpoint.origin,
            risk="medium",
            scope="wiki:write",
            method="POST",
            path=path,
            query={},
            body=body,
            confirmation_id=args.confirm,
            confirmation_text=args.confirm_text,
        )
        result = client.upload_zip(path, archive, branch=args.branch)
        return {"preview": result, "local_manifest": body["manifest"]}
    finally:
        archive.unlink(missing_ok=True)


def handle_gitlab(client, gate, store, endpoint, args, *, apply):
    token = read_secret_source(args, store, required=False)
    body = {"base_url": args.base_url, "connect_ip": args.connect_ip}
    if token:
        body["token"] = token
    validation = client.api("POST", "/integrations/gitlab/settings/validate", body=body, retry=False)
    if not apply:
        return "gitlab.validate", validation
    fingerprint_body = {
        "settings": body,
        "validated_identity": stable_gitlab_validation(validation),
    }
    gate.authorize(
        operation="gitlab.apply",
        endpoint=endpoint.origin,
        risk="critical",
        scope="integrations:manage",
        method="PUT",
        path="/integrations/gitlab/settings",
        query={},
        body=fingerprint_body,
        display_body={"settings": body, "validation": validation},
        confirmation_id=args.confirm,
        confirmation_text=args.confirm_text,
        required_text="APPLY GITLAB SETTINGS",
    )
    result = client.api("PUT", "/integrations/gitlab/settings", body=body, retry=False)
    return "gitlab.apply", {"validation": validation, "applied": result}


def handle_jira(client, gate, store, endpoint, args, handler):
    if handler == "jira_clear":
        gate.authorize(
            operation="jira.clear",
            endpoint=endpoint.origin,
            risk="critical",
            scope="integrations:manage",
            method="DELETE",
            path="/integrations/jira/token",
            query={},
            body=None,
            confirmation_id=args.confirm,
            confirmation_text=args.confirm_text,
            required_text="CLEAR JIRA BINDING",
        )
        return "jira.clear", client.api("DELETE", "/integrations/jira/token", retry=False)

    token = read_secret_source(args, store, required=True)
    body = {"token": token}
    validation = client.api("POST", "/integrations/jira/token/validate", body=body, retry=False)
    if handler == "jira_validate":
        return "jira.validate", validation
    fingerprint_body = {"settings": body, "validated_identity": stable_jira_validation(validation)}
    gate.authorize(
        operation="jira.apply",
        endpoint=endpoint.origin,
        risk="critical",
        scope="integrations:manage",
        method="PUT",
        path="/integrations/jira/token",
        query={},
        body=fingerprint_body,
        display_body={"settings": body, "validation": validation},
        confirmation_id=args.confirm,
        confirmation_text=args.confirm_text,
        required_text="APPLY JIRA TOKEN",
    )
    result = client.api("PUT", "/integrations/jira/token", body=body, retry=False)
    return "jira.apply", {"validation": validation, "applied": result}


def stream_events(client, project_id, body):
    count = 0
    for event in client.stream_sse(f"/projects/{project_id}/ask/stream", body=body):
        print(json.dumps({"ok": True, "command": "knowledge.ask-stream", "event": event}, ensure_ascii=False, separators=(",", ":")), flush=True)
        count += 1
    return {"events": count, "stream_complete": True}


def parse_json_input(args, required=False):
    raw = None
    if getattr(args, "json_value", None) is not None:
        raw = args.json_value
    elif getattr(args, "json_file", None):
        path = Path(args.json_file).expanduser()
        if not path.is_file() or path.is_symlink():
            raise OperatorError(f"JSON 文件不存在或不安全：{path}", code="invalid_json_file")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise OperatorError("JSON 文件超过 2 MiB", code="json_too_large")
        raw = path.read_text(encoding="utf-8")
    if raw is None:
        if required:
            raise OperatorError("必须提供 --json 或 --json-file", code="json_required")
        return None
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise OperatorError("JSON 请求体超过 2 MiB", code="json_too_large")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OperatorError(f"JSON 格式无效：{error.msg}", code="invalid_json") from error
    if not isinstance(value, dict):
        raise OperatorError("JSON 请求体顶层必须是对象", code="invalid_json")
    if contains_sensitive_fields(value):
        raise OperatorError("--json/--json-file 不能包含 Token、密码或密钥字段，请使用专用敏感输入参数", code="sensitive_json_rejected")
    return value


def parse_query(items):
    result = {}
    for item in items or []:
        if "=" not in item:
            raise OperatorError(f"查询参数必须是 KEY=VALUE：{item}", code="invalid_query")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key or is_sensitive_key(key):
            raise OperatorError("查询参数名无效或包含敏感字段", code="invalid_query")
        if key in result:
            current = result[key]
            result[key] = [current, value] if not isinstance(current, list) else [*current, value]
        else:
            result[key] = value
    return result


def render_path(template, args):
    def replace(match):
        value = getattr(args, camel_to_snake(match.group(1)))
        return quote(str(value), safe="")
    return _PLACEHOLDER.sub(replace, template)


def read_secret_source(args, store, *, required):
    raw = None
    if getattr(args, "secret_stdin", False):
        if sys.stdin.isatty():
            raise OperatorError("请通过管道或重定向提供敏感值", code="secret_stdin_required")
        raw = sys.stdin.read(10001)
    elif getattr(args, "secret_env", None):
        name = args.secret_env
        if not _ENVIRONMENT_NAME.fullmatch(name):
            raise OperatorError("敏感环境变量名无效", code="invalid_secret_environment")
        raw = os.environ.get(name)
        if raw is None:
            raise OperatorError(f"环境变量未设置：{name}", code="secret_environment_missing")
    elif getattr(args, "secret_file", None):
        raw = store.read_restricted_file(args.secret_file)
    if raw is None:
        if required:
            raise OperatorError("必须通过标准输入、环境变量或权限 600 文件提供 Token", code="secret_required")
        return None
    if len(raw) > 10000:
        raise OperatorError("敏感值长度异常", code="secret_too_long")
    value = raw.strip()
    if not value or any(character.isspace() for character in value):
        raise OperatorError("敏感值为空或包含空白字符", code="invalid_secret")
    return value


def stable_gitlab_validation(value):
    account = value.get("account") or {}
    linked = value.get("linked_member") or {}
    return {
        "base_url": value.get("base_url"),
        "connect_ip": value.get("connect_ip"),
        "version": value.get("version"),
        "account_id": account.get("id"),
        "account_username": account.get("username"),
        "linked_member_id": linked.get("id"),
        "capabilities": value.get("capabilities") or {},
    }


def stable_jira_validation(value):
    account = value.get("account") or {}
    return {
        "jira_url": value.get("jira_url"),
        "projects_count": value.get("projects_count"),
        "account": account,
    }


def collect_named_objects(value, kind):
    output = []
    seen = set()
    expected_keys = {
        "project": {"project_id", "id"},
        "repository": {"repository_id", "id"},
        "person": {"user_id", "id"},
    }[kind]

    def visit(item):
        if isinstance(item, dict):
            names = [item.get(key) for key in ("name", "full_path", "username", "email", "path") if item.get(key)]
            identifier = next((item.get(key) for key in expected_keys if item.get(key) is not None), None)
            type_value = str(item.get("kind") or item.get("type") or "").lower()
            kind_ok = (
                kind == "project"
                or (kind == "repository" and ("repo" in type_value or "wiki" in type_value or "repository_id" in item or "gitlab_project_id" in item))
                or (kind == "person" and ("email" in item or "username" in item or "employee_role" in item))
            )
            if identifier is not None and names and kind_ok:
                key = (str(identifier), tuple(str(name) for name in names))
                if key not in seen:
                    seen.add(key)
                    output.append(redact(item))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return output


def rank_candidates(candidates, query):
    needle = str(query or "").strip().casefold()
    if not needle:
        raise OperatorError("解析名称不能为空", code="invalid_resolution_query")
    ranked = []
    for candidate in candidates:
        values = [str(candidate.get(key) or "").strip() for key in ("full_path", "name", "username", "email", "path")]
        folded = [value.casefold() for value in values if value]
        if needle in folded:
            score = 0
        elif any(value.startswith(needle) for value in folded):
            score = 1
        elif any(needle in value for value in folded):
            score = 2
        else:
            continue
        ranked.append((score, candidate))
    return sorted(ranked, key=lambda item: (item[0], str(item[1].get("full_path") or item[1].get("name") or "").casefold()))


def write_new_secret_file(value, secret):
    path = Path(value).expanduser().absolute()
    if not path.parent.is_dir():
        raise OperatorError(f"令牌输出目录不存在：{path.parent}", code="output_directory_missing")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise OperatorError(f"令牌输出文件已存在：{path}", code="output_exists") from error
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{secret}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return str(path)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def positive_id(value):
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是正整数") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return result


def camel_to_snake(value):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def camel_to_kebab(value):
    return camel_to_snake(value).replace("_", "-")


def main(argv=None, *, operator_root=None):
    parser = build_parser()
    bootstrap = None
    try:
        args = parser.parse_args(argv)
        if not 1 <= args.timeout <= 300:
            raise OperatorError("--timeout 必须在 1 到 300 秒之间", code="invalid_timeout")
        store = CredentialStore()
        bootstrap = ensure_wiki_skill_once(store, operator_root=operator_root, timeout=args.timeout)
        command, result = run(args, store)
        if result is not None:
            payload = {"ok": True, "command": command, "server": store.endpoint()[0].origin, "result": redact(result)}
            if bootstrap:
                payload["wiki_skill_bootstrap"] = bootstrap
            emit(payload, pretty=args.pretty)
        return 0
    except ConfirmationRequired as error:
        pretty = getattr(locals().get("args", None), "pretty", False)
        payload = {"ok": False, "error": {"code": error.code, "message": str(error), **redact(error.details)}}
        if bootstrap:
            payload["wiki_skill_bootstrap"] = bootstrap
        emit(payload, pretty=pretty)
        return error.exit_code
    except OperatorError as error:
        pretty = getattr(locals().get("args", None), "pretty", False)
        emit_error(error, pretty=pretty, bootstrap=bootstrap)
        return error.exit_code
    except KeyboardInterrupt:
        error = OperatorError("操作已取消", code="interrupted", exit_code=130)
        emit_error(error, pretty=False)
        return error.exit_code
    except Exception as unexpected:
        error = OperatorError(
            "CLI 发生未预期错误；未执行自动重试",
            code="internal_error",
            exit_code=70,
            details={"type": type(unexpected).__name__},
        )
        emit_error(error, pretty=getattr(locals().get("args", None), "pretty", False))
        return error.exit_code


def emit(value, *, pretty=False, stream=None):
    output = stream or sys.stdout
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")), file=output)


def emit_error(error, *, pretty=False, bootstrap=None):
    payload = {
        "ok": False,
        "error": {
            "code": error.code,
            "message": redact(str(error)),
            **redact(error.details),
        },
    }
    if bootstrap:
        payload["wiki_skill_bootstrap"] = bootstrap
    emit(payload, pretty=pretty, stream=sys.stderr)
