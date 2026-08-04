## Dùng để làm gì

Tạo Sale ASN mới từ file Excel, tìm Sale ASN cũ, mở một form New trống, hoặc chỉ
điền Order Details cho chứng từ đã được tạo thủ công.

Module có đúng hai thẻ. `Tạo mới` là thẻ mặc định và là nơi làm việc chính.
`Tra cứu` dùng để tìm chứng từ và xuất Buyer Invoice + Packing List. Nút mở
`Sale ASN List` nằm ở góc phải thanh trên nên bấm được từ cả hai thẻ.

## Các bước

### Tạo Sale ASN từ Excel

1. Mở module `Sale ASN`. Ứng dụng vào sẵn thẻ `Tạo mới`.
2. Bấm `↻` nếu danh sách Buyer chưa có hoặc cần cập nhật.
3. Gõ ít nhất hai ký tự vào ô Buyer rồi chọn đúng Buyer trong danh sách gợi ý.
   Khi đã khớp chính xác, ô Buyer hiện dấu ✓ ở bên phải.
4. Bấm `Tải form trống` nếu bạn chưa có form 20 cột.
5. Điền dữ liệu theo thứ tự từ trên xuống dưới trong file rồi lưu lại.
6. Bấm `Chọn file & kiểm tra`.
7. Kiểm tra Invoice No., số PO, số Style và Destination trong thẻ review.
8. Bấm `Bắt đầu tạo Sale ASN`.
9. Theo dõi thẻ `Tiến độ Sale ASN`: bốn bước `Thêm PO`, `Order Details`,
   `Style Details` và `Shipping Info` sáng dần theo đúng bước ứng dụng đang làm.
   Ba bước đầu hiện thêm số dòng đang xử lý, ví dụ `Order Details 5/12`, nên bạn
   biết ứng dụng đang chạy tới đâu chứ không phải đứng im.
10. Sau khi ứng dụng điền xong, kiểm tra toàn bộ Sale ASN trên WFX rồi tự bấm
    `Save`.
11. Sau khi đã Save, bấm `Xuất Invoice + PKL` trong thẻ kết quả để sang thẳng thẻ
    `Tra cứu` với Invoice No. đã điền sẵn.

> [!luuy]
> Ứng dụng không tự bấm Save. Bạn luôn có bước kiểm tra cuối trên WFX. Nút
> `Xuất Invoice + PKL` chỉ chuyển thẻ và điền sẵn Invoice No.; nó không tự chạy
> xuất báo cáo, vì bạn phải Save trên WFX trước.

> [!meo]
> Nếu Sale ASN New đã mở sẵn hoặc đã chọn Buyer, ứng dụng refresh form trước khi
> bắt đầu để danh sách PO được tải mới.
>
> Ứng dụng dùng `Add & Continue` cho các PO trước. Với PO cuối, ứng dụng giữ
> dòng đang chọn rồi bấm `OK` để vừa thêm PO cuối vừa đóng Add Order Details.

Ứng dụng mặc định tìm PO theo thứ tự `PO` → `Style` → `Destination`. Nếu một
bước chỉ còn một dòng, ứng dụng chọn và thêm ngay. Nếu dùng hết các tiêu chí mà
vẫn còn nhiều dòng, ứng dụng chọn tất cả các dòng đó rồi tiếp tục. Bạn có thể mở
`Tùy chọn nâng cao` > `Tiêu chí tìm PO` ngay trong module Sale ASN để tắt từng
tiêu chí không muốn dùng. Ứng dụng nhớ lựa chọn cho những lần sau; khi bỏ tích
cả ba, ứng dụng tự bật lại cả ba để tránh chạy không có điều kiện tìm.

### Khi ứng dụng dừng giữa chừng

Mọi trạng thái chờ và lỗi hiện ngay bên trong dòng bước đang vướng của thẻ tiến
độ, nên bạn luôn thấy đã chạy được tới đâu.

- **Không thể tự thêm PO.** Dòng `Thêm PO` chuyển sang màu cảnh báo và mở thông
  báo. Chuyển sang WFX, điều chỉnh điều kiện tìm nếu cần, chọn dòng PO rồi bấm
  `Add & Continue` (hoặc `OK` nếu là PO cuối). Quay lại ứng dụng, tích ô xác nhận
  và bấm `Tiếp tục dòng kế`.
  Nếu muốn bỏ hẳn lượt này để làm lại từ file khác, bấm
  `Bỏ lượt này và chọn file khác`.
- **Một bước bị lỗi.** Dòng bước đó chuyển sang màu cảnh báo. Form WFX hiện tại
  được giữ nguyên: xử lý nguyên nhân rồi bấm `Thử lại bước này`, hoặc bấm
  `Bỏ qua ...` để chuyển sang bước sau. Bỏ qua chỉ áp dụng cho ba bước điền dữ
  liệu; bước thêm PO không thể bỏ qua để tránh tạo chứng từ thiếu đơn hàng.
  Khi bỏ qua, ứng dụng đi thẳng sang bước kế tiếp và không chờ tab của bước vừa
  bỏ, nên bạn dùng được nút này cả khi tab đó đang không mở lên được.
