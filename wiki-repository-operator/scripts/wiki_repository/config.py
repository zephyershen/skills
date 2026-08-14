from __future__ import annotations

import ipaddress
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .errors import OperatorError

DEFAULT_ORIGIN = "http://10.40.2.178:4004"
URL_ENV = "WIKI_REPOSITORY_URL"
TOKEN_ENV = "WIKI_REPOSITORY_TOKEN"
CONFIG_DIR_ENV = "WIKI_REPOSITORY_CONFIG_DIR"


@dataclass(frozen=True)
class Endpoint:
    origin: str
    api_url: str


def normalize_server(value: str) -> Endpoint:
    raw = str(value or "").strip()
    if not raw or any(character.isspace() for character in raw):
        raise OperatorError("平台地址不能为空或包含空白字符", code="invalid_server")

    if "://" not in raw:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise OperatorError(
                "只写主机时必须填写有效 IP；域名请填写完整的 http:// 或 https:// 地址",
                code="invalid_server",
            ) from error
        host = f"[{address}]" if address.version == 6 else str(address)
        origin = f"http://{host}:4004"
        return Endpoint(origin=origin, api_url=f"{origin}/api")

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise OperatorError("平台地址只支持 http 或 https", code="invalid_server")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OperatorError("平台地址不能包含账号、密码、查询参数或片段", code="invalid_server")
    if not parsed.hostname:
        raise OperatorError("平台地址缺少主机", code="invalid_server")
    try:
        port = parsed.port
    except ValueError as error:
        raise OperatorError("平台端口无效", code="invalid_server") from error
    path = parsed.path.rstrip("/")
    if path not in {"", "/api"}:
        raise OperatorError("平台地址只能填写根地址或以 /api 结尾的 API 地址", code="invalid_server")

    hostname = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(hostname)
        host = f"[{address}]" if address.version == 6 else str(address)
    except ValueError:
        host = hostname
    netloc = f"{host}:{port}" if port is not None else host
    origin = urlunsplit((parsed.scheme, netloc, "", "", ""))
    return Endpoint(origin=origin, api_url=f"{origin}/api")


class CredentialStore:
    def __init__(self, config_dir: str | os.PathLike[str] | None = None):
        self.config_dir = self._resolve_config_dir(config_dir)
        self.settings_path = self.config_dir / "settings.json"
        self.token_path = self.config_dir / "token"
        self.plans_dir = self.config_dir / "plans"

    @staticmethod
    def _resolve_config_dir(value):
        configured = value or os.environ.get(CONFIG_DIR_ENV)
        if configured:
            path = Path(configured).expanduser()
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
            path = base / "wiki-repository-operator"
        if not path.is_absolute():
            raise OperatorError("配置目录必须是绝对路径", code="invalid_config_directory")
        return path

    def ensure(self):
        if self.config_dir.exists() or self.config_dir.is_symlink():
            info = self.config_dir.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise OperatorError("配置目录不能是符号链接或普通文件", code="unsafe_config_directory")
            if info.st_uid != os.geteuid():
                raise OperatorError("配置目录不属于当前用户", code="unsafe_config_directory")
            os.chmod(self.config_dir, 0o700)
        else:
            self.config_dir.mkdir(parents=True, mode=0o700)
            os.chmod(self.config_dir, 0o700)

    def endpoint(self) -> tuple[Endpoint, str]:
        environment = os.environ.get(URL_ENV)
        if environment:
            return normalize_server(environment), "environment"
        settings = self.read_settings()
        if settings.get("origin"):
            return normalize_server(settings["origin"]), "config"
        return normalize_server(DEFAULT_ORIGIN), "default"

    def save_endpoint(self, endpoint: Endpoint):
        self.update_settings({"origin": endpoint.origin})

    def reset_endpoint(self):
        self.save_endpoint(normalize_server(DEFAULT_ORIGIN))

    def read_settings(self) -> dict:
        if self.config_dir.exists() or self.config_dir.is_symlink():
            self.ensure()
        if not self.settings_path.exists():
            return {}
        try:
            content = self._secure_read(self.settings_path, secret=False)
            value = json.loads(content)
        except json.JSONDecodeError as error:
            raise OperatorError("平台配置文件不是有效 JSON", code="invalid_config") from error
        if not isinstance(value, dict):
            raise OperatorError("平台配置文件格式无效", code="invalid_config")
        return value

    def update_settings(self, values: dict):
        if not isinstance(values, dict):
            raise OperatorError("平台配置更新格式无效", code="invalid_config")
        self.ensure()
        settings = self.read_settings()
        settings.update(values)
        self._atomic_write(self.settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")

    def token(self) -> tuple[str | None, str]:
        environment = os.environ.get(TOKEN_ENV)
        if environment is not None:
            return validate_token(environment), "environment"
        if self.config_dir.exists() or self.config_dir.is_symlink():
            self.ensure()
        if not self.token_path.exists():
            return None, "missing"
        return validate_token(self._secure_read(self.token_path, secret=True)), "config"

    def save_token(self, token: str):
        self.ensure()
        self._atomic_write(self.token_path, f"{validate_token(token)}\n")

    def clear_token(self) -> bool:
        if self.token_path.exists() and not self.token_path.is_symlink():
            self.token_path.unlink()
            return True
        if self.token_path.is_symlink():
            raise OperatorError("令牌文件不能是符号链接", code="unsafe_token_file")
        return False

    def read_restricted_file(self, value: str | os.PathLike[str]) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return self._secure_read(path, secret=True)

    def _secure_read(self, path: Path, *, secret: bool) -> str:
        try:
            info = path.lstat()
        except FileNotFoundError as error:
            raise OperatorError(f"文件不存在：{path}", code="file_not_found") from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise OperatorError(f"拒绝读取符号链接或非普通文件：{path}", code="unsafe_file")
        if info.st_uid != os.geteuid():
            raise OperatorError(f"文件不属于当前用户：{path}", code="unsafe_file")
        if secret and stat.S_IMODE(info.st_mode) & 0o077:
            raise OperatorError(f"敏感文件权限必须为 600：{path}", code="unsafe_file_permissions")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise

    def _atomic_write(self, path: Path, content: str):
        self.ensure()
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=self.config_dir)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def validate_token(value: str) -> str:
    raw = str(value or "")
    token = raw.strip()
    if not token.startswith("wkp_") or len(token) < 12 or len(token) > 512:
        raise OperatorError("个人访问令牌格式无效，必须是平台签发的 wkp_ 令牌", code="invalid_token", exit_code=4)
    if any(character.isspace() for character in token) or raw.strip() != token:
        raise OperatorError("个人访问令牌不能包含空白字符", code="invalid_token", exit_code=4)
    return token


def masked_token(token: str | None) -> str | None:
    if not token:
        return None
    return f"{token[:8]}…{token[-4:]}"
