"""`ccbus` — CLI nhỏ để xem/đăng bảng tin từ terminal, không cần qua Claude."""

from __future__ import annotations

import argparse
import json
import os
import sys
from importlib.resources import files
from pathlib import Path

import httpx

MARKER = "<!-- ccbus:begin -->"
END_MARKER = "<!-- ccbus:end -->"


def _client(args: argparse.Namespace) -> httpx.Client:
    base = args.url or os.environ.get("CCBUS_URL", "http://127.0.0.1:7717")
    token = args.token or os.environ.get("CCBUS_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base.rstrip("/"), headers=headers, timeout=20.0)


def _dump(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _check(resp: httpx.Response) -> object:
    if resp.status_code == 401:
        sys.exit("401: sai hoặc thiếu token (đặt CCBUS_TOKEN hoặc --token)")
    if resp.status_code >= 400:
        sys.exit(f"{resp.status_code}: {resp.text}")
    return resp.json()


def cmd_status(args: argparse.Namespace) -> None:
    with _client(args) as c:
        _dump(_check(c.get("/api/status", params={"project": args.project})))


def cmd_ls(args: argparse.Namespace) -> None:
    with _client(args) as c:
        data = _check(c.get("/api/outputs", params={"project": args.project, "limit": args.limit}))
    entries = data["entries"] if isinstance(data, dict) else []
    if args.json:
        _dump(data)
        return
    if not entries:
        print("(bảng tin trống)")
        return
    for e in entries:
        print(f"{e['created_at']}  {e['agent']:<14} v{e['version']:<3} {e['key']:<32} {e['summary']}")


def cmd_get(args: argparse.Namespace) -> None:
    with _client(args) as c:
        data = _check(c.get(f"/api/outputs/{args.key}", params={"project": args.project}))
    if args.json:
        _dump(data)
        return
    assert isinstance(data, dict)
    print(f"# {data['key']} (v{data['version']}, {data['agent']}, {data['created_at']})")
    print(f"# {data['summary']}\n")
    print(data["body"])


def cmd_post(args: argparse.Namespace) -> None:
    body = Path(args.file).read_text(encoding="utf-8") if args.file else (args.body or sys.stdin.read())
    payload = {
        "project": args.project,
        "key": args.key,
        "summary": args.summary,
        "body": body,
        "kind": args.kind,
        "tags": args.tag or [],
    }
    with _client(args) as c:
        _dump(_check(c.post("/api/outputs", json=payload)))


def cmd_tasks(args: argparse.Namespace) -> None:
    with _client(args) as c:
        data = _check(c.get("/api/tasks", params={"project": args.project, "status": args.status}))
    tasks = data["tasks"] if isinstance(data, dict) else []
    if args.json:
        _dump(data)
        return
    if not tasks:
        print("(hàng đợi trống)")
        return
    for t in tasks:
        deps = ",".join(t["depends_on"]) or "-"
        print(f"{t['id']}  {t['status']:<8} {t['owner'] or '-':<14} deps={deps:<24} {t['title']}")


def cmd_init(args: argparse.Namespace) -> None:
    """Chèn phần hướng dẫn ccbus vào CLAUDE.md của một project."""
    protocol = (
        files("ccbus.templates").joinpath("AGENT_PROTOCOL.md").read_text(encoding="utf-8")
    )
    if args.project != "default":
        protocol = protocol.replace("<ĐIỀN_TÊN_PROJECT>", args.project)
    target = Path(args.path).expanduser() / "CLAUDE.md"
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    if MARKER in existing:
        print(f"{target}: đã có phần ccbus, bỏ qua (xoá khối ccbus cũ nếu muốn cập nhật)")
        return
    block = f"\n{MARKER}\n{protocol}\n{END_MARKER}\n"
    target.write_text((existing.rstrip() + "\n" if existing else "") + block, encoding="utf-8")
    filled = "" if args.project != "default" else " — nhớ thay <ĐIỀN_TÊN_PROJECT>"
    print(f"{target}: đã thêm phần ccbus{filled}")


def cmd_connect(args: argparse.Namespace) -> None:
    """In ra lệnh `claude mcp add` cho máy hiện tại."""
    url = args.url or os.environ.get("CCBUS_URL", "http://127.0.0.1:7717")
    token = args.token or os.environ.get("CCBUS_TOKEN", "")
    if not token:
        sys.exit("cần --token hoặc CCBUS_TOKEN")
    scope = "--scope user" if args.user_scope else "--scope local"
    print(
        f'claude mcp add --transport http ccbus {url.rstrip("/")}/mcp {scope} '
        f'--header "Authorization: Bearer {token}"'
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="ccbus", description="Bảng tin dùng chung cho Claude Code")
    parser.add_argument("--url", help="mặc định $CCBUS_URL hoặc http://127.0.0.1:7717")
    parser.add_argument("--token", help="mặc định $CCBUS_TOKEN")
    parser.add_argument("--project", default=os.environ.get("CCBUS_PROJECT", "default"))
    parser.add_argument("--json", action="store_true", help="in JSON thô")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="ai đang online, hàng đợi và khoá").set_defaults(func=cmd_status)

    p_ls = sub.add_parser("ls", help="liệt kê bảng tin")
    p_ls.add_argument("--limit", type=int, default=30)
    p_ls.set_defaults(func=cmd_ls)

    p_get = sub.add_parser("get", help="đọc một entry")
    p_get.add_argument("key")
    p_get.set_defaults(func=cmd_get)

    p_post = sub.add_parser("post", help="đăng một entry (body từ --body, --file hoặc stdin)")
    p_post.add_argument("key")
    p_post.add_argument("--summary", default="")
    p_post.add_argument("--body")
    p_post.add_argument("--file")
    p_post.add_argument("--kind", default="output")
    p_post.add_argument("--tag", action="append")
    p_post.set_defaults(func=cmd_post)

    p_tasks = sub.add_parser("tasks", help="xem hàng đợi task")
    p_tasks.add_argument("--status", choices=["open", "claimed", "done", "dead"])
    p_tasks.set_defaults(func=cmd_tasks)

    p_init = sub.add_parser("init", help="thêm hướng dẫn ccbus vào CLAUDE.md của project")
    p_init.add_argument("path", nargs="?", default=".")
    p_init.set_defaults(func=cmd_init)

    p_conn = sub.add_parser("connect", help="in lệnh `claude mcp add` cho máy này")
    p_conn.add_argument("--user-scope", action="store_true", help="cài cho mọi project trên máy")
    p_conn.set_defaults(func=cmd_connect)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