- **Bạn bấm `Stop`, hoặc ứng dụng đang bận việc khác.** Lượt chạy dừng lại và
  thẻ file quay lại với nút `Bắt đầu tạo Sale ASN`. Bấm lại để chạy tiếp cùng
  file đó; không cần chọn file lại từ đầu.

Riêng trong `Shipping Info`, từng trường được xử lý độc lập. `Consignee Address`
và `Ship To` có thể nhập gần đúng với nội dung trong danh sách WFX; ứng dụng chọn
dòng gần nhất duy nhất. Nếu không có dòng phù hợp, ứng dụng bỏ qua để bạn tự điền.
Nếu file thiếu dữ liệu hoặc WFX không có lựa chọn tương ứng (ví dụ Factory), ứng
dụng cũng bỏ qua đúng trường đó, tiếp tục điền các trường còn lại và liệt kê toàn
bộ cảnh báo trong thẻ kết quả để bạn bổ sung thủ công trước khi Save.

### Bỏ Add PO và làm tiếp từ chứng từ đang mở

1. Mở đúng Sale ASN đã được thêm PO thủ công và vào bảng `Order Details`.
2. Mở `Tùy chọn nâng cao` ở cuối thẻ `Tạo mới`.
3. Trong `Các bước app sẽ làm`, bỏ tích `Thêm PO`. Chỉ giữ các bước cần app làm:
   `Order Details`, `Style Details` và/hoặc `Shipping Info`.
4. Bấm `Xuất PO đang mở`. App tạo form 20 cột có sẵn PO No. và toàn bộ giá trị
   Order Details đang có trên WFX.
5. Bổ sung Style/HS Code hoặc Shipping Info trong form nếu các bước đó được
   chọn, lưu file rồi bấm `Chọn file & kiểm tra`.
6. Bấm `Chạy các bước đã chọn`.

Khi bỏ `Thêm PO`, Buyer không còn bắt buộc. App không refresh form, không mở
Add Order Details và không tự thêm PO còn thiếu. Nếu file có PO không tồn tại
trên chứng từ đang mở, app dừng đúng bước Order Details để bạn mở lại đúng Sale
ASN rồi thử tiếp.

> [!meo]
> Ứng dụng nhớ các bước bạn đã tích, kể cả sau khi đóng và mở lại app. Nếu còn
> bước nào đang bỏ tích, lần sau mở module ứng dụng tự bung `Tùy chọn nâng cao`
> để bạn không bị bất ngờ vì app chạy thiếu bước. Trong thẻ tiến độ, bước không
> chạy hiện dạng gạch ngang. Bỏ tích cả bốn bước là không hợp lệ; ứng dụng sẽ
> đưa về đủ bốn bước.

### Chỉ điền Order Details cho Sale ASN đã tạo thủ công

1. Tạo hoặc mở đúng Sale ASN trên WFX và bảo đảm các PO đã nằm trong bảng
   `Order Details`.
2. Trong WFX Smart, mở `Tùy chọn nâng cao` > `Chỉ điền Order Details`.
3. Bấm `Xuất form từ WFX`. Ứng dụng xuất sẵn PO No. và các giá trị hiện có của
   chứng từ đang mở.
4. Điền các cột cần cập nhật trong Excel rồi lưu file.
5. Bấm `Chọn file 8 cột`, kiểm tra số PO và số ô sẽ điền.
6. Giữ đúng chứng từ trên WFX rồi bấm `Điền Order Details trên WFX`.
7. Kiểm tra kết quả và tự bấm `Save` trên WFX.

Form riêng gồm tám cột: `PO No`, `Carton`, `NW`, `GW`, `CBM`, `FOB Price`,
`Service Price` và `Cargo Ready Date`. `PO No` dùng để map đúng dòng và không nên
sửa sau khi xuất. Các ô còn lại có thể để trống; ứng dụng chỉ điền ô có dữ liệu.

Luồng này không chọn Buyer, không thêm PO và không chạm vào Style Details hoặc
Shipping Info. Nếu đang mở nhầm chứng từ hoặc thiếu PO, ứng dụng giữ nguyên file
đã review để bạn mở đúng Sale ASN rồi bấm `Thử lại Order Details`; không chạy lại
luồng tạo mới.

### Mở Sale ASN New trống, không cần upload

1. Mở `Tùy chọn nâng cao` trong thẻ `Tạo mới`.
2. Bấm `Mở Sale ASN New trống trên WFX`.
3. Tạo chứng từ và thêm PO thủ công trực tiếp trên WFX.

Nút này chỉ mở màn New. Ứng dụng không yêu cầu file Excel và không tự điền dữ
liệu.

## Quy tắc của file Excel

