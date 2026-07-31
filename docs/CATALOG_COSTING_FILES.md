# Costing Catalog bằng XLSX

Tính năng **Costing file** nằm trong Catalog > Apparel. **Tải XLSX** và
**Import** luôn dùng đúng tab Costing đang được chọn/hiển thị, không phụ thuộc
ô Style Code, không tìm lại style, không chuyển tab và không reload. Apply tiếp
tục dùng chính tab đó và chặn nếu người dùng đã chuyển sang style khác.

## Điều kiện bắt buộc

Costing ở mọi trạng thái có thể **Export** để lấy dữ liệu. Chỉ CostSheet đang
`Open` mới được **Import/Apply**; trạng thái khác trả `COSTING_NOT_OPEN`. Khi
chưa có Costing, người dùng cần tự tạo trong WFX trước.

WFX Smart không tự tạo New Costing.

## Cách sử dụng

1. Chọn `Apparel`. Có thể tìm style bằng app, hoặc tự mở Style > Costing trong
   WFX và giữ chính tab đó đang hiển thị.
2. Bấm **Tải XLSX** và chọn chính xác nơi lưu. App chỉ quét tab Costing đang
   hiển thị; tên file lấy theo Style Name. Sau khi tải, app có thể mở file hoặc
   thư mục theo hai công tắc trong Settings.
3. Mở file, vào sheet `Costing` và điền các ô màu vàng.
   `Material Color`, `Material Size` và `Purchase Officer` có dropdown lấy từ
   đúng Article đang có trên Costing. `Color Mapping`/`Size Mapping` chứa phối
   Table hiện tại để sửa trực tiếp.
4. Với CostSheet `Open`, bấm **Import**, xem dry-run và xử lý Article trùng nếu
   có. Không cần nhập Style Code; app dùng tab Costing hiện tại.
5. Bấm **Áp dụng & Save**. App ghi trên màn hình hiện tại, Save một lần rồi đọc
   lại để xác nhận.
6. Khi cần bỏ toàn bộ phối cũ, bấm **Clear All Dependency** bên dưới Import,
   xác nhận thao tác. App chỉ chạy trên CostSheet `Open`, bấm tất cả nút Clear
   Dependency trong Costing đang chọn rồi Save một lần.

## Workbook chuẩn

File có đúng hai sheet:

- `Hướng dẫn`: Style Code, Style Name lấy sau dấu `/` trong header Article,
  status lúc export, phiên bản form và quy tắc nhập.
- `Costing`: một form duy nhất với các cột cố định, có sẵn dòng Article hiện tại
  và các dòng vàng để thêm dữ liệu.

Form có sáu nhóm nguyên vật liệu, sau đó là ba nhóm chi phí:

- `FABRIC- SHELL`;
- `FABRIC - LINING`;
- `FABRIC - INTERLINING`;
- `FABRIC - PADDING`;
- `SEWING TRIMS`;
- `PACKING TRIMS`.
- `CM Costs`: một dòng;
- `Production Costs`: một dòng;
- `Indirect Costs`: hai dòng.

Các cột form luôn có sẵn:

- Section, Action, Article Code, Article Name;
- Material Size, Material Color, Color Dep., Color Mapping, Size Dep., Size Mapping;
- Shrinkage %(LxW), Cons. Qty., Waste %, Minutes, `Cons. Qty. Incl. Waste`;
- Supplier, Curr., Rate, Value, `Value in (USD)`;
- Remarks, Placement, Purchase Officer.

Các key kỹ thuật ở cuối form được ẩn để app nối đúng Article/section. Không xóa
hoặc đổi các cột này. File không có `Cost Sheet`, `Sections`, `Items`, `_Fields`
hay `_Meta`.

Nếu cần hơn ba Article mới trong một section, sao chép nguyên dòng vàng đậm cuối
và chèn trước section tiếp theo. Không cần dùng dòng nào thì để trống.

