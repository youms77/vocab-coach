"""Hostile and damaged archives are refused before anything is written (M10.a)."""

import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.services import backup_format as fmt
from app.services import backup_verify as verify_module
from app.services.backup import BackupError
from app.services.backup_restore import restore_backup
from app.services.backup_verify import verify_archive
from tests.backup_support import (
    make_archive,
    read_members,
    sha,
    with_manifest,
    write_members,
)


@pytest.fixture
def members(engine: Engine, tmp_path: Path) -> dict[str, bytes]:
    archive = tmp_path / "good.zip"
    make_archive(engine, tmp_path / "audio", archive)
    return read_members(archive)


def forge(members: dict[str, bytes], path: Path, **extra: bytes) -> Path:
    """The good archive plus extra members, listed in the manifest so only the name is wrong."""
    manifest = json.loads(members["manifest.json"])
    for name, data in extra.items():
        manifest["files"][name] = {"sha256": sha(data), "size": len(data)}
    write_members(path, {**members, **extra, "manifest.json": json.dumps(manifest).encode()})
    return path


def refused(path: Path, tmp_path: Path) -> str:
    """Restore must refuse with a code and write nothing at all in the target folder."""
    target = tmp_path / f"target-{path.stem}"
    target.mkdir()
    with pytest.raises(BackupError) as caught:
        restore_backup(path, db_file=target / "d.sqlite3", audio_dir=target / "audio", demo=False)
    assert not list(target.iterdir())
    return caught.value.code


def test_a_good_archive_passes(members: dict[str, bytes], tmp_path: Path) -> None:
    write_members(tmp_path / "ok.zip", members)
    assert verify_archive(tmp_path / "ok.zip")["format"] == fmt.FORMAT


def test_parent_directory_member_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    path = forge(members, tmp_path / "a.zip", **{"../x": b"owned"})
    assert refused(path, tmp_path) == "unsafe_member_name"


def test_absolute_member_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    assert refused(forge(members, tmp_path / "a.zip", **{"/etc/x": b"x"}), tmp_path) == (
        "unsafe_member_name"
    )
    assert refused(forge(members, tmp_path / "b.zip", **{"C:/x": b"x"}), tmp_path) == (
        "unsafe_member_name"
    )


def test_backslash_member_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    forge(members, path)
    with zipfile.ZipFile(path, "a") as archive:
        info = zipfile.ZipInfo("tables/x")
        info.filename = "tables\\x.jsonl"  # ZipInfo turns os.sep into "/" at construction only
        archive.writestr(info, b"x")
    # On Windows the zip reader turns the backslash into "/" (the member then is not in the
    # manifest); elsewhere the name itself is unsafe. Either way, the archive is refused.
    assert refused(path, tmp_path) in ("unsafe_member_name", "members_mismatch")
    assert verify_module._unsafe("tables" + chr(92) + "x.jsonl")


def test_audio_path_must_follow_the_pattern(members: dict[str, bytes], tmp_path: Path) -> None:
    path = forge(members, tmp_path / "a.zip", **{"audio/evil.exe": b"x"})
    assert refused(path, tmp_path) == "unexpected_member"


def test_wrong_checksum_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    tampered = with_manifest(
        members, lambda m: m["files"]["tables/setting.jsonl"].update(sha256="0" * 64)
    )
    write_members(tmp_path / "a.zip", tampered)
    assert refused(tmp_path / "a.zip", tmp_path) == "checksum_mismatch"


def test_changed_data_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    write_members(tmp_path / "a.zip", {**members, "tables/setting.jsonl": b'{"key":"x"}\n'})
    assert refused(tmp_path / "a.zip", tmp_path) == "checksum_mismatch"


def test_zip_bomb_is_refused(
    members: dict[str, bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fmt, "MAX_UNCOMPRESSED_BYTES", 10_000)
    bomb = b"0" * 200_000  # a few hundred bytes once compressed
    path = forge(members, tmp_path / "a.zip", **{"tables/bomb.jsonl": bomb})
    assert path.stat().st_size < 10_000
    assert refused(path, tmp_path) == "archive_too_large"


def test_missing_manifest_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    without = {name: data for name, data in members.items() if name != "manifest.json"}
    write_members(tmp_path / "a.zip", without)
    assert refused(tmp_path / "a.zip", tmp_path) == "manifest_missing"


def test_unknown_format_and_not_a_zip(members: dict[str, bytes], tmp_path: Path) -> None:
    write_members(tmp_path / "a.zip", with_manifest(members, lambda m: m.update(format="x-2")))
    assert refused(tmp_path / "a.zip", tmp_path) == "unknown_format"
    (tmp_path / "b.zip").write_bytes(b"this is not a zip")
    assert refused(tmp_path / "b.zip", tmp_path) == "not_a_zip"


def test_an_unlisted_file_is_refused(members: dict[str, bytes], tmp_path: Path) -> None:
    write_members(tmp_path / "a.zip", {**members, "tables/extra.jsonl": b"{}\n"})
    assert refused(tmp_path / "a.zip", tmp_path) == "members_mismatch"
