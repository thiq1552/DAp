#!/usr/bin/env bash
# Cho máy tự bắt Wi-Fi mỗi lần khởi động — dành cho máy chạy ngầm, không màn hình.
# Dùng: sudo ./deploy/wifi-autoconnect.sh "<ssid>" [--hidden] [--iface wlp2s0]
#   Mật khẩu nhập ở prompt (không truyền qua tham số để khỏi lọt vào history).
#
# Script tự chọn đường đi: máy nào NetworkManager đang quản card thì tạo profile
# bằng nmcli; máy nào netplan giao card cho systemd-networkd thì ghi netplan.
set -euo pipefail

SSID=""
HIDDEN=0
IFACE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --hidden) HIDDEN=1; shift ;;
    --iface) IFACE="${2:?--iface cần tên interface}"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    -*) echo "Tuỳ chọn lạ: $1" >&2; exit 1 ;;
    *) SSID="$1"; shift ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "Chạy bằng sudo." >&2; exit 1; }
[ -n "$SSID" ] || { echo "Dùng: $0 \"<ssid>\" [--hidden] [--iface wlp2s0]" >&2; exit 1; }

if [ -z "$IFACE" ]; then
  for dev in /sys/class/net/*/wireless; do
    [ -e "$dev" ] || continue
    IFACE="$(basename "$(dirname "$dev")")"
    break
  done
fi
[ -n "$IFACE" ] || { echo "Không tìm thấy card Wi-Fi nào. Kiểm tra driver: lspci -k | grep -A3 -i network" >&2; exit 1; }
echo "==> Card Wi-Fi: $IFACE"

echo "==> Mở khoá sóng (rfkill)"
command -v rfkill >/dev/null 2>&1 && rfkill unblock wifi || true
if command -v rfkill >/dev/null 2>&1 && rfkill list wifi | grep -q 'Hard blocked: yes'; then
  echo "Sóng đang bị khoá cứng — bấm Fn + phím hình ăng-ten trên bàn phím rồi chạy lại." >&2
  exit 1
fi

printf 'Mật khẩu Wi-Fi cho "%s" (bỏ trống nếu mạng mở): ' "$SSID" >&2
read -rs PSK
echo >&2

USE_NM=0
if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager; then
  state="$(nmcli -t -f DEVICE,STATE device status | awk -F: -v d="$IFACE" '$1==d{print $2}')"
  if [ "$state" = "unmanaged" ]; then
    echo "==> NetworkManager đang bỏ mặc $IFACE, thử giao lại cho nó"
    nmcli device set "$IFACE" managed yes 2>/dev/null || true
    sleep 1
    state="$(nmcli -t -f DEVICE,STATE device status | awk -F: -v d="$IFACE" '$1==d{print $2}')"
  fi
  [ "$state" != "unmanaged" ] && [ -n "$state" ] && USE_NM=1
fi

if [ "$USE_NM" -eq 1 ]; then
  echo "==> Dùng NetworkManager"
  nmcli radio wifi on
  nmcli connection delete "$SSID" >/dev/null 2>&1 || true

  args=(connection.autoconnect yes
        connection.autoconnect-priority 10
        connection.autoconnect-retries 0)   # 0 = thử lại vô hạn; mặc định bỏ cuộc sau 4 lần
  [ "$HIDDEN" -eq 1 ] && args+=(802-11-wireless.hidden yes)
  if [ -n "$PSK" ]; then
    args+=(wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK")
  fi

  nmcli connection add type wifi con-name "$SSID" ifname "$IFACE" ssid "$SSID" "${args[@]}" >/dev/null
  systemctl enable NetworkManager >/dev/null 2>&1 || true
  nmcli device wifi rescan >/dev/null 2>&1 || true
  sleep 2
  nmcli connection up "$SSID" ifname "$IFACE"
else
  echo "==> Dùng netplan + systemd-networkd (NetworkManager không quản $IFACE)"
  conf=/etc/netplan/60-wifi-autoconnect.yaml
  umask 077
  {
    echo "network:"
    echo "  version: 2"
    echo "  wifis:"
    echo "    $IFACE:"
    echo "      dhcp4: true"
    echo "      optional: true"
    echo "      access-points:"
    echo "        \"$SSID\":"
    [ "$HIDDEN" -eq 1 ] && echo "          hidden: true"
    [ -n "$PSK" ] && echo "          password: \"$PSK\""
  } >"$conf"
  chmod 600 "$conf"
  echo "    đã ghi $conf"
  systemctl enable --now systemd-networkd >/dev/null 2>&1 || true
  netplan generate
  netplan apply
fi

echo "==> Chờ có IP (tối đa 45 giây)"
for _ in $(seq 45); do
  if ip -4 addr show dev "$IFACE" | grep -q 'inet '; then break; fi
  sleep 1
done

echo
ip -4 addr show dev "$IFACE" | sed -n 's/^ *inet /    IP: /p'
if ping -c2 -W3 1.1.1.1 >/dev/null 2>&1; then
  echo "    Ra được Internet."
else
  echo "    Có IP nhưng chưa ping được 1.1.1.1 — xem lại DNS/gateway." >&2
fi

echo
echo "Kiểm tra thật sự: rút dây tether, reboot, rồi từ máy khác ssh vào."
echo "Nếu vẫn cần cắm tether mới lên mạng thì profile chưa tự chạy — xem:"
if [ "$USE_NM" -eq 1 ]; then
  echo "    nmcli -f NAME,AUTOCONNECT,DEVICE connection show"
  echo "    journalctl -u NetworkManager -b --no-pager | tail -40"
else
  echo "    networkctl status $IFACE"
  echo "    journalctl -u systemd-networkd -u wpa_supplicant -b --no-pager | tail -40"
fi
