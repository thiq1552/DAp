import pytest

from onepane.config import Config, ConfigError, Node, write_template


def write(tmp_path, text):
    p = tmp_path / "config.ini"
    p.write_text(text, encoding="utf-8")
    return p


def test_parses_nodes_and_defaults(tmp_path):
    path = write(
        tmp_path,
        """
[node:vivo]
host = vivo.tail1234.ts.net
user = thi

[node:cong-ty]
host = 100.101.102.103
user = thi
display = :7
ssh_port = 2222
""",
    )
    cfg = Config.load(path)

    assert [n.name for n in cfg.nodes] == ["vivo", "cong-ty"]
    vivo = cfg.node("vivo")
    assert vivo.display == ":100"  # mặc định
    assert vivo.ssh_port == 22
    assert vivo.ssh_target == "thi@vivo.tail1234.ts.net"

    ct = cfg.node("cong-ty")
    assert ct.display == ":7"
    assert ct.display_number == "7"
    assert ct.xpra_uri() == "ssh://thi@100.101.102.103:2222/7"


def test_host_defaults_to_node_name(tmp_path):
    cfg = Config.load(write(tmp_path, "[node:acer]\nuser = thi\n"))
    assert cfg.node("acer").host == "acer"


def test_display_accepts_bare_number(tmp_path):
    cfg = Config.load(write(tmp_path, "[node:acer]\ndisplay = 42\n"))
    assert cfg.node("acer").display == ":42"


def test_rejects_non_numeric_display(tmp_path):
    path = write(tmp_path, "[node:acer]\ndisplay = :abc\n")
    with pytest.raises(ConfigError, match="display"):
        Config.load(path)


def test_uri_omits_port_when_default(tmp_path):
    cfg = Config.load(write(tmp_path, "[node:acer]\nuser = thi\n"))
    assert cfg.node("acer").xpra_uri() == "ssh://thi@acer/100"


def test_uri_without_user(tmp_path):
    cfg = Config.load(write(tmp_path, "[node:acer]\n"))
    assert cfg.node("acer").xpra_uri() == "ssh://acer/100"


def test_select_skips_disabled_but_name_still_works(tmp_path):
    path = write(
        tmp_path,
        "[node:a]\n[node:b]\nenabled = no\n",
    )
    cfg = Config.load(path)
    assert [n.name for n in cfg.select(None)] == ["a"]
    # Gọi đích danh vẫn lấy được máy đang tắt.
    assert [n.name for n in cfg.select(["b"])] == ["b"]
    assert [n.name for n in cfg.select(None, include_disabled=True)] == ["a", "b"]


def test_start_apps_multiline_and_comma(tmp_path):
    cfg = Config.load(
        write(tmp_path, "[node:a]\nstart_apps =\n    xterm\n    firefox\n")
    )
    assert cfg.node("a").start_apps == ["xterm", "firefox"]

    cfg2 = Config.load(write(tmp_path, "[node:a]\nstart_apps = xterm, firefox\n"))
    assert cfg2.node("a").start_apps == ["xterm", "firefox"]


def test_hub_defaults_and_overrides(tmp_path):
    cfg = Config.load(write(tmp_path, "[node:a]\n"))
    assert cfg.hub.tmux_session == "onepane"
    assert cfg.hub.ssh_multiplex is True

    cfg2 = Config.load(
        write(
            tmp_path,
            "[hub]\ntmux_session = cum\ntitle_format =\nattach_opts = --opengl=no --speaker=off\n"
            "ssh_multiplex = no\n\n[node:a]\n",
        )
    )
    assert cfg2.hub.tmux_session == "cum"
    assert cfg2.hub.title_format == ""
    assert cfg2.hub.attach_opts == ["--opengl=no", "--speaker=off"]
    assert cfg2.hub.ssh_multiplex is False


def test_unknown_node_lists_known_ones(tmp_path):
    cfg = Config.load(write(tmp_path, "[node:a]\n[node:b]\n"))
    with pytest.raises(ConfigError, match="a, b"):
        cfg.node("khong-co")


def test_empty_config_explains_what_to_add(tmp_path):
    path = write(tmp_path, "[hub]\ntmux_session = x\n")
    with pytest.raises(ConfigError, match="chưa khai báo máy nào"):
        Config.load(path)


def test_missing_file_points_at_init(tmp_path):
    with pytest.raises(ConfigError, match="onepane init"):
        Config.load(tmp_path / "khong-ton-tai.ini")


def test_template_is_valid_config(tmp_path):
    """File mẫu sinh ra phải tự parse được — nếu không thì `init` là bẫy."""
    path = tmp_path / "cfg" / "config.ini"
    write_template(path)
    cfg = Config.load(path)
    assert {n.name for n in cfg.nodes} == {"vivo", "cong-ty"}
    assert cfg.hub.tmux_session == "onepane"


def test_template_refuses_overwrite_without_force(tmp_path):
    path = tmp_path / "config.ini"
    write_template(path)
    with pytest.raises(ConfigError, match="--force"):
        write_template(path)
    write_template(path, force=True)  # không raise
