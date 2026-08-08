# Ubuntu chạy từ ổ ngoài — cắm máy nào cũng boot

Dựng một ổ USB chứa Ubuntu mã hoá LUKS, boot được trên **acer**, **vivo**,
**cong-ty** — và lên bảng tin `ccbus` như một agent mới, đứng cạnh 4 máy đã có.

Ổ do trình cài đặt Ubuntu tạo ra theo cách thông thường chỉ boot được đúng cái
máy đã cài nó. Mọi thứ ở đây khác ở ba chỗ: bootloader đặt ở đường dẫn di động
(`/EFI/BOOT/BOOTX64.EFI`) nên không phụ thuộc NVRAM của máy nào, initramfs mang
theo driver của mọi phần cứng, và mọi tham chiếu đĩa đều bằng UUID. Ba việc đó
nằm trong [`lib-portable.sh`](lib-portable.sh), dùng chung cho cả hai đường dưới.

## Phương án tối ưu

Dữ kiện: máy công ty cấp chạy Windows, RAM 16GB. Thiết bị có trong tay: **một USB
16GB**. Ổ SSD 256GB gắn ngoài đang chạy agent `cong-ty` — vẫn dùng, không đụng vào.
Máy `vivo` ở nhà để dựng. Tiêu chí cứng: **ngày bàn giao máy lại cho công ty,
không được sót một byte nào của bạn trên đó.**

Phương án: **đường A, cộng ba điều chỉnh.**

**1. Thư mục làm việc nằm trong RAM.** `/workspace` (có symlink `~/work`) là tmpfs
35% RAM — trên máy 16GB là 5.6GB. Clone repo vào đó, build ở đó. Điều này vá đúng
điểm yếu duy nhất của USB flash: ghi ngẫu nhiên 4K chậm hơn SSD hai bậc, mà `git`
và trình biên dịch thì toàn ghi kiểu đó. USB chỉ còn chứa hệ điều hành và
credential, gần như chỉ đọc — chạy nhanh hơn hẳn và sống lâu hơn nhiều.
Đổi lại: **push xong hãy tắt máy**, nội dung `/workspace` mất khi poweroff.

**2. Không đăng nhập ở console.** Sau khi gõ passphrase LUKS, cứ để nguyên màn
hình login rồi đi về. `tailscaled` và `sshd` là service hệ thống, chúng tự lên
không cần ai đăng nhập. Bạn SSH từ nhà vào. Như vậy không có phiên mở sẵn cho
người đi ngang qua bàn — thao tác duy nhất phải làm ở máy công ty là gõ passphrase.

**3. Dùng boot menu một lần (`F12`), tuyệt đối không đổi boot order trong BIOS.**
Đổi thứ tự boot là ghi vào NVRAM của máy và **nằm lại đó vĩnh viễn** — đúng loại
dấu vết bạn muốn tránh. Boot menu một lần thì không ghi gì.

### Vì sao không phải bản chạy trong RAM

Vì nó **không cải thiện tiêu chí của bạn**. Đường A đã ghi 0 byte lên ổ công ty:
`protect-internal-disks.service` khoá chỉ-đọc mọi ổ không phải USB ngay lúc boot,
kernel từ chối cả `dd` chạy bằng root. Swap nằm trong zram nên nội dung RAM cũng
không rơi xuống đĩa. Không có gì để bản RAM làm sạch hơn nữa.

Cái nó thật sự đổi được chỉ là *rút USB mang về ngay sau khi boot*. Nhưng USB đã
mã hoá LUKS — để lại trong máy qua đêm thì ai cầm được cũng không đọc nổi. Đổi lại
bạn mất persistence: mất điện là mất sạch, kể cả credential, phải setup lại từ đầu.
Cộng thêm chi phí dựng: `toram` từ phân vùng LUKS cần initramfs tuỳ biến, một bản
dựng khác hẳn.

