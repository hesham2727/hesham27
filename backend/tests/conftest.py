import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fbosint.config import load_settings, set_settings  # noqa: E402
from fbosint.security.ratelimit import limiter  # noqa: E402


@pytest.fixture()
def settings(tmp_path):
    env = {
        "FBO_DATA_DIR": str(tmp_path / "data"),
        "FBO_DATABASE_URL": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "FBO_RUN_JOBS_INLINE": "1",
        "FBO_SCHEDULER_ENABLED": "0",
        "FBO_ENV": "test",
        "FBO_RATE_LIMIT_PER_MINUTE": "10000",
        "FBO_LOGIN_RATE_LIMIT_PER_MINUTE": "1000",
    }
    s = load_settings(env)
    set_settings(s)
    limiter.reset()
    from fbosint.database import create_all, init_engine

    init_engine(s)
    create_all()
    yield s
    set_settings(None)


@pytest.fixture()
def db(settings):
    from fbosint.database import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


STRONG = "Str0ngPassw0rd!"
