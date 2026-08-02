"""Chạy lệnh trên máy từ xa qua ssh.

Mọi thứ đi qua ssh (trên nền Tailscale) — không mở cổng TCP nào ra ngoài, nên
không phải nghĩ tới token hay TLS cho lớp giao diện này.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Hub, Node

DEFAULT_TIMEOUT = 20


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or "~/.local/state"
    d = Path(base).expanduser() / "onepane"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def message(self) -> str:
        """Dòng lỗi gọn nhất có thể hiển thị cho người dùng."""
        text = (self.stderr or self.stdout).strip()
        return text.splitlines()[-1] if text else f"lệnh thoát với mã {self.returncode}"


def ssh_command(node: Node, hub: Hub) -> list[str]:
    """Phần đầu của lệnh ssh, chưa gồm lệnh cần chạy."""
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if hub.ssh_multiplex:
        # Kết nối đầu mở master, các lệnh sau bám vào -> nhanh hơn hẳn khi
        # `doctor`/`status` gọi ssh nhiều lần liên tiếp.
        socket = state_dir() / "ssh-%C"
        cmd += [
            "-o",
            "ControlMaster=auto",
            "-o",
            f"ControlPath={socket}",
            "-o",
            "ControlPersist=60",
        ]
    if node.ssh_port != 22:
        cmd += ["-p", str(node.ssh_port)]
    cmd += node.ssh_opts
    cmd.append(node.ssh_target)
    return cmd


def run(
    node: Node,
    hub: Hub,
    remote_cmd: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> Result:
    """Chạy `remote_cmd` (chuỗi shell) trên node, trả về kết quả đã bắt sẵn."""
    argv = ssh_command(node, hub) + [remote_cmd]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(124, "", f"ssh tới {node.host} quá {timeout}s không phản hồi")
    except FileNotFoundError:
        return Result(127, "", "không tìm thấy lệnh `ssh` trên máy này")
    return Result(proc.returncode, proc.stdout, proc.stderr)


def run_script(node: Node, hub: Hub, script: str, *, timeout: int = 300) -> Result:
    """Đẩy một script bash qua stdin — tránh phải escape nhiều tầng."""
    argv = ssh_command(node, hub) + ["bash -s"]
    try:
        proc = subprocess.run(
            argv,
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(124, "", f"script trên {node.host} chạy quá {timeout}s")
    except FileNotFoundError:
        return Result(127, "", "không tìm thấy lệnh `ssh` trên máy này")
    return Result(proc.returncode, proc.stdout, proc.stderr)


def run_local(script: str, *, timeout: int = 900) -> Result:
    """Chạy script bash ngay trên máy hub (không qua ssh)."""
    try:
        proc = subprocess.run(
            ["bash", "-s"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(124, "", f"script chạy quá {timeout}s")
    return Result(proc.returncode, proc.stdout, proc.stderr)


def which(binary: str) -> str | None:
    """Đường dẫn tới một lệnh trên máy hub, None nếu chưa cài."""
    return shutil.which(binary)


def local_output(argv: list[str], *, timeout: int = 10) -> str:
    """Chạy một lệnh trên hub và lấy stdout+stderr; chuỗi rỗng nếu lỗi."""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return proc.stdout + proc.stderr


def quote_remote(argv: list[str]) -> str:
    """Ghép argv thành một chuỗi shell an toàn để chạy ở đầu bên kia."""
    return " ".join(shlex.quote(a) for a in argv)
