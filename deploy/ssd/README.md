# Ubuntu chạy từ ổ ngoài — cắm máy nào cũng boot

Dựng một ổ USB chứa Ubuntu mã hoá LUKS, boot được trên **acer**, **vivo**,
**cong-ty** — và nối vào bảng tin `ccbus` như máy thứ 5 tên `ssd`.

Ổ do trình cài đặt Ubuntu tạo ra theo cách thông thường chỉ boot được đúng cái
máy đã cài nó. Mọi thứ ở đây khác ở ba chỗ: bootloader đặt ở đường dẫn di động
(`/EFI/BOOT/BOOTX64.EFI`) nên không phụ thuộc NVRAM của máy nào, initramfs mang
theo driver của mọi phần cứng, và mọi tham chiếu đĩa đều bằng UUID. Ba việc đó
nằm trong [`lib-portable.sh`](lib-portable.sh), dùng chung cho cả hai đường dưới.

## Chọn đường nào

| | **A. USB stick sẵn có** | **B. SSD trong box** |
|---|---|---|
| Script | [`build-stick.sh`](build-stick.sh) | [`make-portable.sh`](make-portable.sh) |
| Cách dựng | `debootstrap` thẳng từ máy Ubuntu ở nhà | Trình cài đặt Ubuntu + USB cài đặt |
| Cần thêm gì | Không — một stick là đủ | Phải mua SSD + box, cần thêm USB cài đặt |
| Giao diện | Console, không GUI | Desktop đầy đủ |
| Hợp với | Để máy chạy task qua buổi chiều, không lưu file | Dùng như máy làm việc di động |

Đường **A** không có trình cài đặt tham gia, nên cái bẫy lớn nhất của đường B —
bootloader bị ghi nhầm vào ổ trong của máy — không tồn tại. Cũng không phải rút
ổ trong ra. Nếu bạn chỉ cần *máy chạy*, đi đường A.

> **Không dùng được trên Mac Apple Silicon.** Firmware của Apple không cho boot
> hệ điều hành khác từ thiết bị ngoài. Máy `mac` trong nhóm sẽ không cắm được —
> đó là giới hạn phần cứng, không có cách vòng.

---

# Đường A — USB stick, dựng bằng debootstrap

Hệ thống thu được: Ubuntu Server mã hoá LUKS, không GUI, **ghi xuống stick rất
ít**. USB stick có ghi ngẫu nhiên 4K cực chậm (0.3–1 MB/s, kém SSD hai bậc) và
không có wear leveling tử tế, nên chạy Ubuntu Desktop lên stick là đơ liên tục và
chết stick sau vài tuần. Cấu hình dưới đây né gần hết chỗ ghi:

| Thiết lập | Tác dụng |
|---|---|
| Không cài desktop | Bỏ nguồn ghi nền lớn nhất |
| `journald Storage=volatile` | Log nằm trong RAM, mất khi tắt máy — bạn không cần lưu |
| `/tmp`, `/var/tmp` là tmpfs | Ghi tạm không chạm stick |
| zram thay swap | Swap trên stick là án tử cho nó |
| `commit=600` | ext4 gom ghi 10 phút mới xả một lần |
| `noatime` | Không ghi lại thời điểm truy cập mỗi lần đọc file |
| Tắt unattended-upgrades | Không tự cập nhật ngầm lúc nửa đêm |

Đánh đổi: rút nóng hoặc mất điện thì mất tối đa 10 phút thay đổi cuối, và log
biến mất sau mỗi lần tắt. Với mục đích "để máy chạy task" thì cả hai đều không sao.

## A1. Trên máy Ubuntu ở nhà

```bash
sudo apt install debootstrap cryptsetup-bin gdisk dosfstools parted
lsblk -o NAME,SIZE,TRAN,MODEL          # tìm đúng tên stick
```

Xem trước kế hoạch, **chưa đụng gì vào stick**:

```bash
sudo ./deploy/ssd/build-stick.sh /dev/sdX --dry-run
```

Nó in ra bảng phân vùng dự kiến và toàn bộ nội dung `/etc/fstab`, `/etc/crypttab`
sẽ ghi. Đọc kỹ rồi mới chạy thật:

```bash
sudo ./deploy/ssd/build-stick.sh /dev/sdX --user <tên-đăng-nhập> --hostname ssd
```

Script hỏi ba thứ: gõ lại đúng đường dẫn thiết bị để xác nhận (đây là lớp bảo vệ
thật sự — nó sẽ **xoá sạch** thiết bị đó), passphrase LUKS, và mật khẩu đăng nhập.
Sau đó chạy khoảng 15–30 phút tuỳ mạng.

Phân vùng nó tạo:

```
p1   512M   fat32   ESP        -> /boot/efi
p2   1.5G   ext4    /boot       (không mã hoá — GRUB phải đọc được)
p3   còn lại LUKS2 -> ext4 -> / (mở bằng passphrase lúc boot)
```

