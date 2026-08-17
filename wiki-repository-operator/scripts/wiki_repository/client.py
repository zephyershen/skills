from __future__ import annotations

import http.client
import json
import os
import ssl
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__
from .errors import ApiError, OperatorError
from .security import redact

USER_AGENT = f"wiki-repository-operator/{__version__}"
MAX_JSON_BYTES = 20 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_URL_OPENER = build_opener(_RejectRedirects())


class PlatformClient:
    def __init__(self, endpoint, token=None, *, timeout=30):
        self.endpoint = endpoint
        self.token = token
        self.timeout = max(1, min(int(timeout), 300))

    def api(self, method, path, *, query=None, body=None, token_override=None, retry=None, redact_response=True):
        url = build_url(self.endpoint.api_url, path, query)
        return self.request(
            method,
            url,
            body=body,
            token_override=token_override,
            retry=(method.upper() == "GET") if retry is None else retry,
            redact_response=redact_response,
        )

    def public(self, path, *, base="origin"):
        root = self.endpoint.origin if base == "origin" else self.endpoint.api_url
        return self.request("GET", build_url(root, path), auth=False, retry=True)

    def request(self, method, url, *, body=None, token_override=None, auth=True, retry=False, redact_response=True):
        method = method.upper()
        payload = None
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        token = token_override if token_override is not None else self.token
        if auth:
            if not token:
                raise OperatorError(
                    "尚未配置个人访问令牌，请先在网页创建，再运行 auth set-token --stdin",
                    code="authentication_required",
                    exit_code=4,
                )
            headers["Authorization"] = f"Bearer {token}"

        attempts = 3 if retry and method == "GET" else 1
        for attempt in range(attempts):
            request = Request(url, data=payload, headers=headers, method=method)
            try:
                with _URL_OPENER.open(request, timeout=self.timeout) as response:
                    return parse_response(
                        response.status,
                        response.headers,
                        response.read(MAX_JSON_BYTES + 1),
                        redact_response=redact_response,
                    )
            except HTTPError as error:
                data = error.read(MAX_JSON_BYTES + 1)
                if attempt + 1 < attempts and (error.code == 429 or error.code >= 500):
                    time.sleep(retry_delay(attempt, error.headers.get("Retry-After")))
                    continue
                raise_api_error(error.code, data)
            except (URLError, TimeoutError, OSError) as error:
                if attempt + 1 < attempts:
                    time.sleep(retry_delay(attempt))
                    continue
                reason = getattr(error, "reason", error)
                raise ApiError(
                    f"无法连接 Wiki 平台：{redact(str(reason))}",
                    code="platform_unreachable",
                ) from error
        raise ApiError("Wiki 平台请求失败", code="platform_request_failed")

    def upload_zip(self, path, zip_path, *, branch=None):
        token = self._required_token()
        url = build_url(self.endpoint.api_url, path)
        parsed = urlsplit(url)
        boundary = f"wiki-repository-{os.urandom(16).hex()}"
        filename = "wiki-upload.zip"
        preamble = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode("ascii")
        branch_part = b""
        if branch:
            branch_value = str(branch).encode("utf-8")
            branch_part = (
                f"\r\n--{boundary}\r\n"
                'Content-Disposition: form-data; name="branch"\r\n\r\n'
            ).encode("ascii") + branch_value
        closing = f"\r\n--{boundary}--\r\n".encode("ascii")
        file_size = Path(zip_path).stat().st_size
        content_length = len(preamble) + file_size + len(branch_part) + len(closing)
        connection = create_connection(parsed, self.timeout)
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += f"?{parsed.query}"
            connection.putrequest("POST", target)
            connection.putheader("User-Agent", USER_AGENT)
            connection.putheader("Accept", "application/json")
            connection.putheader("Authorization", f"Bearer {token}")
            connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            connection.putheader("Content-Length", str(content_length))
            connection.endheaders()
            connection.send(preamble)
            with open(zip_path, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    connection.send(chunk)
            if branch_part:
                connection.send(branch_part)
            connection.send(closing)
            response = connection.getresponse()
            data = response.read(MAX_JSON_BYTES + 1)
            if not 200 <= response.status < 300:
                raise_api_error(response.status, data)
            return parse_response(response.status, response.headers, data)
        except ApiError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            raise ApiError(
                f"上传预览失败，写请求不会自动重试：{redact(str(error))}",
                code="upload_failed",
            ) from error
        finally:
            connection.close()

    def download(self, path, output, *, query=None, overwrite=False):
        token = self._required_token()
        destination = Path(output).expanduser().absolute()
        parent = destination.parent
        if not parent.is_dir():
            raise OperatorError(f"输出目录不存在：{parent}", code="output_directory_missing")
        if destination.exists() and not overwrite:
            raise OperatorError(f"输出文件已存在：{destination}", code="output_exists")
        url = build_url(self.endpoint.api_url, path, query)
        request = Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/zip, application/octet-stream",
            "User-Agent": USER_AGENT,
        })
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
        temporary = Path(temporary_name)
        total = 0
        try:
            os.fchmod(descriptor, 0o600)
            with _URL_OPENER.open(request, timeout=max(self.timeout, 180)) as response, os.fdopen(descriptor, "wb") as handle:
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                    raise ApiError("下载文件超过 1 GiB 安全限制", status=413, code="download_too_large")
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ApiError("下载文件超过 1 GiB 安全限制", status=413, code="download_too_large")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                commit_sha = response.headers.get("X-Wiki-Commit-Sha")
            os.replace(temporary, destination)
            os.chmod(destination, 0o600)
            return {"path": str(destination), "bytes": total, "commit_sha": commit_sha}
        except HTTPError as error:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise_api_error(error.code, error.read(MAX_JSON_BYTES + 1))
        except (URLError, TimeoutError, OSError) as error:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise ApiError(f"下载失败：{redact(str(getattr(error, 'reason', error)))}", code="download_failed") from error
        finally:
            temporary.unlink(missing_ok=True)

    def stream_sse(self, path, *, body):
        token = self._required_token()
        url = build_url(self.endpoint.api_url, path)
        request = Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            response = _URL_OPENER.open(request, timeout=max(self.timeout, 180))
        except HTTPError as error:
            raise_api_error(error.code, error.read(MAX_JSON_BYTES + 1))
        except (URLError, TimeoutError, OSError) as error:
            raise ApiError(f"流式问答连接失败：{redact(str(error))}", code="stream_failed") from error

        event_name = "message"
        data_lines = []
        try:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if data_lines:
                        yield parse_sse_event(event_name, data_lines)
                    event_name, data_lines = "message", []
                elif line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                yield parse_sse_event(event_name, data_lines)
        finally:
            response.close()

    def _required_token(self):
        if not self.token:
            raise OperatorError(
                "尚未配置个人访问令牌，请先在网页创建，再运行 auth set-token --stdin",
                code="authentication_required",
                exit_code=4,
            )
        return self.token


