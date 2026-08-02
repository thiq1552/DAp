"""Màn hình tổng hợp trên hub: mỗi task một cửa sổ.

Phần lớn công việc thật sự (Claude Code, build, log, script chạy dài) là
terminal — và với terminal thì tmux cho cảm giác "một máy" tốt hơn hẳn mọi thứ
đồ hoạ: chuyển việc bằng một phím, không độ trễ vẽ hình, dùng được từ điện
thoại qua Tailscale SSH, và mọi thứ vẫn sống khi bạn ngắt kết nối.

Có hai tầng tmux: tầng ngoài trên hub (gom cửa sổ) và tầng trong trên từng máy
con (giữ tiến trình sống). Để hai tầng không tranh phím, tầng ngoài đổi phím
dẫn sang `Ctrl-a`, tầng trong giữ nguyên `Ctrl-b` mặc định.
"""

from __future__ import annotations

import shlex

from .config import Config, Node
from .remote import ssh_command
from .tasks import Task, open_argv

# Phím dẫn của tầng ngoài. Khác mặc định để không đụng tmux trên máy con.
HUB_PREFIX = "C-a"


def _quote(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)


def _resilient(inner: str, label: str) -> str:
    """Bọc lệnh trong vòng lặp thử lại khi máy con tắt hoặc rớt mạng.

    Không có lớp này thì `tmux new-window ssh ...` đóng cửa sổ ngay khi ssh
    thoát — mất luôn vị trí trong phiên, và mất cả nhãn cho biết đó là việc gì.
    """
    return (
        f"while true; do {inner}; "
        f'echo; echo "[onepane] mất kết nối: {label} — Enter để nối lại, Ctrl-C để đóng"; '
        f"read -r || exit 0; done"
    )


def task_window_command(task: Task, node: Node, cfg: Config) -> str:
    """Lệnh cho một cửa sổ: ssh vào máy con rồi bám vào phiên tmux của task."""
    ssh = ssh_command(node, cfg.hub)
    return _resilient(_quote(open_argv(ssh, task.name)), task.label)


def shell_window_command(node: Node, cfg: Config) -> str:
    """Cửa sổ shell trần cho một máy — dùng khi máy đó chưa có task nào."""
    return _resilient(_quote(ssh_command(node, cfg.hub)), f"shell {node.name}")


def build_commands(cfg: Config, windows: list[tuple[str, str]]) -> list[list[str]]:
    """Dựng phiên tmux của hub. `windows` là danh sách (nhãn, lệnh).

    Trả về danh sách lệnh thay vì tự chạy để test được mà không cần tmux thật.
    """
    session = cfg.hub.tmux_session
    cmds: list[list[str]] = []

    (first_label, first_cmd), rest = windows[0], windows[1:]
    cmds.append(
        ["tmux", "new-session", "-d", "-s", session, "-n", first_label, first_cmd]
    )
    for label, command in rest:
        cmds.append(["tmux", "new-window", "-t", session, "-n", label, command])

    opt = ["tmux", "set-option", "-t", session]
    cmds.append([*opt, "mouse", "on"])
    # Tầng ngoài cũng phải cho OSC 52 đi qua, nếu không chuỗi từ máy con dừng
    # ở đây và clipboard của hub không bao giờ nhận được gì. Đây là tuỳ chọn
    # cấp server (-s) nên không gắn với phiên nào.
    cmds.append(["tmux", "set-option", "-s", "set-clipboard", "on"])
    cmds.append(["tmux", "set-option", "-as", "terminal-features", ",*:clipboard"])
    # Bôi đen bằng chuột xong nhả tay là copy luôn, khỏi phải nhớ phím.
    cmds.append(
        ["tmux", "bind-key", "-T", "copy-mode", "MouseDragEnd1Pane",
         "send-keys", "-X", "copy-pipe-and-cancel"]
    )
    # Đánh số từ 1 để khớp hàng phím số trên bàn phím.
    cmds.append([*opt, "base-index", "1"])
    cmds.append([*opt, "prefix", HUB_PREFIX])
    # Nhấn phím dẫn hai lần để gửi nó xuống ứng dụng bên trong.
    cmds.append(["tmux", "bind-key", "-T", "prefix", HUB_PREFIX, "send-prefix"])
    # Thanh trạng thái nói rõ đang ở cửa sổ nào, vì đó là thứ phân biệt máy.
    cmds.append([*opt, "status-left", " onepane "])
    cmds.append([*opt, "status-left-length", "12"])
    cmds.append([*opt, "window-status-format", " #I #W "])
    cmds.append([*opt, "window-status-current-format", " #I #W "])
    cmds.append(["tmux", "select-window", "-t", f"{session}:1"])
    return cmds


def list_windows_command(cfg: Config) -> list[str]:
    return ["tmux", "list-windows", "-t", cfg.hub.tmux_session, "-F", "#{window_name}"]


def add_window_command(cfg: Config, label: str, command: str) -> list[str]:
    """Thêm cửa sổ vào phiên đang chạy mà không nhảy sang nó (-d)."""
    return ["tmux", "new-window", "-d", "-t", cfg.hub.tmux_session, "-n", label, command]


def attach_command(cfg: Config) -> list[str]:
    return ["tmux", "attach-session", "-t", cfg.hub.tmux_session]


def has_session_command(cfg: Config) -> list[str]:
    return ["tmux", "has-session", "-t", cfg.hub.tmux_session]


def kill_session_command(cfg: Config) -> list[str]:
    return ["tmux", "kill-session", "-t", cfg.hub.tmux_session]
