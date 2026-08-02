#!/usr/bin/env bash
# Cài xpra lên một máy. Chạy qua ssh bởi `onepane setup` (máy con), hoặc chạy
# thẳng tại chỗ bởi `onepane setup --hub` (máy bạn ngồi trước).
# Chạy lại nhiều lần được — mọi bước đều kiểm tra trước khi làm.
#
# Biến truyền vào từ onepane:
#   ONEPANE_ROLE     node | hub
#   ONEPANE_DISPLAY  số display cho phiên, ví dụ "100" (chỉ dùng khi role=node)
set -euo pipefail

ROLE="${ONEPANE_ROLE:-node}"
DISPLAY_NUM="${ONEPANE_DISPLAY:-100}"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="onepane-xpra@.service"

say() { printf '  %s\n' "$*"; }

if [ ! -f /etc/os-release ]; then
  echo "LỖI: không xác định được bản Linux trên máy này" >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release
CODENAME="${VERSION_CODENAME:-}"
say "vai trò: $ROLE"
say "hệ điều hành: ${PRETTY_NAME:-?} (codename: ${CODENAME:-không rõ})"

# ---------------------------------------------------------------- 1. kho xpra
# Kho Ubuntu đóng băng xpra ở phiên bản ngày phát hành (24.04 = 3.1.5) trong khi
# upstream đã 6.x. Hub và máy con PHẢI cùng thế hệ, nếu không client/server lệch
# giao thức — nên bước này chạy cho cả hai vai trò.
if [ -f /etc/apt/sources.list.d/xpra.sources ]; then
  say "kho xpra đã có sẵn"
elif [ -n "$CODENAME" ]; then
  REPO_URL="https://raw.githubusercontent.com/Xpra-org/xpra/master/packaging/repos/$CODENAME/xpra.sources"
  say "thêm kho chính chủ xpra cho $CODENAME"
  # Hub chạy tại chỗ và còn nguyên terminal -> để sudo tự hỏi mật khẩu.
  # Máy con thì không: script đi qua `ssh bash -s` ở BatchMode, không có đường
  # nào nhập mật khẩu, nên bắt buộc phải có NOPASSWD sẵn.
  if [ "$ROLE" = "hub" ]; then
    if ! sudo -v; then
      echo "LỖI: cần quyền sudo để cài gói trên máy này." >&2
      exit 1
    fi
  elif ! sudo -n true 2>/dev/null; then
    echo "LỖI: máy con cần sudo không mật khẩu (onepane chạy không tương tác)." >&2
    echo "      Chạy 'sudo visudo' trên máy đó rồi thêm dòng:" >&2
    echo "        $USER ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/wget, /usr/bin/loginctl" >&2
    exit 1
  fi
  sudo apt-get install -y -qq wget ca-certificates >/dev/null
  sudo wget -qO /usr/share/keyrings/xpra.asc https://xpra.org/xpra.asc
  # Kho không có codename này (bản Ubuntu quá mới/quá cũ) -> dùng gói của distro.
  if sudo wget -qO /etc/apt/sources.list.d/xpra.sources "$REPO_URL"; then
    say "đã thêm kho xpra"
    sudo apt-get update -qq
    # Gói distro đã cài sẵn thì phải nâng lên bản của kho mới, `install` không tự làm.
    if command -v xpra >/dev/null 2>&1; then
      say "nâng xpra lên bản của kho chính chủ"
      sudo apt-get install -y -qq --only-upgrade xpra || true
    fi
  else
    sudo rm -f /etc/apt/sources.list.d/xpra.sources
    say "CẢNH BÁO: kho xpra chưa hỗ trợ '$CODENAME', dùng gói sẵn trong Ubuntu (bản cũ hơn)"
  fi
fi

# --------------------------------------------------------------- 2. cài gói
if command -v xpra >/dev/null 2>&1; then
  say "xpra: $(xpra --version 2>&1 | head -1)"
else
  say "cài xpra (có thể mất vài phút)"
  sudo apt-get update -qq
  sudo apt-get install -y -qq xpra
  say "đã cài: $(xpra --version 2>&1 | head -1)"
fi

if [ "$ROLE" = "hub" ]; then
  # Hub chỉ làm client: cần tmux cho `onepane term` và ssh client để nối máy con.
  for pkg in tmux openssh-client; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      say "cài $pkg"
      sudo apt-get install -y -qq "$pkg"
    fi
  done
  say "hub xong — không dựng phiên server ở đây"
  echo "PROVISION_OK"
  exit 0
fi

# Xvfb là màn hình ảo mà phiên seamless vẽ lên. Gói xpra thường kéo theo sẵn,
# nhưng bản distro đôi khi để nó ở recommends nên kiểm tra cho chắc.
if ! command -v Xvfb >/dev/null 2>&1 && ! command -v Xdummy >/dev/null 2>&1; then
  say "cài xvfb"
  sudo apt-get install -y -qq xvfb
fi

# -------------------------------------------------------- 3. systemd user unit
mkdir -p "$UNIT_DIR"
cat >"$UNIT_DIR/$UNIT_NAME" <<'UNIT'
__UNIT_BODY__
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "onepane-xpra@${DISPLAY_NUM}.service"

# linger: phiên vẫn chạy khi bạn đăng xuất và tự bật lại sau khi khởi động máy.
# Không có nó thì tắt ssh là mất hết cửa sổ — đúng thứ ta đang muốn tránh.
if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
  say "bật linger cho $USER"
  sudo -n loginctl enable-linger "$USER" 2>/dev/null \
    || say "CẢNH BÁO: không bật được linger — phiên sẽ tắt khi bạn đăng xuất"
fi

sleep 2
say "trạng thái: $(systemctl --user is-active "onepane-xpra@${DISPLAY_NUM}.service")"
say "phiên xpra:"
xpra list 2>&1 | sed 's/^/    /' || true
echo "PROVISION_OK"
