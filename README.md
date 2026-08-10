# ccbus — bảng tin dùng chung cho nhiều máy chạy Claude Code

Bạn có 4 máy (3 Ubuntu + 1 Mac) cùng chạy Claude Code, chia một project thành
nhiều task nhỏ cho từng máy. Vấn đề: các phiên Claude Code hoàn toàn cô lập —
máy A không biết máy B vừa chốt schema gì, vừa sửa file nào.

`ccbus` là một MCP server chạy trên **một** máy. Ba máy còn lại nối vào qua HTTP.
Mỗi máy đăng kết quả của mình lên bảng tin chung và đọc kết quả của máy khác khi cần.

```
   acer     ──┐
   vivo     ──┼──►  ccbus (HTTP/MCP + SQLite)  ◄── mac
   cong-ty  ──┘        chạy trên máy hay bật nhất
```

Không cần chia sẻ ổ đĩa, không cần cả 4 máy cùng bật. Máy nào online thì đọc
được mọi thứ đã đăng trước đó.

## Nó cho Claude làm được gì

| Nhóm | Tool | Dùng khi |
|---|---|---|
| Bảng tin | `share_output` | xong một việc máy khác cần biết |
| | `get_output` | đọc kết quả máy khác đã đăng |
| | `list_outputs` | đầu task, xem đã có gì rồi để khỏi làm lại |
| | `search_outputs` | tìm theo từ khoá trong mọi output |
| | `wait_for_output` | task đang chờ kết quả máy khác |
| Hàng đợi | `task_add` | bỏ task nhỏ vào hàng đợi chung |
| | `task_claim` | nhận task tiếp theo (không đụng nhau) |
| | `task_finish` | đóng task, trỏ tới output đã đăng |
| | `task_list` | xem hàng đợi |
| Khoá | `lock_acquire` / `lock_release` | tránh hai máy cùng sửa một file |
| Trạng thái | `bus_status` | ai online, đang khoá gì, hàng đợi ra sao |

Ba thứ đáng chú ý:

- **Mỗi máy một token riêng.** Server suy ra tên máy từ token, nên mọi entry đều
  biết do máy nào đăng — Claude không phải tự khai báo và không khai sai được.
- **Task có phụ thuộc.** `task_add(..., depends_on=["api/auth-schema"])` — task chỉ
  được nhận sau khi key đó đã có trên bảng tin. Đây là cách diễn đạt "task B cần
  kết quả task A".
- **Máy chết không làm kẹt hàng đợi.** Task bị giữ quá `CCBUS_CLAIM_TTL` (mặc định
  1 giờ) tự quay lại hàng đợi; quá số lần thử thì chuyển sang `dead`.

## Cài đặt

### 1. Trên máy chủ

Chọn máy bật thường xuyên nhất và có địa chỉ ổn định — không phải máy mạnh nhất.
Server rất nhẹ (vài chục MB), máy 8GB gánh thoải mái; nhưng server tắt là các máy
kia mất bảng tin.

```bash
git clone <repo> ccbus && cd ccbus
./deploy/setup-host.sh acer vivo cong-ty mac
```

Script sẽ tạo venv, sinh token riêng cho từng máy, cài systemd user service, và
in ra sẵn lệnh `claude mcp add` cho từng máy con. Copy đúng dòng của máy nào sang
máy đó.

Sửa cấu hình sau này: `~/.ccbus/env`, rồi `systemctl --user restart ccbus`.

### 2. Nối các máy với nhau

