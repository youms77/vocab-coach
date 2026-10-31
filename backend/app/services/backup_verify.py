"""Checking a backup archive before anything is written (module J, M10.a, D-303).

`verify_archive` opens the zip and refuses it, with a stable code, when any of these fails:

- member names: no absolute path, no `..`, no backslash, no drive letter, only the known layout
  (`manifest.json`, `tables/<table>.jsonl`, `audio/YYYY/MM/<hex32>.<ext>`, D-169), no duplicate;
- size: the bytes actually read stay under `MAX_UNCOMPRESSED_BYTES` (a zip bomb lies about its
  sizes, so the declared sizes are checked first and the real ones while reading);
- the manifest is there, its `format` is known, its `alembic_revision` is in our migration chain
  (an archive from a newer version is `backup_from_newer_version`);
- the manifest lists exactly the files of the archive and every sha256 and size matches.

Nothing is extracted or written: this module only reads.
"""

import hashlib
import json
import zipfile
from collections.abc import Collection
from pathlib import Path
from typing import Any

from alembic.script import ScriptDirectory

from app.db.migrate import alembic_config
from app.services import backup_format as fmt
from app.services.backup import BackupError
from app.speech.audio_store import is_stored_path

CHUNK = 1024 * 1024
REQUIRED_KEYS = (
    "format",
    "created_at",
    "app_version",
    "alembic_revision",
    "study_day",
    "timezone",
    "demo",
    "kind",
    "tables",
    "files",
    "missing_audio",
)


def known_revisions() -> set[str]:
    """Every revision of our migration chain."""
    script = ScriptDirectory.from_config(alembic_config())
    return {revision.revision for revision in script.walk_revisions()}


def _unsafe(name: str) -> bool:
    parts = name.split("/")
    return (
        not name
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or any(part in ("", ".", "..") for part in parts)
    )


def _known_member(name: str) -> bool:
    if name == fmt.MANIFEST or fmt.TABLE_MEMBER.fullmatch(name):
        return True
    return name.startswith("audio/") and is_stored_path(name.removeprefix("audio/"))


def check_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    seen: set[str] = set()
    for info in infos:
        if _unsafe(info.filename):
            raise BackupError(
                "unsafe_member_name", f"Unsafe name in the archive: {info.filename!r}."
            )
        if info.filename in seen:
            raise BackupError("duplicate_member", f"Name used twice: {info.filename!r}.")
        seen.add(info.filename)
        if not _known_member(info.filename):
            raise BackupError("unexpected_member", f"Unexpected file: {info.filename!r}.")
    if sum(info.file_size for info in infos) > fmt.MAX_UNCOMPRESSED_BYTES:
        raise BackupError("archive_too_large", "The archive would unpack to too much data.")
    return infos


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        info = archive.getinfo(fmt.MANIFEST)
    except KeyError:
        raise BackupError("manifest_missing", "There is no manifest.json in the archive.") from None
    if info.file_size > fmt.MAX_MANIFEST_BYTES:
        raise BackupError("archive_too_large", "The manifest is too large.")
    with archive.open(info) as member:
        data = member.read(fmt.MAX_MANIFEST_BYTES + 1)
    if len(data) > fmt.MAX_MANIFEST_BYTES:
        raise BackupError("archive_too_large", "The manifest is too large.")
    try:
        manifest = json.loads(data)
    except ValueError:
        raise BackupError("invalid_manifest", "manifest.json is not valid JSON.") from None
    if not isinstance(manifest, dict):
        raise BackupError("invalid_manifest", "manifest.json is not an object.")
    return manifest


def _check_manifest(manifest: dict[str, Any], revisions: Collection[str]) -> None:
    if manifest.get("format") != fmt.FORMAT:
        raise BackupError(
            "unknown_format",
            f"Unknown backup format {manifest.get('format')!r}, expected {fmt.FORMAT}.",
        )
    if any(key not in manifest for key in REQUIRED_KEYS):
        raise BackupError("invalid_manifest", "manifest.json lacks a required field.")
    tables, files, missing = manifest["tables"], manifest["files"], manifest["missing_audio"]
    if not (
        isinstance(tables, dict)
        and isinstance(files, dict)
        and isinstance(missing, list)
        and isinstance(manifest["demo"], bool)
        and manifest["kind"] in ("manual", "auto")
        and isinstance(manifest["alembic_revision"], str)
    ):
        raise BackupError("invalid_manifest", "manifest.json has a field of the wrong type.")
    if not all(
        isinstance(name, str) and fmt.TABLE_MEMBER.fullmatch(fmt.table_member(name))
        for name in tables
    ) or not all(isinstance(count, int) and count >= 0 for count in tables.values()):
        raise BackupError("invalid_manifest", "manifest.json lists invalid tables.")
    if not all(isinstance(path, str) and is_stored_path(path) for path in missing):
        raise BackupError("invalid_manifest", "manifest.json lists an invalid recording path.")
    if manifest["alembic_revision"] not in revisions:
        raise BackupError(
            "backup_from_newer_version",
            f"The backup is at schema revision {manifest['alembic_revision']!r}, which this "
            "version of the app does not know. Update the app, then restore again.",
        )


def verify_archive(path: Path, revisions: Collection[str] | None = None) -> dict[str, Any]:
    """Return the manifest of a sound archive, or raise BackupError. Writes nothing."""
    revisions = known_revisions() if revisions is None else revisions
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError(
            "not_a_zip", f"{path.name} is not a readable zip archive ({exc})."
        ) from None
    with archive:
        infos = check_members(archive)
        manifest = _read_manifest(archive)
        _check_manifest(manifest, revisions)
        files: dict[str, Any] = manifest["files"]
        members = {info.filename for info in infos} - {fmt.MANIFEST}
        if set(files) != members:
            raise BackupError(
                "members_mismatch", "The files of the archive are not the ones the manifest lists."
            )
        for table in manifest["tables"]:
            if fmt.table_member(table) not in members:
                raise BackupError("members_mismatch", f"The table {table!r} has no data file.")
        total = 0
        try:
            for name in sorted(members):
                entry = files[name]
                digest, size = hashlib.sha256(), 0
                with archive.open(name) as member:
                    while chunk := member.read(CHUNK):
                        size += len(chunk)
                        total += len(chunk)
                        if total > fmt.MAX_UNCOMPRESSED_BYTES:
                            raise BackupError(
                                "archive_too_large", "The archive unpacks to too much data."
                            )
                        digest.update(chunk)
                if not isinstance(entry, dict) or digest.hexdigest() != entry.get("sha256"):
                    raise BackupError("checksum_mismatch", f"Checksum mismatch for {name}.")
                if size != entry.get("size"):
                    raise BackupError("checksum_mismatch", f"Size mismatch for {name}.")
        except (zipfile.BadZipFile, OSError, EOFError) as exc:
            raise BackupError("corrupt_archive", f"The archive is damaged ({exc}).") from None
    return manifest
