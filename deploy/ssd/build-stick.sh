#!/usr/bin/env bash
# Dựng Ubuntu Server mã hoá LUKS lên một USB stick, tối ưu cho việc GHI ÍT.
#
# Chạy trên một máy Ubuntu đang hoạt động (máy ở nhà). Không cần USB cài đặt,
# không cần rút ổ trong của máy nào — không có trình cài đặt nào tham gia nên
# cũng không có chuyện bootloader bị ghi nhầm vào ổ trong.
#
# Dùng:
#   sudo ./deploy/ssd/build-stick.sh /dev/sdX --user thiq --hostname ssd
#   sudo ./deploy/ssd/build-stick.sh /dev/sdX --dry-run     # xem kế hoạch, không đụng ổ
#
# Kết quả: stick boot được trên mọi máy x86_64 UEFI, hỏi passphrase LUKS, vào
# thẳng console. Không GUI. /tmp và log nằm trong RAM, swap dùng zram — stick
# gần như chỉ bị ghi lúc `apt install`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/ssd/lib-portable.sh
. "$HERE/lib-portable.sh"

DEV=""; HOSTNAME_NEW="ssd"; USERNAME=""; RELEASE="noble"; DRY_RUN=0
MIRROR="http://archive.ubuntu.com/ubuntu"
MAPPER="stickcrypt"

log()  { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'LỖI: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --user)     USERNAME="$2"; shift 2 ;;
    --hostname) HOSTNAME_NEW="$2"; shift 2 ;;
    --release)  RELEASE="$2"; shift 2 ;;
    --mirror)   MIRROR="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    /dev/*)     DEV="$1"; shift ;;
    *)          die "Tham số lạ: $1" ;;
  esac
done

