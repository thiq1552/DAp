"""Một phiên tmux duy nhất, mỗi máy một cửa sổ.

Phần lớn công việc thật sự (Claude Code, build, log) là terminal — và với
terminal thì tmux cho cảm giác "một máy" tốt hơn hẳn mọi thứ đồ hoạ: chuyển máy
bằng một phím, không độ trễ vẽ hình, dùng được từ điện thoại qua Tailscale SSH,
và phiên vẫn sống khi bạn ngắt kết nối.
"""

from __future__ import annotations

import shlex

from .config import Config, Node
from .remote import ssh_command


def _window_command(node: Node, cfg: Config) -> str:
    """Lệnh ssh cho một cửa sổ, có vòng lặp thử lại khi máy đang tắt."""
    ssh = " ".join(shlex.quote(a) for a in ssh_command(node, cfg.hub))
    # Máy con tắt/ngủ thì cửa sổ không biến mất — nó chờ và tự nối lại. Đây là
    # điểm khác biệt so với `tmux new-window ssh ...` trần: cửa sổ đó sẽ đóng
    # ngay khi ssh thoát và bạn mất luôn vị trí trong phiên.
    return (
        f"while true; do {ssh}; "
        f'echo; echo "[onepane] mất kết nối tới {node.name} — Enter để thử lại, Ctrl-C để đóng"; '
        f"read -r || exit 0; done"
    )


def build_commands(cfg: Config, nodes: list[Node]) -> list[list[str]]:
    """Danh sách lệnh tmux cần chạy để dựng phiên. Trả về để test được."""
    session = cfg.hub.tmux_session
    cmds: list[list[str]] = []

    first, rest = nodes[0], nodes[1:]
    cmds.append(
        ["tmux", "new-session", "-d", "-s", session, "-n", first.name,
         _window_command(first, cfg)]
    )
    for node in rest:
        cmds.append(
            ["tmux", "new-window", "-t", session, "-n", node.name,
             _window_command(node, cfg)]
        )

    cmds.append(["tmux", "set-option", "-t", session, "mouse", "on"])
    # Đánh số cửa sổ từ 1 để khớp với hàng phím số trên bàn phím.
    cmds.append(["tmux", "set-option", "-t", session, "base-index", "1"])
    cmds.append(["tmux", "select-window", "-t", f"{session}:1"])
    return cmds


def attach_command(cfg: Config) -> list[str]:
    return ["tmux", "attach-session", "-t", cfg.hub.tmux_session]


def has_session_command(cfg: Config) -> list[str]:
    return ["tmux", "has-session", "-t", cfg.hub.tmux_session]


def kill_session_command(cfg: Config) -> list[str]:
    return ["tmux", "kill-session", "-t", cfg.hub.tmux_session]