Điều chỉnh 1 lấy được phần lợi thật sự của nó (tốc độ RAM cho việc hay ghi) mà
không phải trả cái giá nào.

### Ngày bàn giao máy

Không phải làm gì cả — không có gì để xoá, vì chưa từng có gì được ghi. Rút USB
ra là xong. Muốn tự trấn an thì boot Windows lên xem ngày sửa đổi của ổ C:.

Những thứ **không** nằm trên máy nên cũng không xoá được: DHCP lease trên router
công ty có ghi MAC và hostname, và một số BIOS ghi log thiết bị đã từng boot. Cả
hai đều ngoài tầm của hệ điều hành.

### Chỉ có một USB — nên biết trước

USB flash chết đột ngột là chuyện thường, và đây là thiết bị duy nhất bạn có cho
việc này. Không có bản dự phòng nghĩa là hôm nó chết thì mất luôn buổi đó. Hai
cách giảm đau, không cái nào tốn tiền:

- **Đừng để thứ gì chỉ tồn tại trên USB.** Code thì push, kết quả thì đăng lên
  ccbus. Dựng lại một cái mới mất 30 phút và một lệnh — miễn là không mất dữ liệu.
- Khi nào mua thêm USB (hoặc ổ SSD), dựng bản thứ hai bằng đúng lệnh đó, để ở nhà.

## Gọi tên cho khỏi lẫn

| Tên trong tài liệu | Là cái gì |
|---|---|
| **USB** (trong tên script là `stick`) | Cái USB 16GB của bạn. Sau khi dựng xong, **nó chính là hệ điều hành** — không phải bộ cài, không phải ổ chứa file |
| **Máy nhà** | Máy Ubuntu ở nhà bạn. Chỉ dùng một lần, để dựng cái USB |
| **Máy công ty cấp** | Laptop/PC công ty giao, đang chạy **Windows**. Chỉ cho USB mượn CPU. Không cài gì lên nó, không sửa gì trong nó |
| `usb16` | Tên của hệ thống-trên-USB trên bảng tin ccbus — agent **mới**, không phải `cong-ty` |
| `cong-ty` | Agent đã có: ổ SSD 256GB gắn ngoài, vẫn đang chạy. USB không thay nó |

Bốn máy `acer`, `vivo`, `cong-ty`, `mac` là các agent đã có sẵn trên ccbus.
**Máy công ty cấp không phải một agent** — nó chỉ là phần cứng. Agent là cái ổ
đang cắm vào nó: hiện tại là ổ SSD 256GB gắn ngoài, lên bảng tin dưới tên
`cong-ty`.

Tên agent đến từ **token**, không phải hostname: `resolve_agent()` trong
[`src/ccbus/server.py`](../../src/ccbus/server.py) tra bearer token ra tên máy.
`--hostname` chỉ là tên máy tự gọi mình ở local (dấu nhắc shell, SSH, DHCP lease).

> **Mỗi thiết bị một token riêng.** Cái USB 16GB là hệ thống **thứ hai**, đứng
> cạnh ổ SSD `cong-ty` chứ không thay nó. Dùng chung token thì server thấy hai
> thiết bị là *một* agent: `bus_status` gộp làm một dòng, `task_claim` của hai
> bên tranh nhau, và khoá của máy này lại nghĩ là của máy kia. Cấp token mới bằng
> `./deploy/add-agent.sh <tên>` — lệnh đó thêm token mà không xoay token của các
> máy đang chạy.

## Chọn đường nào

| | **A. USB sẵn có** | **B. SSD trong box** |
|---|---|---|
| Script | [`build-stick.sh`](build-stick.sh) | [`make-portable.sh`](make-portable.sh) |
| Cách dựng | `debootstrap` thẳng từ máy Ubuntu ở nhà | Trình cài đặt Ubuntu + USB cài đặt |
| Cần thêm gì | Không — một USB là đủ | Phải mua SSD + box, cần thêm USB cài đặt |
| Giao diện | Console, không GUI | Desktop đầy đủ |
| Hợp với | Để máy chạy task qua buổi chiều, không lưu file | Dùng như máy làm việc di động |

