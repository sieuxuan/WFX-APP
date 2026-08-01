# Cách viết WFX Manual

## 1. Mục tiêu và người đọc

Manual dành cho nhân viên nghiệp vụ dệt may không rành máy tính. Hãy viết như
đang chỉ cho một đồng nghiệp ngồi cạnh: câu ngắn, chỉ rõ màn hình và dùng đúng
tên nút mà người đọc nhìn thấy.

## 2. Quy trình sáu bước khi có tính năng mới

1. Xác định phần vừa thêm: module nào, nút nào, công tắc nào và mã lỗi nào.
2. Chọn chương phù hợp trong `wfx_panel/manual/manifest.json`.
3. Tạo file `.md` theo khuôn ở phần 3.
4. Khai báo `covers` đúng với những module, thao tác, cài đặt và mã lỗi ở bước 1.
5. Chạy `python scripts/generate_user_features.py`.
6. Chạy `python -m pytest tests/test_manual.py` cho tới khi toàn bộ test xanh.

## 3. Khuôn file `.md`

Sao chép khuôn dưới đây. Mỗi mục bắt buộc có `Dùng để làm gì` và `Các bước`.
Thêm `Mẹo` hoặc `Gặp lỗi thì sao` khi có thông tin hữu ích.

```markdown
## Dùng để làm gì

Nói ngắn gọn tình huống người dùng cần thao tác này.

## Các bước

1. Mở màn hình `Tên màn hình`.
2. Bấm `Tên nút`.
3. Kiểm tra thông báo xuất hiện.

> [!meo]
> Mẹo
> Nêu một cách làm nhanh hơn hoặc dễ kiểm tra hơn.

> [!luuy]
> Lưu ý
> Nêu điều người dùng cần tránh hoặc cần chuẩn bị.

> [!loi]
> Gặp lỗi thì sao
> Nêu thông báo có thể gặp và từng bước xử lý.
```

Sau khi tạo file, thêm mục tương ứng vào đúng chương trong `manifest.json`.
Khai báo `id`, `title`, `summary`, `file`, `keywords` và đủ bốn nhóm `covers`:
`modules`, `actions`, `settings`, `errors`.

## 4. Bảng từ cấm và cách viết thay thế

Các từ kỹ thuật dưới đây không được xuất hiện trong nội dung dành cho người
dùng. Cột thay thế là gợi ý; hãy chọn câu tự nhiên theo đúng tình huống.

| Từ cấm | Viết thay thế |
|---|---|
| `frame` | vùng hoặc phần trên màn hình |
| `selector` | ô, nút hoặc dòng cần chọn |
| `CDP` | kết nối trình duyệt |
| `postback` | tải lại dữ liệu |
| `iframe` | vùng nội dung bên trong trang |
| `XPath` | vị trí của nút hoặc ô |
| `DOM` | nội dung đang hiển thị trên trang |
| `endpoint` | địa chỉ dịch vụ |
| `payload` | dữ liệu gửi đi |
| `token` | mã xác nhận hoặc mã phiên |
| `grid` | bảng dữ liệu |

## 5. Quy tắc giọng văn

- Dùng câu ngắn và ngôi thứ hai; có thể gọi trực tiếp là “bạn”.
- Mỗi bước chỉ có một hành động chính.
- Luôn nói rõ bấm nút nào trên màn hình nào.
- Đặt tên nút trong dấu backtick và viết y hệt chữ trên màn hình.
- Mô tả điều người dùng nhìn thấy, không giải thích cách chương trình vận hành.
- Nếu có nhiều nhánh, tách thành các bước hoặc bảng dễ quét mắt.
- Lưu file ở dạng Unicode NFC để dấu tiếng Việt hiển thị thống nhất.
- Dùng nhất quán cách viết hiện đại: `xóa, hủy, hóa`; không trộn với các dạng
  `xoá, huỷ, hoá` trong cùng sản phẩm.
- Ưu tiên từ tiếng Việt như “bảng điều khiển”, “khay hệ thống”, “trình duyệt
  làm việc”. Chỉ giữ từ tiếng Anh khi đó là tên chính thức hiện trên WFX hoặc
  trên nút của ứng dụng.

## 6. Checklist tự kiểm

- [ ] Có đủ `Dùng để làm gì` và `Các bước`.
- [ ] Không còn từ cấm trong nội dung người dùng.
- [ ] Không có HTML thô.
- [ ] Dấu tiếng Việt dùng Unicode NFC và chính tả nhất quán.
- [ ] Mọi giá trị trong `covers` khớp chức năng thật.
- [ ] Đã chạy `python scripts/generate_user_features.py`.
- [ ] `python -m pytest tests/test_manual.py` đã xanh.
