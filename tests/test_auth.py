import httpx
import pytest

from ccbus.config import Config
from ccbus.server import build_app, resolve_agent
from ccbus.store import Store

TOKENS = {"tok_a": "ubuntu-16g", "tok_b": "mac"}


@pytest.fixture()
def config(tmp_path):
    return Config(db_path=tmp_path / "bus.db", tokens=dict(TOKENS), default_project="demo")


@pytest.fixture()
def client(config):
    store = Store(config.db_path)
    app = build_app(config, store)
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://bus")
    store.close()


# ------------------------------------------------------------------ đơn vị


def test_token_identifies_which_machine_is_calling(config):
    assert resolve_agent({"authorization": "Bearer tok_b"}, config) == "mac"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"authorization": "Bearer sai-token"},
        {"authorization": "Basic tok_a"},
        {"authorization": "tok_a"},
        None,
    ],
)
def test_bad_credentials_resolve_to_nobody(config, headers):
    assert resolve_agent(headers, config) is None


def test_without_configured_tokens_the_agent_header_names_the_machine(tmp_path):
    open_config = Config(db_path=tmp_path / "bus.db")
    assert open_config.auth_required is False
    assert resolve_agent({"x-ccbus-agent": "mac"}, open_config) == "mac"
    assert resolve_agent({}, open_config) == "unknown"


def test_agent_name_from_header_is_length_capped(tmp_path):
    open_config = Config(db_path=tmp_path / "bus.db")
    assert len(resolve_agent({"x-ccbus-agent": "m" * 500}, open_config)) == 64


def test_env_maps_each_machine_name_to_its_own_token(monkeypatch, tmp_path):
    monkeypatch.setenv("CCBUS_DB", str(tmp_path / "bus.db"))
    monkeypatch.setenv("CCBUS_TOKENS", "ubuntu-16g:tok_a, mac:tok_b ")
    monkeypatch.setenv("CCBUS_PORT", "9000")
    cfg = Config.from_env()
    assert cfg.tokens == {"tok_a": "ubuntu-16g", "tok_b": "mac"}
    assert (cfg.port, cfg.auth_required) == (9000, True)


@pytest.mark.parametrize("bad", ["khong-co-dau-hai-cham", ":tok", "ten:"])
def test_malformed_token_config_fails_loudly_at_startup(monkeypatch, bad):
    monkeypatch.setenv("CCBUS_TOKENS", bad)
    with pytest.raises(ValueError, match="không hợp lệ"):
        Config.from_env()


def test_wildcard_allowed_hosts_disables_rebinding_protection(monkeypatch, tmp_path):
    monkeypatch.setenv("CCBUS_DB", str(tmp_path / "bus.db"))
    monkeypatch.delenv("CCBUS_TOKENS", raising=False)
    assert Config.from_env().allowed_hosts == ["*"]


# -------------------------------------------------------------------- HTTP


async def test_health_is_public(client):
    async with client as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["auth"] is True


async def test_api_requires_a_token(client):
    async with client as c:
        resp = await c.get("/api/status")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


async def test_api_accepts_a_valid_token(client):
    async with client as c:
        resp = await c.get("/api/status", headers={"Authorization": "Bearer tok_a"})
    assert resp.status_code == 200
    assert resp.json()["project"] == "demo"


async def test_mcp_endpoint_is_also_protected(client):
    async with client as c:
        resp = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401


async def test_rest_post_records_which_machine_published(client):
    async with client as c:
        await c.post(
            "/api/outputs",
            headers={"Authorization": "Bearer tok_b"},
            json={"key": "perf/bench", "summary": "120 rps", "body": "chi tiết"},
        )
        listed = await c.get("/api/outputs", headers={"Authorization": "Bearer tok_b"})
    assert listed.json()["entries"][0]["agent"] == "mac"


async def test_rest_post_reports_a_bad_payload_instead_of_crashing(client):
    async with client as c:
        resp = await c.post(
            "/api/outputs", headers={"Authorization": "Bearer tok_a"}, json={"summary": "thiếu key"}
        )
    assert resp.status_code == 400