Đường **A** không có trình cài đặt tham gia, nên cái bẫy lớn nhất của đường B —
bootloader bị ghi nhầm vào ổ trong của máy — không tồn tại. Cũng không phải rút
ổ trong ra. Nếu bạn chỉ cần *máy chạy*, đi đường A.

> **Không dùng được trên Mac Apple Silicon.** Firmware của Apple không cho boot
> hệ điều hành khác từ thiết bị ngoài. Máy `mac` trong nhóm sẽ không cắm được —
> đó là giới hạn phần cứng, không có cách vòng.

---

# Đường A — USB, dựng bằng debootstrap

Hệ thống thu được: Ubuntu Server mã hoá LUKS, không GUI, **ghi xuống USB rất
ít**. USB có ghi ngẫu nhiên 4K cực chậm (0.3–1 MB/s, kém SSD hai bậc) và
không có wear leveling tử tế, nên chạy Ubuntu Desktop lên USB là đơ liên tục và
chết USB sau vài tuần. Cấu hình dưới đây né gần hết chỗ ghi:

| Thiết lập | Tác dụng |
|---|---|
| Không cài desktop | Bỏ nguồn ghi nền lớn nhất |
| `journald Storage=volatile` | Log nằm trong RAM, mất khi tắt máy — bạn không cần lưu |
| `/tmp`, `/var/tmp` là tmpfs | Ghi tạm không chạm USB |
| zram thay swap | Swap trên USB là án tử cho nó |
| `commit=600` | ext4 gom ghi 10 phút mới xả một lần |
| `noatime` | Không ghi lại thời điểm truy cập mỗi lần đọc file |
| Tắt unattended-upgrades | Không tự cập nhật ngầm lúc nửa đêm |

Đánh đổi: rút nóng hoặc mất điện thì mất tối đa 10 phút thay đổi cuối, và log
biến mất sau mỗi lần tắt. Với mục đích "để máy chạy task" thì cả hai đều không sao.

> **Chỉ có đúng một thiết bị USB trong toàn bộ đường A** — cái USB 16GB, và nó
> *là* hệ điều hành. Không có USB cài đặt riêng, vì `debootstrap` dựng thẳng từ
> máy Ubuntu đang chạy chứ không qua trình cài đặt nào. Mọi chữ "USB" dưới đây
> đều trỏ vào đúng cái đó. (Đường B mới cần hai thiết bị: một USB cài đặt và ổ SSD.)

## Nó KHÔNG phải cái gì

Ba hiểu nhầm dễ mắc, vì cái USB này trông giống mấy thứ khác:

**Không phải phần mềm cắm vào Windows đang chạy.** Cái USB *là* một hệ điều hành,
không phải chương trình để Windows cài. Cắm vào máy đang chạy Windows thì Windows
chỉ thấy một ổ đĩa lạ nó không đọc nổi (ext4 trong LUKS). Muốn dùng phải **tắt hẳn
Windows rồi khởi động lại từ USB**.

**Windows và Ubuntu không chạy song song.** Boot từ USB nghĩa là Windows đang tắt.
Không có chuyện vừa làm việc trên Windows vừa để Ubuntu chạy nền — tại một thời
điểm máy chỉ là cái này hoặc cái kia.

**Không cài gì lên máy rồi rút USB ra.** USB là ổ root; rút nó ra cũng như rút ổ
cứng của máy đang chạy. Nó phải cắm suốt thời gian máy chạy.

