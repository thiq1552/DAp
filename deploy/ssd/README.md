# Ubuntu chạy từ SSD ngoài — cắm máy nào cũng boot

Dựng một ổ SSD USB chứa Ubuntu mã hoá toàn ổ, boot được trên **acer**, **vivo**,
**cong-ty** — và nối vào bảng tin `ccbus` như máy thứ 5 tên `ssd`.

Ổ do trình cài đặt Ubuntu tạo ra theo cách thông thường chỉ boot được đúng cái
máy đã cài nó. Tài liệu này khác ở ba chỗ: bootloader đặt ở đường dẫn di động
(`/EFI/BOOT/BOOTX64.EFI`) nên không phụ thuộc NVRAM của máy nào, initramfs mang
theo driver của mọi phần cứng, và mọi tham chiếu đĩa đều bằng UUID.

> **Không dùng được trên Mac Apple Silicon.** Firmware của Apple không cho boot
> hệ điều hành khác từ thiết bị ngoài. Máy `mac` trong nhóm sẽ không cắm ổ này
> được — đó là giới hạn phần cứng, không có cách vòng.

## Chuẩn bị

| Món | Yêu cầu | Vì sao |
|---|---|---|
| SSD NVMe | 500GB–1TB | 256GB đủ chạy nhưng chật khi build |
| Box USB | 3.2 Gen2 10Gbps, chipset **RTL9210B** hoặc **JMS583** | Hai chipset này hỗ trợ UASP + TRIM. Box 5Gbps đời cũ chậm và không TRIM được → SSD xuống cấp nhanh |
| Thermal pad | Loại đi kèm box | NVMe trong vỏ kín rất nóng, quá nhiệt sẽ throttle |
| Cáp | USB-C↔C **và** một đầu C↔A | Máy cũ có thể chỉ còn cổng USB-A |
| USB stick | ≥ 8GB | Chứa bộ cài |
| ISO | Ubuntu **24.04 LTS** Desktop | Bản LTS cũ hơn có driver ổn định trên nhiều đời máy hơn bản mới nhất. Nếu phần cứng quá mới thì mới cần LTS đời sau |

Toàn bộ ổ SSD sẽ bị xoá. Passphrase LUKS gõ mỗi lần boot — chọn cái gõ được
nhanh trên bàn phím lạ, và **ghi lại ở nơi khác**: mất passphrase là mất sạch,
không có cửa sau.

## 1. Tạo USB cài đặt

