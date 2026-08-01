"""Lớp lưu trữ SQLite cho bảng tin dùng chung giữa các máy chạy Claude Code."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project    TEXT    NOT NULL,
    key        TEXT    NOT NULL,
    version    INTEGER NOT NULL,
    kind       TEXT    NOT NULL,
    summary    TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',
    agent      TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE (project, key, version)
);
CREATE INDEX IF NOT EXISTS idx_entries_lookup ON entries (project, key, version DESC);
CREATE INDEX IF NOT EXISTS idx_entries_recent ON entries (project, id DESC);

CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT    PRIMARY KEY,
    project    TEXT    NOT NULL,
    title      TEXT    NOT NULL,
    detail     TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL,
    priority   INTEGER NOT NULL DEFAULT 0,
    depends_on TEXT    NOT NULL DEFAULT '[]',
    owner      TEXT,
    attempts   INTEGER NOT NULL DEFAULT 0,
    result_key TEXT,
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    claimed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks (project, status, priority DESC, created_at);

CREATE TABLE IF NOT EXISTS locks (
    project     TEXT NOT NULL,
    resource    TEXT NOT NULL,
    owner       TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    acquired_at TEXT NOT NULL,
    expires_at  REAL NOT NULL,
    PRIMARY KEY (project, resource)
);

CREATE TABLE IF NOT EXISTS agents (
    name         TEXT PRIMARY KEY,
    last_seen    TEXT NOT NULL,
    last_project TEXT NOT NULL DEFAULT '',
    calls        INTEGER NOT NULL DEFAULT 0
);
"""

TERMINAL_TASK_STATES = ("done", "dead")
SNIPPET_RADIUS = 120


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class StoreError(RuntimeError):
    """Lỗi nghiệp vụ, trả về cho client dưới dạng thông báo dễ đọc."""