Ràng buộc gốc: hệ điều hành phải nằm ở đâu đó. Hoặc **trên USB** — thì USB phải ở
lại trong máy. Hoặc **trên ổ cứng máy công ty** — thì trái mục tiêu không để lại
dấu vết. Cách duy nhất thoát khỏi lựa chọn này là nạp toàn bộ hệ thống vào RAM rồi
rút USB, nhưng đó là một bản dựng khác hẳn, chưa làm ở đây.

## A0. Máy công ty cấp — cần cài gì?

**Không cài gì cả.** Windows trên máy đó không bị đụng tới: không cài phần mềm,
không thêm driver, không sửa registry, không tạo phân vùng. Toàn bộ hệ điều hành
nằm trên USB, và ổ đĩa trong máy còn bị khoá chỉ-đọc lúc boot (mục A3).

Nhưng có bốn thứ phải **kiểm tra** trước, làm một lần. Nếu thứ nào không đạt thì
biết sớm còn hơn đứng mò lúc 5 giờ chiều:

**1. BitLocker — quan trọng nhất.** Ổ Windows của máy công ty rất hay được mã hoá
BitLocker. Khi đó, đổi thứ tự boot hoặc tắt Secure Boot có thể làm Windows đòi
recovery key ở lần khởi động sau. Mở CMD hoặc PowerShell **bằng quyền admin**:

```
manage-bde -status
```

Thấy `Protection Status: Protection On` thì **lấy recovery key trước khi động vào
BIOS**. Key nằm trong tài khoản Microsoft/Azure AD của công ty, hoặc phải xin IT.
Không có key mà lỡ kích hoạt là máy công ty không vào được Windows — hỏng việc
thật, không phải phiền toái nhỏ.

**2. BIOS có mật khẩu không.** Khởi động lại, bấm `F2` hoặc `Del`. Bị hỏi mật khẩu
mà bạn không có thì kế hoạch dừng ở đây.

**3. Boot từ USB có bị chặn không.** Trong BIOS tìm mục `USB Boot` — nhiều máy
công ty tắt hẳn. Cũng tắt luôn `Fast Boot` nếu có, không thì boot menu hay bị bỏ qua.

**4. Phím mở boot menu.** Acer/Lenovo/Dell thường là `F12`, HP là `F9`. Ghi nhớ
để khỏi mò lúc vội.

Secure Boot thì **không cần tắt** — script đặt shim đã ký của Ubuntu vào USB nên
boot được cả khi Secure Boot đang bật. Cứ để nguyên, đỡ một thay đổi trong BIOS.

Còn *Fast Startup* của Windows (Windows không tắt hẳn mà ngủ đông một phần) thì
kệ nó, đừng tắt. Nó chỉ gây hỏng dữ liệu nếu Linux mount ổ Windows để ghi — mà ở
đây ổ đó không bao giờ được mount, lại còn bị khoá chỉ-đọc.

## A1. Trên máy Ubuntu ở nhà

Cắm USB vào `acer` hoặc `vivo` — máy nào chạy Ubuntu cũng được, không khác gì
nhau. Rồi chạy bản kiểm tra trước; nó **chỉ đọc**, không ghi vào đâu:

```bash
./deploy/portable/preflight.sh
```

Nó trả lời bốn câu: máy này có đủ công cụ chưa (thiếu thì in sẵn lệnh `apt`),
`debootstrap` có biết bản `noble` không, có tải được kho Ubuntu không, và **thiết
bị nào là USB của bạn** — kèm cảnh báo rõ ổ nào là ổ hệ thống để bạn không trỏ
nhầm. Cột `SPEED` là tốc độ cổng đang cắm: `480` là USB 2.0 (đổi cổng đi),
`5000` trở lên là USB 3.x.

Thiếu công cụ thì cài:

```bash
sudo apt install debootstrap cryptsetup-bin gdisk dosfstools parted
```

Xem trước kế hoạch, **chưa đụng gì vào USB**:

```bash
sudo ./deploy/portable/build-stick.sh /dev/sdX --dry-run
```