Không có phân vùng swap: swap nằm trong RAM qua zram. Không có LVM: chỉ một
filesystem trong LUKS, đỡ một tầng phức tạp không dùng đến.

## A2. Boot thử ngay tại nhà

Đừng mang thẳng lên công ty. Tắt máy, cắm lại stick, vào boot menu chọn nó, gõ
passphrase, đăng nhập. Rồi nối mạng và nối bảng tin:

```bash
nmtui                                   # chọn Wi-Fi
sudo tailscale up                       # nếu 4 máy kia đang dùng Tailscale
curl -fsSL https://claude.ai/install.sh | bash
./deploy/setup-client.sh http://100.x.y.z:7717 <token-ssd> ten-project
```

Token lấy từ máy chủ ccbus bằng `./deploy/add-agent.sh ssd` — lệnh đó cấp token
cho máy mới mà không xoay token của 4 máy đang chạy.

## A3. Máy công ty còn lại gì sau khi rút stick

Mục tiêu là mượn CPU, không đụng đĩa. Hệ thống này không chạm vào ổ trong vì bốn
lý do độc lập, cái sau chặn được cả khi cái trước hỏng:

| | |
|---|---|
| Không có desktop | Không có `udisks` tự động mount ổ Windows khi thấy nó |
| Không cài `ntfs-3g` | Muốn mount NTFS bằng tay cũng không có driver |
| Không swap trên đĩa | Swap nằm trong RAM qua zram — nội dung RAM không bao giờ rơi xuống đĩa nào |
| `protect-internal-disks.service` | Lúc boot, mọi ổ **không phải USB** bị `blockdev --setro`. Kernel từ chối mọi lệnh ghi, kể cả `dd` chạy bằng root |

Lớp thứ tư là lớp duy nhất không dựa vào "không có lý do gì để ghi". Kiểm tra sau
khi boot:

```bash
lsblk -o NAME,SIZE,RO,TRAN,MOUNTPOINTS     # ổ trong phải hiện RO=1
sudo dd if=/dev/zero of=/dev/nvme0n1 count=1   # phải báo "Operation not permitted"
```

Nếu `RO` vẫn là 0, xem log: `journalctl -t protect-internal-disks`. Script cố tình
**tha** ổ nào nó không phân loại được kiểu kết nối, vì khoá nhầm cái stick đang
chạy sẽ biến hệ thống thành chỉ-đọc giữa chừng.

### Những dấu vết vẫn còn

Nói thẳng, vì "không lưu gì" chỉ đúng với ổ đĩa:

**Mạng công ty thấy bạn.** Máy xin DHCP thì lease ghi lại MAC và hostname `ssd`
trên router/DHCP server. Traffic Tailscale là UDP mã hoá — nội dung thì không ai
đọc được, nhưng việc *có* traffic thì hiện rõ. Đây là dấu vết nằm ngoài cái máy,
khoá ổ đĩa không giải quyết được.

**Đừng `apt upgrade` gói GRUB khi đang cắm ở máy công ty.** Script dựng stick
dùng `grub-install --no-nvram` nên không thêm entry vào NVRAM của máy nào. Nhưng
postinst của gói `grub-efi-*` khi cập nhật có thể tự chạy `grub-install` và ghi
NVRAM của cái máy đang cắm. Cập nhật ở nhà, đừng cập nhật ở công ty.

**Firmware và TPM.** Một số BIOS ghi log thiết bị đã boot, và giá trị PCR của TPM
thay đổi khi boot hệ điều hành khác. Không xoá được từ phía hệ điều hành.

**Có người nhìn thấy màn hình.** Cái này thì không có giải pháp kỹ thuật nào.

## A4. Quy trình dùng hàng ngày

Trước khi về, ở máy công ty: cắm stick → boot menu → passphrase → đăng nhập →
kiểm tra `tailscale status` thấy online → để đó, không tắt màn hình cũng được.
Về nhà thì `ssh ssd` qua Tailscale, hoặc để nó tự nhận task từ `ccbus`.

Kết thúc thì tắt sạch, từ nhà cũng được:

```bash
ssh ssd sudo poweroff
```

Sáng hôm sau ra rút stick. Máy bật lại là vào Windows như chưa có gì xảy ra.

**Stick phải cắm suốt thời gian máy chạy** — nó là ổ root, không phải bộ cài.
Ai rút giữa chừng thì Linux chết ngay tại chỗ: bẩn, nhưng ổ trong vẫn không bị
ghi gì, và máy khởi động lại là về Windows. Mất tối đa 10 phút thay đổi cuối
trên stick vì `commit=600`.

Ba chỗ kế hoạch có thể vỡ, biết trước thì đỡ mất buổi:

**Bạn phải có mặt để boot.** Cắm stick, chọn boot menu, gõ passphrase — đều cần
tay người. Không có cách boot nó từ xa.

**LUKS chặn khởi động lại tự động.** Máy reboot vì bất kỳ lý do gì — mất điện, IT
đẩy update — là dừng ở màn hình hỏi passphrase cho tới sáng hôm sau. Đó là cái
giá của mã hoá; đổi lại, ai rút stick mang đi cũng không đọc được token ccbus và
SSH key của bạn.