class Store:
    """Bọc SQLite. An toàn với nhiều luồng nhờ một khoá ghi duy nhất."""

    def __init__(self, path: Path, max_body_bytes: int = 1_048_576) -> None:
        self.path = Path(path)
        self.max_body_bytes = max_body_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- bảng tin

    def put_entry(
        self,
        *,
        project: str,
        key: str,
        summary: str,
        body: str,
        kind: str,
        tags: list[str],
        agent: str,
    ) -> dict[str, Any]:
        if not key.strip():
            raise StoreError("`key` không được để trống")
        size = len(body.encode("utf-8"))
        if size > self.max_body_bytes:
            raise StoreError(
                f"body {size} byte vượt giới hạn {self.max_body_bytes} byte. "
                "Hãy đăng phần tóm tắt và trỏ tới đường dẫn file/commit thay vì dán toàn bộ."
            )
        key = key.strip()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT MAX(version) AS v FROM entries WHERE project = ? AND key = ?",
                    (project, key),
                ).fetchone()
                version = (row["v"] or 0) + 1
                created = utcnow()
                self._conn.execute(
                    "INSERT INTO entries (project, key, version, kind, summary, body, tags, agent,"
                    " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (project, key, version, kind, summary, body, json.dumps(tags), agent, created),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return {
            "project": project,
            "key": key,
            "version": version,
            "kind": kind,
            "agent": agent,
            "bytes": size,
            "created_at": created,
        }

    def get_entry(self, *, project: str, key: str, version: int | None = None) -> dict[str, Any] | None:
        if version is None:
            row = self._conn.execute(
                "SELECT * FROM entries WHERE project = ? AND key = ? ORDER BY version DESC LIMIT 1",
                (project, key),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM entries WHERE project = ? AND key = ? AND version = ?",
                (project, key, version),
            ).fetchone()
        if row is None:
            return None
        latest = self._conn.execute(
            "SELECT MAX(version) AS v FROM entries WHERE project = ? AND key = ?", (project, key)
        ).fetchone()["v"]
        entry = self._row_to_entry(row, include_body=True)
        entry["latest_version"] = latest
        return entry

    def latest_version(self, *, project: str, key: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(version) AS v FROM entries WHERE project = ? AND key = ?", (project, key)
        ).fetchone()
        return row["v"] or 0

    def list_entries(
        self,
        *,
        project: str,
        kind: str | None = None,
        tag: str | None = None,
        agent: str | None = None,
        since_minutes: int | None = None,
        limit: int = 30,
        latest_only: bool = True,
    ) -> list[dict[str, Any]]:
        sql = ["SELECT * FROM entries WHERE project = ?"]
        params: list[Any] = [project]
        if latest_only:
            sql.append(
                "AND version = (SELECT MAX(e2.version) FROM entries e2"
                " WHERE e2.project = entries.project AND e2.key = entries.key)"
            )
        if kind:
            sql.append("AND kind = ?")
            params.append(kind)
        if agent:
            sql.append("AND agent = ?")
            params.append(agent)
        if tag:
            sql.append("AND tags LIKE ? ESCAPE '\\'")
            params.append(f'%"{_escape_like(tag)}"%')
        if since_minutes:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            sql.append("AND created_at >= ?")
            params.append(cutoff.isoformat(timespec="seconds"))
        sql.append("ORDER BY id DESC LIMIT ?")
        params.append(max(1, min(limit, 200)))
        rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [self._row_to_entry(r, include_body=False) for r in rows]

    def search_entries(self, *, project: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            raise StoreError("`query` không được để trống")
        pattern = f"%{_escape_like(query.strip())}%"
        rows = self._conn.execute(
            "SELECT * FROM entries WHERE project = ?"
            " AND (key LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')"
            " ORDER BY id DESC LIMIT ?",
            (project, pattern, pattern, pattern, max(1, min(limit, 100))),
        ).fetchall()
        results = []
        for row in rows:
            item = self._row_to_entry(row, include_body=False)
            item["snippet"] = self._snippet(row["body"], query.strip())
            results.append(item)
        return results

    @staticmethod
    def _snippet(body: str, query: str) -> str:
        idx = body.lower().find(query.lower())
        if idx < 0:
            return body[: SNIPPET_RADIUS * 2].strip()
        start = max(0, idx - SNIPPET_RADIUS)
        end = min(len(body), idx + len(query) + SNIPPET_RADIUS)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(body) else ""
        return f"{prefix}{body[start:end].strip()}{suffix}"

    @staticmethod
    def _row_to_entry(row: sqlite3.Row, *, include_body: bool) -> dict[str, Any]:
        entry = {
            "key": row["key"],
            "version": row["version"],
            "kind": row["kind"],
            "summary": row["summary"],
            "tags": json.loads(row["tags"]),
            "agent": row["agent"],
            "created_at": row["created_at"],
            "bytes": len(row["body"].encode("utf-8")),
        }
        if include_body:
            entry["body"] = row["body"]
        return entry

    # ---------------------------------------------------------- hàng đợi task

    def add_task(
        self,
        *,
        project: str,
        title: str,
        detail: str = "",
        depends_on: list[str] | None = None,
        priority: int = 0,
        agent: str = "",
    ) -> dict[str, Any]:
        if not title.strip():
            raise StoreError("`title` không được để trống")
        task_id = f"t_{uuid.uuid4().hex[:10]}"
        now = utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tasks (id, project, title, detail, status, priority, depends_on,"
                " created_at, updated_at, note) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)",
                (
                    task_id,
                    project,
                    title.strip(),
                    detail,
                    priority,
                    json.dumps(depends_on or []),
                    now,
                    now,
                    f"tạo bởi {agent}" if agent else "",
                ),
            )
        return {"id": task_id, "project": project, "title": title.strip(), "status": "open"}

    def claim_task(
        self, *, project: str, agent: str, claim_ttl_s: int, max_attempts: int
    ) -> dict[str, Any] | None:
        """Nhận một task 'open' đã đủ phụ thuộc. Đảm bảo không hai máy nhận cùng task."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._requeue_stale(project, claim_ttl_s, max_attempts)
                rows = self._conn.execute(
                    "SELECT * FROM tasks WHERE project = ? AND status = 'open'"
                    " ORDER BY priority DESC, created_at ASC",
                    (project,),
                ).fetchall()
                for row in rows:
                    deps = json.loads(row["depends_on"])
                    missing = [d for d in deps if self._entry_missing(project, d)]
                    if missing:
                        continue
                    self._conn.execute(
                        "UPDATE tasks SET status = 'claimed', owner = ?, claimed_at = ?,"
                        " attempts = attempts + 1, updated_at = ? WHERE id = ?",
                        (agent, time.time(), utcnow(), row["id"]),
                    )
                    self._conn.execute("COMMIT")
                    task = self._row_to_task(row)
                    task.update(status="claimed", owner=agent, attempts=row["attempts"] + 1)
                    task["dependencies"] = [
                        self._dep_summary(project, d) for d in deps
                    ]
                    return task
                self._conn.execute("COMMIT")
                return None
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def _entry_missing(self, project: str, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM entries WHERE project = ? AND key = ? LIMIT 1", (project, key)
        ).fetchone()
        return row is None

    def _dep_summary(self, project: str, key: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT key, version, summary, agent FROM entries WHERE project = ? AND key = ?"
            " ORDER BY version DESC LIMIT 1",
            (project, key),
        ).fetchone()
        if row is None:
            return {"key": key, "available": False}
        return {
            "key": row["key"],
            "version": row["version"],
            "summary": row["summary"],
            "agent": row["agent"],
            "available": True,
        }

    def _requeue_stale(self, project: str, claim_ttl_s: int, max_attempts: int) -> None:
        """Máy chết giữa chừng thì task quay lại hàng đợi thay vì kẹt mãi ở 'claimed'."""
        cutoff = time.time() - claim_ttl_s
        stale = self._conn.execute(
            "SELECT id, attempts FROM tasks WHERE project = ? AND status = 'claimed'"
            " AND claimed_at IS NOT NULL AND claimed_at < ?",
            (project, cutoff),
        ).fetchall()
        for row in stale:
            if row["attempts"] >= max_attempts:
                self._conn.execute(
                    "UPDATE tasks SET status = 'dead', updated_at = ?,"
                    " note = 'quá số lần thử sau khi hết hạn nhận' WHERE id = ?",
                    (utcnow(), row["id"]),
                )
            else:
                self._conn.execute(
                    "UPDATE tasks SET status = 'open', owner = NULL, claimed_at = NULL,"
                    " updated_at = ? WHERE id = ?",
                    (utcnow(), row["id"]),
                )

    def finish_task(
        self,
        *,
        task_id: str,
        agent: str,
        status: str,
        result_key: str | None = None,
        note: str = "",
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        if status not in ("done", "failed"):
            raise StoreError("`status` phải là 'done' hoặc 'failed'")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                if row is None:
                    raise StoreError(f"không tìm thấy task {task_id}")
                if row["status"] in TERMINAL_TASK_STATES:
                    raise StoreError(f"task {task_id} đã ở trạng thái cuối: {row['status']}")
                if status == "done":
                    new_status = "done"
                elif row["attempts"] >= max_attempts:
                    new_status = "dead"
                else:
                    new_status = "open"
                self._conn.execute(
                    "UPDATE tasks SET status = ?, result_key = ?, note = ?, updated_at = ?,"
                    " owner = ?, claimed_at = NULL WHERE id = ?",
                    (
                        new_status,
                        result_key,
                        note,
                        utcnow(),
                        agent if new_status == "done" else None,
                        task_id,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return {"id": task_id, "status": new_status, "result_key": result_key, "note": note}

    def list_tasks(
        self, *, project: str, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        sql = ["SELECT * FROM tasks WHERE project = ?"]
        params: list[Any] = [project]
        if status:
            sql.append("AND status = ?")
            params.append(status)
        sql.append("ORDER BY priority DESC, created_at ASC LIMIT ?")
        params.append(max(1, min(limit, 200)))
        rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [self._row_to_task(r) for r in rows]

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "detail": row["detail"],
            "status": row["status"],
            "priority": row["priority"],
            "depends_on": json.loads(row["depends_on"]),
            "owner": row["owner"],
            "attempts": row["attempts"],
            "result_key": row["result_key"],
            "note": row["note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ---------------------------------------------------------------- khoá

    def acquire_lock(
        self, *, project: str, resource: str, owner: str, ttl_s: int, note: str = ""
    ) -> dict[str, Any]:
        if not resource.strip():
            raise StoreError("`resource` không được để trống")
        resource = resource.strip()
        now = time.time()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT * FROM locks WHERE project = ? AND resource = ?", (project, resource)
                ).fetchone()
                if row is not None and row["expires_at"] > now and row["owner"] != owner:
                    self._conn.execute("COMMIT")
                    return {
                        "acquired": False,
                        "resource": resource,
                        "held_by": row["owner"],
                        "expires_in_s": int(row["expires_at"] - now),
                        "note": row["note"],
                    }
                self._conn.execute(
                    "INSERT INTO locks (project, resource, owner, note, acquired_at, expires_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (project, resource) DO UPDATE SET owner = excluded.owner,"
                    " note = excluded.note, acquired_at = excluded.acquired_at,"
                    " expires_at = excluded.expires_at",
                    (project, resource, owner, note, utcnow(), now + ttl_s),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return {"acquired": True, "resource": resource, "held_by": owner, "expires_in_s": ttl_s}

    def release_lock(self, *, project: str, resource: str, owner: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT owner FROM locks WHERE project = ? AND resource = ?", (project, resource)
            ).fetchone()
            if row is None:
                return {"released": False, "reason": "khoá không tồn tại"}
            if row["owner"] != owner:
                return {"released": False, "reason": f"khoá đang do {row['owner']} giữ"}
            self._conn.execute(
                "DELETE FROM locks WHERE project = ? AND resource = ?", (project, resource)
            )
        return {"released": True, "resource": resource}

    def list_locks(self, *, project: str) -> list[dict[str, Any]]:
        now = time.time()
        rows = self._conn.execute(
            "SELECT * FROM locks WHERE project = ? AND expires_at > ? ORDER BY acquired_at",
            (project, now),
        ).fetchall()
        return [
            {
                "resource": r["resource"],
                "held_by": r["owner"],
                "note": r["note"],
                "expires_in_s": int(r["expires_at"] - now),
            }
            for r in rows
        ]

    # --------------------------------------------------------------- agents

    def touch_agent(self, *, name: str, project: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO agents (name, last_seen, last_project, calls) VALUES (?, ?, ?, 1)"
                " ON CONFLICT (name) DO UPDATE SET last_seen = excluded.last_seen,"
                " last_project = excluded.last_project, calls = agents.calls + 1",
                (name, utcnow(), project),
            )

    def list_agents(self, *, within_s: int) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_s)).isoformat(
            timespec="seconds"
        )
        rows = self._conn.execute("SELECT * FROM agents ORDER BY last_seen DESC").fetchall()
        return [
            {
                "name": r["name"],
                "last_seen": r["last_seen"],
                "last_project": r["last_project"],
                "calls": r["calls"],
                "online": r["last_seen"] >= cutoff,
            }
            for r in rows
        ]

    def stats(self, *, project: str) -> dict[str, Any]:
        entries = self._conn.execute(
            "SELECT COUNT(DISTINCT key) AS keys, COUNT(*) AS versions FROM entries WHERE project = ?",
            (project,),
        ).fetchone()
        tasks = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks WHERE project = ? GROUP BY status",
            (project,),
        ).fetchall()
        return {
            "project": project,
            "entry_keys": entries["keys"],
            "entry_versions": entries["versions"],
            "tasks": {r["status"]: r["n"] for r in tasks},
            "locks": len(self.list_locks(project=project)),
        }

    def projects(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT project FROM entries UNION SELECT project FROM tasks ORDER BY 1"
        ).fetchall()
        return [r["project"] for r in rows]
