# WFX Smart website

Cloudflare Worker `wfx-smart` (https://wfx-smart.itps.workers.dev) gồm bốn trang:
Tải về, Có gì mới, Hướng dẫn và Đề xuất tính năng.

- Hướng dẫn và Có gì mới lấy từ `wfx_panel/manual/` qua
  `scripts/export_site_content.py`; danh sách module lấy từ
  `wfx_panel/ui/panel/core.js`. Không sửa tay `public/content/site.json`.
- Tải về đọc bản phát hành mới nhất trên GitHub Releases (cache 10 phút).
- Đề xuất và luồng trả lời lưu ở D1 `wfx-smart-db`, ảnh ở KV `wfx-smart-images`.
  Không ai cần tài khoản: gửi và trả lời ký bằng tên + bộ phận đã nhập ở form.
  Người gửi tự đánh dấu xong/mở lại bằng mã chủ đề xuất trình duyệt nhận lúc
  gửi (chỉ lưu hash ở D1). Đổi sang trạng thái khác và xóa cần secret `ADMIN_KEY`.

## Lệnh

```bash
npm install
npm run dev        # sinh content rồi chạy local (cần site/.dev.vars có ADMIN_KEY)
npm run deploy     # sinh content rồi deploy
npm run db:migrate # áp migration D1 lên Cloudflare
```

Deploy lại sau mỗi lần phát hành app để Hướng dẫn và Có gì mới khớp bản mới.

## Nhúng vào Google Sites

Chèn → Nhúng → theo URL. Thêm `?embed=1` để ẩn thanh điều hướng của site, ví dụ
`https://wfx-smart.itps.workers.dev/de-xuat?embed=1`. Trang không gửi
`frame-ancestors`/`X-Frame-Options`: Google Sites kiểm tra URL nhúng từ máy chủ
riêng của nó và từ chối mọi trang có giới hạn nguồn nhúng, kể cả khi đã liệt kê
`sites.google.com` (xem `public/_headers`).
