"""Task: terminal có tên, ghim vào một máy, sống qua mất kết nối."""

from __future__ import annotations

import pytest

from onepane import tasks
from onepane.tasks import Task, TaskError


# ------------------------------------------------------------------ tên task


def test_validate_rejects_tmux_metacharacters():
    # tmux hiểu `:` là session:window và `.` là pane — tên chứa chúng sẽ làm
    # mọi lệnh sau đó trỏ sai chỗ.
    for bad in ("zalo:quét", "zalo.quét"):
        with pytest.raises(TaskError, match="tmux"):
            tasks.validate(bad)


def test_validate_allows_spaces_and_vietnamese():
    assert tasks.validate("zalo quét") == "zalo quét"
    assert tasks.session_name("zalo quét") == "op-zalo quét"


def test_validate_rejects_manual_prefix():
    with pytest.raises(TaskError, match="tự thêm"):
        tasks.validate("op-zalo")


def test_validate_rejects_empty():
    with pytest.raises(TaskError):
        tasks.validate("   ")


# -------------------------------------------------------------- đọc danh sách


def test_parse_list_ignores_foreign_tmux_sessions():
    """Máy con có thể đã có tmux riêng của người dùng — không được đụng vào."""
    out = "op-zalo quét\t2\t1\nviec-rieng-cua-toi\t1\t0\nop-build\t1\t0\n"
    found = tasks.parse_list("may-nha", out)
    assert [t.name for t in found] == ["build", "zalo quét"]
    assert next(t for t in found if t.name == "zalo quét").attached is True
    assert next(t for t in found if t.name == "build").attached is False


def test_parse_list_survives_garbage():
    assert tasks.parse_list("n", "") == []
    assert tasks.parse_list("n", "op-x\tkhông-phải-số\t0\n") == []


def test_task_label_shows_work_and_machine():
    t = Task(node="may-nha", name="zalo quét", windows=1, attached=False)
    assert t.label == "zalo quét · may-nha"
    assert t.ref == "may-nha/zalo quét"


# ------------------------------------------------------------------ dựng lệnh


def test_create_is_idempotent():
    """Chạy lại không được đá phiên đang chạy — đó là mất việc đang dở."""
    cmd = tasks.create_cmd("zalo quét")
    assert "has-session" in cmd
    assert cmd.index("has-session") < cmd.index("new-session")


def test_create_with_command_uses_exec():
    cmd = tasks.create_cmd("quét", ["python3", "run.py", "--once"])
    assert "exec python3 run.py --once" in cmd


def test_open_attaches_or_creates():
    argv = tasks.open_argv(["ssh", "thi@may-nha"], "zalo quét")
    assert argv[:2] == ["ssh", "thi@may-nha"]
    assert "-t" in argv  # cần tty, nếu không tmux từ chối chạy
    body = argv[-1]
    # Tạo (nếu chưa có) -> đặt tuỳ chọn -> mới nối; `-A` không còn chỗ đặt tuỳ chọn.
    assert "has-session -t 'op-zalo quét'" in body
    assert "attach-session -t 'op-zalo quét'" in body
    assert body.index("has-session") < body.index("attach-session")


# ----------------------------------------------------------------- clipboard


def test_open_enables_clipboard_forwarding():
    """Không có OSC 52 thì copy ở máy con không bao giờ tới clipboard của hub."""
    body = tasks.open_argv(["ssh", "n"], "x")[-1]
    assert "set-clipboard on" in body
    assert "clipboard" in body
    assert body.index("set-clipboard") < body.index("new-session")


def test_create_enables_clipboard_forwarding():
    assert "set-clipboard on" in tasks.create_cmd("x")


def test_clipboard_setup_never_breaks_the_command():
    """Máy con dùng tmux quá cũ không hiểu terminal-features -> phải nuốt lỗi,
    vì mở được terminal vẫn quan trọng hơn là copy được."""
    assert tasks.CLIPBOARD_SETUP.count("2>/dev/null") == 2