Nó in ra bảng phân vùng dự kiến và toàn bộ nội dung `/etc/fstab`, `/etc/crypttab`
sẽ ghi. Đọc kỹ rồi mới chạy thật:

```bash
sudo ./deploy/portable/build-stick.sh /dev/sdX --user <tên-đăng-nhập> --hostname usb16
```

Script hỏi ba thứ: gõ lại đúng đường dẫn thiết bị để xác nhận (đây là lớp bảo vệ
thật sự — nó sẽ **xoá sạch** thiết bị đó), passphrase LUKS, và mật khẩu đăng nhập.
Sau đó chạy khoảng 15–30 phút tuỳ mạng.

Phân vùng nó tạo:

```
p1   512M   fat32   ESP        -> /boot/efi
p2     1G   ext4    /boot       (không mã hoá — GRUB phải đọc được)
p3   còn lại LUKS2 -> ext4 -> / (mở bằng passphrase lúc boot)
```

Script từ chối thiết bị dưới 8GB và cảnh báo nếu dưới 14GB.

### Hết bao nhiêu dung lượng

| Thành phần | |
|---|---|
| Hệ nền debootstrap | ~350 MB |
| Kernel + modules + `linux-modules-extra` | ~1.1 GB |
| `linux-firmware` | 534 MB |
| GRUB, cryptsetup, systemd | ~200 MB |
| NetworkManager, ssh, git, python3 | ~150 MB |
| Claude Code, Tailscale | ~350 MB |
| **Tổng** | **~2.7 GB** |

Trên USB 16GB: trừ 1.5GB cho ESP và `/boot`, còn ~13.4GB cho root, dùng hết 2.7GB
→ **trống khoảng 10.8GB**. Và nó không phình thêm khi dùng, vì `/workspace` với
log đều nằm trong RAM còn `.deb` thì không giữ lại.

`linux-modules-extra` và `linux-firmware` chiếm gần hai phần ba, nhưng đó chính là
thứ làm USB boot được trên máy lạ — không cắt được.

Không có phân vùng swap: swap nằm trong RAM qua zram. Không có LVM: chỉ một
filesystem trong LUKS, đỡ một tầng phức tạp không dùng đến.

## A2. Boot thử ngay tại nhà

Đừng mang thẳng lên công ty — boot thử ngay trên máy vừa dựng nó.

Script chạy xong đã tự umount và đóng LUKS, nên **cứ để nguyên USB trong cổng**:
tắt máy nhà, bật lại, vào boot menu chọn USB, gõ passphrase, đăng nhập. Không
phải rút ra cắm vào gì cả.

Lúc này bạn có hai hệ điều hành trên cùng cái máy nhà: Ubuntu trong ổ trong (cái
vừa dùng để dựng) và Ubuntu trên USB. Chọn nhầm thì chỉ việc tắt đi boot lại —
USB không đụng gì tới ổ trong.

Vào được rồi thì nối mạng và nối bảng tin:

```bash
nmtui                                   # chọn Wi-Fi
sudo tailscale up                       # nếu 4 máy kia đang dùng Tailscale
curl -fsSL https://claude.ai/install.sh | bash
./deploy/setup-client.sh http://100.x.y.z:7717 <token-usb16> ten-project
```

Token lấy trên **máy chủ ccbus** trước, vì đây là agent mới:

```bash
./deploy/add-agent.sh usb16
```

Lệnh đó sinh token, ghi vào `~/.ccbus/env`, khởi động lại server để nạp, rồi in
sẵn dòng `setup-client.sh` để bạn dán sang. Token của `acer`, `vivo`, `cong-ty`,
`mac` giữ nguyên không đổi.

Đừng dùng lại token `cong-ty` — ổ SSD 256GB đang cầm nó. Hai thiết bị chung một
token thì server thấy chúng là một agent, và `task_claim` của hai bên sẽ tranh nhau.

