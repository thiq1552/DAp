import argparse

import pytest

from ccbus.cli import MARKER, cmd_init, cmd_connect


def init_args(path, project="default"):
    return argparse.Namespace(path=str(path), project=project)


def test_init_appends_the_protocol_and_keeps_existing_instructions(tmp_path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Project\n\nHướng dẫn sẵn có.\n", encoding="utf-8")

    cmd_init(init_args(tmp_path, "my-app"))

    text = claude_md.read_text(encoding="utf-8")
    assert "Hướng dẫn sẵn có." in text
    assert MARKER in text
    assert "`my-app`" in text
    assert "<ĐIỀN_TÊN_PROJECT>" not in text


def test_init_creates_claude_md_when_the_project_has_none(tmp_path):
    cmd_init(init_args(tmp_path))
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith(f"\n{MARKER}")
    assert "<ĐIỀN_TÊN_PROJECT>" in text  # chưa truyền --project thì để chỗ trống


def test_init_run_twice_does_not_duplicate_the_block(tmp_path):
    cmd_init(init_args(tmp_path, "my-app"))
    first = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    cmd_init(init_args(tmp_path, "my-app"))
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == first


def test_connect_prints_a_ready_to_paste_command(capsys, monkeypatch):
    monkeypatch.delenv("CCBUS_URL", raising=False)
    cmd_connect(
        argparse.Namespace(url="http://100.1.2.3:7717/", token="tok_x", user_scope=True)
    )
    out = capsys.readouterr().out
    assert "claude mcp add --transport http ccbus http://100.1.2.3:7717/mcp" in out
    assert '--scope user --header "Authorization: Bearer tok_x"' in out


def test_connect_refuses_to_emit_a_command_without_a_token(monkeypatch):
    monkeypatch.delenv("CCBUS_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="token"):
        cmd_connect(argparse.Namespace(url="http://x", token=None, user_scope=False))
