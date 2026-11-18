"""Run the real backend + built web UI against the *simulated* Meta Graph API
and simulated public websites (for end-to-end UI tests, no internet needed).

    python backend/tests/e2e_server.py <data_dir> <port>
"""
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fbosint.config import load_settings, set_settings  # noqa: E402

data_dir, port = sys.argv[1], int(sys.argv[2])
set_settings(load_settings({
    "FBO_DATA_DIR": data_dir, "FBO_SCHEDULER_ENABLED": "0", "FBO_PORT": str(port),
    "FBO_FRONTEND_DIST": str(ROOT.parent / "frontend" / "dist"), "FBO_RATE_LIMIT_PER_MINUTE": "5000",
}))

import uvicorn  # noqa: E402

from fbosint.main import create_app  # noqa: E402
from fbosint.services import engine  # noqa: E402
from tests.fakes import FakeGraph, FakeWeb, public_resolver  # noqa: E402

engine.deps = engine.EngineDeps(graph_transport=httpx.MockTransport(FakeGraph()), web_transport=httpx.MockTransport(FakeWeb()), resolver=public_resolver)
uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
