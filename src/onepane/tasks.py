"""Task — một terminal có tên, sống dai, ghim cứng vào một máy.

Mỗi task là một phiên tmux chạy **trên chính máy con**, tên `op-<tên task>`.
Ba tính chất quan trọng suy ra từ đó:

- **Không bao giờ di chuyển.** Phiên nằm trên máy nào thì chạy ở máy đó. Việc
  như quét Zalo bằng trình duyệt đã đăng nhập sẵn không thể bị kéo sang máy
  khác làm mất phiên — đơn giản vì chẳng có gì bị kéo đi.
- **Không chết khi mất kết nối.** Bạn rớt mạng, đóng laptop, tắt máy hub — tiến
  trình vẫn chạy tiếp trên máy con. Nối lại là thấy đúng chỗ đang dở.
- **Không cần sổ ghi chép.** Danh sách task lấy trực tiếp từ `tmux ls` của từng
  máy, nên nó luôn khớp thực tế; không có file trạng thái nào để lệch.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

PREFIX = "op-"

# tmux dùng `:` để ngăn session:window và `.` cho pane, nên tên chứa hai ký tự
# này sẽ bị hiểu nhầm ở mọi lệnh sau đó. Dấu cách và tiếng Việt thì thoải mái.
FORBIDDEN = (":", ".")


class TaskError(Exception):
    """Sai tên task hoặc không tìm thấy — thông báo đã ở dạng đọc được."""


def validate(name: str) -> str:
    name = name.strip()
    if not name:
        raise TaskError("tên task không được để trống")
    for ch in FORBIDDEN:
        if ch in name:
            raise TaskError(f"tên task không được chứa {ch!r} (tmux dùng ký tự này)")
    if name.startswith(PREFIX):
        raise TaskError(f"đừng tự thêm {PREFIX!r} vào tên — onepane tự thêm")
    return name


def session_name(name: str) -> str:
    return PREFIX + validate(name)


@dataclass(frozen=True)
class Task:
    node: str
    name: str
    windows: int
    attached: bool

    @property
    def label(self) -> str:
        """Nhãn hiện trên cửa sổ tmux của hub: biết ngay việc gì, máy nào."""
        return f"{self.name} · {self.node}"

    @property
    def ref(self) -> str:
        """Cách gọi không nhập nhằng khi hai máy trùng tên task."""
        return f"{self.node}/{self.name}"


def list_cmd() -> str:
    """Lệnh chạy TRÊN máy con để liệt kê task. Không có task thì im lặng."""
    fmt = "#{session_name}\t#{session_windows}\t#{session_attached}"
    return f"tmux ls -F {shlex.quote(fmt)} 2>/dev/null || true"


def parse_list(node: str, output: str) -> list[Task]:
    """Đọc output của list_cmd(), bỏ qua phiên tmux không phải của onepane."""
    tasks: list[Task] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].startswith(PREFIX):
            continue
        name = parts[0][len(PREFIX) :]
        try:
            windows = int(parts[1])
            attached = int(parts[2]) > 0
        except ValueError:
            continue
        tasks.append(Task(node=node, name=name, windows=windows, attached=attached))
    return sorted(tasks, key=lambda t: t.name)


# Copy ở máy con phải về được clipboard của hub, nếu không thì không thể lấy
# kết quả của task máy này làm đầu vào cho task máy kia.
#
# Chữ trên màn hình là do tmux của máy con vẽ, nên bôi đen chỉ vào bộ đệm của
# tmux đó. OSC 52 là đường đưa nội dung ngược lại: tmux gói nội dung vào một
# escape sequence, nó chảy qua ssh về terminal trên hub, terminal đặt vào
# clipboard hệ thống. Từ đó dán vào cửa sổ nào cũng được.
#
# `set-clipboard on` bật đường đó; `terminal-features ...clipboard` khai báo là
# terminal đầu kia hiểu OSC 52 (VTE 0.64+ có, tức GNOME Terminal trên 24.04).
CLIPBOARD_SETUP = (
    "tmux set -s set-clipboard on 2>/dev/null; "
    "tmux set -as terminal-features ',*:clipboard' 2>/dev/null"
)


def create_cmd(name: str, command: list[str] | None = None) -> str:
    """Tạo task chạy nền trên máy con. Đã tồn tại thì không đụng tới."""
    sess = shlex.quote(session_name(name))
    argv = ["tmux", "new-session", "-d", "-s", sess]
    if command:
        # `exec` để tiến trình thật thay chỗ shell: task kết thúc đúng lúc lệnh
        # kết thúc, không để lại một shell rỗng trông như vẫn đang chạy.
        argv.append(shlex.quote("exec " + " ".join(shlex.quote(c) for c in command)))
    create = " ".join(argv)
    return f"{CLIPBOARD_SETUP}; tmux has-session -t {sess} 2>/dev/null || {create}"


def kill_cmd(name: str) -> str:
    sess = shlex.quote(session_name(name))
    return f"tmux kill-session -t {sess}"


def open_argv(ssh_prefix: list[str], name: str) -> list[str]:
    """Lệnh chạy TRÊN hub để mở terminal của task.

    `new-session -A` = nối nếu đã có, tạo nếu chưa. Nên `open` một task chưa tồn
    tại vẫn chạy được thay vì báo lỗi rồi bắt gõ thêm lệnh tạo.
    """
    sess = session_name(name)
    # Đặt clipboard mỗi lần mở: task tạo bằng `open` (chưa qua `new`) vẫn phải
    # copy được, và đây là lệnh rẻ, chạy lại bao nhiêu lần cũng không sao.
    return [
        *ssh_prefix,
        "-t",
        f"{CLIPBOARD_SETUP}; tmux new-session -A -s {shlex.quote(sess)}",
    ]


def resolve(tasks: list[Task], ref: str) -> Task:
    """Tìm task theo `tên` hoặc `máy/tên`. Trùng tên thì bắt nói rõ máy nào."""
    if "/" in ref:
        node, _, name = ref.partition("/")
        for t in tasks:
            if t.node == node and t.name == name:
                return t
        raise TaskError(f"không có task {ref!r}")

    hits = [t for t in tasks if t.name == ref]
    if not hits:
        known = ", ".join(t.ref for t in tasks) or "(chưa có task nào)"
        raise TaskError(f"không có task {ref!r}. Đang có: {known}")
    if len(hits) > 1:
        options = ", ".join(t.ref for t in hits)
        raise TaskError(f"tên {ref!r} có ở nhiều máy — gõ rõ một trong: {options}")
    return hits[0]
