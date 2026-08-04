# Quy tắc viết chữ và cỡ chữ trong giao diện

File này là chuẩn bắt buộc cho mọi chữ hiển thị trong `wfx_panel/ui/`. Thêm nút
mới, thêm công tắc hay thêm mã lỗi đều phải theo đúng các giới hạn dưới đây.

## Thang cỡ chữ

Không được đặt bất kỳ `font-size` nào dưới **11.5px**. Tiếng Việt có dấu chồng
(ế, ộ, ữ) nên dưới ngưỡng này chữ bị bết, không đọc được ở màn hình thường.

| Vai trò | Cỡ | Ví dụ selector |
|---|---|---|
| Micro: badge, số đếm | 11.5px | `.catalog-step-badge` |
| Phụ: mô tả, hint, footer, label form | 12px | `.setting-row span`, `.module-action-hint` |
| Tiêu đề trong thẻ / hàng cài đặt | **13px** | `.setting-row strong`, `.workflow-choice strong` |
| Thân: nút chính, tên module | 12.5–13px | `.module-card strong` |
| Tiêu đề màn / số liệu lớn | 14–21px | `.sheet-heading strong` |

**Quy tắc bắt buộc về thứ bậc:** khi một tiêu đề nằm ngay trên dòng mô tả của
nó, hai bên phải **chênh nhau ít nhất 1px**. Nếu để cùng cỡ thì mắt không phân
biệt được đâu là tên thiết lập, đâu là lời giải thích. Cặp chuẩn là 13px/12px.

## Giới hạn độ dài

| Loại | Trần | Ghi chú |
|---|---|---|
| Nhãn nút | 22 ký tự | Điều kiện sử dụng đẩy xuống dòng hint, không nhét vào nhãn |
| Tiêu đề hàng cài đặt | 28 ký tự | |
| Dòng phụ (`<small>`, `<span>` mô tả) | 55 ký tự, **một câu** | |
| Tiêu đề lỗi | 45 ký tự | |
| Cách xử lý lỗi | 70 ký tự, **một hành động** | |

Đoạn văn độc lập (ghi chú quyền riêng tư, cảnh báo an toàn) được phép tới 80 ký
tự vì người dùng chỉ đọc một lần, không phải nhãn lặp lại.

## Quy tắc câu

1. **Nút = động từ + tân ngữ.** `Tìm`, `Tải file mẫu`, `Áp dụng`.
   Không viết `Tìm theo các điều kiện đã nhập` — điều kiện thuộc về dòng hint.
2. **Công tắc phải nói cả hai trạng thái:** `Bật: … Tắt: …`.
   Cấm dạng `Tắt để…` bắt người dùng tự suy ra vế còn lại.
3. **Không viết meta-text về chính giao diện.** Bỏ những câu kiểu
   `Ba nhóm ngắn gọn, thay đổi được lưu ngay`.
4. **Label và placeholder không được trùng nghĩa.** Nếu label đã ghi `Supplier`
   thì placeholder phải là ví dụ thật hoặc bỏ hẳn, không ghi `Nhập Supplier`.
5. **Tiêu đề thẻ không được lặp lại ở dòng phụ.** Thẻ `List` + phụ `Mở RMPO List`
   là tautology; đổi thành tiêu đề `RMPO List` + phụ nói việc thật sự xảy ra.
6. **Lỗi = chuyện gì xảy ra + làm gì tiếp**, không lộ tên kỹ thuật nội bộ.
7. **Dấu ba chấm dùng `…`** một ký tự, không dùng `...`.
8. Bỏ từ đệm không mang thông tin: `hiện tại`, `để tìm`, `an toàn`, `vui lòng`.

## Từ tiếng Anh

Giữ nguyên khi là **tên nghiệp vụ hoặc nhãn thật trên WFX**:
Costing, BOM, Article Code, Buyer, Supplier, Style, PO, Invoice No.,
Order Details, Shipping Info, Master, Save, Import, Export, List, New.

Dịch sang tiếng Việt khi là từ do app tự đặt:

| Tiếng Anh | Dùng |
|---|---|
| Dry-run | Xem trước thay đổi |
| Publish | Đẩy lên server |
| Check File | Kiểm tra file |
| grid | bảng |
| Floating Filter (trong câu lỗi) | ô lọc trên bảng |
| Run ID | mã lượt chạy |
| ONLINE / SETUP | Sẵn sàng / Cần cài đặt |

## Nhãn bị khóa cứng — không được đổi

`tests/test_ui_assets.py` và `tests/test_oc_list_buttons.py` khóa đúng ba nhãn
sau, vì đổi nhầm sẽ tạo sai chứng từ hoặc phá hợp đồng nêu trong `CLAUDE.md`:

- `Mở Catalog`
- `Chọn file OC mới`
- `Chọn file Revise`

## Khi đổi nhãn thì phải làm gì

1. Sửa `wfx_panel/ui/index.html` hoặc `panel.js`.
2. Tìm nhãn cũ trong `wfx_panel/manual/**/*.md` và sửa theo — manual trích dẫn
   nhãn trong dấu backtick, để lệch là hướng dẫn sai.
3. Chạy `python scripts/generate_user_features.py` (không sửa tay
   `docs/USER_FEATURES.md`).
4. Chạy `python -m pytest` và `ruff check .`.

Đổi nội dung trong `telemetry.ERROR_CODE_INFO` thì không cần sửa manual tay:
`manual_book.py` sinh bảng mã lỗi thẳng từ đó, chỉ cần chạy lại generator.