```bash
# Trên một máy Ubuntu sẵn có. Kiểm tra kỹ tên thiết bị trước khi ghi.
lsblk -o NAME,SIZE,TRAN,MODEL
sudo dd if=ubuntu-24.04-desktop-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

`/dev/sdX` là **cả ổ USB**, không phải phân vùng (`sdX1`). Ghi nhầm vào ổ hệ
thống là mất máy.

## 2. Rút ổ trong ra trước khi cài

Đây là bước dễ bỏ qua nhất và cũng là bước hay làm hỏng cả kế hoạch. Trình cài
đặt Ubuntu có thói quen đặt bootloader vào phân vùng EFI của **ổ đầu tiên nó
thấy** — thường là ổ NVMe trong máy — kể cả khi bạn chọn cài hệ thống lên ổ
ngoài. Kết quả: ổ ngoài không boot độc lập được, còn máy dùng để cài thì hỏng
boot.

Chọn một máy cá nhân (`acer` hoặc `vivo` — **không dùng máy công ty**), rồi:

- Tháo nắp, rút ổ NVMe/SATA trong ra; hoặc
- Vào BIOS tắt ổ trong nếu BIOS có tuỳ chọn đó.

Nếu không làm được cả hai thì đừng cài trực tiếp — nhắn tôi, tôi viết đường
`debootstrap` không cần đụng vào ổ trong.

Tiện lúc ở trong BIOS, bật sẵn: **UEFI mode** (tắt CSM/Legacy), và ghi nhớ phím
mở boot menu — Acer `F12`, Lenovo `F12`, Dell `F12`, HP `F9`.

## 3. Cài Ubuntu lên ổ SSD

Cắm cả USB cài đặt lẫn ổ SSD, boot từ USB, chọn *Install Ubuntu*.

Tới phần chọn ổ đĩa:

1. Chọn **Erase disk and install Ubuntu** — lúc này ổ SSD là ổ duy nhất trong
   máy nên không có gì để chọn nhầm.
2. Vào **Advanced features** → chọn **Use LVM and encryption**.
3. **Quan trọng: không chọn tuỳ chọn mã hoá gắn với TPM / hardware-backed.**
   Kiểu mã hoá đó khoá key vào chip TPM của đúng máy đang cài, cắm sang máy khác
   là không mở được ổ. Phải là LUKS dùng **passphrase**.
4. Đặt passphrase, cài, khởi động lại — vẫn giữ nguyên ổ trong đang rút.

Layout thu được: ESP (fat32) + `/boot` (ext4, không mã hoá) + LUKS chứa LVM với
root và swap. Đúng cái ta cần.

## 4. Biến nó thành ổ di động

Boot vào Ubuntu vừa cài trên ổ SSD (vẫn ở máy dùng để cài), nối mạng, rồi:

```bash
git clone <repo> ~/ccbus && cd ~/ccbus
sudo ./deploy/ssd/make-portable.sh
```

Script kiểm tra ổ, rồi làm 7 việc:

| Việc | Vì sao cần |
|---|---|
| Cài `linux-firmware` + microcode Intel/AMD | Máy đích không có mạng lúc boot lần đầu để tải firmware Wi-Fi |
| `MODULES=most` trong initramfs | Mặc định `dep` chỉ nhét driver của máy đang cài → máy khác không thấy ổ, kernel panic |
| `RESUME=none` | Hibernate trỏ sang swap của máy cũ làm treo ~30s mỗi lần boot |
| Chặn `/dev/sdX` trong fstab/crypttab | Tên thiết bị đổi theo từng máy; phải là UUID |
| `usbcore.autosuspend=-1` | Ổ root nằm trên USB — controller ngủ là treo cứng hệ thống |
| Copy **shim đã ký** vào `/EFI/BOOT/BOOTX64.EFI` | Firmware mọi máy đều tự tìm đường dẫn này ở thiết bị rời, không cần entry NVRAM. Dùng shim của Ubuntu nên vẫn boot được cả khi máy đích **bật Secure Boot** |
| Thử `fstrim` | Báo ngay nếu box USB không truyền TRIM xuống SSD |

Script chạy lại được nhiều lần, không hỏng gì.

Xong thì tắt máy, lắp lại ổ trong, kiểm tra máy đó vẫn boot Windows/Ubuntu cũ
bình thường.

## 5. Thử trên máy khác

Cắm ổ vào `vivo` hoặc `cong-ty`, mở boot menu, chọn dòng có tên box USB.

- Hiện màn hình GRUB → gõ passphrase → vào desktop: xong.
- **Không thấy ổ trong boot menu:** vào BIOS bật *USB Boot*, tắt *Fast Boot*.
- **Thấy ổ nhưng báo Secure Boot violation:** shim chưa được copy (xem lại
  output của script), hoặc tắt Secure Boot trong BIOS.
- **GRUB hiện rồi treo đen sau khi gõ passphrase:** GPU lạ. Ở menu GRUB nhấn
  `e`, thêm `nomodeset` vào dòng `linux`, `Ctrl+X`. Vào được rồi thì cài driver
  cho GPU đó.
- **`ALERT! UUID=... does not exist`:** initramfs thiếu driver USB/NVMe của máy
  này — boot lại trên máy cũ và chạy lại `make-portable.sh`.

Cắm vào `cong-ty` trước khi hỏi IT là chuyện riêng của bạn, nhưng lưu ý: nếu máy
đó đang bật BitLocker, việc đổi thứ tự boot hoặc tắt Secure Boot có thể làm
Windows đòi recovery key ở lần khởi động sau. Lấy sẵn key từ tài khoản công ty
trước khi động vào BIOS.

## 6. Nối vào bảng tin ccbus

Trên **máy chủ** ccbus, cấp token cho máy mới mà không đụng token các máy đang chạy:

```bash
./deploy/add-agent.sh ssd
```

Script in ra sẵn lệnh. Chạy lệnh đó **trên ổ SSD**:

```bash
# cài Claude Code nếu chưa có
curl -fsSL https://claude.ai/install.sh | bash

./deploy/setup-client.sh http://100.x.y.z:7717 <token-ssd> ten-project
ccbus --project ten-project init /đường/dẫn/project
```

Nếu bốn máy kia đang nối qua Tailscale thì ổ SSD cũng cần: `sudo tailscale up`.
Ổ này sẽ xuất hiện dưới cái tên `ssd` trong `ccbus status` bất kể đang cắm vào
máy nào — vì tên máy suy ra từ token, không phải từ phần cứng.

## Sống chung với nó

**Tốc độ.** Box 10Gbps + NVMe cho khoảng 900–1000 MB/s tuần tự, chậm hơn NVMe
trong máy (3000+) nhưng nhanh hơn SATA. Cảm giác dùng hàng ngày gần như không
khác. Cắm nhầm cổng USB 2.0 thì rớt xuống ~40 MB/s và bạn sẽ nhận ra ngay.

**Đừng rút nóng.** Ổ này là root filesystem. Rút khi máy đang chạy là hỏng dữ
liệu, không phải "unmount không an toàn". Luôn shutdown trước.

**Backup.** Ổ rời rơi, mất, hỏng cổng nhiều hơn ổ trong máy. Những gì chỉ tồn
tại trên ổ này — token, SSH key, code chưa push — nên có bản thứ hai.

**Sau khi cắm sang máy mới lần đầu**, chạy `sudo apt install --install-recommends
linux-generic` nếu Wi-Fi hoặc GPU chưa nhận, rồi `sudo update-initramfs -u -k all`
để lần sau boot thẳng.