- Mỗi file chỉ chứa một Invoice No. và một FTY.
- Chỉ dòng có `PO No` mới được tính và xử lý; dòng tổng hoặc ghi chú không có PO sẽ được bỏ qua.
- Với mỗi dòng có PO, `Style No`, `Destination` và `FTY` là dữ liệu bắt buộc.
- Form có 20 cột và không còn `SEASON` hoặc `DESCRIPTION`.
- `Shipping Mode` bắt buộc khi chạy bước Shipping Info. Chọn `AIR`, `SEA` hoặc `COURIER` trong danh sách của Excel.
- `HS CODE`, `Qty`, `Carton`, `NW`, `GW`, `CBM`, `FOB Price`, `Service Price`, `Cargo Ready Date`, `Consignee Address` và `Ship To` có thể để trống.
- `Cargo Ready Date` trống sẽ được giữ trống để bạn tự điền; ứng dụng không lấy ngày hiện tại và không sao chép ngày từ dòng khác.
- `Invoice Date` và `Shipping Bill Date` trống vẫn lấy ngày có dữ liệu đầu tiên trong file; nếu cả file không có thì dùng ngày hiện tại.
- Nếu Shipping Bill No. bị trống, ứng dụng dùng Invoice No.
- PO luôn được xử lý đúng thứ tự dòng trong file.

Ứng dụng tự điền Port of Loading và Delivery Terms theo Shipping Mode:

| Shipping Mode | Port of Loading | Delivery Terms |
|---|---|---|
| `AIR` | `HAN- Hanoi` | `FCA HANOI, VIETNAM` |
| `SEA` | `HPH- Haiphong` | `FOB HAIPHONG, VIETNAM` |
| `COURIER` | `HAN- Hanoi` | `EXW` |

## Tìm Sale ASN và tải Documents

1. Chọn thẻ `Tra cứu`.
2. Chọn `Invoice No.` hoặc `Buyer Order Ref/OC`.
3. Nhập nội dung rồi bấm `Tìm`.
4. Bấm `Xuất Buyer Invoice + Packing List` để lấy hai báo cáo trong cùng một file Excel.

> [!luuy]
> Report WFX có thể tải chậm. Ứng dụng chờ tối đa ba phút cho từng Packing List
> hoặc Buyer Invoice; không bấm xuất lại khi trạng thái vẫn đang chạy.

> [!meo]
> Khi gộp file, ứng dụng giữ nguyên tên sheet do WFX xuất. Chỉ khi hai report có
> sheet trùng tên, chúng được đổi theo dạng `PKL 1083.26.PS.PSHK_7` và
> `INVOICE 1083.26.PS.PSHK_7` để Excel chấp nhận. Nếu report có nhiều sheet,
> ứng dụng xếp xen kẽ `Invoice 1`, `PKL 1`, `Invoice 2`, `PKL 2` cho đến hết;
> Invoice luôn đứng trước PKL. Sau khi lưu thành công, Explorer sẽ tự mở và chọn
> đúng file vừa lưu. Khung, rich text, merged cell và định dạng gốc của cả
> Invoice lẫn PKL được giữ nguyên khi ghép.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không có Buyer để chọn | Nút `↻` sẽ nhấp nháy màu vàng khi kho Buyer còn rỗng. Mở đúng phiên WFX rồi bấm `↻`. Ứng dụng không tự quét vì thao tác này mở hẳn form Sale ASN New trên Chrome. |
| Ô Buyer viền vàng, không có dấu ✓ | Tên đang gõ chưa khớp Buyer nào. Gõ lại và chọn đúng dòng trong danh sách gợi ý. |
| File có lỗi | Đọc vị trí ô hoặc dòng trong thông báo, sửa file rồi chọn lại. |
| Báo một ô số `quá lớn` | Ô Qty, Carton, NW, GW, CBM hoặc giá đang chứa giá trị vượt ngoài phạm vi thực tế (thường do dán nhầm hoặc Excel đổi sang dạng `1E+...`). Nhập lại đúng số rồi chọn file lại. |
| Có nhiều dòng sau tiêu chí cuối | Ứng dụng chọn tất cả dòng còn lại và tiếp tục. Nếu không muốn vậy, mở `Tùy chọn nâng cao` và bật thêm tiêu chí Style hoặc Destination trước lượt chạy kế tiếp. |
| Không tìm thấy PO | Kiểm tra `Tiêu chí tìm PO` trong `Tùy chọn nâng cao` cùng PO No., Style và Destination trong file; bạn có thể tìm và chọn thủ công trên cửa sổ đang mở. |
| Đã đóng cửa sổ Add PO | Hủy phiên đang chuẩn bị và chạy lại từ file để tránh bỏ sót dòng. |
| Không xuất được form Order Details | Mở đúng chứng từ có PO và vào tab Order Details rồi bấm xuất lại. |
| PO trong form Order Details hoặc form 20 cột không có trên trang | Mở đúng Sale ASN có đủ PO rồi bấm thử lại; app không tự thêm PO khi bước Thêm PO đã được bỏ chọn. |
| Order Details, Style Details hoặc cả tab Shipping Info bị lỗi | Giữ nguyên form WFX, sửa trạng thái/ô đang vướng rồi bấm `Thử lại bước này` ngay trong dòng bước đó; hoặc bấm `Bỏ qua ...` nếu muốn tự điền bước đó. Một field riêng lẻ trong Shipping Info sẽ tự được bỏ qua và báo lại trong thẻ kết quả. |
