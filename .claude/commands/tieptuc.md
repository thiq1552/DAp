---
description: Đọc bàn giao trong handoffs/ và làm tiếp từ chỗ phiên trước dừng
---

Lấy code mới nhất, đọc bàn giao, rồi làm tiếp từ chỗ phiên trước dừng.

Tên mạch việc và bối cảnh thêm (có thể trống): $ARGUMENTS

## Chọn bàn giao

1. `git pull` nhánh phát triển ghi trong `CLAUDE.md`. Xung đột thì dừng lại hỏi,
   đừng tự ý gỡ.
2. Liệt kê `handoffs/*.md`.
   - **Có tên trong `$ARGUMENTS`** → mở đúng file đó. Không tìm thấy thì liệt kê
     những file đang có rồi hỏi, đừng đoán file gần giống.
   - **Chỉ có một file** → dùng luôn.
   - **Nhiều file** → đọc khối metadata đầu mỗi file rồi in bảng gọn: tên file,
     `chu-de`, `may`, `trang-thai`, `cap-nhat`. Hỏi người dùng chọn cái nào.
     **Đừng tự chọn** — chọn nhầm mạch việc là sửa nhầm thứ.
   - **Không có file nào** → nói thẳng và hỏi người dùng muốn làm gì.
3. In `phien:` của file đã chọn cho người dùng thấy. Đó là link tới cuộc hội thoại
   đã tạo ra bàn giao này — họ mở lại được nếu cần xem đã bàn những gì.
4. File có ghi `may:` khác máy đang chạy thì nói ra trước khi làm — có thể người
   dùng gõ nhầm phiên.

## Trước khi tin bàn giao

**Kiểm chứng lại.** "Đã chạy được" lúc viết không có nghĩa bây giờ vẫn chạy: máy
có thể đã tắt, phiên đã chết, cấu hình đã đổi, nhánh đã đi tiếp. Chạy lại những
lệnh kiểm tra rẻ tiền để biết trạng thái thật rồi hãy làm tiếp.

Đọc kỹ mục "lỗi đã sửa" trước khi sửa gì — phần lớn lỗi trông giống nhau nhưng
gốc rễ đã ghi sẵn ở đó.

Nếu bàn giao có nhắc mạch việc khác giẫm lên, đọc luôn file đó trước khi sửa
những chỗ chung.

## Trong lúc làm

- Làm mục đầu tiên trong "việc tiếp theo", trừ khi `$ARGUMENTS` nói khác.
- **Tự chạy lệnh, tự đọc kết quả.** Chỉ nhờ người dùng khi thật sự cần tay người:
  bấm phím trong ứng dụng tương tác, nhìn màn hình, thao tác GUI, nhập mật khẩu.
  Mọi thứ khác hãy tự làm — bắt người dùng copy/paste chính là thứ khiến phiên
  trước phải bàn giao.
- Mỗi bước hỏng phải nói ra. Đừng chạy lệnh với `capture_output` rồi vứt mã thoát.
- Đừng báo xong khi chưa kiểm chứng.

Làm xong một chặng thì chạy `/handoff <tên mạch việc>` để cập nhật lại đúng file
đó rồi push, cho phiên sau — có thể là phiên trên claude.ai — bắt được ngay.
