## Dùng để làm gì

Nhận gợi ý Article Code, Article Name và Buyer Reference khi bạn tìm Catalog
hoặc điền file Costing.

## Các bước

1. Mở module Catalog.
2. Chọn Category.
3. Nhập từ hai ký tự vào ô tìm.
4. Đọc tối đa 20 gợi ý phù hợp.
5. Bấm đúng gợi ý để điền Article Code chính xác.

## Mẹo

> [!meo]
> Dữ liệu được lấy từ PostgreSQL qua n8n tối đa một lần mỗi 30 ngày. Muốn lấy
> ngay bản mới, mở `Cài đặt > Tài khoản` và bấm `Đồng bộ ngay`.

> [!meo]
> Khi mất mạng, ứng dụng tiếp tục dùng danh sách gần nhất đã lưu trên máy.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Chưa có gợi ý | Bạn vẫn có thể nhập Article Code hoặc tên Article bằng tay. |
| Gợi ý chưa có Article mới | Bấm `Đồng bộ ngay`; nếu server chưa có, báo Admin publish snapshot mới. |

## Dành cho Admin

1. Đăng nhập tài khoản WFX có quyền quản trị.
2. Mở `Cài đặt > Tài khoản`.
3. Nhập Admin key một lần và bấm `Lưu key`. Key được mã hóa bằng Windows DPAPI,
   chỉ dùng được bởi đúng tài khoản Windows trên máy đó.
4. Sau khi cache Article và dropdown Style đã đúng, bấm
   `Đẩy lên server` và xác nhận.

User khác sẽ nhận snapshot mới ở lần tự đồng bộ tháng kế tiếp hoặc ngay khi họ
bấm `Đồng bộ ngay`.
