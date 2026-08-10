#!/usr/bin/env bash
# Nối MỘT MÁY vào tailnet và bật điều khiển từ xa qua Tailscale SSH.
# Chạy trực tiếp trên máy cần điều khiển (chạy được ở tty, không cần màn hình đồ hoạ).
#
# Dùng: ./deploy/setup-tailscale.sh [tuỳ-chọn]
#   --hostname NAME   tên máy trong tailnet (mặc định: hostname hiện tại)
#   --auth-key KEY    auth key tạo sẵn ở admin console; không có thì script in
#                     ra link để bạn mở bằng điện thoại/máy khác
#   --keep-awake      không ngủ khi đóng nắp / để không (dành cho laptop làm máy chạy ngầm)
#   --openssh         cài thêm sshd thường làm đường dự phòng nếu Tailscale SSH lỗi
#   --no-ssh          chỉ nối tailnet, không bật Tailscale SSH
set -euo pipefail

HOSTNAME_ARG=""
AUTH_KEY=""
KEEP_AWAKE=0
WANT_OPENSSH=0
WANT_SSH=1

need_value() { [ -n "${2:-}" ] || { echo "$1 cần một giá trị đi kèm." >&2; exit 1; }; }

while [ $# -gt 0 ]; do
  case "$1" in
    --hostname) need_value "$1" "${2:-}"; HOSTNAME_ARG="$2"; shift 2 ;;
    --auth-key) need_value "$1" "${2:-}"; AUTH_KEY="$2"; shift 2 ;;
    --keep-awake) KEEP_AWAKE=1; shift ;;
    --openssh) WANT_OPENSSH=1; shift ;;
    --no-ssh) WANT_SSH=0; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "Tuỳ chọn lạ: $1 (xem $0 --help)" >&2; exit 1 ;;
  esac
done

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
  command -v sudo >/dev/null 2>&1 || { echo "Cần sudo hoặc chạy bằng root." >&2; exit 1; }
fi

TS_HOSTNAME="${HOSTNAME_ARG:-$(hostname -s)}"
# Tailscale chỉ nhận chữ thường, số và dấu gạch ngang
TS_HOSTNAME="$(printf '%s' "$TS_HOSTNAME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/^-*//; s/-*$//')"

echo "==> Kiểm tra mạng ra Internet"
if ! curl -fsS --max-time 15 -o /dev/null https://login.tailscale.com/; then
  echo "Không ra được login.tailscale.com — máy này phải có Internet trước đã." >&2
  echo >&2
  if command -v nmcli >/dev/null 2>&1; then
    echo "--- nmcli device status ---" >&2
    nmcli device status >&2 || true
  fi
  if command -v rfkill >/dev/null 2>&1; then
    echo "--- rfkill list ---" >&2
    rfkill list >&2 || true
  fi
  cat >&2 <<'EOF'

Nối Wi-Fi ở tty:
  sudo rfkill unblock all                       # nếu rfkill báo "Soft blocked: yes"
  sudo nmcli device set <iface> managed yes     # nếu device status báo "unmanaged"
  sudo nmcli device wifi rescan
  nmcli device wifi list
  sudo nmcli device wifi connect "<ssid>" --ask

Cách nhanh hơn: cắm dây USB từ điện thoại rồi bật USB tethering.
EOF
  exit 1
fi

if command -v tailscale >/dev/null 2>&1; then
  echo "==> tailscale đã có sẵn ($(tailscale version | head -1))"
else
  echo "==> Cài tailscale"
  curl -fsSL https://tailscale.com/install.sh | $SUDO sh
fi

echo "==> Bật dịch vụ tailscaled"
$SUDO systemctl enable --now tailscaled

UP_ARGS=(--hostname="$TS_HOSTNAME")
[ "$WANT_SSH" -eq 1 ] && UP_ARGS+=(--ssh)
[ -n "$AUTH_KEY" ] && UP_ARGS+=(--auth-key="$AUTH_KEY")

echo "==> tailscale up ${UP_ARGS[*]}"
if [ -z "$AUTH_KEY" ]; then
  echo "    Không có --auth-key: bên dưới sẽ hiện một link https://login.tailscale.com/a/..."
  echo "    Mở link đó bằng điện thoại hoặc máy khác, đăng nhập ĐÚNG tài khoản đang dùng"
  echo "    cho các máy kia, rồi quay lại đây."
fi
$SUDO tailscale up "${UP_ARGS[@]}"

if [ "$KEEP_AWAKE" -eq 1 ]; then
  echo "==> Chặn ngủ khi đóng nắp / để không"
  $SUDO mkdir -p /etc/systemd/logind.conf.d
  $SUDO tee /etc/systemd/logind.conf.d/99-ccbus-keep-awake.conf >/dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
HandleLidSwitchExternalPower=ignore
IdleAction=ignore
EOF
  $SUDO systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null
  echo "    Đã ghi /etc/systemd/logind.conf.d/99-ccbus-keep-awake.conf — reboot để chắc chắn có hiệu lực."
  echo "    Gỡ sau này: xoá file đó + systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target"
fi

if [ "$WANT_OPENSSH" -eq 1 ]; then
  echo "==> Cài openssh-server làm đường dự phòng"
  $SUDO apt-get update -qq
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server
  $SUDO systemctl enable --now ssh
  echo "    sshd chỉ nên nghe trên tailnet. Khoá lại bằng:"
  echo "      echo 'ListenAddress $(tailscale ip -4 2>/dev/null | head -1)' | sudo tee /etc/ssh/sshd_config.d/tailscale-only.conf"
  echo "      sudo systemctl restart ssh"
fi

TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"

echo
echo "==================== XONG ===================="
tailscale status || true
echo
echo "Máy này:  $TS_HOSTNAME  ${TS_IP:+($TS_IP)}"
if [ "$WANT_SSH" -eq 1 ]; then
  echo "Từ máy khác trong cùng tailnet, chạy:"
  echo "    ssh $USER@$TS_HOSTNAME          # cần MagicDNS; không thì dùng IP 100.x.y.z"
  echo "    tailscale ssh $USER@$TS_HOSTNAME"
  echo
  echo "Bị 'access denied'? Tailnet của bạn chưa cho phép SSH — vào admin console,"
  echo "mục Access controls, thêm vào policy file:"
  cat <<'EOF'
    "ssh": [
      { "action": "accept",
        "src": ["autogroup:member"],
        "dst": ["autogroup:self"],
        "users": ["autogroup:nonroot", "root"] }
    ]
EOF
fi
echo
echo "Nối luôn máy này vào ccbus:"
echo "    ./deploy/setup-client.sh http://<ip-máy-chủ>:7717 <token-của-máy-này> <tên-project>"
