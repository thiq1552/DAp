#!/usr/bin/env bash
# Kiểm tra máy ở nhà đã đủ điều kiện dựng USB chưa, và USB nào là USB nào.
#
# CHỈ ĐỌC — không ghi, không format, không đụng vào thiết bị nào. Chạy được
# không cần sudo (thiếu quyền thì vài mục hiện "không đọc được", không sao).
#
# Dùng: ./deploy/ssd/preflight.sh
set -uo pipefail

RELEASE="${1:-noble}"
ok=0; warn=0; fail=0
say()  { printf '%s\n' "$*"; }
pass() { printf '  [OK]   %s\n' "$*"; ok=$((ok+1)); }
warn_() { printf '  [!!]   %s\n' "$*"; warn=$((warn+1)); }
bad()  { printf '  [XX]   %s\n' "$*"; fail=$((fail+1)); }

say "===================== MÁY DỰNG ====================="
if [ -r /etc/os-release ]; then
  . /etc/os-release
  say "  Hệ điều hành: ${PRETTY_NAME:-?}"
  [ "${ID:-}" = ubuntu ] && pass "Ubuntu — đúng loại máy để dựng" \
    || warn_ "Không phải Ubuntu. debootstrap vẫn chạy được trên Debian, khác nữa thì chưa chắc."
else
  bad "Không đọc được /etc/os-release"
fi
say "  Kiến trúc:    $(uname -m)  (cần x86_64)"
[ "$(uname -m)" = x86_64 ] || bad "Máy này không phải x86_64 — USB dựng ra sẽ không boot được trên máy công ty."
[ -d /sys/firmware/efi ] && pass "Máy đang chạy UEFI" \
  || warn_ "Máy dựng đang ở Legacy BIOS. Không cản việc dựng, nhưng bạn sẽ không boot thử được USB trên chính máy này."

say
say "===================== CÔNG CỤ ======================"
missing=()
for t in debootstrap cryptsetup sgdisk mkfs.vfat mkfs.ext4 partprobe blkid lsblk; do
  if command -v "$t" >/dev/null 2>&1; then pass "$t"; else bad "thiếu $t"; missing+=("$t"); fi
done
if [ ${#missing[@]} -gt 0 ]; then
  say
  say "  Cài bằng:  sudo apt install debootstrap cryptsetup-bin gdisk dosfstools parted util-linux"
fi

if [ -e "/usr/share/debootstrap/scripts/$RELEASE" ]; then
  pass "debootstrap biết bản '$RELEASE'"
elif command -v debootstrap >/dev/null 2>&1; then
  bad "debootstrap chưa biết bản '$RELEASE'"
  say "         Vá:  sudo ln -s gutsy /usr/share/debootstrap/scripts/$RELEASE"
fi

say
say "===================== MẠNG ========================="
if curl -fsS --max-time 10 -o /dev/null http://archive.ubuntu.com/ubuntu/dists/"$RELEASE"/Release 2>/dev/null; then
  pass "Tải được kho Ubuntu (debootstrap sẽ chạy được)"
else
  warn_ "Không với tới archive.ubuntu.com — kiểm tra mạng/proxy trước khi dựng."
fi

say
say "================ ĐĨA: CÁI NÀO LÀ CÁI NÀO ==========="
root_src="$(findmnt -no SOURCE / 2>/dev/null)"
root_disk="$(lsblk -no PKNAME "$(realpath "$root_src" 2>/dev/null)" 2>/dev/null | head -1)"
while [ -n "$root_disk" ] && [ -n "$(lsblk -no PKNAME "/dev/$root_disk" 2>/dev/null | head -1)" ]; do
  root_disk="$(lsblk -no PKNAME "/dev/$root_disk" | head -1)"
done
say "  Ổ hệ thống của máy này: /dev/${root_disk:-?}  <-- TUYỆT ĐỐI không trỏ script vào đây"
say

# Tốc độ cổng nằm ở sysfs của thiết bị USB, không phải ở block device. Đi ngược
# lên cây sysfs tới thư mục đầu tiên có file `speed` — đó chính là cổng đang cắm.
port_speed() {
  local p; p="$(readlink -f "/sys/block/$1" 2>/dev/null)"
  while [ -n "$p" ] && [ "$p" != / ]; do
    [ -r "$p/speed" ] && { cat "$p/speed"; return 0; }
    p="$(dirname "$p")"
  done
  return 1   # không có file speed nào trên đường đi -> để phía gọi in '?'
}

# Tiêu đề để ASCII: printf căn theo byte, chữ có dấu sẽ làm lệch cột.
printf '  %-12s %-8s %-7s %-8s %s\n' DEVICE SIZE BUS SPEED MODEL
found_usb=0
while read -r name size tran; do
  [ -z "$name" ] && continue
  dev="/dev/$name"
  if [ "$name" = "$root_disk" ]; then
    printf '  %-12s %-8s %-7s %-8s %s\n' "$dev" "$size" "${tran:--}" "-" "<< ổ hệ thống, đừng đụng"
    continue
  fi
  model="$(lsblk -dno MODEL "$dev" 2>/dev/null)"
  printf '  %-12s %-8s %-7s %-8s %s\n' "$dev" "$size" "${tran:--}" "$(port_speed "$name" || echo '?')" "$model"
  [ "$tran" = usb ] && found_usb=$((found_usb+1))
done < <(lsblk -dno NAME,SIZE,TRAN 2>/dev/null | grep -vE '^(loop|sr|ram|zram)')

say
if [ "$found_usb" -eq 0 ]; then
  bad "Không thấy thiết bị USB nào. Cắm USB vào rồi chạy lại."
elif [ "$found_usb" -eq 1 ]; then
  pass "Thấy đúng 1 thiết bị USB — không sợ nhầm"
else
  warn_ "Thấy $found_usb thiết bị USB. Rút bớt cái không liên quan để khỏi trỏ nhầm."
fi

say "  Cổng 480M = USB 2.0 (rất chậm, nên đổi cổng). 5000M trở lên = USB 3.x."

say
say "===================== KẾT LUẬN ====================="
say "  $ok đạt, $warn cảnh báo, $fail lỗi"
if [ "$fail" -eq 0 ]; then
  say
  say "  Sẵn sàng. Bước tiếp — xem trước, vẫn chưa ghi gì:"
  say "    sudo ./deploy/ssd/build-stick.sh /dev/sdX --dry-run"
  exit 0
fi
say
say "  Sửa các mục [XX] ở trên rồi chạy lại."
exit 1
