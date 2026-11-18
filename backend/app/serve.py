"""Command-line entry points.

    python -m app.serve                       # full app on 127.0.0.1:8000
    python -m app.serve --host 0.0.0.0        # LAN access (authorized users)
    python -m app.serve --public-only --port 8001   # consent page only (for tunnels)
    python -m app.serve create-admin USERNAME       # create an admin interactively
"""
from __future__ import annotations

import argparse
import getpass
import sys

import uvicorn


def _create_admin(username: str) -> int:
    from .config import get_settings
    from .db import SessionLocal, init_engine, run_migrations
    from .models import User
    from .security import hash_password, password_problems

    s = get_settings()
    s.ensure_dirs()
    init_engine(s.database_url)
    run_migrations(s.database_url)
    pw = getpass.getpass("كلمة المرور / Password: ")
    if pw != getpass.getpass("تأكيد / Confirm: "):
        print("كلمتا المرور غير متطابقتين")
        return 1
    problems = password_problems(pw)
    if problems:
        print("؛ ".join(problems))
        return 1
    with SessionLocal() as db:
        if db.query(User).filter(User.username == username).first():
            print("اسم المستخدم موجود")
            return 1
        db.add(User(username=username, full_name=username, role="admin", password_hash=hash_password(pw)))
        db.commit()
    print(f"تم إنشاء المدير {username}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["create-admin"]:
        if len(argv) != 2:
            print("usage: python -m app.serve create-admin USERNAME")
            return 2
        return _create_admin(argv[1])
    p = argparse.ArgumentParser(description="Tahqiq server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--public-only", action="store_true", help="serve only the customer consent page")
    p.add_argument("--proxy-headers", action="store_true", help="trust X-Forwarded-* from a local reverse proxy")
    a = p.parse_args(argv)
    factory = "app.main:create_public_app" if a.public_only else "app.main:create_app"
    uvicorn.run(factory, factory=True, host=a.host, port=a.port, proxy_headers=a.proxy_headers,
                forwarded_allow_ips="127.0.0.1", log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
