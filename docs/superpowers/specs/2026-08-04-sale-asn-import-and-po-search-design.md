# Sale ASN import và tìm PO — thiết kế

Ngày: 2026-08-04

## Mục tiêu

Cập nhật luồng Tạo Sale ASN để form Excel phản ánh đúng dữ liệu Shipping Info,
không tự sinh Cargo Ready Date, và tự thêm PO theo chuỗi điều kiện người dùng có
thể cấu hình. Luồng vẫn dừng trước Save và giữ nguyên cơ chế review/resume hiện có.

## Schema workbook

Form `SALE ASN` chuyển từ 19 sang 20 cột:

1. Invoice No
2. Invoice Date
3. Shipping Bill No
4. Shipping Bill Date
5. Style No
6. PO No
7. HS CODE
8. Qty
9. Carton
10. NW
11. GW
12. CBM
13. Destination
14. FTY
15. FOB Price
16. Service Price
17. Cargo Ready Date
18. Consignee Address
19. Ship To
20. Shipping Mode

`SEASON` và `DESCRIPTION` bị loại khỏi form phát hành và payload automation.
`Shipping Mode` bắt buộc khi chạy bước Shipping Info, chỉ chấp nhận `AIR`, `SEA`
hoặc `COURIER` sau khi trim và chuẩn hóa chữ hoa. Workbook phát hành dùng data
validation dropdown cho ba giá trị này.

`Cargo Ready Date` là dữ liệu tùy chọn theo từng dòng. Ô trống được giữ trống;
không kế thừa từ dòng đầu và không fallback sang ngày hiện tại. Invoice Date và
Shipping Bill Date tiếp tục dùng fallback hiện hành để tránh thay đổi ngoài phạm
vi yêu cầu.

`Consignee Address`, `Ship To`, `Shipping Mode` được phép nhập ở một dòng đầu rồi
kế thừa cho các dòng sau. Review trả thêm Shipping Mode để người dùng kiểm tra.

## Điền Shipping Info

Shipping Mode sinh hai giá trị cố định:

| Mode | Port of Loading | Delivery Terms |
|---|---|---|
| AIR | HAN- Hanoi | FCA HANOI, VIETNAM |
| SEA | HPH- Haiphong | FOB HAIPHONG, VIETNAM |
| COURIER | HAN- Hanoi | EXW |

Automation điền thêm Consignee Address, Ship To và Port of Loading trên tab
Shipping Info. Với Consignee Address và Ship To, app đọc option thật trong
dropdown, chuẩn hóa Unicode/dấu câu và chấm điểm gần đúng. Chỉ tự chọn khi có
một ứng viên tốt nhất với điểm dương; nếu dropdown/ứng viên không tồn tại hoặc
đồng hạng thì bỏ qua field, ghi log và trả warning như các field Shipping Info
khác. Không chọn tùy tiện option đầu tiên.

Shipping Mode không nhất thiết có control riêng trên WFX; nó là dữ liệu điều
khiển mapping. Port of Loading và Delivery Terms dùng exact value đã sinh. Nếu
WFX không có option tương ứng, field đó được bỏ qua có cảnh báo, không làm hỏng
toàn bộ Sale ASN.

## Logic Add PO

Ba tiêu chí tìm có thứ tự cố định `PO → Style → Destination`. Preference
`sale_asn_po_search_fields` chứa danh sách tiêu chí bật; mặc định và fallback dữ
liệu hỏng là đủ ba tiêu chí. Cho phép tắt từng tiêu chí nhưng không cho lưu danh
sách rỗng; nếu cả ba bị tắt thì quay về mặc định.

Trong mỗi dòng:

1. Chạy search với tiêu chí bật đầu tiên.
2. Nếu kết quả còn đúng một dòng, chọn dòng đó và bấm `Add & Continue` hoặc `OK`
   cho PO cuối.
3. Nếu nhiều dòng, thêm tiêu chí bật kế tiếp vào cùng bộ lọc rồi search lại.
4. Nếu một bước trả 0 dòng, dừng tự động và giữ popup để user xử lý thủ công;
   không thể mở rộng lại kết quả bằng cách thêm điều kiện.
5. Nếu đã dùng hết tiêu chí mà vẫn còn nhiều dòng, chọn tất cả dòng kết quả rồi
   bấm action một lần.

Không dùng heuristic Dispatched Qty nữa. Style và Destination chỉ được dùng làm
điều kiện search khi preference tương ứng bật. Tập preference được snapshot vào
review token lúc kiểm tra file để một lượt đang chạy không đổi hành vi nếu user
chỉnh Settings giữa chừng.

## Settings và bridge

Trong `Cài đặt → Tự động hóa`, thêm nhóm `Tìm PO khi tạo Sale ASN` gồm ba toggle
`PO`, `Style`, `Destination`; cả ba bật mặc định. Mỗi thay đổi gọi
`set_sale_asn_po_search_fields`, backend chuẩn hóa và lưu prefs, rồi phản hồi danh
sách canonical để UI đồng bộ lại.

`get_initial_state` trả preference mới. `prepare_sale_asn_create` đọc preference
đã lưu và đưa snapshot vào review. `_run_sale_asn_create_review` truyền snapshot
đến `run_sale_asn_create`; các lượt Continue/Skip dùng cùng snapshot.

## Tương thích và lỗi

Workbook cũ 19 cột không còn hợp lệ vì thiếu ba cột shipping mới và còn schema
cũ; lỗi header hiện rõ form chuẩn gồm 20 cột. Luồng 8 cột `ORDER DETAILS` không
đổi schema hay hành vi.

Không thêm mã lỗi automation mới. Validation Shipping Mode dùng mã
`SALE_ASN_FILE_VALIDATION_FAILED`. Việc không khớp Address/Ship To/Port/Terms chỉ
tạo warning và luồng vẫn dừng trước Save.

## Kiểm thử

- Workbook: đúng 20 cột, không còn Season/Description, dropdown Shipping Mode,
  Shipping Mode bắt buộc/hợp lệ, Cargo Ready Date trống không fallback.
- Shipping: ánh xạ đủ ba mode, fuzzy match duy nhất, không thấy/đồng hạng thì
  warning và tiếp tục.
- Add PO: dừng ngay khi một kết quả, thu hẹp PO→Style→Destination, 0 kết quả chờ
  user, nhiều kết quả cuối chọn tất cả, preference tắt tiêu chí được tôn trọng.
- Prefs/API/UI: mặc định đủ ba, normalize dữ liệu hỏng/rỗng, lưu qua bridge,
  bootstrap UI và snapshot vào review token.
- Manual và `CLAUDE.md` mô tả schema, mapping, search settings mới; sinh lại
  `docs/USER_FEATURES.md`.

Nghiệm thu bằng test mục tiêu, toàn bộ `python -m pytest` và `ruff check .`.