Nếu các máy không cùng mạng LAN, dùng [Tailscale](https://tailscale.com) — đơn giản
nhất, chạy được cả Ubuntu lẫn macOS, và không phải mở port ra Internet. Trên **mỗi**
máy, chạy trong repo:

```bash
./deploy/setup-tailscale.sh --hostname may-khac --keep-awake
tailscale ip -4      # trên máy chủ, lấy IP dạng 100.x.y.z
```

Script cài `tailscale`, bật `tailscaled`, đăng nhập vào tailnet, và bật **Tailscale
SSH** để bạn ssh thẳng vào máy đó từ các máy còn lại. Không có màn hình đồ hoạ cũng
chạy được: nó in ra một link `https://login.tailscale.com/a/...` để bạn mở bằng điện
thoại. Tất cả các máy phải đăng nhập **cùng một tài khoản** thì mới thấy nhau.

Cùng LAN thì dùng thẳng IP nội bộ. **Đừng mở port 7717 ra Internet** — token là
lớp bảo vệ duy nhất, chưa có TLS.

#### Điều khiển một máy từ xa

Sau khi máy đó đã vào tailnet, từ bất kỳ máy nào khác trong tailnet:

```bash
ssh thi@may-khac              # tên máy do MagicDNS phân giải
tailscale ssh thi@may-khac    # tương đương, không phụ thuộc MagicDNS
tailscale status              # xem máy nào đang online
```

Tailscale SSH không dùng key hay password — quyền vào máy do policy file của tailnet
quyết định. Tailnet mới mặc định cho phép bạn ssh vào chính máy của mình; nếu bị
`access denied` thì vào admin console → **Access controls** và thêm:

```json
"ssh": [
  { "action": "accept",
    "src": ["autogroup:member"],
    "dst": ["autogroup:self"],
    "users": ["autogroup:nonroot", "root"] }
]
```

Vài lưu ý khi máy được điều khiển là laptop:

- `--keep-awake` chặn ngủ khi đóng nắp (`logind.conf.d` + mask `sleep.target`).
  Không có nó thì đóng nắp là mất kết nối. Gỡ lại: xoá
  `/etc/systemd/logind.conf.d/99-ccbus-keep-awake.conf` rồi `systemctl unmask`.
- Thêm `--openssh` nếu muốn có `sshd` thường làm đường dự phòng; nhớ giới hạn
  `ListenAddress` vào IP `100.x.y.z` để không phơi ra LAN.
- Máy đó cũng cần chạy `setup-client.sh` mới thấy bảng tin ccbus — vào được SSH
  không có nghĩa là đã nối ccbus.

### 3. Trên mỗi máy con

```bash
./deploy/setup-client.sh http://100.x.y.z:7717 <token-của-máy-này> ten-project
```

Script kiểm tra kết nối, kiểm tra token, rồi chạy `claude mcp add` giúp bạn.
Hoặc làm tay:

```bash
claude mcp add --transport http ccbus http://100.x.y.z:7717/mcp --scope user \
  --header "Authorization: Bearer <token>"
```

`--scope user` để mọi project trên máy đó đều dùng được.

### 4. Dạy Claude tự dùng bảng tin

Đây là bước quan trọng nhất — có tool không có nghĩa Claude sẽ tự dùng đúng lúc.
Trong thư mục project **trên từng máy**:

```bash
ccbus --project ten-project init .    # chèn phần hướng dẫn vào CLAUDE.md
```

Cả 4 máy phải dùng **cùng một** `ten-project`. Nội dung gốc ở
[`src/ccbus/templates/AGENT_PROTOCOL.md`](src/ccbus/templates/AGENT_PROTOCOL.md) —
sửa cho hợp cách bạn làm việc rồi commit `CLAUDE.md` để cả 4 máy dùng chung.

## Dùng thử

Chia một project thành các task nhỏ rồi thả vào hàng đợi:

```
# trên máy nào cũng được
> Dùng ccbus tạo 4 task cho project này: schema DB, API auth, worker gửi mail, docs.
  Task API auth phụ thuộc key "db/schema", worker phụ thuộc "api/auth-schema".
```

Trên 3 máy còn lại:

```
> Nhận task tiếp theo từ ccbus và làm nó.
```

Mỗi máy `task_claim` được một task khác nhau, chờ đúng phụ thuộc của mình, và
đăng kết quả lên cho máy sau dùng.

## CLI

Xem bảng tin từ terminal mà không cần mở Claude:

```bash
. ~/.ccbus/client-env      # setup-client.sh đã tạo sẵn

ccbus status               # ai online, hàng đợi, khoá
ccbus ls                   # danh sách output
ccbus get api/auth-schema  # đọc một entry
ccbus tasks --status open
echo "kết quả benchmark" | ccbus post perf/bench --summary "120 rps"
ccbus connect              # in lệnh `claude mcp add` cho máy này
```

## Cấu hình

Đặt trong `~/.ccbus/env` trên máy chủ:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CCBUS_TOKENS` | *(trống)* | `ten-may:token,ten-may2:token2`. Trống = **không auth**, chỉ dùng khi test trên localhost |
| `CCBUS_DB` | `~/.ccbus/bus.db` | file SQLite |
| `CCBUS_HOST` / `CCBUS_PORT` | `0.0.0.0` / `7717` | địa chỉ lắng nghe |
| `CCBUS_DEFAULT_PROJECT` | `default` | tên project khi Claude không truyền `project` |
| `CCBUS_ALLOWED_HOSTS` | `*` | danh sách Host hợp lệ; đặt cụ thể để bật chống DNS rebinding |
| `CCBUS_MAX_BODY_BYTES` | `1048576` | chặn dán nguyên log dài vào bảng tin |
| `CCBUS_CLAIM_TTL` | `3600` | giây trước khi task của máy chết được trả lại hàng đợi |
| `CCBUS_MAX_ATTEMPTS` | `3` | số lần thử trước khi task thành `dead` |
| `CCBUS_AGENT_WINDOW` | `900` | giây coi là "còn online" |

## Giới hạn cần biết

- **Chưa có TLS.** Chỉ chạy trong LAN hoặc Tailscale, đừng phơi ra Internet.
- **Khoá là khoá mềm.** `lock_acquire` chỉ có tác dụng vì mọi máy đều chịu khó
  hỏi trước; nó không chặn được thao tác ghi file thật.
- **Một tiến trình, một file SQLite.** Đủ cho vài chục máy; không phải hệ thống
  hàng đợi phân tán.
- **`wait_for_output` giữ kết nối tối đa 600 giây.** Nếu Claude Code báo timeout
  trước đó, tăng `MCP_TOOL_TIMEOUT` ở máy con.
- Server chỉ lưu những gì Claude chủ động đăng. Không có gì tự động hút output
  từ phiên làm việc — chất lượng bảng tin phụ thuộc vào hướng dẫn trong `CLAUDE.md`.

## Phát triển

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest          # test kho dữ liệu, auth, và end-to-end MCP thật
```

`tests/test_mcp_e2e.py` bật server thật rồi nối vào bằng hai MCP client mang hai
token khác nhau — tức là kiểm tra đúng con đường mà 4 máy của bạn sẽ đi.
