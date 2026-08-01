"""Chạy server thật rồi nối vào bằng MCP client thật, giả lập hai máy khác nhau."""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

TOKENS = {"ubuntu-16g": "tok_ubuntu", "mac": "tok_mac"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _free_port()
    env = {
        **os.environ,
        "CCBUS_DB": str(tmp_path_factory.mktemp("bus") / "bus.db"),
        "CCBUS_HOST": "127.0.0.1",
        "CCBUS_PORT": str(port),
        "CCBUS_DEFAULT_PROJECT": "demo",
        "CCBUS_TOKENS": ",".join(f"{name}:{token}" for name, token in TOKENS.items()),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "ccbus.server"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"server chết khi khởi động:\n{proc.stdout.read().decode()}")
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server không lên kịp")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def machine(base: str, name: str) -> Client:
    """Một máy con nối vào bus bằng token riêng của nó."""
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {TOKENS[name]}"})
    return Client(streamable_http_client(f"{base}/mcp", http_client=http), raise_exceptions=True)


async def call(client: Client, tool: str, **args):
    return (await client.call_tool(tool, args)).structured_content


async def test_every_tool_is_advertised(server):
    async with machine(server, "mac") as mac:
        names = {t.name for t in (await mac.list_tools()).tools}
    assert names == {
        "share_output", "get_output", "list_outputs", "search_outputs", "wait_for_output",
        "task_add", "task_claim", "task_finish", "task_list",
        "lock_acquire", "lock_release", "bus_status",
    }


async def test_a_bad_token_cannot_reach_the_tools(server):
    http = create_mcp_http_client(headers={"Authorization": "Bearer sai"})
    with pytest.raises(Exception):
        async with Client(
            streamable_http_client(f"{server}/mcp", http_client=http), raise_exceptions=True
        ) as bad:
            await bad.list_tools()


async def test_output_published_on_one_machine_is_readable_on_another(server):
    key = "api/auth-schema"
    async with machine(server, "ubuntu-16g") as ubuntu:
        published = await call(
            ubuntu, "share_output",
            key=key, summary="chốt schema JWT",
            body="access 15m, refresh 7d, xem src/auth/schema.py",
            kind="decision", tags=["api"],
        )
    assert published["agent"] == "ubuntu-16g"

    async with machine(server, "mac") as mac:
        fetched = await call(mac, "get_output", key=key)
        listed = await call(mac, "list_outputs", kind="decision")
        found = await call(mac, "search_outputs", query="refresh 7d")

    assert fetched["found"] is True
    assert "refresh 7d" in fetched["body"]
    assert fetched["agent"] == "ubuntu-16g"
    assert key in [e["key"] for e in listed["entries"]]
    assert found["results"][0]["key"] == key


async def test_each_machine_sees_its_own_identity(server):
    async with machine(server, "mac") as mac:
        assert (await call(mac, "bus_status"))["you_are"] == "mac"
    async with machine(server, "ubuntu-16g") as ubuntu:
        status = await call(ubuntu, "bus_status")
    assert status["you_are"] == "ubuntu-16g"
    assert {a["name"] for a in status["agents"]} >= {"mac", "ubuntu-16g"}


async def test_missing_key_returns_a_hint_not_an_error(server):
    async with machine(server, "mac") as mac:
        result = await call(mac, "get_output", key="khong/ton-tai")
    assert result["found"] is False
    assert "existing_keys" in result


async def test_long_body_is_truncated_and_can_be_paged(server):
    body = "".join(f"dòng {i}\n" for i in range(4000))
    async with machine(server, "ubuntu-16g") as ubuntu:
        await call(ubuntu, "share_output", key="log/dai", summary="log dài", body=body)
        first = await call(ubuntu, "get_output", key="log/dai", max_chars=500)
        rest = await call(ubuntu, "get_output", key="log/dai", offset=first["next_offset"])
    assert first["truncated"] is True
    assert first["body"] + rest["body"] == body[: len(first["body"]) + len(rest["body"])]
    assert body.startswith(first["body"])


async def test_a_queued_task_flows_from_one_machine_to_another(server):
    async with machine(server, "ubuntu-16g") as ubuntu:
        await call(ubuntu, "share_output", key="queue/dep", summary="phụ thuộc đã sẵn sàng", body="ok")
        task = await call(
            ubuntu, "task_add",
            title="viết middleware auth", depends_on=["queue/dep"], priority=3,
        )

    async with machine(server, "mac") as mac:
        claimed = await call(mac, "task_claim")
        assert claimed["id"] == task["id"]
        assert claimed["owner"] == "mac"
        assert claimed["dependencies"][0]["summary"] == "phụ thuộc đã sẵn sàng"

        await call(mac, "share_output", key="api/middleware", summary="xong middleware", body="src/auth/mw.py")
        done = await call(mac, "task_finish", task_id=task["id"], result_key="api/middleware")
    assert done["status"] == "done"

    async with machine(server, "ubuntu-16g") as ubuntu:
        finished = [t for t in (await call(ubuntu, "task_list", status="done"))["tasks"]]
    assert task["id"] in {t["id"] for t in finished}


async def test_a_task_waiting_on_an_unpublished_key_is_reported_as_blocked(server):
    async with machine(server, "ubuntu-16g") as ubuntu:
        await call(ubuntu, "task_add", title="viết docs", depends_on=["docs/outline-chua-co"])
    async with machine(server, "mac") as mac:
        result = await call(mac, "task_claim")
    assert result["claimed"] is False
    assert "docs/outline-chua-co" in result["blocked_tasks"][0]["depends_on"]


async def test_two_machines_cannot_hold_the_same_lock(server):
    async with machine(server, "mac") as mac:
        assert (await call(mac, "lock_acquire", resource="src/auth/", note="đang sửa"))["acquired"]
        async with machine(server, "ubuntu-16g") as ubuntu:
            blocked = await call(ubuntu, "lock_acquire", resource="src/auth/")
            assert blocked == {
                "acquired": False, "resource": "src/auth/", "held_by": "mac",
                "expires_in_s": blocked["expires_in_s"], "note": "đang sửa",
            }
            assert (await call(ubuntu, "lock_release", resource="src/auth/"))["released"] is False
        assert (await call(mac, "lock_release", resource="src/auth/"))["released"] is True

    async with machine(server, "ubuntu-16g") as ubuntu:
        assert (await call(ubuntu, "lock_acquire", resource="src/auth/"))["acquired"]
        await call(ubuntu, "lock_release", resource="src/auth/")


async def test_wait_unblocks_as_soon_as_the_other_machine_publishes(server):
    import anyio

    key = "db/migration-plan"

    async def publisher():
        await anyio.sleep(1.5)
        async with machine(server, "ubuntu-16g") as ubuntu:
            await call(ubuntu, "share_output", key=key, summary="kế hoạch migrate", body="3 bước")

    async with machine(server, "mac") as mac:
        async with anyio.create_task_group() as tg:
            tg.start_soon(publisher)
            result = await call(mac, "wait_for_output", key=key, timeout_s=30)

    assert result["found"] is True
    assert result["body"] == "3 bước"


async def test_wait_reports_a_timeout_instead_of_hanging_forever(server):
    async with machine(server, "mac") as mac:
        result = await call(mac, "wait_for_output", key="khong/bao-gio-co", timeout_s=5)
    assert result == {
        "found": False, "timed_out": True,
        "key": "khong/bao-gio-co", "project": "demo", "waited_s": 5,
    }


async def test_reposting_a_key_keeps_the_earlier_version_readable(server):
    async with machine(server, "ubuntu-16g") as ubuntu:
        await call(ubuntu, "share_output", key="api/v", summary="lần 1", body="một")
        second = await call(ubuntu, "share_output", key="api/v", summary="lần 2", body="hai")
    assert second["version"] == 2

    async with machine(server, "mac") as mac:
        assert (await call(mac, "get_output", key="api/v"))["body"] == "hai"
        assert (await call(mac, "get_output", key="api/v", version=1))["body"] == "một"


async def test_projects_do_not_leak_into_each_other(server):
    async with machine(server, "mac") as mac:
        await call(mac, "share_output", key="rieng/khac", summary="s", body="b", project="project-khac")
        listed = await call(mac, "list_outputs")
    assert "rieng/khac" not in {e["key"] for e in listed["entries"]}

    async with machine(server, "ubuntu-16g") as ubuntu:
        other = await call(ubuntu, "list_outputs", project="project-khac")
    assert [e["key"] for e in other["entries"]] == ["rieng/khac"]
