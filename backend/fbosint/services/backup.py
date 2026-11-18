"""Database + media backup and restore.

SQLite: consistent online snapshot via the sqlite3 backup API, zipped with the
media directory and a manifest. PostgreSQL: use ``pg_dump`` (documented);
the media archive is still produced here.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ..config import Settings, get_settings


def _sqlite_path(settings: Settings) -> Path:
    url = settings.database_url
    return Path(url.split("sqlite:///", 1)[1])


def create_backup(settings: Settings | None = None, label: str = "auto") -> Path:
    s = settings or get_settings()
    s.ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = s.backup_dir / f"fbosint-backup-{stamp}-{label}.zip"
    i = 1
    while target.exists():
        target = s.backup_dir / f"fbosint-backup-{stamp}-{label}-{i}.zip"
        i += 1
    with tempfile.TemporaryDirectory() as tmp:
        manifest = {"app_version": __version__, "created_at": stamp, "database": "sqlite" if s.is_sqlite else "postgresql", "files": {}}
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            if s.is_sqlite:
                snap = Path(tmp) / "fbosint.db"
                src = sqlite3.connect(str(_sqlite_path(s)))
                dst = sqlite3.connect(str(snap))
                with dst:
                    src.backup(dst)
                src.close()
                dst.close()
                zf.write(snap, "fbosint.db")
                manifest["files"]["fbosint.db"] = hashlib.sha256(snap.read_bytes()).hexdigest()
            else:
                manifest["note"] = "PostgreSQL data must be backed up with pg_dump; this archive contains media only."
            if s.media_dir.exists():
                for f in s.media_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, f"media/{f.relative_to(s.media_dir).as_posix()}")
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    rotate(s)
    return target


def rotate(settings: Settings | None = None, keep: int | None = None) -> list[Path]:
    s = settings or get_settings()
    keep = keep or s.backup_keep
    files = sorted(s.backup_dir.glob("fbosint-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for f in files[keep:]:
        f.unlink(missing_ok=True)
        removed.append(f)
    return removed


def list_backups(settings: Settings | None = None) -> list[dict]:
    s = settings or get_settings()
    if not s.backup_dir.exists():
        return []
    out = []
    for f in sorted(s.backup_dir.glob("fbosint-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"name": f.name, "size_bytes": f.stat().st_size, "created_at": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()})
    return out


def verify_backup(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        for name, digest in manifest.get("files", {}).items():
            if hashlib.sha256(zf.read(name)).hexdigest() != digest:
                raise ValueError(f"checksum_mismatch:{name}")
        bad = zf.testzip()
        if bad:
            raise ValueError(f"corrupt_member:{bad}")
    return manifest


def restore_backup(path: Path, settings: Settings | None = None) -> dict:
    """Restore a backup. The server must be stopped. The current DB is kept as *.pre-restore."""
    s = settings or get_settings()
    manifest = verify_backup(path)
    if not s.is_sqlite:
        raise ValueError("restore_supported_for_sqlite_only")
    from ..database import get_engine

    get_engine().dispose()
    db_path = _sqlite_path(s)
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("unsafe_archive_path")
        if db_path.exists():
            shutil.copy2(db_path, db_path.with_suffix(".db.pre-restore"))
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        db_path.write_bytes(zf.read("fbosint.db"))
        if s.media_dir.exists():
            shutil.rmtree(s.media_dir)
        s.media_dir.mkdir(parents=True, exist_ok=True)
        for name in zf.namelist():
            if name.startswith("media/") and not name.endswith("/"):
                dest = s.media_dir / name[len("media/"):]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))
    return manifest
