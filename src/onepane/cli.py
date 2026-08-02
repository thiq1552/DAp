"""CLI của onepane — một cửa vào cho nhiều máy."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import config as cfgmod
from . import tmux, xpra
from .config import Config, ConfigError, Node
from .remote import Result, run, run_script, state_dir

OK = "✓"
BAD = "✗"
WARN = "!"


def err(msg: str) -> None:
    print(f"{BAD} {msg}", file=sys.stderr)


def _template(name: str) -> str:
    return resources.files("onepane.templates").joinpath(name).read_text(encoding="utf-8")


def _provision_script(node: Node) -> str:
    """Ghép unit systemd vào script cài để chỉ tốn một lần ssh."""
    unit = _template("onepane-xpra@.service")
    script = _template("provision.sh").replace("__UNIT_BODY__", unit.rstrip("\n"))
    return f"export ONEPANE_DISPLAY={node.display_number}\n{script}"


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

    ver = run(node, cfg.hub, xpra.version_cmd(), timeout=15)
    info["xpra_version"] = xpra.parse_version(ver.stdout) if ver.ok else None
    info["xpra_installed"] = bool(ver.ok and ver.stdout.strip())

    if info["xpra_installed"]:
        listing = run(node, cfg.hub, xpra.list_cmd(), timeout=15)
        info["session"] = xpra.session_state(listing.stdout, node.display)
    else:
        info["session"] = "NONE"
    return info


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    nodes = cfg.select(args.nodes)
    failed = 0

    for node in nodes:
        print(f"\n── {node.name}  ({node.ssh_target}, display {node.display})")
        info = _probe(node, cfg)

        if not info["reachable"]:
            print(f"  {BAD} ssh: {info.get('error')}")
            if info.get("code") == 127:
                print("      cài client ssh cho máy hub: sudo apt install openssh-client")
            else:
                print(f"      thử: ssh {node.ssh_target} — máy có bật không? Tailscale đã lên chưa?")
            failed += 1
            continue
        print(f"  {OK} ssh")

        if not info["xpra_installed"]:
            print(f"  {BAD} xpra: chưa cài  →  onepane setup {node.name}")
            failed += 1
            continue

        version = info["xpra_version"]
        label = xpra.format_version(version)
        if version and version[0] < 4:
            print(f"  {WARN} xpra {label} — bản cũ trong kho Ubuntu, nên nâng: onepane setup {node.name}")
        else:
            print(f"  {OK} xpra {label}")

        state = info["session"]
        if state == "LIVE":
            print(f"  {OK} phiên {node.display} đang chạy")
        elif state == "DEAD":
            print(f"  {WARN} phiên {node.display} chết — dọn: onepane up {node.name}")
            failed += 1
        else:
            print(f"  {WARN} chưa có phiên {node.display}  →  onepane up {node.name}")

    print()
    if failed:
        print(f"{failed}/{len(nodes)} máy cần xử lý.")
    else:
        print(f"{OK} cả {len(nodes)} máy sẵn sàng.  Chạy: onepane attach --all")
    return 1 if failed else 0


# -------------------------------------------------------------------- setup


def cmd_setup(args: argparse.Namespace) -> int:
    cfg = Config.load(_config_path(args))
    nodes = cfg.select(args.nodes)
    failed = 0

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
        if res.ok:
            print(f"{OK} {node.name}: đã dựng phiên {node.display}")
        else:
            failed += 1
            print(f"{BAD} {node.name}: {res.message}")
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

    res = run(node, cfg.hub, xpra.launch_app_cmd(node, args.command), timeout=30)
    if not res.ok:
        err(f"{node.name}: {res.message}")
        return 1
    print(f"{OK} {node.name}: đã mở {' '.join(args.command)}")
    if not _attach_pid(node):
        print(f"{WARN} chưa nối tới {node.name} nên cửa sổ chưa hiện — chạy: onepane attach {node.name}")
    return 0


# ------------------------------------------------------------------- attach


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

    for node in cfg.select(args.nodes):
        if _attach_pid(node):
            print(f"{OK} {node.name}: đã nối sẵn")
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

        _pid_file(node).write_text(str(proc.pid))
        print(f"{OK} {node.name}: đang nối (pid {proc.pid}, log {log})")

    return 0


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
