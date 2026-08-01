## Làm việc nhiều máy qua ccbus

Project này được chia nhỏ cho nhiều máy cùng chạy Claude Code. Các máy không
thấy màn hình của nhau — thứ duy nhất dùng chung là bảng tin `ccbus` (MCP server).
Nếu một kết quả không được đăng lên bảng tin thì coi như các máy khác không biết.

**Tên project trên bảng tin:** `<ĐIỀN_TÊN_PROJECT>` — luôn truyền `project` này
trong mọi lời gọi ccbus (hoặc bỏ trống nếu server đã đặt đúng mặc định).

### Bắt đầu một task

1. `bus_status` — xem máy nào đang online và đang giữ khoá gì.
2. `list_outputs` — xem máy khác đã đăng gì. Nếu việc bạn định làm đã có kết quả
   ở đó, đọc bằng `get_output` và dùng lại thay vì làm lại từ đầu.
3. `search_outputs` khi cần tìm theo từ khoá (tên hàm, tên file, lỗi cụ thể).
4. Nếu task cần kết quả máy khác chưa có: `wait_for_output` với key đã hẹn.
   Nếu hết giờ chờ, **báo lại là đang bị chặn** — đừng tự bịa ra kết quả còn thiếu.

### Trong lúc làm

- Sắp sửa file/thư mục mà máy khác có thể đụng → `lock_acquire` trước,
  `lock_release` ngay khi xong. Nếu `acquired: false`, chuyển sang việc khác.
- Chốt được một quyết định ảnh hưởng máy khác (tên API, schema, format dữ liệu)
  → đăng ngay bằng `share_output` với `kind: "decision"`, đừng đợi tới cuối task.
- Gặp lỗi chặn đường mà máy khác cũng sẽ gặp → `share_output` với `kind: "blocker"`.

### Khi xong

`share_output` với:

- `key`: đặt theo dạng `<vùng>/<việc>`, ví dụ `api/auth-schema`, `db/migration-plan`,
  `perf/bench-baseline`. Key phải ổn định — đăng lại cùng key sẽ tạo version mới,
  không mất lịch sử.
- `summary`: một dòng, để máy khác quét nhanh trong danh sách.
- `body`: **thứ máy khác thực sự cần để đi tiếp** — quyết định, chữ ký hàm/API,
  đường dẫn file, commit sha, cách chạy. Không dán nguyên log build hay diff dài;
  tóm tắt rồi trỏ tới file/commit.
- `kind`: `output` | `decision` | `interface` | `note` | `blocker`.

Nếu task lấy từ hàng đợi chung thì kết bằng `task_finish` với `result_key` trỏ
đúng vào entry vừa đăng.

### Hàng đợi chung (khi chia một project thành nhiều task nhỏ)

- `task_add` — bỏ task vào hàng đợi; `depends_on` là danh sách key trên bảng tin
  phải có trước thì task mới được nhận.
- `task_claim` — nhận task tiếp theo. Không bao giờ có hai máy nhận cùng một task.
  Kết quả trả về kèm tóm tắt output của các phụ thuộc.
- `task_finish` — `status: "done"` hoặc `"failed"`. Task `failed` tự quay lại hàng đợi.

### Nguyên tắc

Đăng bảng tin là để **máy khác** đọc, không phải để ghi nhật ký cho bản thân.
Trước khi đăng, tự hỏi: một máy chưa từng thấy phiên làm việc này có đọc hiểu và
đi tiếp được không?