# ------------------------------------------------------------------- resolve


def _two_machines():
    return [
        Task(node="may-nha", name="zalo quét", windows=1, attached=False),
        Task(node="thi-pc", name="zalo quét", windows=1, attached=False),
        Task(node="may-nha", name="build", windows=1, attached=False),
    ]


def test_resolve_by_bare_name():
    assert tasks.resolve(_two_machines(), "build").node == "may-nha"


def test_resolve_refuses_to_guess_when_ambiguous():
    """Trùng tên ở hai máy thì đoán bừa là mở nhầm việc — phải hỏi lại."""
    with pytest.raises(TaskError, match="nhiều máy"):
        tasks.resolve(_two_machines(), "zalo quét")


def test_resolve_qualified_name():
    assert tasks.resolve(_two_machines(), "thi-pc/zalo quét").node == "thi-pc"


def test_resolve_unknown_lists_what_exists():
    with pytest.raises(TaskError, match="may-nha/build"):
        tasks.resolve(_two_machines(), "khong-co")


# ------------------------------------------------- gom cửa sổ vào phiên có sẵn


def test_add_window_does_not_steal_focus():
    """Thêm cửa sổ cho task mới không được nhảy màn hình khỏi việc đang làm."""
    from onepane import tmux
    from onepane.config import Config, Hub, Node

    cfg = Config(hub=Hub(tmux_session="cum"), nodes=[Node(name="a", host="a")])
    cmd = tmux.add_window_command(cfg, "viec · a", "echo x")
    assert cmd[:3] == ["tmux", "new-window", "-d"]
    assert "cum" in cmd


def test_window_labels_are_not_auto_renamed():
    """tmux đổi tên cửa sổ thành 'ssh' thì mất nhãn máy, và sync thêm trùng."""
    from onepane import tmux
    from onepane.config import Config, Hub, Node

    cfg = Config(hub=Hub(tmux_session="cum"), nodes=[Node(name="a", host="a")])
    opts = tmux.session_option_commands(cfg)
    # `-wg` chứ không phải `-t <phiên>`: đây là tuỳ chọn CỬA SỔ, đặt theo phiên
    # chỉ trúng cửa sổ đang mở nên các cửa sổ khác vẫn bị đổi tên.
    assert ["tmux", "set-option", "-wg", "automatic-rename", "off"] in opts
    assert ["tmux", "set-option", "-wg", "allow-rename", "off"] in opts


def test_build_applies_the_same_options_as_sync():
    """Phiên dựng mới và phiên áp lại phải giống nhau, nếu không hành vi lệch."""
    from onepane import tmux
    from onepane.config import Config, Hub, Node

    cfg = Config(hub=Hub(tmux_session="cum"), nodes=[Node(name="a", host="a")])
    built = tmux.build_commands(cfg, [("x", "echo 1")])
    for opt in tmux.session_option_commands(cfg):
        assert opt in built


def test_inner_status_bar_is_hidden():
    """Hai thanh trạng thái chồng nhau: hub đã ghi đủ việc gì/máy nào."""
    assert "status off" in tasks.session_setup("'op-x'")
    assert "status off" in tasks.open_argv(["ssh", "n"], "x")[-1]


def test_window_list_reports_real_tmux_index():
    """In số bằng bộ đếm Python thì lệch với số thật của tmux -> bấm sai cửa sổ."""
    from onepane import tmux
    from onepane.config import Config, Hub, Node

    cfg = Config(hub=Hub(tmux_session="cum"), nodes=[Node(name="a", host="a")])
    assert "#{window_index}" in tmux.list_windows_command(cfg)[-1]
    # base-index chỉ áp cho cửa sổ tạo sau, nên phải đánh số lại tường minh.
    assert tmux.renumber_command(cfg)[:3] == ["tmux", "move-window", "-r"]