def build_url(root, path, query=None):
    safe_path = "/" + str(path or "").lstrip("/")
    url = f"{root.rstrip('/')}{safe_path}"
    if query:
        values = [(str(key), value) for key, value in query.items() if value is not None]
        if values:
            url += f"?{urlencode(values, doseq=True)}"
    return url


def parse_response(status, headers, data, *, redact_response=True):
    if len(data) > MAX_JSON_BYTES:
        raise ApiError("平台响应超过 20 MiB 安全限制", status=502, code="response_too_large")
    if not data:
        return {"ok": True, "status": status}
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        content_type = str(headers.get("Content-Type", "")) if headers else ""
        raise ApiError(
            f"平台返回了无法解析的响应（{content_type or 'unknown content type'}）",
            status=502,
            code="invalid_platform_response",
        ) from error
    return redact(value) if redact_response else value


def raise_api_error(status, data):
    payload = {}
    try:
        payload = json.loads(data.decode("utf-8")) if data else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    payload = redact(payload)
    message = payload.get("error") if isinstance(payload, dict) else None
    code = payload.get("code") if isinstance(payload, dict) else None
    details = {}
    if isinstance(payload, dict) and payload.get("required_scope"):
        details["required_scope"] = payload["required_scope"]
    raise ApiError(
        str(message or f"Wiki 平台返回 HTTP {status}"),
        status=status,
        code=str(code or "platform_api_error"),
        details=details,
    )


def retry_delay(attempt, retry_after=None):
    try:
        if retry_after is not None:
            return min(max(float(retry_after), 0.0), 5.0)
    except ValueError:
        pass
    return min(0.25 * (2 ** attempt), 2.0)


def create_connection(parsed, timeout):
    host = parsed.hostname
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(host, parsed.port or 443, timeout=timeout, context=ssl.create_default_context())
    return http.client.HTTPConnection(host, parsed.port or 80, timeout=timeout)


def parse_sse_event(name, data_lines):
    text = "\n".join(data_lines)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = text
    return redact({"event": name, "data": data})
