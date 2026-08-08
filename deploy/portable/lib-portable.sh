#!/usr/bin/env bash
# Phần dùng chung của hai đường dựng ổ boot di động:
#   - make-portable.sh: sửa một bản Ubuntu đã cài sẵn bằng trình cài đặt
#   - build-stick.sh:   dựng thẳng từ debootstrap
# Cả hai đều phải làm đúng hai việc dưới đây, nên để một chỗ cho khỏi lệch nhau.
#
# Không chạy trực tiếp file này — nó chỉ để `source`.

# initramfs phải mang driver của MỌI máy, không chỉ máy đang dựng.
# Mặc định MODULES=dep chỉ nhét driver của phần cứng hiện tại → cắm sang máy
# khác là kernel không thấy nổi ổ USB và panic.
portable_initramfs_conf() {
  local conf=/etc/initramfs-tools/initramfs.conf
  mkdir -p /etc/initramfs-tools/conf.d
  if grep -q '^MODULES=' "$conf" 2>/dev/null; then
    sed -i 's/^MODULES=.*/MODULES=most/' "$conf"
  else
    echo 'MODULES=most' >>"$conf"
  fi
  # RESUME trỏ tới swap của máy đã dựng; cắm sang máy khác thì initramfs đi tìm
  # một swap không tồn tại và treo khoảng 30 giây mỗi lần boot.
  echo 'RESUME=none' >/etc/initramfs-tools/conf.d/resume
}

# Firmware UEFI của mọi máy đều tự tìm <ESP>/EFI/BOOT/BOOTX64.EFI trên thiết bị
# rời, không cần entry trong NVRAM — đó là thứ làm ổ này "cắm đâu cũng boot".
#
# Đặt shim ĐÃ KÝ của Ubuntu vào đó thay vì grub trần thì ổ còn boot được cả khi
# máy đích đang bật Secure Boot. grubx64.efi.signed có prefix cố định /EFI/ubuntu
# nên nó vẫn đọc đúng grub.cfg ở đó dù bản thân nằm tại /EFI/BOOT.
#
# Đặt PORTABLE_SECUREBOOT=yes/no để phía gọi biết kết quả.
portable_bootloader() {
  local esp="$1"
  local shim=/usr/lib/shim/shimx64.efi.signed
  local grub_signed=/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed

  [ -d "$esp" ] || { echo "portable_bootloader: không thấy ESP tại $esp" >&2; return 1; }
  [ -f "$shim" ] || shim=/usr/lib/shim/shimx64.efi.signed.latest

  mkdir -p "$esp/EFI/BOOT"
  if [ -f "$shim" ] && [ -f "$grub_signed" ]; then
    install -m 644 "$shim" "$esp/EFI/BOOT/BOOTX64.EFI"
    install -m 644 "$grub_signed" "$esp/EFI/BOOT/grubx64.efi"
    [ -f /usr/lib/shim/mmx64.efi.signed ] &&
      install -m 644 /usr/lib/shim/mmx64.efi.signed "$esp/EFI/BOOT/mmx64.efi"
    PORTABLE_SECUREBOOT=yes
  else
    echo "!!  Không có shim-signed/grub-signed — dùng grub trần, chỉ boot khi Secure Boot TẮT." >&2
    grub-install --target=x86_64-efi --efi-directory="$esp" --removable --recheck
    PORTABLE_SECUREBOOT=no
  fi

  [ -f "$esp/EFI/ubuntu/grub.cfg" ] || [ -f "$esp/EFI/BOOT/grub.cfg" ] ||
    echo "!!  Chưa có grub.cfg trong $esp/EFI/ubuntu — nhớ chạy update-grub." >&2
}
