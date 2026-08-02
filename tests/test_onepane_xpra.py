from onepane import tmux, xpra
from onepane.config import Config, Hub, Node
from onepane.remote import ssh_command

VIVO = Node(name="vivo", host="vivo", user="thi", display=":100")


def test_parse_sessions_reads_live_and_dead():
    out = """Found the following xpra sessions:
/run/user/1000/xpra:
\tLIVE session at :100
\tDEAD session at :7
"""
    sessions = xpra.parse_sessions(out)
    assert [(s.display, s.state) for s in sessions] == [(":100", "LIVE"), (":7", "DEAD")]
    assert sessions[0].live is True
    assert sessions[1].live is False


def test_session_state_for_specific_display():
    out = "\tLIVE session at :100\n\tDEAD session at :7\n"
    assert xpra.session_state(out, ":100") == "LIVE"
    assert xpra.session_state(out, ":7") == "DEAD"
    assert xpra.session_state(out, ":55") == "NONE"
    assert xpra.session_state("", ":100") == "NONE"


def test_session_state_when_no_sessions():
    assert xpra.session_state("No xpra sessions found", ":100") == "NONE"


def test_parse_version_handles_both_package_styles():
    assert xpra.parse_version("xpra v6.2.1") == (6, 2, 1)
    assert xpra.parse_version("xpra v3.1.5-r0") == (3, 1, 5)
    assert xpra.parse_version("xpra v5.0") == (5, 0)
    assert xpra.parse_version("command not found") is None


def test_format_version():
    assert xpra.format_version((6, 2, 1)) == "6.2.1"
    assert xpra.format_version(None) == "?"


def test_version_gap_flags_ubuntu_repo_vs_upstream():
    """Bẫy hay gặp nhất: hub dùng xpra 3.1.5 của Ubuntu, máy con đã lên 6.x."""
    gap = xpra.version_gap((3, 1, 5), (6, 2, 1))
    assert gap is not None
    assert "hub 3.1.5" in gap and "máy con 6.2.1" in gap
    assert "hub cũ hơn máy con" in gap


def test_version_gap_names_whichever_side_is_older():
    gap = xpra.version_gap((6, 2, 1), (3, 1, 5))
    assert "máy con cũ hơn hub" in gap


def test_version_gap_silent_when_same_major():
    assert xpra.version_gap((6, 2, 1), (6, 0)) is None
    assert xpra.version_gap((3, 1, 5), (3, 1, 5)) is None


def test_version_gap_silent_when_version_unknown():
    # Không đọc được phiên bản thì im lặng còn hơn cảnh báo sai.
    assert xpra.version_gap(None, (6, 2)) is None
    assert xpra.version_gap((6, 2), None) is None


def test_start_server_uses_start_alias_for_old_version_compat():
    cmd = xpra.start_server_cmd(VIVO)
    # `start` chứ không phải `seamless`: chạy được cả xpra 3.x lẫn 6.x.
    assert cmd.startswith("xpra start :100")
    assert "--daemon=yes" in cmd
    assert "--sharing=yes" in cmd
    # Không có --start-child thì phiên phải sống dù không còn ứng dụng nào.
    assert "--exit-with-children=no" in cmd


def test_start_server_includes_start_apps():
    node = Node(name="a", host="a", start_apps=["xterm -title shell", "firefox"])
    cmd = xpra.start_server_cmd(node)
    assert "--start-child=xterm -title shell" in cmd
    assert "--start-child=firefox" in cmd


def test_launch_app_falls_back_when_control_unsupported():
    cmd = xpra.launch_app_cmd(VIVO, ["firefox", "--new-window"])
    assert "xpra control :100 start firefox" in cmd
    # Bản cũ không có control command -> vẫn mở được bằng DISPLAY.
    assert "DISPLAY=:100 setsid" in cmd
    # setsid + tách stdio để app không chết theo phiên ssh.
    assert "</dev/null" in cmd


def test_launch_app_quotes_arguments_with_spaces():
    cmd = xpra.launch_app_cmd(VIVO, ["xterm", "-title", "hai chu"])
    assert "'hai chu'" in cmd


def test_attach_argv_includes_node_label_in_title():
    hub = Hub(title_format="@title@ · {node}")
    argv = xpra.attach_argv(VIVO, hub)
    assert argv[:3] == ["xpra", "attach", "ssh://thi@vivo/100"]
    assert "--title=@title@ · vivo" in argv


def test_attach_argv_omits_title_when_disabled():
    argv = xpra.attach_argv(VIVO, Hub(title_format=""))
    assert not any(a.startswith("--title") for a in argv)


def test_attach_argv_appends_hub_options():
    hub = Hub(title_format="", attach_opts=["--opengl=no"])
    assert xpra.attach_argv(VIVO, hub)[-1] == "--opengl=no"


def test_ssh_command_multiplexing_toggle():
    with_mux = ssh_command(VIVO, Hub(ssh_multiplex=True))
    assert "ControlMaster=auto" in with_mux
    assert with_mux[-1] == "thi@vivo"

    without = ssh_command(VIVO, Hub(ssh_multiplex=False))
    assert "ControlMaster=auto" not in without


def test_ssh_command_adds_port_only_when_non_default():
    assert "-p" not in ssh_command(VIVO, Hub())
    other = Node(name="a", host="a", ssh_port=2222)
    argv = ssh_command(other, Hub())
    assert argv[argv.index("-p") + 1] == "2222"


def test_ssh_command_is_non_interactive():
    """BatchMode để lệnh không treo chờ mật khẩu khi chạy doctor hàng loạt."""
    assert "BatchMode=yes" in ssh_command(VIVO, Hub())


def test_tmux_builds_one_window_per_node():
    cfg = Config(hub=Hub(tmux_session="cum"), nodes=[VIVO, Node(name="acer", host="acer")])
    cmds = tmux.build_commands(cfg, cfg.nodes)

    assert cmds[0][:6] == ["tmux", "new-session", "-d", "-s", "cum", "-n"]
    assert cmds[0][6] == "vivo"
    assert cmds[1][:6] == ["tmux", "new-window", "-t", "cum", "-n", "acer"]


def test_tmux_window_reconnects_instead_of_closing():
    cfg = Config(hub=Hub(), nodes=[VIVO])
    body = tmux.build_commands(cfg, cfg.nodes)[0][-1]
    # Máy con tắt thì cửa sổ phải chờ và thử lại, không được biến mất.
    assert body.startswith("while true; do")
    assert "thử lại" in body