# ----------------------------------------------------------------- sinh config
# Tách riêng để `--dry-run` gọi được vào thư mục tạm mà không cần ổ thật.
emit_configs() {
  local root="$1" uuid_esp="$2" uuid_boot="$3" uuid_luks="$4"

  mkdir -p "$root/etc/initramfs-tools/conf.d" \
           "$root/etc/systemd/journald.conf.d" \
           "$root/etc/systemd/logind.conf.d" \
           "$root/etc/apt/apt.conf.d" \
           "$root/etc/systemd" \
           "$root/etc/default"

  # commit=600: ext4 gom ghi lại 10 phút mới xả một lần. Trên stick đây là thay
  # đổi ăn tiền nhất — đổi lại mất tối đa 10 phút dữ liệu nếu rút nóng.
  cat >"$root/etc/fstab" <<EOF
# <spec>                <mount>    <type>  <options>                                  <dump> <pass>
/dev/mapper/$MAPPER  /          ext4    defaults,noatime,commit=600,errors=remount-ro 0      1
UUID=$uuid_boot         /boot      ext4    defaults,noatime                              0      2
UUID=$uuid_esp          /boot/efi  vfat    umask=0077                                    0      1
tmpfs                   /tmp       tmpfs   defaults,noatime,nosuid,nodev,size=25%        0      0
tmpfs                   /var/tmp   tmpfs   defaults,noatime,nosuid,nodev,size=10%        0      0
EOF
  # Dùng % chứ không phải số GB cố định: cái USB này cắm vào nhiều máy RAM khác
  # nhau, và tmpfs chỉ chiếm RAM theo lượng thực dùng chứ không giữ trước, nên %
  # là trần an toàn. Máy 16GB -> /tmp tối đa 4G; máy 8GB -> 2G.

  # discard để lệnh TRIM đi xuyên qua lớp LUKS xuống tới stick. Đánh đổi: ai cầm
  # được stick sẽ biết bao nhiêu phần đã dùng. Với stick thì độ bền đáng giá hơn.
  cat >"$root/etc/crypttab" <<EOF
$MAPPER UUID=$uuid_luks none luks,discard
EOF

  # journald là thứ ghi nhiều nhất trên một máy chạy suốt đêm. Cho vào RAM.
  cat >"$root/etc/systemd/journald.conf.d/volatile.conf" <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=64M
EOF

  cat >"$root/etc/systemd/zram-generator.conf" <<'EOF'
[zram0]
zram-size = min(ram / 2, 4096)
compression-algorithm = zstd
EOF

  # Không giữ .deb sau khi cài, và không tự động cập nhật — cả hai đều là
  # nguồn ghi nền mà máy này không cần.
  cat >"$root/etc/apt/apt.conf.d/99-stick" <<'EOF'
APT::Keep-Downloaded-Packages "false";
EOF
  cat >"$root/etc/apt/apt.conf.d/20auto-upgrades" <<'EOF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
EOF

  # Máy phải chạy suốt buổi chiều sau khi bạn về: cấm mọi đường ngủ, và đóng
  # nắp laptop cũng không được ngủ.
  cat >"$root/etc/systemd/logind.conf.d/no-sleep.conf" <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF

  cat >"$root/etc/default/grub" <<'EOF'
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR=Ubuntu
# usbcore.autosuspend=-1: root nằm trên USB, controller ngủ là treo cứng máy.
GRUB_CMDLINE_LINUX_DEFAULT="usbcore.autosuspend=-1"
GRUB_CMDLINE_LINUX=""
EOF

  # Máy công ty chỉ cho mượn CPU. Đánh dấu chỉ-đọc mọi ổ không phải USB ngay lúc
  # boot, để việc "không ghi lên ổ trong" là do kernel ép chứ không phải do mình
  # nhớ đừng làm. Cả `mount` lẫn `dd` đều bị từ chối sau bước này.
  mkdir -p "$root/usr/local/sbin" "$root/etc/systemd/system/multi-user.target.wants"
  cat >"$root/usr/local/sbin/protect-internal-disks" <<'PROTECT'
#!/usr/bin/env bash
set -uo pipefail

# Ổ đang chứa / — lần ngược từ mapper LUKS lên đĩa vật lý.
root_disk="$(lsblk -no PKNAME "$(realpath "$(findmnt -no SOURCE /)")" 2>/dev/null | head -1)"
while [ -n "$root_disk" ] && [ -n "$(lsblk -no PKNAME "/dev/$root_disk" 2>/dev/null | head -1)" ]; do
  root_disk="$(lsblk -no PKNAME "/dev/$root_disk" | head -1)"
done

for path in /sys/block/*; do
  dev="$(basename "$path")"
  case "$dev" in loop*|ram*|zram*|dm-*|sr*|md*) continue ;; esac
  [ "$dev" = "$root_disk" ] && continue

  # Chỉ khoá khi chắc chắn phân loại được và chắc chắn KHÔNG phải USB.
  # Không đọc được kiểu kết nối thì tha: khoá nhầm cái stick đang chạy sẽ biến
  # hệ thống thành chỉ-đọc giữa chừng, tệ hơn nhiều so với việc bỏ sót một ổ mà
  # dù sao cũng chẳng có gì định ghi vào.
  tran="$(lsblk -dno TRAN "/dev/$dev" 2>/dev/null)"
  if [ -z "$tran" ]; then
    logger -t protect-internal-disks "bỏ qua /dev/$dev: không xác định được kiểu kết nối"
    continue
  fi
  [ "$tran" = usb ] && continue

  if blockdev --setro "/dev/$dev" 2>/dev/null; then
    logger -t protect-internal-disks "đã khoá chỉ-đọc /dev/$dev"
  fi
done
exit 0
PROTECT
  chmod 755 "$root/usr/local/sbin/protect-internal-disks"

  cat >"$root/etc/systemd/system/protect-internal-disks.service" <<'EOF'
[Unit]
Description=Khoá chỉ-đọc mọi ổ đĩa trong máy (chỉ mượn CPU, không đụng đĩa)
After=local-fs.target
Before=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/protect-internal-disks
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  ln -sf ../protect-internal-disks.service \
    "$root/etc/systemd/system/multi-user.target.wants/protect-internal-disks.service"

  printf '%s\n' "$HOSTNAME_NEW" >"$root/etc/hostname"
  cat >"$root/etc/hosts" <<EOF
127.0.0.1   localhost
127.0.1.1   $HOSTNAME_NEW
::1         localhost ip6-localhost ip6-loopback
EOF

  cat >"$root/etc/apt/sources.list" <<EOF
deb $MIRROR $RELEASE main restricted universe multiverse
deb $MIRROR $RELEASE-updates main restricted universe multiverse
deb $MIRROR $RELEASE-security main restricted universe multiverse
EOF
}

# ------------------------------------------------------------------- dry run
if [ "$DRY_RUN" -eq 1 ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  emit_configs "$TMP" "AAAA-BBBB" "1111-2222-boot" "3333-4444-luks"
  log "Kế hoạch phân vùng cho ${DEV:-/dev/sdX}:"
  printf '    p1  512M  fat32  ESP        -> /boot/efi\n'
  printf '    p2  1.5G  ext4   /boot      (không mã hoá, GRUB cần đọc được)\n'
  printf '    p3  còn lại LUKS2 -> ext4   -> /  (mapper: %s)\n' "$MAPPER"
  printf '    swap: KHÔNG có phân vùng, dùng zram trong RAM\n\n'
  log "Các file cấu hình sẽ được ghi:"
  ( cd "$TMP" && find . -type f | sort | sed 's|^\./|    /|' )
  echo
  log "Nội dung /etc/fstab:"; sed 's/^/    /' "$TMP/etc/fstab"
  log "Nội dung /etc/crypttab:"; sed 's/^/    /' "$TMP/etc/crypttab"
  echo; log "Dry run — không có gì bị ghi lên đĩa."
  exit 0
fi

# ------------------------------------------------------------------- kiểm tra
[ "$(id -u)" -eq 0 ] || die "Cần chạy bằng sudo."
[ -n "$DEV" ] || die "Thiếu thiết bị đích. Xem: lsblk -o NAME,SIZE,TRAN,MODEL"
[ -n "$USERNAME" ] || die "Thiếu --user <tên-đăng-nhập>."
[ -b "$DEV" ] || die "$DEV không phải block device."

for tool in debootstrap cryptsetup sgdisk mkfs.vfat mkfs.ext4 partprobe; do
  command -v "$tool" >/dev/null 2>&1 ||
    die "Thiếu '$tool'. Cài: sudo apt install debootstrap cryptsetup-bin gdisk dosfstools parted"
done
[ -e "/usr/share/debootstrap/scripts/$RELEASE" ] ||
  die "debootstrap trên máy này chưa biết bản '$RELEASE'.
Cách vá nhanh: sudo ln -s gutsy /usr/share/debootstrap/scripts/$RELEASE"

# Chặn việc trỏ nhầm vào ổ hệ thống — đây là script xoá sạch thiết bị.
ROOT_SRC="$(findmnt -no SOURCE / || true)"
ROOT_DISK="$(lsblk -no PKNAME "$(realpath "$ROOT_SRC")" 2>/dev/null | head -1 || true)"
while [ -n "$ROOT_DISK" ] && [ -n "$(lsblk -no PKNAME "/dev/$ROOT_DISK" 2>/dev/null | head -1)" ]; do
  ROOT_DISK="$(lsblk -no PKNAME "/dev/$ROOT_DISK" | head -1)"
done
[ "/dev/$ROOT_DISK" != "$DEV" ] || die "$DEV chính là ổ đang chạy hệ điều hành này. Dừng."

TRAN="$(lsblk -dno TRAN "$DEV" 2>/dev/null || true)"
SIZE="$(lsblk -dno SIZE "$DEV" 2>/dev/null || true)"
MODEL="$(lsblk -dno MODEL "$DEV" 2>/dev/null || true)"
[ "$TRAN" = "usb" ] || warn "$DEV không nối qua USB (tran=${TRAN:-?}). Chắc chắn đúng thiết bị chứ?"

echo
lsblk -o NAME,SIZE,TRAN,MODEL,MOUNTPOINTS "$DEV" || true
echo
warn "TOÀN BỘ $DEV ($SIZE, $MODEL) SẼ BỊ XOÁ SẠCH."
read -r -p "Gõ đúng đường dẫn thiết bị để xác nhận: " confirm
[ "$confirm" = "$DEV" ] || die "Không khớp. Dừng."

read -r -s -p "Passphrase LUKS (gõ mỗi lần boot): " LUKS_PW; echo
read -r -s -p "Nhập lại: " LUKS_PW2; echo
[ "$LUKS_PW" = "$LUKS_PW2" ] || die "Hai lần nhập không khớp."
[ ${#LUKS_PW} -ge 8 ] || die "Passphrase quá ngắn (tối thiểu 8 ký tự)."
read -r -s -p "Mật khẩu đăng nhập cho '$USERNAME': " USER_PW; echo
read -r -s -p "Nhập lại: " USER_PW2; echo
[ "$USER_PW" = "$USER_PW2" ] || die "Hai lần nhập không khớp."

# -------------------------------------------------------------------- dọn dẹp
TARGET="$(mktemp -d /tmp/stick.XXXXXX)"
cleanup() {
  set +e
  for m in dev/pts dev proc sys boot/efi boot ""; do
    mountpoint -q "$TARGET/$m" && umount -lf "$TARGET/$m"
  done
  [ -e "/dev/mapper/$MAPPER" ] && cryptsetup close "$MAPPER"
  rmdir "$TARGET" 2>/dev/null
  # Đừng để lệnh dọn dẹp cuối cùng nuốt mất mã thoát thật của script.
  return 0
}
trap cleanup EXIT

# ----------------------------------------------------------------- phân vùng
log "Xoá bảng phân vùng cũ và tạo GPT"
wipefs -a "$DEV" >/dev/null
sgdisk --zap-all "$DEV" >/dev/null
sgdisk -n1:0:+512M -t1:ef00 -c1:ESP \
       -n2:0:+1536M -t2:8300 -c2:boot \
       -n3:0:0     -t3:8309 -c3:luks "$DEV" >/dev/null
partprobe "$DEV"; udevadm settle

# nvme0n1 -> nvme0n1p1, sdb -> sdb1
part() { case "$DEV" in *[0-9]) echo "${DEV}p$1" ;; *) echo "${DEV}$1" ;; esac; }
P_ESP="$(part 1)"; P_BOOT="$(part 2)"; P_LUKS="$(part 3)"

log "Định dạng ESP và /boot"
mkfs.vfat -F32 -n ESP "$P_ESP" >/dev/null
mkfs.ext4 -q -L boot "$P_BOOT"

log "Tạo LUKS2 trên $P_LUKS (bước này lâu — cryptsetup đang đo argon2id)"
printf '%s' "$LUKS_PW" | cryptsetup luksFormat --type luks2 --batch-mode "$P_LUKS" -
printf '%s' "$LUKS_PW" | cryptsetup open "$P_LUKS" "$MAPPER" -
mkfs.ext4 -q -L root "/dev/mapper/$MAPPER"

mount "/dev/mapper/$MAPPER" "$TARGET"
mkdir -p "$TARGET/boot"; mount "$P_BOOT" "$TARGET/boot"
mkdir -p "$TARGET/boot/efi"; mount "$P_ESP" "$TARGET/boot/efi"

# ---------------------------------------------------------------- debootstrap
log "Tải hệ thống nền Ubuntu $RELEASE (mất 5–15 phút tuỳ mạng)"
debootstrap --arch=amd64 --components=main,restricted,universe,multiverse \
  "$RELEASE" "$TARGET" "$MIRROR"

log "Ghi cấu hình"
UUID_ESP="$(blkid -s UUID -o value "$P_ESP")"
UUID_BOOT="$(blkid -s UUID -o value "$P_BOOT")"
UUID_LUKS="$(blkid -s UUID -o value "$P_LUKS")"
emit_configs "$TARGET" "$UUID_ESP" "$UUID_BOOT" "$UUID_LUKS"

install -m 644 "$HERE/lib-portable.sh" "$TARGET/tmp/lib-portable.sh"
umask 077
printf '%s:%s\n' "$USERNAME" "$USER_PW" >"$TARGET/tmp/userpw"
umask 022

for m in proc sys dev dev/pts; do mkdir -p "$TARGET/$m"; done
mount -t proc  proc  "$TARGET/proc"
mount -t sysfs sys   "$TARGET/sys"
mount --bind /dev    "$TARGET/dev"
mount --bind /dev/pts "$TARGET/dev/pts"
cp /etc/resolv.conf "$TARGET/etc/resolv.conf"

# ---------------------------------------------------------------- trong chroot
log "Cài kernel, bootloader và các gói cần thiết (bước lâu nhất)"
cat >"$TARGET/tmp/stage2.sh" <<'STAGE2'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
. /tmp/lib-portable.sh

apt-get update -qq
apt-get install -y --no-install-recommends \
  linux-generic linux-firmware intel-microcode amd64-microcode \
  initramfs-tools cryptsetup cryptsetup-initramfs \
  grub-efi-amd64 grub-efi-amd64-signed shim-signed efibootmgr \
  systemd-resolved systemd-zram-generator network-manager \
  openssh-server sudo ca-certificates curl wget git \
  python3 python3-venv locales tzdata less nano htop bash-completion

locale-gen en_US.UTF-8 >/dev/null
ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf

# Tài khoản đăng nhập
user="$(cut -d: -f1 /tmp/userpw)"
useradd -m -s /bin/bash -G sudo,adm,plugdev,netdev "$user"
chpasswd </tmp/userpw
shred -u /tmp/userpw

# Cấm mọi đường ngủ — máy phải chạy suốt buổi chiều sau khi bạn về.
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
systemctl enable ssh NetworkManager systemd-resolved fstrim.timer

portable_initramfs_conf
update-initramfs -c -k all

grub-install --target=x86_64-efi --efi-directory=/boot/efi \
  --bootloader-id=ubuntu --recheck --no-nvram
update-grub
portable_bootloader /boot/efi
echo "PORTABLE_SECUREBOOT=$PORTABLE_SECUREBOOT" >/tmp/result

apt-get clean
STAGE2

chroot "$TARGET" /bin/bash /tmp/stage2.sh
SB="$(sed -n 's/^PORTABLE_SECUREBOOT=//p' "$TARGET/tmp/result")"
rm -f "$TARGET/tmp/stage2.sh" "$TARGET/tmp/lib-portable.sh" "$TARGET/tmp/result"

sync
log "XONG."
echo "    Thiết bị:     $DEV"
echo "    Hostname:     $HOSTNAME_NEW"
echo "    Đăng nhập:    $USERNAME"
echo "    Secure Boot:  $([ "$SB" = yes ] && echo 'boot được khi BẬT hoặc TẮT' || echo 'phải TẮT ở máy đích')"
echo
echo "Boot thử ngay trên máy này trước khi mang đi:"
echo "  1. Tắt máy, rút stick ra rồi cắm lại, vào boot menu chọn nó."
echo "  2. Gõ passphrase LUKS, đăng nhập bằng '$USERNAME'."
echo "  3. Nối mạng:  nmtui"
echo "  4. Nối bảng tin:  ./deploy/setup-client.sh http://<ip-máy-chủ>:7717 <token> <project>"
