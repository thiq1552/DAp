"""Cấu hình server, đọc hoàn toàn từ biến môi trường."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} phải là số nguyên, nhận được {raw!r}") from exc


def _parse_tokens(raw: str) -> dict[str, str]:
    """`CCBUS_TOKENS="ubuntu-16g:tok_a,mac:tok_b"` -> {token: agent_name}."""
    tokens: dict[str, str] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, token = chunk.partition(":")
        if not sep or not name.strip() or not token.strip():
            raise ValueError(
                f"Mục CCBUS_TOKENS không hợp lệ: {chunk!r} (định dạng đúng: 'ten-may:token')"
            )
        tokens[token.strip()] = name.strip()
    return tokens


@dataclass(frozen=True)
class Config:
    db_path: Path
    host: str = "0.0.0.0"
    port: int = 7717
    tokens: dict[str, str] = field(default_factory=dict)
    allowed_hosts: list[str] = field(default_factory=list)
    max_body_bytes: int = 1_048_576
    default_project: str = "default"
    task_claim_ttl_s: int = 3600
    max_attempts: int = 3
    agent_online_window_s: int = 900

    @property
    def auth_required(self) -> bool:
        return bool(self.tokens)

    @classmethod
    def from_env(cls) -> "Config":
        db = os.environ.get("CCBUS_DB", "").strip()
        db_path = Path(db).expanduser() if db else Path.home() / ".ccbus" / "bus.db"

        hosts_raw = os.environ.get("CCBUS_ALLOWED_HOSTS", "*").strip()
        allowed_hosts = [h.strip() for h in hosts_raw.split(",") if h.strip()]

        return cls(
            db_path=db_path,
            host=os.environ.get("CCBUS_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_int("CCBUS_PORT", 7717),
            tokens=_parse_tokens(os.environ.get("CCBUS_TOKENS", "")),
            allowed_hosts=allowed_hosts,
            max_body_bytes=_int("CCBUS_MAX_BODY_BYTES", 1_048_576),
            default_project=os.environ.get("CCBUS_DEFAULT_PROJECT", "default").strip() or "default",
            task_claim_ttl_s=_int("CCBUS_CLAIM_TTL", 3600),
            max_attempts=_int("CCBUS_MAX_ATTEMPTS", 3),
            agent_online_window_s=_int("CCBUS_AGENT_WINDOW", 900),
        )
