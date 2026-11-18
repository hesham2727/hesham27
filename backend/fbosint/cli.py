"""Command-line utilities: serve, init-db, create-admin, backup/restore, purge, TLS cert, schema export."""
from __future__ import annotations

import argparse
import getpass
import ipaddress
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import APP_NAME, __version__
from .config import get_settings


def cmd_serve(a: argparse.Namespace) -> int:
    import uvicorn

    from .main import create_app

    s = get_settings()
    if a.host:
        s.host = a.host
    if a.port:
        s.port = a.port
    if a.host and a.host not in ("127.0.0.1", "localhost", "::1"):
        s.mode = "network"
    kw = {}
    if s.tls_enabled:
        kw = {"ssl_certfile": s.tls_certfile, "ssl_keyfile": s.tls_keyfile}
    elif s.mode == "network":
        print("WARNING: network mode without TLS. Configure FBO_TLS_CERTFILE/FBO_TLS_KEYFILE (see 'fbosint gen-cert').", file=sys.stderr)
    print(f"{APP_NAME} {__version__} listening on {'https' if s.tls_enabled else 'http'}://{s.host}:{s.port}  (data: {s.data_dir})")
    uvicorn.run(create_app(), host=s.host, port=s.port, log_level="info", proxy_headers=False, server_header=False, **kw)
    return 0


def cmd_init_db(_a: argparse.Namespace) -> int:
    from .main import init_database

    init_database()
    print(f"Database initialised: {get_settings().database_url.split('@')[-1]}")
    return 0


def cmd_create_admin(a: argparse.Namespace) -> int:
    from sqlalchemy import select

    from .database import session_scope
    from .main import init_database
    from .models import User
    from .security.passwords import hash_password, password_problems

    init_database()
    password = a.password or getpass.getpass("Password: ")
    problems = password_problems(password, a.username)
    if problems:
        print("Weak password: " + ", ".join(problems), file=sys.stderr)
        return 2
    with session_scope() as db:
        u = db.scalar(select(User).where(User.username == a.username))
        if u is None:
            db.add(User(username=a.username, full_name=a.full_name, password_hash=hash_password(password), role=a.role))
            print(f"User '{a.username}' created with role {a.role}")
        else:
            u.password_hash, u.role, u.is_active, u.failed_logins, u.locked_until = hash_password(password), a.role, True, 0, None
            print(f"User '{a.username}' updated (password reset, role {a.role})")
    return 0


def cmd_backup(_a: argparse.Namespace) -> int:
    from .main import init_database
    from .services.backup import create_backup

    init_database()
    print(create_backup(label="cli"))
    return 0


def cmd_restore(a: argparse.Namespace) -> int:
    from .services.backup import restore_backup

    path = Path(a.file)
    if not a.yes:
        ans = input(f"Restore {path.name}? The current database will be replaced (a .pre-restore copy is kept). Stop the server first. [y/N] ")
        if ans.strip().lower() != "y":
            return 1
    manifest = restore_backup(path)
    print(f"Restored backup created {manifest.get('created_at')} (app {manifest.get('app_version')})")
    return 0


def cmd_purge(_a: argparse.Namespace) -> int:
    from .database import session_scope
    from .main import init_database
    from .services.retention import purge_expired

    init_database()
    with session_scope() as db:
        print(f"Deleted {purge_expired(db)} expired investigations")
    return 0


def cmd_gen_cert(a: argparse.Namespace) -> int:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    out = Path(a.out or get_settings().data_dir / "tls")
    out.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    host = a.hostname or socket.gethostname()
    names: list[x509.GeneralName] = [x509.DNSName(host), x509.DNSName("localhost")]
    for ip in ["127.0.0.1", *(a.ip or [])]:
        names.append(x509.IPAddress(ipaddress.ip_address(ip)))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host), x509.NameAttribute(NameOID.ORGANIZATION_NAME, APP_NAME)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=a.days))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    (out / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path = out / "server.key"
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    print(f"Certificate: {out / 'server.crt'}\nKey: {key_path}\nSet FBO_TLS_CERTFILE and FBO_TLS_KEYFILE to these paths.")
    return 0


def cmd_schema(a: argparse.Namespace) -> int:
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable

    from . import models  # noqa: F401
    from .database import Base

    dialect = postgresql.dialect() if a.dialect == "postgresql" else sqlite.dialect()
    parts = [f"-- {APP_NAME} {__version__} schema ({a.dialect}), generated from the ORM\n"]
    for t in Base.metadata.sorted_tables:
        parts.append(str(CreateTable(t).compile(dialect=dialect)).strip() + ";\n")
        for ix in t.indexes:
            parts.append(str(CreateIndex(ix).compile(dialect=dialect)).strip() + ";\n")
    sql = "\n".join(parts)
    if a.out:
        Path(a.out).write_text(sql, encoding="utf-8")
    else:
        print(sql)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fbosint", description=f"{APP_NAME} {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the API + web dashboard")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(func=cmd_serve)
    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    c = sub.add_parser("create-admin", help="create or reset a user")
    c.add_argument("username")
    c.add_argument("--password")
    c.add_argument("--full-name", default="")
    c.add_argument("--role", default="admin", choices=["admin", "investigator", "viewer"])
    c.set_defaults(func=cmd_create_admin)
    sub.add_parser("backup").set_defaults(func=cmd_backup)
    r = sub.add_parser("restore")
    r.add_argument("file")
    r.add_argument("--yes", action="store_true")
    r.set_defaults(func=cmd_restore)
    sub.add_parser("purge-expired").set_defaults(func=cmd_purge)
    g = sub.add_parser("gen-cert", help="self-signed TLS certificate for network mode")
    g.add_argument("--hostname")
    g.add_argument("--ip", action="append")
    g.add_argument("--days", type=int, default=825)
    g.add_argument("--out")
    g.set_defaults(func=cmd_gen_cert)
    sc = sub.add_parser("schema")
    sc.add_argument("--dialect", choices=["sqlite", "postgresql"], default="sqlite")
    sc.add_argument("--out")
    sc.set_defaults(func=cmd_schema)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