**Máy phải không được ngủ.** Script đã `mask` sẵn suspend/hibernate và đặt đóng
nắp laptop không ngủ. Nhưng BIOS máy công ty có thể có lịch tự tắt máy theo giờ —
cái đó nằm ngoài tầm với của hệ điều hành, phải kiểm tra trong BIOS.

---

# Đường B — SSD trong box

## Chuẩn bị

| Món | Yêu cầu | Vì sao |
|---|---|---|
| SSD NVMe | **1TB, Gen3, có DRAM** — vd. Samsung 970 EVO Plus hoặc SK Hynix Gold P31 | Xem mục dưới: ổ DRAM-less mất HMB khi cắm qua USB |
| Box USB | 3.2 Gen2 10Gbps, chipset **RTL9210B** (ưu tiên) hoặc **JMS583** | Cả hai có UASP + TRIM; RTL9210B mát hơn và biết ngủ khi rảnh. Box 5Gbps đời cũ chậm và thường không TRIM → SSD xuống cấp nhanh |
| Thermal pad | Loại đi kèm box | NVMe trong vỏ kín rất nóng, quá nhiệt sẽ throttle |
| Cáp | USB-C↔C **và** một đầu C↔A | Máy cũ có thể chỉ còn cổng USB-A |
| USB stick | ≥ 8GB | Chứa bộ cài |
| ISO | Ubuntu **24.04 LTS** Desktop | Bản LTS cũ hơn có driver ổn định trên nhiều đời máy hơn bản mới nhất. Nếu phần cứng quá mới thì mới cần LTS đời sau |

### Vì sao SSD phải có DRAM

USB 10Gbps chặn trần ở khoảng 1000 MB/s, nên bất kỳ SSD Gen3/Gen4 đời gần đây
nào cũng thừa sức bão hoà cổng — tiền đổ vào SSD cao cấp bị cổng USB ăn hết.
Tiêu chí đáng quan tâm không phải tốc độ tuần tự, mà là **cache bảng ánh xạ**.

Các ổ giá tốt hiện nay (WD SN770/SN570, Kingston NV2, Crucial P3) đều DRAM-less
và bù bằng **HMB** — mượn RAM của máy qua PCIe. HMB chỉ chạy khi ổ cắm thẳng vào
khe M.2; qua USB thì cầu nối không chuyển tiếp được cơ chế này, ổ chạy hoàn toàn
không cache. Ghi tuần tự vẫn đẹp, nhưng ghi ngẫu nhiên và thao tác nhiều file nhỏ
chậm rõ — đúng thứ `apt`, `git`, build và Docker layer làm suốt ngày.

Cũng đừng mua Gen4 cao cấp (990 PRO, SN850X): nóng trong vỏ kín, ăn điện từ cổng
USB vốn đã hạn chế, và vẫn bị cắt tốc độ xuống ~1/3.

Chọn 1TB thay vì 500GB: chừa trống ~20% giúp SSD bền, quan trọng hơn hẳn nếu box
hoá ra không TRIM được.

Toàn bộ ổ SSD sẽ bị xoá. Passphrase LUKS gõ mỗi lần boot — chọn cái gõ được
nhanh trên bàn phím lạ, và **ghi lại ở nơi khác**: mất passphrase là mất sạch,
không có cửa sau.

### Kiểm tra ngay khi hàng về

Lắp SSD vào box, cắm vào một máy Ubuntu bất kỳ (chưa cần cài gì):

```bash
lsusb | grep -iE 'realtek|jmicron'   # chipset có đúng như quảng cáo không
lsusb -t                             # phải thấy Driver=uas, KHÔNG phải usb-storage
sudo hdparm -t --direct /dev/sdX     # kỳ vọng 800–1000 MB/s ở cổng 10Gbps
```

`Driver=usb-storage` nghĩa là UASP không hoạt động — thường do cắm nhầm cổng USB
2.0, hoặc box nói dối về chipset. Tốc độ ~40 MB/s cũng là dấu hiệu cổng USB 2.0.
Cả hai trường hợp đều nên đổi cổng trước, còn không thì trả hàng — đừng cài
Ubuntu lên rồi mới phát hiện.

## B1. Tạo USB cài đặt

```bash
# Trên một máy Ubuntu sẵn có. Kiểm tra kỹ tên thiết bị trước khi ghi.
lsblk -o NAME,SIZE,TRAN,MODEL
sudo dd if=ubuntu-24.04-desktop-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

`/dev/sdX` là **cả ổ USB**, không phải phân vùng (`sdX1`). Ghi nhầm vào ổ hệ
thống là mất máy.

## B2. Rút ổ trong ra trước khi cài

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

## B3. Cài Ubuntu lên ổ SSD

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

## B4. Biến nó thành ổ di động

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

## B5. Thử trên máy khác

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

## B6. Nối vào bảng tin ccbus

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
