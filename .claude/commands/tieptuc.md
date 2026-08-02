---
description: Đọc HANDOFF.md và làm tiếp từ chỗ phiên trước dừng
---

Lấy code mới nhất, đọc `HANDOFF.md`, rồi làm tiếp từ chỗ phiên trước dừng.

Bối cảnh thêm từ người dùng (có thể trống): $ARGUMENTS

Các bước:

1. `git pull` nhánh phát triển ghi trong `CLAUDE.md`. Nếu pull xung đột thì dừng
   lại hỏi, đừng tự ý gỡ.
2. Đọc `HANDOFF.md`. Không có file đó thì nói thẳng và hỏi người dùng muốn làm gì.
3. **Kiểm chứng trước khi tin.** Bàn giao ghi "đã chạy được" không có nghĩa là bây
   giờ vẫn chạy — máy có thể đã tắt, phiên đã chết, cấu hình đã đổi. Chạy lại
   những lệnh kiểm tra rẻ tiền để biết trạng thái thật.
4. Làm mục đầu tiên trong "việc tiếp theo", trừ khi bối cảnh trên nói khác.

Trong lúc làm:

- **Tự chạy lệnh, tự đọc kết quả.** Chỉ nhờ người dùng khi thật sự cần tay người:
  bấm phím trong ứng dụng tương tác, nhìn màn hình, thao tác GUI, nhập mật khẩu.
  Mọi thứ khác hãy tự làm.
- Đọc kỹ mục "lỗi đã sửa" trước khi sửa gì — phần lớn lỗi trông giống nhau nhưng
  gốc rễ đã ghi sẵn ở đó.
- Mỗi bước hỏng phải nói ra. Đừng chạy lệnh với `capture_output` rồi vứt mã thoát.
- Đừng báo xong khi chưa kiểm chứng.

Làm xong một chặng thì cập nhật lại `HANDOFF.md` (dùng `/handoff`) rồi push, để
phiên sau — có thể là phiên trên claude.ai — bắt được ngay.
