from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from . import __version__
from .errors import OperatorError

DEFAULT_SKILLHUB_ORIGIN = "http://10.40.2.15:2323"
SKILLHUB_URL_ENV = "WIKI_REPOSITORY_SKILLHUB_URL"
SKILLHUB_COMPAT_URL_ENV = "SKILLHUB_API_URL"
SKILLS_DIR_ENV = "WIKI_REPOSITORY_SKILLS_DIR"

WIKI_NAMESPACE = "global-skills"
WIKI_NAME = "wiki"
WIKI_VERSION = "1.0.0"
WIKI_COORDINATE = f"{WIKI_NAMESPACE}/{WIKI_NAME}@{WIKI_VERSION}"
WIKI_PACKAGE_SHA256 = "43837e035d6d58e3ea9d44c57d3fa9f077ce940fc3ffdee7a171b536b8e18678"
BOOTSTRAP_SETTINGS_KEY = "wiki_skill_bootstrap"

MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_ARCHIVE_FILES = 100
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
USER_AGENT = f"wiki-repository-operator/{__version__}"

CORE_FILE_SHA256 = {
    "SKILL.md": "7f3c7a4edc0931063ad5d3b64d797bd9b3dc0faac31499f691a44bb3e0761402",
    "references/templates.md": "b7eedf2de7530a509a9afb99632033645d5f3ca823476cb3224a5eee40723070",
    "references/wiki-location.md": "0b68e4cc260940e57e1f6455340e7899dcdc289561776964fb4b8170859c94bf",
}


def ensure_wiki_skill_once(store, *, operator_root=None, timeout=30, expected_checksum=None):
    """Install the pinned Wiki Skill once for this operator installation.

    A completed marker is intentionally authoritative: normal later invocations do
    not inspect the Wiki Skill directory and do not contact SkillHub again.
    """

    root = Path(operator_root or Path(__file__).absolute().parents[2]).expanduser().absolute()
    completed = _completed_record(store.read_settings(), root)
    if completed:
        return None
    target = _wiki_skill_target(root)

    with _bootstrap_lock(store):
        completed = _completed_record(store.read_settings(), root)
        if completed:
            return None

        installed_kind = _inspect_installed_skill(target)
        skillhub_origin = None
        if installed_kind is None:
            skillhub_origin = configured_skillhub_origin()
            archive = _download_wiki_package(skillhub_origin, timeout=timeout)
            checksum = hashlib.sha256(archive).hexdigest()
            required_checksum = expected_checksum or WIKI_PACKAGE_SHA256
            if checksum != required_checksum:
                raise OperatorError(
                    "公司 SkillHub 返回的 Wiki Skill 校验值与固定版本不一致",
                    code="wiki_skill_checksum_mismatch",
                    exit_code=5,
                    details={"coordinate": WIKI_COORDINATE},
                )
            _install_archive(archive, target)
            installed_kind = "skillhub"
            status = "installed"
        else:
            status = "already_installed"

        record = {
            "status": "complete",
            "coordinate": WIKI_COORDINATE,
            "operator_root": str(root),
            "install_path": str(target),
            "installed_kind": installed_kind,
            "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if skillhub_origin:
            record["skillhub_origin"] = skillhub_origin
        store.update_settings({BOOTSTRAP_SETTINGS_KEY: record})
        return {
            "status": status,
            "coordinate": WIKI_COORDINATE,
            "install_path": str(target),
        }


def configured_skillhub_origin():
    value = (
        os.environ.get(SKILLHUB_URL_ENV)
        or os.environ.get(SKILLHUB_COMPAT_URL_ENV)
        or DEFAULT_SKILLHUB_ORIGIN
    )
    return normalize_skillhub_origin(value)


def normalize_skillhub_origin(value):
    raw = str(value or "").strip()
    if not raw or any(character.isspace() for character in raw):
        raise OperatorError("公司 SkillHub 地址不能为空或包含空白字符", code="invalid_skillhub_server")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OperatorError("公司 SkillHub 地址必须是完整的 http:// 或 https:// 根地址", code="invalid_skillhub_server")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OperatorError("公司 SkillHub 地址不能包含账号、密码、查询参数或片段", code="invalid_skillhub_server")
    if parsed.path.rstrip("/"):
        raise OperatorError("公司 SkillHub 地址只能填写根地址", code="invalid_skillhub_server")
    try:
        port = parsed.port
    except ValueError as error:
        raise OperatorError("公司 SkillHub 端口无效", code="invalid_skillhub_server") from error
    hostname = parsed.hostname.lower()
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def _wiki_skill_target(operator_root):
    configured = os.environ.get(SKILLS_DIR_ENV)
    if configured:
        base = Path(configured).expanduser()
        if not base.is_absolute():
            raise OperatorError(f"{SKILLS_DIR_ENV} 必须是绝对路径", code="invalid_skills_directory")
    else:
        base = operator_root.parent
    return base / WIKI_NAME


def _completed_record(settings, operator_root):
    record = settings.get(BOOTSTRAP_SETTINGS_KEY) if isinstance(settings, dict) else None
    return bool(
        isinstance(record, dict)
        and record.get("status") == "complete"
        and record.get("coordinate") == WIKI_COORDINATE
        and record.get("operator_root") == str(operator_root)
        and isinstance(record.get("install_path"), str)
        and bool(record["install_path"])
    )


def _inspect_installed_skill(target):
    if not target.exists() and not target.is_symlink():
        return None
    if not target.is_dir():
        raise OperatorError(
            f"Wiki Skill 安装位置已被其他文件占用：{target}",
            code="wiki_skill_install_conflict",
            exit_code=5,
        )

    for relative, expected in CORE_FILE_SHA256.items():
        path = target / relative
        if not path.is_file() or _sha256_file(path) != expected:
            raise OperatorError(
                f"本地已有同名 Wiki Skill，但内容不是公司发布的兼容版本：{target}",
                code="wiki_skill_install_conflict",
                exit_code=5,
                details={"coordinate": WIKI_COORDINATE, "install_path": str(target)},
            )

    manifest_path = target / "skill.json"
    if not manifest_path.exists():
        return "compatible_local"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperatorError("本地 Wiki Skill 的 skill.json 无效", code="wiki_skill_install_conflict", exit_code=5) from error
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value
        for key, value in (("namespace", WIKI_NAMESPACE), ("name", WIKI_NAME), ("version", WIKI_VERSION))
    ):
        raise OperatorError(
            f"本地已有同名 Wiki Skill，但发布坐标不匹配：{target}",
            code="wiki_skill_install_conflict",
            exit_code=5,
            details={"coordinate": WIKI_COORDINATE, "install_path": str(target)},
        )
    return "skillhub"