## A3. Máy công ty còn lại gì sau khi rút USB

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
**tha** ổ nào nó không phân loại được kiểu kết nối, vì khoá nhầm cái USB đang
chạy sẽ biến hệ thống thành chỉ-đọc giữa chừng.

### Những dấu vết vẫn còn

Nói thẳng, vì "không lưu gì" chỉ đúng với ổ đĩa:

**Mạng công ty thấy bạn.** Máy xin DHCP thì lease ghi lại MAC và hostname `usb16`
trên router/DHCP server. Traffic Tailscale là UDP mã hoá — nội dung thì không ai
đọc được, nhưng việc *có* traffic thì hiện rõ. Đây là dấu vết nằm ngoài cái máy,
khoá ổ đĩa không giải quyết được.

**Đừng `apt upgrade` gói GRUB khi đang cắm ở máy công ty.** Script dựng USB
dùng `grub-install --no-nvram` nên không thêm entry vào NVRAM của máy nào. Nhưng
postinst của gói `grub-efi-*` khi cập nhật có thể tự chạy `grub-install` và ghi
NVRAM của cái máy đang cắm. Cập nhật ở nhà, đừng cập nhật ở công ty.

**Firmware và TPM.** Một số BIOS ghi log thiết bị đã boot, và giá trị PCR của TPM
thay đổi khi boot hệ điều hành khác. Không xoá được từ phía hệ điều hành.

**Có người nhìn thấy màn hình.** Cái này thì không có giải pháp kỹ thuật nào.

## A4. Quy trình dùng hàng ngày

Ở máy công ty, sau khi tắt hẳn Windows — **đúng ba thao tác**:

1. Cắm USB, bật máy, bấm `F12` chọn USB (đừng đổi boot order trong BIOS)
2. Gõ passphrase LUKS
3. Đi về — **không đăng nhập ở console**

`tailscaled` và `sshd` là service hệ thống, tự lên sau khi ổ đĩa được mở khoá,
không cần ai đăng nhập. Để nguyên màn hình login thì không có phiên mở sẵn cho
người đi ngang qua bàn.

Về nhà thì `ssh usb16` qua Tailscale, hoặc để nó tự nhận task từ `ccbus`. Làm
việc trong `~/work` (chính là `/workspace`, nằm trong RAM):

```bash
ssh usb16
cd ~/work && git clone <repo> && cd <repo>
```

**Push xong hãy tắt máy** — `/workspace` là tmpfs, poweroff là sạch.

Kết thúc thì tắt sạch, từ nhà cũng được:

```bash
ssh usb16 sudo poweroff
```

Sáng hôm sau ra rút USB. Máy bật lại là vào Windows như chưa có gì xảy ra.

**USB phải cắm suốt thời gian máy chạy** — nó là ổ root, không phải bộ cài.
Ai rút giữa chừng thì Linux chết ngay tại chỗ: bẩn, nhưng ổ trong vẫn không bị
ghi gì, và máy khởi động lại là về Windows. Mất tối đa 10 phút thay đổi cuối
trên USB vì `commit=600`.

Ba chỗ kế hoạch có thể vỡ, biết trước thì đỡ mất buổi:

**Bạn phải có mặt để boot.** Cắm USB, chọn boot menu, gõ passphrase — đều cần
tay người. Không có cách boot nó từ xa.

**LUKS chặn khởi động lại tự động.** Máy reboot vì bất kỳ lý do gì — mất điện, IT
đẩy update — là dừng ở màn hình hỏi passphrase cho tới sáng hôm sau. Đó là cái
giá của mã hoá; đổi lại, ai rút USB mang đi cũng không đọc được token ccbus và
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
| USB cài đặt | ≥ 8GB, **riêng** ngoài ổ SSD | Chứa bộ cài Ubuntu. Đường B cần hai thiết bị USB: cái này để cài, ổ SSD là đích |
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
sudo ./deploy/portable/make-portable.sh
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
