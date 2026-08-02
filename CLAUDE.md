# DAp

Hệ thống nối bốn máy của một người thành một chỗ làm việc: 3 Ubuntu 24.04
(cài từ cùng một USB) + 1 MacBook, nối với nhau qua Tailscale.

**Người dùng nói tiếng Việt. Trả lời bằng tiếng Việt.**

## Bàn giao giữa các phiên

Thư mục `handoffs/` chứa các mạch việc đang mở, **mỗi mạch việc một file**. Mỗi
file ghi: đang dở tới đâu, cái gì đã xác nhận chạy trên phần cứng thật, cái gì
chưa, và những lỗi đã sửa rồi để không lặp lại.

Người dùng nói "làm tiếp" → xem `handoffs/`. Có nhiều file thì **hỏi chọn cái
nào**, đừng tự đoán: chọn nhầm mạch việc là sửa nhầm thứ. Dùng `/tieptuc` để
làm đúng trình tự này, và `/handoff` khi bàn giao đi.

Phiên chạy trên claude.ai không gõ được vào máy người dùng, nên nó thiết kế và
viết code rồi bàn giao qua thư mục này. Phiên chạy tại chỗ (`claude` trong
terminal) chạy lệnh thật được — hãy tự chạy và tự đọc kết quả, đừng bắt người
dùng copy/paste.

## Hai thành phần

| | Việc | Tài liệu |
|---|---|---|
| `ccbus` | MCP bus chia sẻ kết quả giữa các phiên Claude Code | [README.md](README.md) |
| `onepane` | gom terminal/cửa sổ nhiều máy về một màn hình | [ONEPANE.md](ONEPANE.md) |

## Bản đồ máy

Tất cả gọi nhau bằng **tên Tailscale**. Ba máy Ubuntu cài từ cùng một USB nên
**hostname trùng nhau** — đừng bao giờ dùng `hostname` để phân biệt máy.

| Tailscale | Là máy gì |
|---|---|
| `may-cty` | SSD ở công ty — nơi người dùng ngồi nhiều nhất |
| `may-nha-thi` | Acer ở nhà — cũng là máy chủ của `ccbus` |
| `thi-pc` | VivoBook |

Vai trò hub/node của `onepane` **không cố định**: hub là máy đang ngồi. Ngồi ở
đâu thì máy đó làm hub, mỗi máy giữ config riêng.

## Quy ước

- **Nhánh phát triển**: `claude/distributed-ubuntu-vm-r2997w`. Commit và push
  vào đúng nhánh này.
- **Test**: `PYTHONPATH=src python3 -m pytest tests/test_onepane_*.py`.
  Test `ccbus` cần `mcp`/`httpx`; thiếu thì bỏ qua, không phải lỗi.
- **Không dùng `pip install`** trên các máy này — Ubuntu 24.04 chặn cài vào
  Python hệ thống (PEP 668). `onepane` chỉ dùng stdlib và chạy qua wrapper ở
  `~/.local/bin/onepane`.
- **ssh luôn ở `BatchMode`**, không có đường nhập mật khẩu. Máy con cần sudo
  không mật khẩu cho `apt-get`, `wget`, `loginctl` qua `/etc/sudoers.d/onepane`.

## Nguyên tắc rút ra từ những lỗi đã mất thời gian

**Đừng nuốt lỗi.** Phần lớn lỗi tốn thời gian nhất trong repo này sống lâu vì
code chạy lệnh với `capture_output=True` rồi vứt mã thoát đi — người dùng làm
theo hướng dẫn, không ăn, và không có một dòng nào giải thích. Mỗi bước hỏng
phải nói ra.

**Đừng suy ra trạng thái từ mã thoát của lệnh có ống dẫn.** `xpra --version |
head -1` trả về mã thoát của `head` — luôn bằng 0, kể cả khi `xpra` không tồn
tại. Hỏi thẳng bằng `command -v` rồi in dấu hiệu rõ ràng.

**Đừng báo thành công khi chưa kiểm chứng.** `attach`, `run`, `up` từng in ✓
ngay sau khi sinh tiến trình, trong khi tiến trình chết một giây sau đó. Kiểm
tra rồi mới báo.

**Kiểm bằng đúng thứ được cấp.** `sudo -n true` luôn thất bại với NOPASSWD chỉ
cấp ba lệnh cụ thể — thử sai lệnh thì kết luận sai.