def _download_wiki_package(origin, *, timeout):
    path = f"/api/v1/skills/{WIKI_NAMESPACE}/{WIKI_NAME}/versions/{WIKI_VERSION}/download"
    request = Request(
        f"{origin}{path}",
        data=b'{"allowed":true}',
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=max(1, min(int(timeout), 300))) as response:
            payload = _read_limited(response, MAX_RESPONSE_BYTES)
    except HTTPError as error:
        raise OperatorError(
            f"公司 SkillHub 拒绝下载 Wiki Skill（HTTP {error.code}）",
            code="wiki_skill_download_failed",
            exit_code=5,
        ) from error
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise OperatorError(
            "无法从公司 SkillHub 下载 Wiki Skill",
            code="wiki_skill_download_failed",
            exit_code=5,
            details={"skillhub_origin": origin, "coordinate": WIKI_COORDINATE},
        ) from error

    try:
        envelope = json.loads(payload.decode("utf-8"))
        data = envelope.get("data") if isinstance(envelope, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperatorError("公司 SkillHub 返回了无效下载响应", code="wiki_skill_download_failed", exit_code=5) from error
    if not isinstance(data, dict) or (envelope.get("code") not in {None, 0}):
        raise OperatorError("公司 SkillHub 未返回 Wiki Skill 安装包", code="wiki_skill_download_failed", exit_code=5)

    content = data.get("content")
    if content:
        try:
            archive = base64.b64decode(content, validate=True)
        except (ValueError, binascii.Error) as error:
            raise OperatorError(
                "公司 SkillHub 返回的 Wiki Skill 安装包编码无效",
                code="wiki_skill_download_failed",
                exit_code=5,
            ) from error
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise OperatorError("Wiki Skill 安装包大小异常", code="wiki_skill_download_failed", exit_code=5)
        return archive

    download_url = data.get("url")
    if not download_url:
        raise OperatorError("公司 SkillHub 未提供 Wiki Skill 安装包内容", code="wiki_skill_download_failed", exit_code=5)
    resolved = urljoin(f"{origin}/", str(download_url))
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise OperatorError("公司 SkillHub 返回了无效安装包地址", code="wiki_skill_download_failed", exit_code=5)
    try:
        download_request = Request(resolved, headers={"User-Agent": USER_AGENT})
        with urlopen(download_request, timeout=max(1, min(int(timeout), 300))) as response:
            return _read_limited(response, MAX_ARCHIVE_BYTES)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise OperatorError("无法下载 Wiki Skill 安装包文件", code="wiki_skill_download_failed", exit_code=5) from error


def _install_archive(archive, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".wiki-skill-install-", dir=target.parent))
    os.chmod(temporary, 0o700)
    total_bytes = 0
    file_count = 0
    seen = set()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            entries = bundle.infolist()
            if len(entries) > MAX_ARCHIVE_FILES:
                raise OperatorError("Wiki Skill 安装包文件数量异常", code="unsafe_wiki_skill_archive", exit_code=5)
            for entry in entries:
                relative = _safe_archive_path(entry.filename)
                key = relative.as_posix().casefold()
                if key in seen:
                    raise OperatorError("Wiki Skill 安装包包含重复路径", code="unsafe_wiki_skill_archive", exit_code=5)
                seen.add(key)
                entry_type = (entry.external_attr >> 16) & 0o170000
                if entry_type == stat.S_IFLNK:
                    raise OperatorError("Wiki Skill 安装包包含符号链接", code="unsafe_wiki_skill_archive", exit_code=5)
                total_bytes += entry.file_size
                if total_bytes > MAX_ARCHIVE_BYTES:
                    raise OperatorError("Wiki Skill 安装包展开大小异常", code="unsafe_wiki_skill_archive", exit_code=5)
                output = temporary.joinpath(*relative.parts)
                if entry.is_dir():
                    output.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                file_count += 1
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(
                    output,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                with bundle.open(entry) as source, os.fdopen(descriptor, "wb") as destination:
                    shutil.copyfileobj(source, destination, length=64 * 1024)
                    destination.flush()
                    os.fsync(destination.fileno())
        if file_count == 0:
            raise OperatorError("Wiki Skill 安装包为空", code="unsafe_wiki_skill_archive", exit_code=5)
        _inspect_installed_skill(temporary)
        if target.exists() or target.is_symlink():
            _inspect_installed_skill(target)
            return
        os.replace(temporary, target)
        os.chmod(target, 0o700)
    except (zipfile.BadZipFile, RuntimeError) as error:
        raise OperatorError("Wiki Skill 安装包不是有效 ZIP", code="unsafe_wiki_skill_archive", exit_code=5) from error
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _safe_archive_path(value):
    name = str(value or "")
    if not name or "\\" in name or "\x00" in name:
        raise OperatorError("Wiki Skill 安装包包含无效路径", code="unsafe_wiki_skill_archive", exit_code=5)
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise OperatorError("Wiki Skill 安装包包含越界路径", code="unsafe_wiki_skill_archive", exit_code=5)
    return path


def _read_limited(response, limit):
    declared = response.headers.get("Content-Length")
    if declared and int(declared) > limit:
        raise OperatorError("公司 SkillHub 响应过大", code="wiki_skill_download_failed", exit_code=5)
    data = response.read(limit + 1)
    if len(data) > limit:
        raise OperatorError("公司 SkillHub 响应过大", code="wiki_skill_download_failed", exit_code=5)
    return data


def _sha256_file(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise OperatorError("无法读取本地 Wiki Skill", code="wiki_skill_install_conflict", exit_code=5) from error
    return digest.hexdigest()


@contextmanager
def _bootstrap_lock(store):
    store.ensure()
    path = store.config_dir / "wiki-skill-bootstrap.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise OperatorError("无法创建 Wiki Skill 首次安装锁", code="wiki_skill_bootstrap_lock_failed", exit_code=5) from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise OperatorError("Wiki Skill 首次安装锁不安全", code="wiki_skill_bootstrap_lock_failed", exit_code=5)
        os.fchmod(descriptor, 0o600)
        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except ImportError:
            pass
        yield
    finally:
        os.close(descriptor)