Hai hay nhiều dòng liền nhau có cùng Article Code được hiểu là cùng item cần
split theo màu/size/phối và giá khác nhau. App Add Article một lần (nếu chưa có),
sau đó dùng đúng nút Splitter để tạo đủ dòng `>>` trước khi điền dữ liệu.

Article Code và Article Name đều có dropdown theo từng section. Chọn Code thì
Name đổi bằng công thức Excel. Nếu người dùng chọn Name và ghi đè công thức, app
sẽ đồng bộ ngược Code khi kiểm tra/import nếu tên chỉ khớp một mã. Tên trùng
nhiều mã không được tự đoán; file sẽ báo đúng ô và yêu cầu chọn Article Code.

Hai cột đỏ là công thức WFX và chỉ đọc:

- `Cons. Qty. Incl. Waste = Cons. Qty. × (1 + Waste %/100)`;
- `Value in (USD) = Rate × Cons. Qty. Incl. Waste`.

Hai cột công thức chỉ để xem và không được gửi ngược lên WFX. App bỏ Delivery
Terms, Process Required, BOM, SNO, Roll/Lot Avg, Destination Country, Des.
Specific, Material Cost và Included In.

Ba nhóm chi phí hoạt động như sau:

- `CM Costs`: chọn nhà máy từ danh sách đã quét; Curr. luôn là USD.
- `Production Costs`: chọn quy trình từ danh sách đã quét; Minutes luôn là 1.
  Khi cập nhật, app điền Minutes ở cả dòng tổng và dòng quy trình, sau đó điền
  Value của dòng tổng Production Costs rồi mới điền Rate của quy trình.
- `Indirect Costs`: chọn loại chi phí từ danh sách đã quét; Curr. luôn là USD.
- Dòng chưa chọn Article Name được bỏ qua và không tạo dòng mới trên WFX.

Ba danh sách trên được cache 7 ngày theo tài khoản và Division nên Export/Import
không mở editor để scan lại mỗi lần. Công tắc **Quét lại danh sách chi phí** cạnh
Thư viện Article mặc định tắt; bật lên chỉ ép lần Costing kế tiếp scan mới, sau
khi scan và lưu cache thành công công tắc tự tắt. Color/Size, mapping và field
riêng của Style vẫn luôn được đọc mới.

## Action và giá trị

- Để trống Action: cập nhật dòng hiện có hoặc thêm dòng mới.
- `DELETE`: xóa đúng dòng sau khi app đã chọn dòng đó.
- Ô trống giữ nguyên dữ liệu live.
- `__CLEAR__` chủ động xóa giá trị của field hỗ trợ.
- Công thức Excel trong vùng dữ liệu bị từ chối.
- Style Code trong file phải khớp style đang mở.
- Với phối Table, giữ `Color Dep.`/`Size Dep.` là `[Table]`. Mỗi dòng trong
  `Color Mapping`/`Size Mapping` có dạng `Material => Style 1 | Style 2`.
  App mở bảng phối và tick exact theo từng Material Color/Size; các lựa chọn
  Style đã scan nằm trong comment của ô Mapping.
- `Purchase Officer` là bắt buộc khi WFX đánh dấu mandatory; dry-run sẽ yêu cầu
  chọn giá trị trước khi cho Apply.

Khi thêm Article, app tìm exact Article Code trước, rồi mới dùng Article Name.
Không có kết quả thì bỏ qua và báo; nhiều kết quả thì chờ người dùng chọn, không
tự lấy dòng đầu.

## Dry-run và an toàn

Import chỉ tạo plan, chưa ghi WFX. Trước Apply, app quét lại Costing đang mở và
hủy plan nếu status không còn `Open` hoặc dữ liệu live đã thay đổi. Mọi field
Minutes editable được đặt thành `1`. Save dùng đúng nút Cost Sheet đã đặc tả và
app đọc lại DOM để xác minh.

Workflow không bao giờ click Body Type, Delete Section, Edit Section hoặc Copy
Section.
