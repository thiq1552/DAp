"""ccbus — MCP server làm "bảng tin" dùng chung cho nhiều máy chạy Claude Code.

Chạy trên một máy; các máy còn lại nối vào qua MCP streamable-HTTP. Mỗi máy
đăng output của mình lên bảng tin và đọc output của máy khác khi cần.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Config
from .store import Store, StoreError

INSTRUCTIONS = """\
Bảng tin dùng chung (shared board) giữa các máy cùng làm một project.

Cách dùng chuẩn cho mỗi task:
1. Trước khi bắt đầu: gọi `list_outputs` (và `search_outputs` nếu cần) để xem
   máy khác đã làm/quyết định gì rồi — đừng làm lại từ đầu.
2. Nếu task phụ thuộc kết quả của máy khác: `wait_for_output` với key đã hẹn.
3. Nếu sắp sửa file mà máy khác có thể đụng: `lock_acquire` trước, `lock_release` sau.
4. Khi xong: `share_output` với `key` ổn định, `summary` một dòng, `body` gồm
   những gì máy khác thực sự cần (quyết định, API, đường dẫn file, commit sha).

Quy ước đặt `key`: "<vùng>/<việc>", ví dụ `api/auth-schema`, `db/migration-plan`.
Đừng dán nguyên log dài — hãy tóm tắt và trỏ tới file/commit.
"""

PROTECTED_PREFIXES = ("/mcp", "/api")


class BearerAuthMiddleware:
    """ASGI middleware: chặn request không có bearer token hợp lệ."""

    def __init__(self, app: ASGIApp, config: Config) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.config.auth_required:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith(PROTECTED_PREFIXES):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if resolve_agent(headers, self.config) is None:
            response = JSONResponse(
                {"error": "unauthorized", "detail": "thiếu hoặc sai Authorization: Bearer <token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def resolve_agent(headers: Mapping[str, str] | None, config: Config) -> str | None:
    """Đổi bearer token thành tên máy. Trả None nếu token sai."""
    if not config.auth_required:
        if headers:
            named = headers.get("x-ccbus-agent")
            if named:
                return named.strip()[:64]
        return "unknown"
    if not headers:
        return None
    auth = headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return config.tokens.get(token.strip())


def build_server(config: Config, store: Store) -> MCPServer:
    mcp = MCPServer(name="ccbus", version="0.1.0", instructions=INSTRUCTIONS)

    def whoami(ctx: Context) -> str:
        agent = resolve_agent(ctx.headers, config)
        if agent is None:
            raise StoreError("token không hợp lệ")
        return agent

    def proj(project: str | None) -> str:
        return (project or config.default_project).strip() or config.default_project

    def seen(agent: str, project: str) -> None:
        store.touch_agent(name=agent, project=project)

    # ------------------------------------------------------------ bảng tin

    @mcp.tool()
    def share_output(
        ctx: Context,
        key: str,
        summary: str,
        body: str,
        kind: str = "output",
        tags: list[str] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Publish a result so the other machines working on this project can read it.

        Call this whenever you finish a unit of work another machine might depend on:
        a decision, an interface/schema, a file path, a commit sha, a benchmark number.

        key: stable identifier, "<area>/<thing>" (e.g. "api/auth-schema"). Re-posting
             the same key creates a new version instead of overwriting history.
        summary: one line another agent can scan in a list.
        body: what a *different* machine actually needs to continue. Prefer decisions
              and pointers (paths, commits) over raw logs.
        kind: one of output | decision | interface | note | blocker.
        """
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        return store.put_entry(
            project=p,
            key=key,
            summary=summary,
            body=body,
            kind=kind,
            tags=tags or [],
            agent=agent,
        )

    @mcp.tool()
    def get_output(
        ctx: Context,
        key: str,
        version: int | None = None,
        max_chars: int = 20_000,
        offset: int = 0,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Read the full body of one board entry published by any machine.

        Omit `version` for the latest. Long bodies are truncated to `max_chars`;
        continue with `offset` if the result says it was truncated.
        """
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        entry = store.get_entry(project=p, key=key, version=version)
        if entry is None:
            near = [e["key"] for e in store.list_entries(project=p, limit=20)]
            return {
                "found": False,
                "key": key,
                "project": p,
                "hint": "chưa có entry này",
                "existing_keys": near,
            }
        body = entry["body"]
        window = body[offset : offset + max(500, max_chars)]
        entry["body"] = window
        entry["found"] = True
        entry["truncated"] = offset + len(window) < len(body)
        entry["next_offset"] = offset + len(window) if entry["truncated"] else None
        return entry

    @mcp.tool()
    def list_outputs(
        ctx: Context,
        kind: str | None = None,
        tag: str | None = None,
        agent: str | None = None,
        since_minutes: int | None = None,
        limit: int = 30,
        project: str | None = None,
    ) -> dict[str, Any]:
        """List what every machine has published (metadata only, newest first).

        Run this at the start of a task to avoid redoing work another machine
        already finished. Bodies are not included — follow up with `get_output`.
        """
        me = whoami(ctx)
        p = proj(project)
        seen(me, p)
        entries = store.list_entries(
            project=p,
            kind=kind,
            tag=tag,
            agent=agent,
            since_minutes=since_minutes,
            limit=limit,
        )
        return {"project": p, "count": len(entries), "entries": entries}

    @mcp.tool()
    def search_outputs(
        ctx: Context, query: str, limit: int = 20, project: str | None = None
    ) -> dict[str, Any]:
        """Full-text search over board entries (key, summary and body) with snippets."""
        me = whoami(ctx)
        p = proj(project)
        seen(me, p)
        hits = store.search_entries(project=p, query=query, limit=limit)
        return {"project": p, "query": query, "count": len(hits), "results": hits}

    @mcp.tool()
    async def wait_for_output(
        ctx: Context,
        key: str,
        timeout_s: int = 120,
        min_version: int = 1,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Block until another machine publishes `key`, then return it.

        Use when your task genuinely cannot start without another machine's result.
        Returns `{"found": false, "timed_out": true}` instead of raising if it expires —
        report that back rather than guessing the missing result.
        """
        me = whoami(ctx)
        p = proj(project)
        seen(me, p)
        deadline = time.monotonic() + max(5, min(timeout_s, 600))
        interval = 1.0
        while True:
            if store.latest_version(project=p, key=key) >= min_version:
                entry = store.get_entry(project=p, key=key)
                assert entry is not None
                entry["found"] = True
                return entry
            if time.monotonic() >= deadline:
                return {
                    "found": False,
                    "timed_out": True,
                    "key": key,
                    "project": p,
                    "waited_s": max(5, min(timeout_s, 600)),
                }
            await anyio.sleep(interval)
            interval = min(interval * 1.5, 10.0)

    # ---------------------------------------------------------- hàng đợi task

    @mcp.tool()
    def task_add(
        ctx: Context,
        title: str,
        detail: str = "",
        depends_on: list[str] | None = None,
        priority: int = 0,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Put a sub-task on the shared queue for whichever machine is free next.

        depends_on: board keys that must exist before the task becomes claimable —
        this is how you express "task B needs task A's output".
        """
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        return store.add_task(
            project=p,
            title=title,
            detail=detail,
            depends_on=depends_on,
            priority=priority,
            agent=agent,
        )

    @mcp.tool()
    def task_claim(ctx: Context, project: str | None = None) -> dict[str, Any]:
        """Atomically take the next runnable task, so two machines never grab the same one.

        Returns the task plus a summary of each dependency's published output. Tasks
        left claimed by a machine that died are automatically requeued.
        """
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        task = store.claim_task(
            project=p,
            agent=agent,
            claim_ttl_s=config.task_claim_ttl_s,
            max_attempts=config.max_attempts,
        )
        if task is None:
            pending = store.list_tasks(project=p, status="open")
            return {
                "claimed": False,
                "project": p,
                "reason": "không có task nào sẵn sàng (hết task hoặc còn chờ phụ thuộc)",
                "blocked_tasks": [
                    {"id": t["id"], "title": t["title"], "depends_on": t["depends_on"]}
                    for t in pending
                ],
            }
        task["claimed"] = True
        task["project"] = p
        return task

    @mcp.tool()
    def task_finish(
        ctx: Context,
        task_id: str,
        status: str = "done",
        result_key: str | None = None,
        note: str = "",
        project: str | None = None,
    ) -> dict[str, Any]:
        """Close out a claimed task. status: "done" or "failed".

        Pass `result_key` pointing at the board entry you published with
        `share_output`, so the machine picking up a dependent task can find it.
        A "failed" task returns to the queue until it runs out of attempts.
        """
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        return store.finish_task(
            task_id=task_id,
            agent=agent,
            status=status,
            result_key=result_key,
            note=note,
            max_attempts=config.max_attempts,
        )

    @mcp.tool()
    def task_list(
        ctx: Context, status: str | None = None, limit: int = 50, project: str | None = None
    ) -> dict[str, Any]:
        """Show the shared queue. status filter: open | claimed | done | dead."""
        me = whoami(ctx)
        p = proj(project)
        seen(me, p)
        tasks = store.list_tasks(project=p, status=status, limit=limit)
        return {"project": p, "count": len(tasks), "tasks": tasks}

    # ----------------------------------------------------------------- khoá

    @mcp.tool()
    def lock_acquire(
        ctx: Context,
        resource: str,
        ttl_s: int = 900,
        note: str = "",
        project: str | None = None,
    ) -> dict[str, Any]:
        """Claim exclusive ownership of a file, directory or subsystem before editing it.

        Advisory only — it works because every machine checks first. If it returns
        `acquired: false`, work on something else instead of editing anyway.
        Locks expire after `ttl_s` so a crashed machine cannot block the others.
        """
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        return store.acquire_lock(
            project=p, resource=resource, owner=agent, ttl_s=max(30, min(ttl_s, 7200)), note=note
        )

    @mcp.tool()
    def lock_release(ctx: Context, resource: str, project: str | None = None) -> dict[str, Any]:
        """Release a lock you hold, as soon as you are done editing."""
        agent = whoami(ctx)
        p = proj(project)
        seen(agent, p)
        return store.release_lock(project=p, resource=resource, owner=agent)

    # --------------------------------------------------------------- trạng thái

    @mcp.tool()
    def bus_status(ctx: Context, project: str | None = None) -> dict[str, Any]:
        """Who else is online, what is queued, and which resources are locked right now."""
        me = whoami(ctx)
        p = proj(project)
        seen(me, p)
        return {
            "you_are": me,
            "project": p,
            "agents": store.list_agents(within_s=config.agent_online_window_s),
            "locks": store.list_locks(project=p),
            "stats": store.stats(project=p),
            "known_projects": store.projects(),
        }

    # ------------------------------------------------- REST cho CLI/giám sát

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "service": "ccbus", "auth": config.auth_required})

    @mcp.custom_route("/api/status", methods=["GET"])
    async def api_status(request: Request) -> JSONResponse:
        p = proj(request.query_params.get("project"))
        return JSONResponse(
            {
                "project": p,
                "stats": store.stats(project=p),
                "agents": store.list_agents(within_s=config.agent_online_window_s),
                "locks": store.list_locks(project=p),
                "known_projects": store.projects(),
            }
        )

    @mcp.custom_route("/api/outputs", methods=["GET", "POST"])
    async def api_outputs(request: Request) -> JSONResponse:
        p = proj(request.query_params.get("project"))
        if request.method == "GET":
            limit = int(request.query_params.get("limit", "30"))
            return JSONResponse(
                {"project": p, "entries": store.list_entries(project=p, limit=limit)}
            )
        payload = await request.json()
        agent = resolve_agent(dict(request.headers), config) or "unknown"
        try:
            return JSONResponse(
                store.put_entry(
                    project=payload.get("project") or p,
                    key=payload["key"],
                    summary=payload.get("summary", ""),
                    body=payload.get("body", ""),
                    kind=payload.get("kind", "output"),
                    tags=payload.get("tags") or [],
                    agent=agent,
                )
            )
        except (KeyError, StoreError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/api/outputs/{key:path}", methods=["GET"])
    async def api_output(request: Request) -> JSONResponse:
        p = proj(request.query_params.get("project"))
        entry = store.get_entry(project=p, key=request.path_params["key"])
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry)

    @mcp.custom_route("/api/tasks", methods=["GET"])
    async def api_tasks(request: Request) -> JSONResponse:
        p = proj(request.query_params.get("project"))
        return JSONResponse(
            {"project": p, "tasks": store.list_tasks(project=p, status=request.query_params.get("status"))}
        )

    return mcp


def build_app(config: Config, store: Store):
    mcp = build_server(config, store)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=config.allowed_hosts not in ([], ["*"]),
        allowed_hosts=config.allowed_hosts,
        allowed_origins=config.allowed_hosts,
    )
    app = mcp.streamable_http_app(transport_security=security, host=config.host)
    return BearerAuthMiddleware(app, config)


def main() -> None:
    import uvicorn

    config = Config.from_env()
    store = Store(config.db_path, max_body_bytes=config.max_body_bytes)
    app = build_app(config, store)
    agents = ", ".join(sorted(config.tokens.values())) or "(không bật auth)"
    print(f"ccbus → http://{config.host}:{config.port}/mcp")
    print(f"  db      : {config.db_path}")
    print(f"  project : {config.default_project}")
    print(f"  máy     : {agents}")
    if not config.auth_required:
        print("  CẢNH BÁO: chưa đặt CCBUS_TOKENS — ai vào được cổng này cũng đọc/ghi được.")
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
