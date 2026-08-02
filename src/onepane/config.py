"""Đọc cấu hình onepane từ file INI.

Dùng `configparser` của stdlib thay vì TOML: chạy được trên mọi Python >= 3.10
(`tomllib` chỉ có từ 3.11), và định dạng `[node:ten-may]` đọc/sửa bằng tay rất dễ.
"""

from __future__ import annotations

import configparser
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

NODE_PREFIX = "node:"
DEFAULT_DISPLAY_BASE = 100


class ConfigError(Exception):
    """Cấu hình sai — thông báo đã ở dạng đọc được cho người dùng."""


def _split_list(raw: str) -> list[str]:
    """Tách giá trị nhiều dòng hoặc ngăn bằng dấu phẩy thành list."""
    items: list[str] = []
    for line in raw.replace(",", "\n").splitlines():
        line = line.strip()
        if line:
            items.append(line)
    return items


def _bool(section: configparser.SectionProxy, key: str, default: bool) -> bool:
    try:
        return section.getboolean(key, fallback=default)
    except ValueError as exc:
        raise ConfigError(
            f"[{section.name}] {key} phải là yes/no, nhận được {section.get(key)!r}"
        ) from exc


@dataclass(frozen=True)
class Node:
    """Một máy trong cụm — nơi ứng dụng thật sự chạy."""

    name: str
    host: str
    user: str | None = None
    display: str = ":100"
    ssh_port: int = 22
    ssh_opts: list[str] = field(default_factory=list)
    enabled: bool = True
    # Lệnh chạy sẵn khi `onepane up` dựng phiên (ví dụ một terminal luôn mở).
    start_apps: list[str] = field(default_factory=list)

    @property
    def display_number(self) -> str:
        """`:100` -> `100`, dùng cho tên instance của systemd và URI xpra."""
        return self.display.lstrip(":")

    @property
    def ssh_target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def xpra_uri(self) -> str:
        """URI ssh:// mà client xpra dùng để nối tới phiên trên máy này."""
        port = f":{self.ssh_port}" if self.ssh_port != 22 else ""
        return f"ssh://{self.ssh_target}{port}/{self.display_number}"


@dataclass(frozen=True)
class Hub:
    """Máy bạn đang ngồi trước — nơi mọi cửa sổ hiện ra."""

    tmux_session: str = "onepane"
    # Nhãn thêm vào tiêu đề cửa sổ để biết cửa sổ nào của máy nào.
    # Đặt rỗng nếu bản xpra của bạn không hiểu cú pháp @title@.
    title_format: str = "@title@ · {node}"
    # Tuỳ chọn truyền thẳng cho `xpra attach`.
    attach_opts: list[str] = field(default_factory=list)
    # Bật ControlMaster để lệnh ssh thứ hai trở đi không phải bắt tay lại.
    ssh_multiplex: bool = True


