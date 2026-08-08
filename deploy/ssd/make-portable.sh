#!/usr/bin/env bash
# Biến một bản Ubuntu vừa cài lên SSD ngoài thành ổ boot được trên MỌI máy x86_64.
#
# Chạy từ CHÍNH hệ điều hành trên ổ SSD đó (đã boot vào nó), không chạy từ live USB.
# Dùng: sudo ./deploy/ssd/make-portable.sh
#
# Bản Ubuntu do trình cài đặt tạo ra chỉ boot được đúng cái máy đã cài nó, vì ba lý do:
#   1. Bootloader nằm ở /EFI/ubuntu và phụ thuộc một entry trong NVRAM của máy đó.
#   2. initramfs chỉ chứa driver của phần cứng máy đó (MODULES=dep).
#   3. RESUME trỏ tới swap để hibernate — sai máy là treo ~30s mỗi lần boot.
# Script này sửa cả ba, cộng vài thứ riêng của ổ USB (autosuspend, TRIM, noatime).
set -euo pipefail

# shellcheck source=deploy/ssd/lib-portable.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-portable.sh"

log()  { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'LỖI: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Cần chạy bằng sudo."
[ -d /sys/firmware/efi ] || die "Máy đang boot ở chế độ Legacy BIOS. Ổ này phải được cài ở chế độ UEFI thì mới boot đa máy được."

# ---------------------------------------------------------------- kiểm tra ổ
ROOT_SRC="$(findmnt -no SOURCE /)"
ROOT_DISK="$(lsblk -no PKNAME "$(realpath "$ROOT_SRC")" 2>/dev/null | head -1)"
# Với LUKS/LVM, PKNAME trỏ tới dm device — lần ngược lên đĩa vật lý thật.
while [ -n "$ROOT_DISK" ] && [ -n "$(lsblk -no PKNAME "/dev/$ROOT_DISK" 2>/dev/null | head -1)" ]; do
  ROOT_DISK="$(lsblk -no PKNAME "/dev/$ROOT_DISK" | head -1)"
done
[ -n "$ROOT_DISK" ] || die "Không xác định được ổ đĩa chứa /."

ROOT_TRAN="$(lsblk -dno TRAN "/dev/$ROOT_DISK" 2>/dev/null || true)"
log "Ổ chứa hệ thống: /dev/$ROOT_DISK (kết nối: ${ROOT_TRAN:-không rõ})"
if [ "$ROOT_TRAN" != "usb" ]; then
  warn "Ổ này KHÔNG nối qua USB. Bạn đang chạy script từ hệ điều hành trong máy, không phải từ ổ SSD ngoài."
  read -r -p "    Vẫn tiếp tục? [y/N] " ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || die "Dừng lại."
fi

ESP="$(findmnt -no TARGET /boot/efi 2>/dev/null || true)"
[ -n "$ESP" ] || die "Không thấy phân vùng EFI ở /boot/efi. Ổ này chưa được cài ở chế độ UEFI."
ESP_DISK="$(lsblk -no PKNAME "$(findmnt -no SOURCE /boot/efi)" | head -1)"
[ "$ESP_DISK" = "$ROOT_DISK" ] || die "Phân vùng EFI nằm trên /dev/$ESP_DISK, không phải ổ SSD /dev/$ROOT_DISK.
Trình cài đặt đã ghi bootloader vào ổ trong. Phải cài lại với ổ trong đã rút ra."

# ------------------------------------------------------- 1. firmware đầy đủ
log "Cài firmware và microcode cho mọi loại phần cứng"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  linux-firmware intel-microcode amd64-microcode \
  firmware-sof-signed fwupd efibootmgr cryptsetup-initramfs >/dev/null
# Wi-Fi Broadcom trên vài dòng laptop cần driver ngoài repo chính.
apt-get install -y --no-install-recommends bcmwl-kernel-source >/dev/null 2>&1 \
  || warn "Không cài được bcmwl-kernel-source (bỏ qua — chỉ cần cho Wi-Fi Broadcom)."

# --------------------------------------------- 2. initramfs chứa mọi driver
log "Đặt MODULES=most và tắt hibernate (xem lib-portable.sh)"
portable_initramfs_conf

# ------------------------------------------- 3. crypttab/fstab phải dùng UUID
log "Kiểm tra /etc/fstab và /etc/crypttab không tham chiếu tên thiết bị cố định"
# Chỉ bắt /dev/sdX, /dev/nvmeX, /dev/vdX — tên do kernel đánh theo thứ tự phát hiện
# nên đổi theo từng máy. /dev/mapper/* của LVM thì ổn định, không tính.
offenders() {
  awk '
    /^[[:space:]]*(#|$)/ { next }
    { for (i = 1; i <= NF; i++)
        if ($i ~ /^\/dev\/(sd[a-z]|nvme[0-9]|vd[a-z])/) { print FILENAME ":" FNR ": " $0; next } }
  ' "$1"
}
bad=0
for f in /etc/fstab /etc/crypttab; do
  [ -f "$f" ] || continue
  found="$(offenders "$f")"
  if [ -n "$found" ]; then
    warn "$f dùng tên thiết bị cố định — tên này đổi theo từng máy, phải thay bằng UUID=:"
    printf '%s\n' "$found" >&2
    bad=1
  fi
done
[ "$bad" -eq 0 ] || die "Sửa các dòng trên (lấy UUID bằng \`blkid\`) rồi chạy lại script."

# Cảnh báo nếu fstab còn mount phân vùng của ổ trong máy dùng để cài.
while read -r spec _; do
  case "$spec" in
    UUID=*)
      uuid="${spec#UUID=}"
      dev="$(blkid -U "$uuid" 2>/dev/null || true)"
      if [ -z "$dev" ]; then
        warn "fstab tham chiếu UUID=$uuid nhưng không tìm thấy — nếu đó là ổ trong của máy cài đặt, hãy xoá dòng đó hoặc thêm 'nofail'."
      fi
      ;;
  esac
done < <(grep -vE '^\s*(#|$)' /etc/fstab)

log "Thêm noatime cho / để giảm ghi xuống SSD qua USB"
awk '
  /^[[:space:]]*(#|$)/ { print; next }
  $2 == "/" && $4 !~ /(^|,)noatime(,|$)/ { $4 = $4 ",noatime"; print; next }
  { print }
' /etc/fstab >/etc/fstab.new && mv /etc/fstab.new /etc/fstab
awk '$2 == "/" && $4 ~ /noatime/ { found = 1 } END { exit !found }' /etc/fstab \
  || warn "Không tự thêm được noatime — thêm tay vào dòng / trong /etc/fstab."

# ------------------------------------------------ 4. tham số kernel cho USB
log "Chặn USB autosuspend (ổ root bị ngủ = treo cả hệ thống)"
CMDLINE_FILE=/etc/default/grub.d/99-portable-ssd.cfg
mkdir -p /etc/default/grub.d
cat >"$CMDLINE_FILE" <<'EOF'
# Ổ root nằm trên USB: nếu controller ngủ thì filesystem treo cứng.
GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT usbcore.autosuspend=-1"
# Hiện menu để còn chọn được Recovery khi cắm vào máy có GPU lạ.
GRUB_TIMEOUT=3
GRUB_TIMEOUT_STYLE=menu
EOF

# ------------------------------------------ 5. bootloader ở đường dẫn di động
log "Cài bootloader vào đường dẫn di động $ESP/EFI/BOOT/ (xem lib-portable.sh)"
portable_bootloader "$ESP"
SECUREBOOT_OK="$PORTABLE_SECUREBOOT"

log "Cập nhật grub.cfg và initramfs (bước này lâu)"
update-grub
update-initramfs -u -k all

# ------------------------------------------------------------ 6. kiểm tra TRIM
log "Kiểm tra box USB có hỗ trợ TRIM không"
if fstrim -v / >/dev/null 2>&1; then
  systemctl enable fstrim.timer >/dev/null 2>&1 || true
  log "    TRIM chạy được, đã bật fstrim.timer hàng tuần."
else
  warn "Box USB không truyền lệnh TRIM xuống SSD (chipset không hỗ trợ UNMAP)."
  warn "    SSD vẫn chạy nhưng sẽ chậm dần khi đầy. Chừa trống ~20% dung lượng."
fi

# ------------------------------------------------------------- 7. cảnh báo GPU
if [ -f /etc/X11/xorg.conf ]; then
  warn "Có /etc/X11/xorg.conf — file này ghim cấu hình GPU của một máy, cắm sang máy khác sẽ không lên màn hình."
  warn "    Nên xoá: mv /etc/X11/xorg.conf /etc/X11/xorg.conf.bak"
fi
if lsmod | grep -q '^nvidia'; then
  warn "Đang dùng driver NVIDIA đóng. Trên máy chạy Intel/AMD ổ vẫn boot (nouveau/amdgpu tự nhận),"
  warn "    nhưng module NVIDIA ký bằng MOK sẽ bị Secure Boot của máy lạ từ chối."
  warn "    Nếu định cắm sang nhiều máy: cân nhắc gỡ driver đóng."
fi

echo
log "XONG."
echo "    Ổ:            /dev/$ROOT_DISK"
echo "    ESP:          $ESP"
echo "    Secure Boot:  $([ "$SECUREBOOT_OK" = yes ] && echo 'boot được khi BẬT hoặc TẮT' || echo 'phải TẮT ở máy đích')"
echo
echo "Bước tiếp: tắt máy, rút ổ, cắm sang máy khác, vào boot menu chọn ổ USB."
echo "Nối vào bảng tin ccbus:  ./deploy/setup-client.sh <url> <token-ssd> <project>"
