"""CLI của onepane — một cửa vào cho nhiều máy."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path

from . import config as cfgmod
from . import tmux, xpra
from . import remote
from .config import Config, ConfigError, Node
from .remote import run, run_script, state_dir

OK = "✓"
BAD = "✗"
WARN = "!"

# Đợi trước khi kết luận client xpra nối được: nối hụt thì nó thoát gần như ngay.
ATTACH_SETTLE_S = 2.0


def err(msg: str) -> None:
    print(f"{BAD} {msg}", file=sys.stderr)


def _template(name: str) -> str:
    return resources.files("onepane.templates").joinpath(name).read_text(encoding="utf-8")


def _provision_script(node: Node | None) -> str:
    """Ghép unit systemd vào script cài để chỉ tốn một lần ssh.

    node=None nghĩa là cài cho chính máy hub — chỉ client, không dựng phiên.
    """
    unit = _template("onepane-xpra@.service")
    script = _template("provision.sh").replace("__UNIT_BODY__", unit.rstrip("\n"))
    if node is None:
        return f"export ONEPANE_ROLE=hub\n{script}"
    return (
        f"export ONEPANE_ROLE=node ONEPANE_DISPLAY={node.display_number}\n{script}"
    )


def _hub_xpra_version() -> tuple[int, ...] | None:
    """Phiên bản xpra trên máy hub, None nếu chưa cài."""
    if not remote.which("xpra"):
        return None
    return xpra.parse_version(remote.local_output(["xpra", "--version"]))


# --------------------------------------------------------------------- init


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.config).expanduser() if args.config else Config.default_path()
    written = cfgmod.write_template(path, force=args.force)
    print(f"{OK} đã tạo {written}")
    print("\nSửa lại `host`/`user` cho đúng máy của bạn, rồi chạy:")
    print("    onepane doctor")
    return 0


# ------------------------------------------------------------------- doctor


def _probe(node: Node, cfg: Config) -> dict[str, object]:
    """Kiểm tra một máy: ssh, xpra, phiên. Mỗi bước phụ thuộc bước trước."""
    info: dict[str, object] = {"node": node, "reachable": False}

    ping = run(node, cfg.hub, "echo onepane-ok", timeout=12)
    if not ping.ok or "onepane-ok" not in ping.stdout:
        info["error"] = ping.message
        info["code"] = ping.returncode
        return info
    info["reachable"] = True

    probe = run(node, cfg.hub, xpra.probe_cmd(), timeout=20)
    parsed = xpra.parse_probe(probe.stdout)
    info["xpra_installed"] = parsed.installed
    info["xpra_version"] = parsed.version
    info["session"] = (
        xpra.session_state(parsed.sessions, node.display) if parsed.installed else "NONE"
    )
    return info


def _check_hub() -> tuple[tuple[int, ...] | None, int]:
    """Kiểm tra máy hub. Trả (phiên bản xpra, số lỗi)."""
    print("── máy này (hub)")
    problems = 0

    for binary, hint in (
        ("ssh", "sudo apt install openssh-client"),
        ("tmux", "sudo apt install tmux"),
    ):
        if remote.which(binary):
            print(f"  {OK} {binary}")
        else:
            print(f"  {BAD} {binary}: chưa cài  →  {hint}")
            problems += 1

    version = _hub_xpra_version()
    if version is None:
        print(f"  {BAD} xpra: chưa cài  →  onepane setup --hub")
        problems += 1
    elif version[0] < 4:
        print(
            f"  {WARN} xpra {xpra.format_version(version)} — bản trong kho Ubuntu, "
            f"sẽ lệch với máy con  →  onepane setup --hub"
        )
    else:
        print(f"  {OK} xpra {xpra.format_version(version)}")

    return version, problems


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    nodes = cfg.select(args.nodes)
    hub_version, hub_problems = _check_hub()
    failed = 0

    for node in nodes:
        print(f"\n── {node.name}  ({node.ssh_target}, display {node.display})")
        info = _probe(node, cfg)

        if not info["reachable"]:
            print(f"  {BAD} ssh: {info.get('error')}")
            if info.get("code") == 127:
                print("      cài client ssh cho máy hub: sudo apt install openssh-client")
            else:
                print(f"      {xpra.ssh_hint(info.get('error') or '', node.ssh_target)}")
            failed += 1
            continue
        print(f"  {OK} ssh")

        if not info["xpra_installed"]:
            print(f"  {BAD} xpra: chưa cài  →  onepane setup {node.name}")
            failed += 1
            continue

        version = info["xpra_version"]
        label = xpra.format_version(version)
        if version is None:
            # Có lệnh xpra nhưng không đọc nổi phiên bản -> đừng báo xanh.
            print(f"  {WARN} xpra: có cài nhưng không đọc được phiên bản")
            failed += 1
        elif version[0] < 4:
            print(f"  {WARN} xpra {label} — bản cũ trong kho Ubuntu, nên nâng: onepane setup {node.name}")
        else:
            print(f"  {OK} xpra {label}")

        gap = xpra.version_gap(hub_version, version)
        if gap:
            print(f"  {WARN} {gap}")
            failed += 1

        state = info["session"]
        if state == "LIVE":
            print(f"  {OK} phiên {node.display} đang chạy")
        elif state == "DEAD":
            print(f"  {WARN} phiên {node.display} chết — dọn: onepane up {node.name}")
            failed += 1
        else:
            print(f"  {WARN} chưa có phiên {node.display}  →  onepane up {node.name}")

    print()
    if hub_problems:
        print(f"{BAD} máy hub thiếu {hub_problems} thứ — sửa trước, vì mọi thứ khác đi qua nó.")
    if failed:
        print(f"{BAD} {failed}/{len(nodes)} máy con cần xử lý.")
    if not hub_problems and not failed:
        print(f"{OK} hub và cả {len(nodes)} máy con đều sẵn sàng.  Chạy: onepane attach --all")
    return 1 if (hub_problems or failed) else 0


# -------------------------------------------------------------------- setup


def cmd_setup(args: argparse.Namespace) -> int:
    failed = 0

    if args.hub:
        print("── cài đặt máy này (hub)")
        print("   (sudo sẽ hỏi mật khẩu nếu cần — cứ nhập bình thường)")
        # Output chảy thẳng ra terminal để sudo hỏi được và bạn thấy apt chạy tới đâu.
        code = remote.run_local(_provision_script(None))
        if code == 0:
            print(f"  {OK} xong")
        else:
            failed += 1
            print(f"  {BAD} thất bại (mã {code})")
        # `--hub` một mình thì chỉ cài hub, không đụng máy con.
        if not args.nodes:
            return 1 if failed else 0

    cfg = Config.load(_config_path(args))
    nodes = cfg.select(args.nodes)

    for node in nodes:
        print(f"\n── cài đặt {node.name} ({node.ssh_target})")
        res = run_script(node, cfg.hub, _provision_script(node), timeout=900)
        for line in res.stdout.splitlines():
            if line.strip() and line.strip() != "PROVISION_OK":
                print(line if line.startswith("  ") else f"  {line}")
        if res.ok and "PROVISION_OK" in res.stdout:
            print(f"  {OK} xong")
        else:
            failed += 1
            print(f"  {BAD} thất bại: {res.message}")
            if res.stderr.strip():
                for line in res.stderr.strip().splitlines()[-5:]:
                    print(f"      {line}")

    return 1 if failed else 0


# ------------------------------------------------------------------ up/down


def cmd_up(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    failed = 0
    for node in cfg.select(args.nodes):
        listing = run(node, cfg.hub, xpra.list_cmd(), timeout=15)
        state = xpra.session_state(listing.stdout, node.display)
        if state == "LIVE":
            print(f"{OK} {node.name}: phiên {node.display} đã chạy sẵn")
            continue
        res = run(node, cfg.hub, xpra.start_server_cmd(node), timeout=60)
        if not res.ok:
            failed += 1
            print(f"{BAD} {node.name}: {res.message}")
            continue

        # `xpra start --daemon=yes` trả 0 ngay khi tách tiến trình, trước khi
        # biết server có trụ được không. Hỏi lại mới chắc.
        recheck = run(node, cfg.hub, xpra.list_cmd(), timeout=20)
        if xpra.session_state(recheck.stdout, node.display) == "LIVE":
            print(f"{OK} {node.name}: đã dựng phiên {node.display}")
        else:
            failed += 1
            print(f"{BAD} {node.name}: phiên {node.display} không trụ được sau khi dựng")
            for line in (res.stdout + res.stderr).strip().splitlines()[-3:]:
                print(f"      {line.strip()}")
    return 1 if failed else 0


def cmd_down(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    failed = 0
    for node in cfg.select(args.nodes):
        res = run(node, cfg.hub, xpra.stop_server_cmd(node), timeout=30)
        if res.ok:
            print(f"{OK} {node.name}: đã dừng phiên {node.display}")
        else:
            failed += 1
            print(f"{BAD} {node.name}: {res.message}")
    return 1 if failed else 0


# ---------------------------------------------------------------------- run


def cmd_run(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    node = cfg.node(args.node)
    if not args.command:
        err("thiếu lệnh cần chạy. Ví dụ: onepane run vivo firefox")
        return 2

    # Kiểm tra phiên trước: `launch_app_cmd` có nhánh dự phòng chạy nền nên gần
    # như luôn trả 0, kể cả khi không có phiên nào để mở app vào.
    state, problem = _require_live_session(node, cfg)
    if problem:
        err(f"{node.name}: {problem}")
        return 1

    res = run(node, cfg.hub, xpra.launch_app_cmd(node, args.command), timeout=30)
    if not res.ok:
        err(f"{node.name}: {res.message}")
        return 1
    print(f"{OK} {node.name}: đã mở {' '.join(args.command)}")
    if not _attach_pid(node):
        print(f"{WARN} chưa nối tới {node.name} nên cửa sổ chưa hiện — chạy: onepane attach {node.name}")
    return 0


# ------------------------------------------------------------------- attach


def _require_live_session(node: Node, cfg: Config) -> tuple[str, str | None]:
    """(trạng thái phiên, lý do không dùng được). Lý do None nghĩa là sẵn sàng."""
    probe = run(node, cfg.hub, xpra.probe_cmd(), timeout=20)
    if not probe.ok and not probe.stdout.strip():
        return "UNKNOWN", f"không hỏi được máy này: {probe.message}"

    parsed = xpra.parse_probe(probe.stdout)
    if not parsed.installed:
        return "NONE", f"chưa cài xpra  →  onepane setup {node.name}"

    state = xpra.session_state(parsed.sessions, node.display)
    if state != "LIVE":
        return state, f"chưa có phiên {node.display}  →  onepane up {node.name}"
    return state, None


def _tail(path: Path, count: int) -> list[str]:
    """Vài dòng cuối của file log, bỏ dòng trống."""
    try:
        lines = [ln.strip() for ln in path.read_text(errors="replace").splitlines()]
    except OSError:
        return []
    return [ln for ln in lines if ln][-count:]


def _pid_file(node: Node) -> Path:
    return state_dir() / f"attach-{node.name}.pid"


def _attach_pid(node: Node) -> int | None:
    """PID của client xpra đang nối tới node, None nếu không có."""
    pf = _pid_file(node)
    if not pf.exists():
        return None
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)  # chỉ kiểm tra tiến trình còn sống
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        pf.unlink(missing_ok=True)
        return None
    return pid


def cmd_attach(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    failed = 0

    for node in cfg.select(args.nodes):
        if _attach_pid(node):
            print(f"{OK} {node.name}: đã nối sẵn")
            continue

        # Nối vào phiên không tồn tại thì client chết ngay sau khi Popen trả về.
        # Hỏi trước để báo đúng việc cần làm thay vì in ✓ rồi để bạn tự phát hiện.
        _, problem = _require_live_session(node, cfg)
        if problem:
            print(f"{BAD} {node.name}: {problem}")
            failed += 1
            continue

        argv = xpra.attach_argv(node, cfg.hub)
        log = state_dir() / f"attach-{node.name}.log"
        try:
            with log.open("wb") as fh:
                proc = subprocess.Popen(
                    argv,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except FileNotFoundError:
            err("không tìm thấy `xpra` trên máy này — cài xpra cho máy hub trước")
            return 1

        # Client xpra hỏng thì chết trong khoảng một giây; đợi rồi kiểm tra lại
        # mới biết là nối được thật hay chỉ mới sinh ra tiến trình.
        time.sleep(ATTACH_SETTLE_S)
        if proc.poll() is not None:
            failed += 1
            print(f"{BAD} {node.name}: client thoát ngay (mã {proc.returncode})")
            for line in _tail(log, 3):
                print(f"      {line}")
            print(f"      log đầy đủ: {log}")
            continue

        _pid_file(node).write_text(str(proc.pid))
        print(f"{OK} {node.name}: đã nối (pid {proc.pid})")

    return 1 if failed else 0


def cmd_detach(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    for node in cfg.select(args.nodes):
        pid = _attach_pid(node)
        if not pid:
            print(f"{WARN} {node.name}: không có kết nối nào")
            continue
        os.kill(pid, signal.SIGTERM)
        _pid_file(node).unlink(missing_ok=True)
        # Ứng dụng bên máy con vẫn chạy — đây chỉ là ngắt phần hiển thị.
        print(f"{OK} {node.name}: đã ngắt hiển thị (ứng dụng vẫn chạy bên đó)")
    return 0


# ------------------------------------------------------------------- status


def cmd_status(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    nodes = cfg.select(args.nodes, include_disabled=True)

    rows = []
    for node in nodes:
        if not node.enabled:
            rows.append((node.name, "tắt", "-", "-"))
            continue
        info = _probe(node, cfg)
        if not info["reachable"]:
            rows.append((node.name, "không tới được", "-", "-"))
            continue
        session = str(info["session"])
        session_label = {"LIVE": "đang chạy", "DEAD": "chết", "NONE": "chưa có"}.get(
            session, session
        )
        attached = "có" if _attach_pid(node) else "không"
        rows.append((node.name, "online", session_label, attached))

    width = max((len(r[0]) for r in rows), default=4)
    print(f"{'MÁY'.ljust(width)}  {'KẾT NỐI':<16} {'PHIÊN':<12} HIỂN THỊ")
    for name, conn, session, attached in rows:
        print(f"{name.ljust(width)}  {conn:<16} {session:<12} {attached}")
    return 0


# --------------------------------------------------------------------- term


def cmd_term(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    nodes = cfg.select(args.nodes)

    if subprocess.run(tmux.has_session_command(cfg), capture_output=True).returncode == 0:
        if args.recreate:
            subprocess.run(tmux.kill_session_command(cfg), capture_output=True)
        else:
            print(f"{OK} nối vào phiên tmux '{cfg.hub.tmux_session}' đang có")
            return subprocess.run(tmux.attach_command(cfg)).returncode

    for command in tmux.build_commands(cfg, nodes):
        res = subprocess.run(command, capture_output=True, text=True)
        if res.returncode != 0:
            err(f"tmux lỗi: {res.stderr.strip() or ' '.join(command)}")
            return 1

    print(f"{OK} đã dựng phiên '{cfg.hub.tmux_session}' với {len(nodes)} cửa sổ")
    print("   Ctrl-b <số>  đổi máy    Ctrl-b d  thoát (phiên vẫn chạy)")
    return subprocess.run(tmux.attach_command(cfg)).returncode


# --------------------------------------------------------------------- main


def _config_path(args: argparse.Namespace) -> Path | None:
    return Path(args.config).expanduser() if args.config else None


def _add_nodes_arg(p: argparse.ArgumentParser, help_text: str) -> None:
    p.add_argument("nodes", nargs="*", help=help_text)
    p.add_argument("--all", action="store_true", help="áp dụng cho mọi máy (mặc định)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="onepane",
        description="Gộp cửa sổ và terminal của nhiều máy Linux về một màn hình. "
        "Ứng dụng vẫn chạy trên máy của nó — chỉ phần hiển thị được gộp lại.",
    )
    p.add_argument("--config", help="đường dẫn file cấu hình khác mặc định")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="tạo file cấu hình mẫu")
    s.add_argument("--force", action="store_true", help="ghi đè file đã có")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", help="kiểm tra ssh / xpra / phiên trên từng máy")
    _add_nodes_arg(s, "tên máy cần kiểm tra; bỏ trống = tất cả")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("setup", help="cài xpra + systemd lên máy con (chạy lại được)")
    _add_nodes_arg(s, "tên máy cần cài; bỏ trống = tất cả")
    s.add_argument(
        "--hub",
        action="store_true",
        help="cài cho chính máy này (client xpra + tmux), không dựng phiên server",
    )
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("up", help="dựng phiên xpra trên máy con")
    _add_nodes_arg(s, "tên máy; bỏ trống = tất cả")
    s.set_defaults(func=cmd_up)

    s = sub.add_parser("down", help="dừng phiên xpra (đóng mọi ứng dụng trong đó)")
    _add_nodes_arg(s, "tên máy; bỏ trống = tất cả")
    s.set_defaults(func=cmd_down)

    s = sub.add_parser("run", help="mở một ứng dụng trên máy con, cửa sổ hiện ở đây")
    s.add_argument("node", help="tên máy")
    s.add_argument("command", nargs=argparse.REMAINDER, help="lệnh cần chạy")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("attach", help="kéo cửa sổ của máy con về màn hình này")
    _add_nodes_arg(s, "tên máy; bỏ trống = tất cả")
    s.set_defaults(func=cmd_attach)

    s = sub.add_parser("detach", help="ngắt hiển thị (ứng dụng bên kia vẫn chạy)")
    _add_nodes_arg(s, "tên máy; bỏ trống = tất cả")
    s.set_defaults(func=cmd_detach)

    s = sub.add_parser("status", help="bảng trạng thái toàn cụm")
    _add_nodes_arg(s, "tên máy; bỏ trống = tất cả")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("term", help="phiên tmux một cửa sổ mỗi máy")
    _add_nodes_arg(s, "tên máy; bỏ trống = tất cả")
    s.add_argument("--recreate", action="store_true", help="xoá phiên cũ rồi dựng lại")
    s.set_defaults(func=cmd_term)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        err(str(exc))
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