@dataclass(frozen=True)
class Config:
    hub: Hub
    nodes: list[Node]
    source: Path | None = None

    def node(self, name: str) -> Node:
        for n in self.nodes:
            if n.name == name:
                return n
        known = ", ".join(n.name for n in self.nodes) or "(chưa khai báo máy nào)"
        raise ConfigError(f"Không có máy tên {name!r}. Đang có: {known}")

    def select(self, names: list[str] | None, *, include_disabled: bool = False) -> list[Node]:
        """Chọn node theo tên; không truyền tên thì lấy hết node đang bật."""
        if names:
            return [self.node(n) for n in names]
        return [n for n in self.nodes if include_disabled or n.enabled]

    @classmethod
    def default_path(cls) -> Path:
        base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
        return Path(base).expanduser() / "onepane" / "config.ini"

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or cls.default_path()
        if not path.exists():
            raise ConfigError(
                f"Chưa có cấu hình tại {path}.\nChạy `onepane init` để tạo file mẫu rồi sửa lại."
            )

        parser = configparser.ConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except configparser.Error as exc:
            raise ConfigError(f"Không đọc được {path}: {exc}") from exc

        hub = cls._parse_hub(parser)
        nodes = cls._parse_nodes(parser, path)
        return cls(hub=hub, nodes=nodes, source=path)

    @staticmethod
    def _parse_hub(parser: configparser.ConfigParser) -> Hub:
        if not parser.has_section("hub"):
            return Hub()
        s = parser["hub"]
        return Hub(
            tmux_session=s.get("tmux_session", "onepane").strip() or "onepane",
            title_format=s.get("title_format", "@title@ · {node}").strip(),
            attach_opts=shlex.split(s.get("attach_opts", "")),
            ssh_multiplex=_bool(s, "ssh_multiplex", True),
        )

    @staticmethod
    def _parse_nodes(parser: configparser.ConfigParser, path: Path) -> list[Node]:
        nodes: list[Node] = []
        seen_displays: dict[str, str] = {}

        for section in parser.sections():
            if not section.startswith(NODE_PREFIX):
                continue
            name = section[len(NODE_PREFIX) :].strip()
            if not name:
                raise ConfigError(f"Section [{section}] thiếu tên máy sau dấu hai chấm")
            s = parser[section]

            host = s.get("host", "").strip() or name
            display = s.get("display", "").strip() or f":{DEFAULT_DISPLAY_BASE}"
            if not display.startswith(":"):
                display = f":{display}"
            if not display[1:].isdigit():
                raise ConfigError(
                    f"[{section}] display phải dạng ':100', nhận được {display!r}"
                )

            try:
                ssh_port = int(s.get("ssh_port", "22"))
            except ValueError as exc:
                raise ConfigError(f"[{section}] ssh_port phải là số") from exc

            user = s.get("user", "").strip() or None
            nodes.append(
                Node(
                    name=name,
                    host=host,
                    user=user,
                    display=display,
                    ssh_port=ssh_port,
                    ssh_opts=shlex.split(s.get("ssh_opts", "")),
                    enabled=_bool(s, "enabled", True),
                    start_apps=_split_list(s.get("start_apps", "")),
                )
            )

            # Hai máy khác nhau trùng display là hợp lệ (display là số cục bộ trên
            # từng máy), nhưng trùng *tên máy* thì không.
            seen_displays[name] = display

        if not nodes:
            raise ConfigError(
                f"{path} chưa khai báo máy nào.\n"
                f"Thêm một section dạng:\n\n[{NODE_PREFIX}vivo]\nhost = vivo\nuser = thi\n"
            )
        return nodes


TEMPLATE = """\
# Cấu hình onepane — gộp cửa sổ của nhiều máy về một màn hình.
#
# Sửa xong chạy:  onepane doctor      (kiểm tra từng máy)
#                 onepane setup --all (cài xpra + systemd lên các máy)
#                 onepane up --all    (dựng phiên)
#                 onepane attach --all

[hub]
# Tên phiên tmux mà `onepane term` tạo ra.
tmux_session = onepane

# Nhãn gắn vào tiêu đề cửa sổ để biết cửa sổ của máy nào.
# {node} được thay bằng tên máy. Để trống nếu xpra bản cũ không hiểu @title@.
title_format = @title@ · {node}

# Tuỳ chọn thêm cho `xpra attach`, ví dụ: --opengl=no --speaker=off
attach_opts =

# Dùng lại một kết nối ssh cho nhiều lệnh (nhanh hơn nhiều khi chạy doctor/status).
ssh_multiplex = yes


# Mỗi máy một section. Tên sau `node:` là tên bạn gõ ở dòng lệnh.
# `host` là tên Tailscale (MagicDNS) hoặc IP 100.x.y.z.

[node:vivo]
host = vivo
user = CHANGE_ME
display = :100

[node:cong-ty]
host = cong-ty
user = CHANGE_ME
display = :100

# Ví dụ mở sẵn một terminal mỗi khi dựng phiên:
# start_apps =
#     xterm -title "cong-ty shell"

# Máy tạm không dùng thì tắt bằng enabled = no thay vì xoá section.
# [node:acer]
# host = acer
# user = CHANGE_ME
# enabled = no
"""


def write_template(path: Path, *, force: bool = False) -> Path:
    """Ghi file cấu hình mẫu. Không ghi đè trừ khi force."""
    if path.exists() and not force:
        raise ConfigError(f"{path} đã tồn tại. Dùng `onepane init --force` để ghi đè.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return path
