---
chu-de: onepane — gom terminal nhiều máy về một màn hình
may: may-cty
trang-thai: đang làm
cap-nhat: 2026-08-02
---

# onepane — bàn giao cho phiên chạy tại chỗ

Bạn đang chạy trên **may-cty** (hub). Phiên trước làm việc từ xa nên mọi lệnh
phải nhờ người dùng copy/paste — chậm và dễ sai. Bạn chạy được lệnh trực tiếp,
nên hãy tự chạy và tự đọc kết quả.

## Bản đồ máy

| Tên trong config | Tailscale | Vai trò | Hostname thật |
|---|---|---|---|
| *(hub)* | `may-cty` | máy người dùng ngồi | `may-cty` |
| `acer` | `may-nha-thi` | node | `thi-Aspire-A315-57G` |
| `vivo` | `thi-pc` | node | `thi-VivoBook-ASUSLaptop-X421EAY-A415EA` |

Cả ba chạy Ubuntu 24.04 (noble), cài từ cùng một USB. **Hostname không dùng để
phân biệt máy được** — acer khác, nhưng nhiều máy trùng tên. Luôn dùng tên
Tailscale.

Người dùng nói tiếng Việt. Trả lời bằng tiếng Việt.

## onepane là gì

Repo này có hai thứ:

- **`ccbus`** — MCP bus chia sẻ kết quả giữa các phiên Claude Code. Xong từ trước,
  không đụng tới trong phiên này.
- **`onepane`** — gom terminal/cửa sổ của nhiều máy về một màn hình. Đang làm dở.

Lệnh `onepane` đã cài ở `~/.local/bin/onepane` (wrapper gọi
`PYTHONPATH=~/DAp/src python3 -m onepane.cli`). Không dùng pip vì Ubuntu 24.04
chặn cài vào Python hệ thống (PEP 668), và onepane chỉ dùng stdlib.

### Khái niệm

- **hub** = máy đang ngồi, chỉ vẽ cửa sổ, không chạy gì.
- **node** = máy chạy thật, tốn RAM/CPU của chính nó.
- **task** = một terminal có tên, là phiên tmux `op-<tên>` **trên máy con**. Không
  bao giờ đổi máy, không chết khi mất kết nối.

Ràng buộc quan trọng của người dùng: có task quét Zalo bằng Chrome headless đã
đăng nhập sẵn trên một máy cụ thể. **Chạy sang máy khác là mất phiên đăng nhập.**
Thiết kế task đảm bảo điều này vì phiên tmux nằm trên chính máy đó.

## Trạng thái hiện tại

Đã chạy được, đã xác nhận trên phần cứng thật:

- `onepane doctor` — hub và 2 node đều xanh, xpra 6.5.2 cả ba.
- `onepane task new/ls/open/kill` — tạo task trên acer và vivo, liệt kê đúng.
- `onepane term` — dựng tmux trên hub, mỗi task một cửa sổ, nhãn `việc · máy`.
- Đã xác nhận đa máy: gõ `hostname` trong cửa sổ acer trả về
  `thi-Aspire-A315-57G` trong khi người dùng ngồi may-cty.

Task đang tồn tại: `zalo quét` (acer), `build` (vivo), và hai task thử
`thu-acer` / `thu-vivo` — hai cái này xoá được sau khi thử xong.

### Chưa xác nhận — cần làm

1. **`Ctrl-a` có chuyển cửa sổ không.** Người dùng báo bấm `Ctrl-a` rồi số thì
   chỉ ra số, không đổi cửa sổ. Đã sửa nhiều vòng (xem "Lỗi đã sửa"), lần cuối
   `_verify_prefix()` không cảnh báo gì nghĩa là `prefix C-a` đã đặt được. Cần
   người dùng bấm thử vì đây là phím tương tác.
2. **Clipboard giữa hai máy.** Copy ở task máy A, dán vào task máy B. Cần GUI và
   người thật, bạn không tự kiểm được.

## Lỗi đã sửa — đừng lặp lại

Mỗi lỗi dưới đây đều từng làm mất thời gian. Chúng nằm trong test rồi.

| Lỗi | Gốc rễ |
|---|---|
| `doctor` báo `✓ xpra ?` khi máy chưa cài xpra | `xpra --version \| head -1` — mã thoát là của `head`, luôn 0 |
| `attach`/`run` báo ✓ mà không có gì chạy | không kiểm tra phiên trước khi báo thành công |
| `setup` báo thiếu sudo dù sudoers đúng | thử bằng `sudo -n true`, mà NOPASSWD chỉ cấp apt-get/wget/loginctl |
| tuỳ chọn tmux chỉ ăn ở một cửa sổ | `automatic-rename`, `allow-rename`, `window-status-*` là tuỳ chọn **cửa sổ**, phải `-wg` chứ không `-t <phiên>` |
| số cửa sổ in ra lệch với tmux | in bằng bộ đếm Python thay vì `#{window_index}` |
| loa hú | xpra chuyển tiếp cả loa lẫn micro → vòng lặp âm |

**Bài học chung: đừng nuốt lỗi.** Nhiều lỗi trên tồn tại lâu vì code chạy lệnh
với `capture_output=True` rồi vứt mã thoát đi. Luôn báo khi một bước hỏng.

## Quy ước khi làm tiếp

- **Máy con cần sudo không mật khẩu** cho `apt-get`, `wget`, `loginctl` (đặt ở
  `/etc/sudoers.d/onepane`). Cả acer và vivo đã có.
- **ssh luôn ở `BatchMode`** — không có đường nhập mật khẩu. Key đã có sẵn từ
  may-cty sang cả hai node.
- **Nhánh phát triển: `claude/distributed-ubuntu-vm-r2997w`.** Commit và push
  lên đúng nhánh này.
- **Test**: `PYTHONPATH=src python3 -m pytest tests/test_onepane_*.py`
  (71 test). Test của `ccbus` cần `mcp`/`httpx`, bỏ qua được.
- Thư mục repo: `~/DAp`. Config: `~/.config/onepane/config.ini`.

## Việc nên làm tiếp, theo thứ tự giá trị

1. **Xác nhận nốt 2 điểm chưa kiểm** ở trên. Hỏi người dùng bấm thử, đừng đoán.
2. **Filesystem chung.** Đây là lỗ hổng lớn nhất còn lại: app chạy trên máy nào
   thì thấy ổ đĩa máy đó. Người dùng lưu file trong task của acer thì file nằm
   ở acer. Cần lớp chia sẻ (NFS qua Tailscale, hoặc Syncthing) để cùng đường dẫn
   trên cả ba máy.
3. **Tự động nối khi đăng nhập** — đỡ phải gõ `onepane term` mỗi sáng.
4. **Đổi hostname ba máy** cho hết mập mờ (`hostnamectl set-hostname`).
5. **Máy Mac** làm client — xpra có bản macOS.

## Đọc thêm

- [`ONEPANE.md`](ONEPANE.md) — tài liệu đầy đủ của onepane
- [`README.md`](README.md) — tài liệu ccbus
- `src/onepane/tasks.py` — mô hình task, đọc trước khi sửa gì liên quan
