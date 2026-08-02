"""Dựng lệnh xpra và đọc kết quả trả về.

Cố tình dùng subcommand `start` chứ không phải `seamless`: từ xpra 6 `seamless`
là tên chính thức nhưng `start` vẫn là alias hợp lệ, mà `start` lại chạy được
cả trên bản 3.x trong kho Ubuntu. Một lệnh đúng cho mọi phiên bản.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Hub, Node
from .remote import quote_remote

# Tuỳ chọn cho phiên chạy nền trên máy con.
#   sharing=yes  -> nối được từ nhiều máy cùng lúc (laptop + điện thoại)
#   exit-with-children=no + không có --start-child -> phiên sống cả khi không còn app
SERVER_OPTS = [
    "--daemon=yes",
    "--sharing=yes",
    "--exit-with-children=no",
    "--notifications=yes",
]


@dataclass(frozen=True)
class Session:
    display: str
    state: str  # LIVE / DEAD / UNKNOWN

    @property
    def live(self) -> bool:
        return self.state == "LIVE"


# `xpra list` in ra các dòng kiểu:
#   LIVE session at :100
#   DEAD session at :7
_LIST_RE = re.compile(r"\b(LIVE|DEAD)\b\s+session\s+at\s+(:\d+)", re.IGNORECASE)

# `xpra --version` -> "xpra v6.2.1" hoặc "xpra v3.1.5-r0"
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?")


def parse_sessions(output: str) -> list[Session]:
    """Đọc output của `xpra list` thành danh sách phiên."""
    found: list[Session] = []
    for state, display in _LIST_RE.findall(output):
        found.append(Session(display=display, state=state.upper()))
    return found


def session_state(output: str, display: str) -> str:
    """Trạng thái của một display cụ thể trong output của `xpra list`."""
    for s in parse_sessions(output):
        if s.display == display:
            return s.state
    return "NONE"


def parse_version(output: str) -> tuple[int, ...] | None:
    """`xpra v6.2.1` -> (6, 2, 1). Trả None nếu không nhận ra."""
    m = _VERSION_RE.search(output.strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def format_version(parts: tuple[int, ...] | None) -> str:
    return ".".join(str(p) for p in parts) if parts else "?"


def ssh_hint(error: str, host: str) -> str:
    """Biến lỗi ssh thô thành câu gợi ý cụ thể.

    Bẫy hay gặp nhất là đặt `host` bằng tên máy tự nghĩ ra thay vì tên Tailscale
    thật — ssh chỉ báo "Name or service not known", không nói phải sửa ở đâu.
    """
    low = error.lower()
    if "not known" in low or "could not resolve" in low or "nodename nor servname" in low:
        return (
            f"không phân giải được tên {host!r}. Chạy `tailscale status` để lấy tên "
            f"thật (hoặc IP 100.x.y.z) rồi sửa `host` trong config."
        )
    if "permission denied" in low:
        return f"ssh từ chối. Chạy: ssh-copy-id {host}"
    if "connection refused" in low:
        return f"máy có trả lời nhưng không mở sshd. Trên {host}: sudo systemctl enable --now ssh"
    if "timed out" in low or "quá" in error:
        return f"{host} không phản hồi — máy tắt, hoặc Tailscale trên máy đó chưa lên."
    return f"thử tay: ssh {host}"


def version_gap(hub: tuple[int, ...] | None, node: tuple[int, ...] | None) -> str | None:
    """Cảnh báo nếu client (hub) và server (máy con) lệch thế hệ giao thức.

    xpra tương thích ngược trong cùng dòng major, nhưng client 3.x nối server
    6.x thì hỏng theo kiểu khó đoán. Đây là bẫy dễ dính nhất vì kho Ubuntu
    đứng ở 3.1.5 còn `onepane setup` cài 6.x lên máy con.
    """
    if not hub or not node:
        return None
    if hub[0] == node[0]:
        return None
    older, newer = ("hub", "máy con") if hub[0] < node[0] else ("máy con", "hub")
    return (
        f"lệch phiên bản: hub {format_version(hub)} vs máy con {format_version(node)} "
        f"— {older} cũ hơn {newer} một thế hệ, nên nâng cho khớp"
    )


def start_server_cmd(node: Node) -> str:
    """Lệnh chạy TRÊN máy con để dựng phiên seamless."""
    argv = ["xpra", "start", node.display, *SERVER_OPTS]
    for app in node.start_apps:
        argv += [f"--start-child={app}"]
    return quote_remote(argv)


def stop_server_cmd(node: Node) -> str:
    return quote_remote(["xpra", "stop", node.display])


def list_cmd() -> str:
    return "xpra list 2>&1 || true"


def version_cmd() -> str:
    return "xpra --version 2>&1 | head -1"


def launch_app_cmd(node: Node, argv: list[str]) -> str:
    """Mở một ứng dụng trong phiên đang chạy của node.

    Ưu tiên `xpra control ... start` vì xpra tự dựng đúng môi trường cho tiến
    trình con. Bản cũ không có control command này thì lùi về đặt DISPLAY thủ
    công — `setsid` + tách hẳn stdio để app không chết theo phiên ssh.
    """
    app = quote_remote(argv)
    control = quote_remote(["xpra", "control", node.display, "start", *argv])
    fallback = (
        f"DISPLAY={node.display} setsid {app} </dev/null >/dev/null 2>&1 &"
    )
    return f"{control} 2>/dev/null || ({fallback})"


def attach_argv(node: Node, hub: Hub) -> list[str]:
    """Lệnh chạy TRÊN hub để kéo cửa sổ của node về màn hình mình."""
    argv = ["xpra", "attach", node.xpra_uri()]
    if hub.title_format:
        argv.append("--title=" + hub.title_format.format(node=node.name))
    argv += hub.attach_opts
    return argv
