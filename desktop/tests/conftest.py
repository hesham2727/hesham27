import os
import sys
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FBO_DESKTOP_HEADLESS"] = "1"
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "desktop"), str(ROOT / "backend")]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """Real uvicorn server (shared backend) with the simulated Meta API."""
    from fbosint.services import engine
    from fbosint_desktop.server import LocalServer, port_free
    from tests.fakes import FakeGraph, FakeWeb, public_resolver  # backend test fakes

    engine.deps = engine.EngineDeps(graph_transport=httpx.MockTransport(FakeGraph()), web_transport=httpx.MockTransport(FakeWeb()), resolver=public_resolver, sleep=lambda s: None)
    port = next(p for p in range(19100, 19200) if port_free(p))
    data = tmp_path_factory.mktemp("data")
    srv = LocalServer(port, str(data), {"FBO_SCHEDULER_ENABLED": "0", "FBO_RATE_LIMIT_PER_MINUTE": "10000", "FBO_LOGIN_RATE_LIMIT_PER_MINUTE": "1000"})
    srv.start()
    yield srv
    srv.stop()
    engine.deps = engine.EngineDeps()
