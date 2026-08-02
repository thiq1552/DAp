#!/usr/bin/env bash
# Cài xpra + systemd user unit lên MỘT máy con. Chạy qua ssh bởi `onepane setup`.
# Chạy lại nhiều lần được — mọi bước đều kiểm tra trước khi làm.
#
# Biến truyền vào từ onepane: ONEPANE_DISPLAY (ví dụ "100")
set -euo pipefail

DISPLAY_NUM="${ONEPANE_DISPLAY:-100}"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="onepane-xpra@.service"

say() { printf '  %s\n' "$*"; }

# ---------------------------------------------------------------- 1. kho xpra
if ! command -v lsb_release >/dev/null 2>&1 && [ ! -f /etc/os-release ]; then
  echo "LỖI: không xác định được bản Linux trên máy này" >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release
CODENAME="${VERSION_CODENAME:-}"
say "hệ điều hành: ${PRETTY_NAME:-?} (codename: ${CODENAME:-không rõ})"

need_repo=1
if [ -f /etc/apt/sources.list.d/xpra.sources ]; then
  say "kho xpra đã có sẵn"
  need_repo=0
fi

if [ "$need_repo" = 1 ] && [ -n "$CODENAME" ]; then
  REPO_URL="https://raw.githubusercontent.com/Xpra-org/xpra/master/packaging/repos/$CODENAME/xpra.sources"
  say "thêm kho chính chủ xpra cho $CODENAME"
  sudo -n true 2>/dev/null || { echo "LỖI: cần sudo không mật khẩu để cài gói" >&2; exit 1; }
  sudo apt-get install -y -qq wget ca-certificates >/dev/null
  sudo wget -qO /usr/share/keyrings/xpra.asc https://xpra.org/xpra.asc
  # Kho không có codename này (bản Ubuntu quá mới/quá cũ) -> dùng gói của distro.
  if sudo wget -qO /etc/apt/sources.list.d/xpra.sources "$REPO_URL"; then
    say "đã thêm kho xpra"
  else
    sudo rm -f /etc/apt/sources.list.d/xpra.sources
    say "CẢNH BÁO: kho xpra chưa hỗ trợ '$CODENAME', dùng gói sẵn trong Ubuntu (bản cũ hơn)"
  fi
fi

# --------------------------------------------------------------- 2. cài xpra
if command -v xpra >/dev/null 2>&1; then
  say "xpra đã cài: $(xpra --version 2>&1 | head -1)"
else
  say "cài xpra (có thể mất vài phút)"
  sudo apt-get update -qq
  sudo apt-get install -y -qq xpra
  say "đã cài: $(xpra --version 2>&1 | head -1)"
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
