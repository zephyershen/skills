from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .errors import OperatorError

MAX_UPLOAD_FILES = 20_000
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_EXTRACT_FILES = 50_000
MAX_EXTRACT_BYTES = 1024 * 1024 * 1024


def create_directory_zip(directory):
    root = Path(directory).expanduser().absolute()
    try:
        info = root.lstat()
    except FileNotFoundError as error:
        raise OperatorError(f"上传目录不存在：{root}", code="directory_not_found") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise OperatorError("上传目标必须是真实目录，不能是符号链接", code="unsafe_upload_directory")

    descriptor, temporary_name = tempfile.mkstemp(prefix="wiki-repository-upload-", suffix=".zip")
    os.close(descriptor)
    os.chmod(temporary_name, 0o600)
    archive = Path(temporary_name)
    file_count = 0
    total_bytes = 0
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for current, directory_names, file_names in os.walk(root, followlinks=False):
                current_path = Path(current)
                safe_directories = []
                for name in directory_names:
                    candidate = current_path / name
                    if name.casefold() == ".git":
                        continue
                    if candidate.is_symlink():
                        raise OperatorError(f"上传目录包含符号链接：{candidate}", code="unsafe_upload_symlink")
                    safe_directories.append(name)
                directory_names[:] = safe_directories

                for name in file_names:
                    source = current_path / name
                    source_info = source.lstat()
                    if stat.S_ISLNK(source_info.st_mode) or not stat.S_ISREG(source_info.st_mode):
                        raise OperatorError(f"上传目录包含非普通文件：{source}", code="unsafe_upload_file")
                    file_count += 1
                    total_bytes += source_info.st_size
                    if file_count > MAX_UPLOAD_FILES:
                        raise OperatorError("上传目录超过 20000 个文件", code="upload_file_limit")
                    if total_bytes > MAX_UPLOAD_BYTES:
                        raise OperatorError("上传目录展开后超过 200 MiB", code="upload_size_limit")
                    relative = source.relative_to(root).as_posix()
                    output.write(source, relative)
        if file_count == 0:
            raise OperatorError("上传目录中没有可提交的文件", code="empty_upload")
        return archive, {"files": file_count, "uncompressed_bytes": total_bytes, "zip_bytes": archive.stat().st_size}
    except Exception:
        archive.unlink(missing_ok=True)
        raise


def extract_zip_safely(archive, destination):
    source = Path(archive).expanduser().absolute()
    target = Path(destination).expanduser().absolute()
    if not source.is_file() or source.is_symlink():
        raise OperatorError(f"ZIP 文件不存在或不安全：{source}", code="unsafe_archive")
    if target.exists() or target.is_symlink():
        raise OperatorError(f"解压目标必须尚不存在：{target}", code="extract_target_exists")
    if not target.parent.is_dir():
        raise OperatorError(f"解压目标的父目录不存在：{target.parent}", code="extract_parent_missing")

    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    os.chmod(temporary, 0o700)
    total_bytes = 0
    file_count = 0
    try:
        with zipfile.ZipFile(source) as bundle:
            entries = bundle.infolist()
            if len(entries) > MAX_EXTRACT_FILES:
                raise OperatorError("ZIP 超过 50000 个条目", code="extract_file_limit")
            for entry in entries:
                relative = safe_zip_path(entry.filename)
                mode = (entry.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise OperatorError(f"ZIP 包含符号链接：{entry.filename}", code="unsafe_archive_entry")
                total_bytes += entry.file_size
                if total_bytes > MAX_EXTRACT_BYTES:
                    raise OperatorError("ZIP 展开后超过 1 GiB", code="extract_size_limit")
                output = temporary.joinpath(*relative.parts)
                if entry.is_dir():
                    output.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                file_count += 1
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with bundle.open(entry) as input_handle, os.fdopen(descriptor, "wb") as output_handle:
                    shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
        os.replace(temporary, target)
        return {"path": str(target), "files": file_count, "uncompressed_bytes": total_bytes}
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def safe_zip_path(value):
    name = str(value or "")
    if not name or "\\" in name or "\x00" in name:
        raise OperatorError("ZIP 包含无效路径", code="unsafe_archive_entry")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise OperatorError(f"ZIP 包含越界路径：{name}", code="unsafe_archive_entry")
    return path
