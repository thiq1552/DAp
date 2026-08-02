# onepane — nhiều máy, một màn hình

Bạn có 4 máy nối bằng Tailscale. Hiện tại muốn đụng tới máy nào thì phải mở một
phiên remote desktop riêng cho máy đó, và chuyển qua lại giữa các phiên rất cực.

`onepane` gộp **phần hiển thị** của các máy lại: cửa sổ của máy `vivo` và cửa sổ
của máy `cong-ty` nằm cạnh nhau trên cùng một desktop, cùng một thanh taskbar,
cùng một clipboard — như thể chúng chạy trên máy bạn đang ngồi.

**Phần cứng không gộp gì cả.** Firefox mở trên `vivo` vẫn ăn RAM của `vivo`,
vẫn ghi vào đĩa của `vivo`. Chỉ có pixel và sự kiện bàn phím/chuột đi qua mạng.

```
       máy bạn đang ngồi (hub)
    ┌───────────────────────────────┐
    │  [Firefox·vivo] [term·acer]   │   ← cửa sổ thật, WM cục bộ quản lý
    │  [VSCode·cong-ty]             │
    └───────────────────────────────┘
              ▲       ▲       ▲
         ssh/Tailscale (WireGuard)
              │       │       │
           vivo   cong-ty   acer      ← ứng dụng chạy thật ở đây
```

## Vì sao là "seamless" chứ không phải remote desktop

Remote desktop truyền cả một màn hình vào trong một khung hình chữ nhật — bạn
được một cái desktop *lồng trong* desktop, phải chuyển toàn màn hình để đổi máy.

xpra ở chế độ seamless truyền **từng cửa sổ một**. Cửa sổ đó do window manager
*trên máy bạn* quản lý, nên kéo thả, phóng to, Alt-Tab, snap nửa màn hình đều
chạy ở tốc độ cục bộ — độ trễ mạng không xen vào những thao tác này. Đó là khác
biệt lớn nhất so với VNC/RDP.

Thêm hai thứ đi kèm:

- **Ứng dụng sống độc lập với kết nối.** Ngắt máy hub, mở lại từ máy khác (hoặc
  điện thoại), mọi cửa sổ vẫn nguyên trạng thái. Phiên chạy dưới systemd với
  `linger` nên sống qua cả lần khởi động lại máy.
- **Clipboard dùng chung.** Copy ở máy này, dán ở máy kia, không cần nghĩ.

## Và phần quan trọng hơn: terminal

Nếu phần lớn việc bạn làm là Claude Code, build, đọc log — tức là terminal —
thì `onepane term` mới là thứ bạn dùng hàng ngày, không phải cửa sổ đồ hoạ.

Nó dựng **một phiên tmux, mỗi máy một cửa sổ**. `Ctrl-b 1/2/3` để nhảy máy,
gần như tức thời vì chỉ có text đi qua mạng. Phiên sống khi bạn ngắt kết nối,
và mở lại được từ điện thoại qua Tailscale SSH.

Cửa sổ nào cũng tự nối lại nếu máy con tắt hay ngủ — nó chờ và thử lại chứ không
biến mất kéo theo vị trí của bạn trong phiên.

## Cài

Trên **máy hub** (máy bạn ngồi trước):

```bash
pip install -e .            # trong thư mục repo này
onepane setup --hub         # xpra (bản mới) + tmux + ssh client
onepane init                # tạo ~/.config/onepane/config.ini
```

Đừng dùng `apt install xpra` cho hub: kho Ubuntu 24.04 dừng ở xpra 3.1.5, trong
khi `onepane setup` cài 6.x lên máy con — client và server lệch hai thế hệ giao
thức thì hỏng theo kiểu rất khó đoán. `setup --hub` thêm kho xpra.org rồi cài
đúng bản, nên hai đầu khớp nhau. `onepane doctor` cũng kiểm tra chuyện này và
báo nếu lệch.

Sửa `config.ini` cho khớp máy của bạn — `host` là tên Tailscale (MagicDNS) hoặc
IP `100.x.y.z`:

```ini
[node:vivo]
host = vivo
user = thi
display = :100
```

Rồi cài lên các máy con và dựng phiên:

