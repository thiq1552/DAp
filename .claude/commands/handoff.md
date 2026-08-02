---
description: Viết bàn giao vào handoffs/<tên>.md rồi push, để phiên khác tiếp tục
---

Ghi bàn giao cho phiên Claude tiếp theo vào `handoffs/<tên>.md`, rồi commit và
push lên nhánh phát triển của repo.

Tên mạch việc và bối cảnh thêm (có thể trống): $ARGUMENTS

## Chọn file

Mỗi **mạch việc** một file, để nhiều việc song song không đè lên nhau.

- Có tên trong `$ARGUMENTS` → dùng `handoffs/<tên>.md`. Chuyển tên về dạng
  kebab-case không dấu (`onepane clipboard` → `onepane-clipboard.md`).
- Không có tên → tự đặt theo việc vừa làm. Xem `handoffs/` trước: nếu có file
  nào đúng là mạch việc này thì **cập nhật file đó**, đừng tạo file mới gần
  trùng tên. Không chắc thì hỏi người dùng.

Mở đầu file bằng khối metadata này (giữ nguyên tên khoá):

```
---
chu-de: <một dòng, việc này là gì>
may: <tên Tailscale của máy sẽ chạy tiếp, hoặc "bất kỳ">
trang-thai: đang làm | chờ người dùng | xong
cap-nhat: <YYYY-MM-DD>
---
```

`trang-thai: xong` thì xoá file luôn trong lần bàn giao sau — thư mục này là
việc đang mở, không phải nhật ký.

## Nội dung

Người đọc là **một phiên Claude khác, không có ký ức gì về cuộc hội thoại này**.
Viết cho người đó, không phải cho người dùng. Bỏ mục nào không áp dụng.

1. **Đang làm gì** — mục tiêu trong 2–3 câu. Vì sao làm, không chỉ làm gì.
2. **Tới đâu rồi** — tách bạch cái **đã chạy thật và tự tay xác nhận** với cái
   **mới viết xong nhưng chưa chạy**. Đừng gộp; phiên sau tin nhầm là mất thời
   gian gấp đôi.
3. **Chưa xác nhận / đang kẹt** — nói rõ cần gì để xác nhận. Thứ nào chỉ người
   thật kiểm được (bấm phím, nhìn màn hình, thao tác GUI) thì ghi rõ là phải nhờ
   người dùng, đừng để phiên sau tưởng tự làm được.
4. **Lỗi đã sửa và gốc rễ** — dạng bảng, ghi *nguyên nhân* chứ không chỉ triệu
   chứng. Đây là phần giá trị nhất: nó chặn phiên sau đi lại vết xe cũ.
5. **Việc tiếp theo** — xếp theo giá trị, kèm một câu vì sao cái đầu đáng làm trước.
6. **Cạm bẫy** — ràng buộc môi trường thật mà đọc code không thấy: máy nào tên gì,
   quyền gì cần sẵn, lệnh nào không dùng được, giả định nào sai.

Nếu mạch việc này **giẫm lên** một bàn giao khác trong `handoffs/` (sửa cùng
file, đổi cùng hành vi), ghi rõ tên file đó và chỗ giẫm nhau.

## Cách viết

- Tiếng Việt.
- Cụ thể hơn là đầy đủ. Đường dẫn thật, tên lệnh thật, tên máy thật.
- Đừng chép lại thứ đọc code là biết. Chỉ ghi cái **không suy ra được** từ repo:
  kết quả chạy thật, quyết định và lý do, chỗ đã thử và thất bại.
- File cũ còn mục nào đúng thì giữ, đừng bịa lại.

Xong thì commit với thông điệp mô tả chặng vừa làm, push lên nhánh phát triển,
rồi in cho người dùng **đúng hai dòng** họ cần gõ ở máy kia (gồm cả tên mạch việc
để truyền cho `/tieptuc`).
