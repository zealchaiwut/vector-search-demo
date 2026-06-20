"""Tests for deployment ENV label in UI header."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"
INDEX_HTML = REPO_ROOT / "public" / "index.html"
SERVER_MJS = REPO_ROOT / "src" / "server.mjs"


def test_env_example_contains_env_var():
    content = ENV_EXAMPLE.read_text()
    assert re.search(r"^ENV=", content, re.MULTILINE), ".env.example must define ENV="


def test_server_exposes_api_config():
    src = SERVER_MJS.read_text()
    assert "/api/config" in src, "server.mjs must expose GET /api/config"
    assert "process.env.ENV" in src, "server.mjs must read ENV from the environment"


def test_index_html_loads_env_badge():
    src = INDEX_HTML.read_text()
    assert 'id="env-badge"' in src, "index.html must include env-badge element"
    assert "/api/config" in src, "index.html must fetch /api/config for the ENV label"
