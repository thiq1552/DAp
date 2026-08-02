---
description: Viết bàn giao vào HANDOFF.md rồi push, để phiên khác tiếp tục được
---

Ghi bàn giao cho phiên Claude tiếp theo vào `HANDOFF.md` (ghi đè nội dung cũ),
rồi commit và push lên nhánh phát triển của repo.

Bối cảnh thêm từ người dùng (có thể trống): $ARGUMENTS

Người đọc file này là **một phiên Claude khác, không có ký ức gì về cuộc hội
thoại này**. Viết cho người đó, không phải cho người dùng. Nếu bối cảnh trên chỉ
rõ máy nào sẽ chạy tiếp, viết cho đúng máy đó.

Nội dung cần có, bỏ mục nào không áp dụng:

1. **Đang làm gì** — mục tiêu của chặng này trong 2–3 câu. Vì sao làm, không chỉ
   làm gì.
2. **Tới đâu rồi** — tách bạch hai loại: cái **đã chạy thật và tự tay xác nhận**,
   và cái **mới viết xong nhưng chưa chạy**. Đừng gộp; phiên sau tin nhầm là mất
   thời gian gấp đôi.
3. **Chưa xác nhận / đang kẹt** — nói rõ cần gì để xác nhận. Thứ nào chỉ người
   thật kiểm được (bấm phím, nhìn màn hình, thao tác GUI) thì ghi rõ là phải nhờ
   người dùng, đừng để phiên sau tưởng tự làm được.
4. **Lỗi đã sửa và gốc rễ** — dạng bảng. Ghi *nguyên nhân*, không chỉ triệu
   chứng. Đây là phần giá trị nhất: nó chặn phiên sau đi lại vết xe cũ.
5. **Việc tiếp theo** — xếp theo giá trị, kèm một câu vì sao cái đầu tiên đáng
   làm trước.
6. **Cạm bẫy** — ràng buộc của môi trường thật mà đọc code không thấy: máy nào
   tên gì, quyền gì cần sẵn, lệnh nào không dùng được, giả định nào sai.

Cách viết:

- Tiếng Việt.
- Cụ thể hơn là đầy đủ. Đường dẫn thật, tên lệnh thật, tên máy thật.
- Đừng chép lại thứ đọc code là biết. Chỉ ghi cái **không suy ra được** từ repo:
  kết quả chạy thật, quyết định và lý do, chỗ đã thử và thất bại.
- Nếu `HANDOFF.md` cũ còn mục nào đúng thì giữ, đừng bịa lại.

Xong thì commit với thông điệp mô tả chặng vừa làm, rồi push lên nhánh phát
triển. Cuối cùng in cho người dùng **đúng hai dòng** họ cần gõ ở máy kia.