```bash
onepane doctor        # hub ổn chưa, ssh được chưa, xpra hai đầu có khớp không
onepane setup --all   # cài xpra + systemd unit lên từng máy con (chạy lại được)
onepane up --all      # dựng phiên
onepane attach --all  # kéo cửa sổ về đây
```

`setup` cần **ssh bằng key, không hỏi mật khẩu** (mọi lệnh chạy ở `BatchMode`)
và cần `sudo` không mật khẩu trên máy con để cài gói.

### Về phiên bản xpra

Kho Ubuntu đóng băng xpra ở phiên bản của ngày phát hành — 24.04 dừng ở 3.1.5
trong khi bản chính chủ đã 6.x. `onepane setup` tự thêm kho của xpra.org theo
đúng codename của máy đó. Nếu kho chưa hỗ trợ codename ấy, script lùi về gói
trong Ubuntu và in cảnh báo — vẫn chạy, chỉ là bản cũ hơn.

Điều quan trọng: **hub và máy con phải cùng thế hệ.** Đó là lý do `setup --hub`
tồn tại và `doctor` so phiên bản hai đầu. Máy nào đã lỡ cài gói distro thì script
tự `--only-upgrade` lên bản của kho mới, vì `apt install` không tự nâng.

Vì vậy mọi lệnh trong `onepane` dùng subcommand `xpra start` chứ không phải
`xpra seamless`: từ v6 `seamless` là tên chính thức nhưng `start` vẫn là alias
hợp lệ, mà `start` thì chạy được cả trên 3.x. Một lệnh đúng cho mọi phiên bản.

## Dùng

```bash
onepane status              # bảng: máy nào online, phiên nào sống, đang nối máy nào
onepane run vivo firefox    # mở firefox TRÊN vivo, cửa sổ hiện ở đây
onepane term                # phiên tmux, mỗi máy một cửa sổ
onepane detach vivo         # cất cửa sổ đi, ứng dụng bên vivo vẫn chạy
onepane down vivo           # đóng hẳn phiên (mọi ứng dụng trong đó tắt theo)
```

`detach` và `down` khác nhau ở chỗ đó, và đây là chỗ dễ nhầm nhất: `detach` chỉ
ngắt hiển thị, `down` giết phiên.

## Giới hạn cần biết

- **Không gộp RAM/CPU.** Một tiến trình vẫn bị giới hạn bởi RAM của máy nó chạy.
  Gộp RAM thật qua mạng là chuyện không làm được: RAM ~100 nano giây, Tailscale
  ~1–2 mili giây kể cả trong LAN — chậm hơn khoảng chục nghìn lần. Các dự án từng
  thử (openMosix, Kerrighed) đều đã chết; thứ duy nhất làm được là CXL, và đó là
  cáp phần cứng trong cùng một rack chứ không phải mạng.
- **Video và game thì đừng.** xpra tốt cho cửa sổ giao diện thông thường. Xem
  phim hay 3D thì dùng Sunshine + Moonlight, chúng mã hoá bằng phần cứng.
- **macOS chỉ làm hub, không làm máy con.** xpra chạy được trên máy Mac ở vai trò
  client, nhưng chế độ seamless server thì gắn với X11 nên chỉ có Linux. Máy Mac
  của bạn vào cụm qua `onepane term` (tmux + ssh) là đủ.
- **Ứng dụng Wayland thuần** không xuất hiện trong phiên xpra. Hầu hết app vẫn
  chạy qua XWayland nên trong thực tế ít gặp; gặp thì đặt `GDK_BACKEND=x11`.
- **Không có filesystem chung.** Đây là lớp giao diện. Chia sẻ file vẫn dùng
  `ccbus` hoặc một thư mục NFS/Syncthing riêng.
- **Bảo mật dựa hoàn toàn vào ssh.** Không mở cổng TCP nào. Đừng thêm
  `--bind-tcp` mà không đọc kỹ phần xác thực của xpra.

## Phát triển

```bash
PYTHONPATH=src python -m pytest tests/test_onepane_config.py tests/test_onepane_xpra.py
```

Test phủ phần logic thuần: parse cấu hình, dựng lệnh xpra/ssh/tmux, và đọc output
của `xpra list`. Phần gọi ssh thật thì `onepane doctor` là công cụ kiểm tra.
