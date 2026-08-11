## Dùng để làm gì

Tạo Sale ASN mới từ file Excel, tìm Sale ASN cũ, hoặc mở một form New trống.
Chứng từ đã được thêm PO thủ công thì bỏ tích bước `Thêm PO` rồi chạy các bước
còn lại bằng chính form 22 cột.

Module có đúng hai thẻ. `Tạo mới` là thẻ mặc định và là nơi làm việc chính.
`Tra cứu` dùng để tìm chứng từ và xuất Buyer Invoice + Packing List. Nút mở
`Sale ASN List` nằm ở góc phải thanh trên nên bấm được từ cả hai thẻ.

## Các bước

### Tạo Sale ASN từ Excel

1. Mở module `Sale ASN`. Ứng dụng vào sẵn thẻ `Tạo mới`.
2. Bấm `↻` nếu danh sách Buyer chưa có hoặc cần cập nhật.
3. Bấm mũi tên trong ô để mở toàn bộ danh sách Buyer, hoặc gõ ít nhất hai ký tự
   để lọc nhanh, rồi chọn đúng Buyer.
   Khi đã khớp chính xác, ô Buyer hiện dấu ✓ ở bên phải.
4. Bấm `Tải form trống` nếu bạn chưa có form 22 cột.
5. Điền dữ liệu theo thứ tự từ trên xuống dưới trong file rồi lưu lại.
6. Bấm `Chọn file & kiểm tra`.
7. Kiểm tra Invoice No., số PO, số Style và các dữ liệu cần điền trong thẻ review.
   Từ lúc này, ô Buyer, nút chọn file và `Tùy chọn nâng cao` thu lại thành một
   dòng gọn ở trên cùng ghi Buyer và tên file. Bấm `Đổi` trên dòng đó để quay về
   chọn Buyer/file khác.
8. Bấm `Bắt đầu tạo Sale ASN`.
9. Theo dõi thẻ `Tiến độ Sale ASN`: năm bước `Thêm PO`, `Order Details`,
   `Style Details`, `Shipping Info` và bước cuối `Check giá / Qty` sáng dần theo
   đúng bước ứng dụng đang làm.
   Ba bước đầu hiện thêm số dòng đang xử lý, ví dụ `Order Details 5/12`, nên bạn
   biết ứng dụng đang chạy tới đâu chứ không phải đứng im.
10. Khi hoàn tất, ứng dụng tự đưa thẻ kết quả vào tầm nhìn. Thẻ này hiện Invoice
    No., số cảnh báo Shipping Info, kết quả đối chiếu và các nút xuất.
11. Sau khi ứng dụng điền xong, kiểm tra toàn bộ Sale ASN trên WFX rồi tự bấm
    `Save`.
12. Nếu đã nhập `Qty` và `Price`, bước `Check giá / Qty` tự chạy trước Save.
    Ứng dụng đối chiếu từng `PO No` + `Style No` trong file với `PO` được tách từ
    `Order No.` dạng `mã hệ thống/PO` + `Article` ở `Shipment Details`, sau đó tổng
    kết `Total Quantity`, `Value In Doc Currency` và `Net Value In Doc Currency`
    của `Summary Total`. Kết quả hiện gọn trong app: một hàng chip
    `n khớp`, `n lệch`, `Summary ✓` hoặc `✕`; chỉ các dòng lệch được liệt kê sẵn
    theo dạng `File → WFX`, còn các dòng khớp nằm trong mục `n dòng khớp` bấm để
    mở ra. Bấm `Xuất kết quả check` để lưu file Excel gồm hai sheet
    `PO + Style` và `Summary Total`, tô rõ các dòng khớp hoặc cần kiểm tra.
13. Sau khi đã Save, bấm `Xuất Invoice + PKL` trong thẻ kết quả để sang thẳng thẻ
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
> Nếu WFX tự đóng Add Order Details giữa danh sách, ứng dụng xác nhận các dòng
> đã thêm, mở lại popup và tiếp tục từ dòng kế tiếp. Bạn có thể chuyển sang phần
> mềm khác trong lúc chạy; task không phụ thuộc Chrome đang ở foreground và
> không phụ thuộc vị trí scroll hiện tại của WFX.

Ứng dụng mặc định tìm PO theo thứ tự `PO` → `Style` → `Destination`. Nếu một
bước chỉ còn một dòng, ứng dụng chọn và thêm ngay. Nếu dùng hết các tiêu chí mà
vẫn còn nhiều dòng, ứng dụng chỉ chọn tất cả khi tổng `Dispatched Qty` bằng đúng
`Qty` trong file. Nếu tổng không khớp, popup được giữ mở để bạn chọn lại thủ công
rồi bấm `Add & Continue` hoặc `OK`. Bạn có thể mở
`Tùy chọn nâng cao` > `Tiêu chí tìm PO` ngay trong module Sale ASN để tắt từng
tiêu chí không muốn dùng. Ứng dụng nhớ lựa chọn cho những lần sau; khi bỏ tích
cả ba, ứng dụng tự bật lại cả ba để tránh chạy không có điều kiện tìm. Cột
`Destination` không bắt buộc: nếu để trống ở dòng nào, ứng dụng bỏ qua tiêu chí
Destination của dòng đó và không thay đổi `Country Of Destination` hoặc
`Final Destination` mặc định trên WFX.

### Khi ứng dụng dừng giữa chừng

Mọi trạng thái chờ và lỗi hiện ngay bên trong dòng bước đang vướng của thẻ tiến
độ, nên bạn luôn thấy đã chạy được tới đâu.

- **Không thể tự thêm PO.** Dòng `Thêm PO` chuyển sang màu cảnh báo và mở thông
  báo. Chuyển sang WFX, điều chỉnh điều kiện tìm nếu cần, chọn dòng PO rồi bấm
  `Add & Continue` (hoặc `OK` nếu là PO cuối). Quay lại ứng dụng, tích ô xác nhận
  và bấm `Tiếp tục dòng kế`.
  Nếu muốn bỏ hẳn lượt này để làm lại từ file khác, bấm
  `Chọn file khác`.
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
Với `FTY`, bạn có thể nhập phần tên gần đúng, ví dụ `giao thuy`. Ứng dụng tìm
không phân biệt hoa/thường, chọn giá trị gần nhất trong danh sách Factory và bỏ
qua các lựa chọn có dấu chấm ở cuối. Nếu file thiếu dữ liệu hoặc WFX không có lựa chọn tương ứng, ứng
dụng bỏ qua đúng trường đó, tiếp tục điền các trường còn lại và liệt kê toàn bộ
cảnh báo trong thẻ kết quả để bạn bổ sung thủ công trước khi Save. Ứng dụng điền
`Shipment Mode` trước, sau đó điền Port of Loading vào cả trường WFX có sẵn:
`AWB Loading Port` và `BL Mother Loading Port`. Chỉ cần một trường tồn tại và
nhận giá trị là bước này thành công. `Notify 1` được giữ nguyên để bạn tự chọn
khi cần. Nếu `Country Of Destination` không có lựa chọn khớp vì WFX dùng tên
quốc gia đầy đủ, ứng dụng giữ nguyên `Final Destination` theo giá trị mặc định
của `Country Of Destination`; không đổi riêng `Final Destination`.

### Bỏ Add PO và làm tiếp từ chứng từ đang mở

1. Mở đúng Sale ASN đã được thêm PO thủ công và vào bảng `Order Details`.
2. Mở `Tùy chọn nâng cao` ở cuối thẻ `Tạo mới`.
3. Trong `Các bước app sẽ làm`, bỏ tích `Thêm PO`. Chỉ giữ các bước cần app làm:
   `Order Details`, `Style Details` và/hoặc `Shipping Info`.
4. Bấm `Xuất PO đang mở`. Ứng dụng đọc chứng từ đang mở trên WFX và tạo form
   22 cột có sẵn PO No. cùng các giá trị Order Details hiện có, nên bạn không
   phải gõ lại danh sách PO.
5. Bổ sung Style/HS Code/Goods Description hoặc Shipping Info trong form nếu các bước đó được
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

### Mở Sale ASN New trống, không cần upload

1. Mở `Tùy chọn nâng cao` trong thẻ `Tạo mới`.
2. Bấm `Mở Sale ASN New trống`.
3. Tạo chứng từ và thêm PO thủ công trực tiếp trên WFX.

Nút này chỉ mở màn New. Ứng dụng không yêu cầu file Excel và không tự điền dữ
liệu.

## Quy tắc của file Excel

- Mỗi file chỉ chứa một Invoice No. và một FTY.
- Chỉ dòng có `PO No` mới được tính và xử lý; dòng tổng hoặc ghi chú không có PO sẽ được bỏ qua.
- Với mỗi dòng có PO, `Style No` và `FTY` là dữ liệu bắt buộc. `Destination` có
  thể để trống.
- `Style No` được dùng như từ khóa tìm gần đúng. Ví dụ `M Acel Jacket` có thể khớp với Style `JLD-SMOW17905-M ACEL JACKET-MEN` trên WFX.
- Một `PO No` có thể xuất hiện ở nhiều dòng khi mỗi dòng là một `Style No` khác nhau. Chỉ cặp `PO No` + `Style No` trùng hoàn toàn mới bị báo lỗi.
- Form có 22 cột và không còn `SEASON` hoặc cột `DESCRIPTION` cũ. Thứ tự cột là:
  `Style No`, `PO No`, `Qty`, `Price`, `Carton`, `NW`, `GW`, `CBM`, `FOB Price`,
  `Service Price`, `Cargo Ready Date`, `HS CODE`, `Goods Description`, `Invoice No`, `Invoice Date`,
  `Shipping Bill No`, `Shipping Bill Date`, `Destination`, `FTY`,
  `Consignee Address`, `Ship To`, `Shipping Mode`.
- Chỉ điền `Shipping Mode` tại dòng dữ liệu đầu tiên. Ô này bắt buộc khi chạy
  bước Shipping Info và chỉ nhận `AIR`, `SEA` hoặc `COURIER`; các dòng sau có thể
  để trống vì ứng dụng dùng mode của dòng đầu cho toàn bộ chứng từ.
- `Destination`, `HS CODE`, `Goods Description`, `Qty`, `Price`, `Carton`, `NW`, `GW`,
  `CBM`, `FOB Price`, `Service Price`, `Cargo Ready Date`, `Consignee Address`
  và `Ship To` có thể để trống. Khi có Goods Description, app điền vào đúng dòng
  Style Details trên WFX.
- Ba cột `Cargo Ready Date`, `Invoice Date` và `Shipping Bill Date` cho phép chọn
  ngày và sẽ báo nếu giá trị không phải ngày hợp lệ.
- Nếu cả file không có `Cargo Ready Date`, ứng dụng giữ trống toàn bộ và không
  lấy ngày hiện tại. Nếu bạn nhập ngày ở một dòng, ứng dụng dùng ngày có dữ liệu
  đầu tiên để điền tất cả dòng còn trống.
- `Invoice Date` và `Shipping Bill Date` trống vẫn lấy ngày có dữ liệu đầu tiên trong file; nếu cả file không có thì dùng ngày hiện tại.
- Nếu Shipping Bill No. bị trống, ứng dụng dùng Invoice No.
- PO luôn được xử lý đúng thứ tự dòng trong file.

Ứng dụng chọn chính Shipping Mode trên WFX, rồi tự điền Port of Loading và
Delivery Terms theo mode đó:

| Shipping Mode | Port of Loading | Delivery Terms |
|---|---|---|
| `AIR` | `HAN - Hanoi` | `FCA HANOI, VIET NAM` |
| `SEA` | `HPH - Haiphong` | `FOB HAIPHONG, VIETNAM` |
| `COURIER` | `HAN - Hanoi` | `EXW` |

## Tìm Sale ASN và tải Documents

1. Chọn thẻ `Tra cứu`.
2. Chọn `Invoice No.` hoặc `Buyer Order Ref/OC`.
3. Nhập nội dung rồi bấm `Tìm`.
4. Bấm `Xuất Invoice + PKL` để lấy hai báo cáo trong cùng một file Excel.

> [!luuy]
> Report WFX có thể tải chậm. Ứng dụng chờ tối đa ba phút cho từng Packing List
> hoặc Buyer Invoice; không bấm xuất lại khi trạng thái vẫn đang chạy.

> [!meo]
> Khi gộp file, ứng dụng giữ nguyên tên sheet do WFX xuất. Chỉ khi hai report có
> sheet trùng tên, chúng được đổi theo dạng `PKL 1083.26.PS.PSHK_7` và
> `INVOICE 1083.26.PS.PSHK_7` để Excel chấp nhận. Nếu report có nhiều sheet,
> ứng dụng xếp xen kẽ `Invoice 1`, `PKL 1`, `Invoice 2`, `PKL 2` cho đến hết;
> Invoice luôn đứng trước PKL. Sau khi lưu thành công, Explorer sẽ tự mở và chọn
> đúng file vừa lưu. Các cửa sổ Docs/report do chính lượt tải mở sẽ tự đóng; các
> cửa sổ WFX đã có từ trước vẫn được giữ nguyên. Khung, rich text, merged cell
> và định dạng gốc của cả Invoice lẫn PKL được giữ nguyên khi ghép. Hàng có nội
> dung xuống dòng sẽ được tăng chiều cao khi ghép để không bị cắt lúc mở Excel.
> Các cột No of Pcs, Net Wt, Gross Wt, No of Carton và CBM cũng được nới để thấy
> trọn header/số liệu. Mỗi sheet vẫn đặt A4, giữ đúng hướng dọc/ngang từ report
> WFX và fit vừa một trang theo chiều ngang khi in. Popup Docs/report do lượt
> bấm Docs mở sẽ luôn tự đóng sau lượt tải, kể cả khi có lỗi; tab WFX có sẵn được giữ.

> Ứng dụng tải trực tiếp đúng file Excel từ URL do Report Viewer cung cấp và
> kiểm tra nội dung từng workbook trước khi ghép. Packing List không thể bị dùng
> nhầm làm Buyer Invoice và không tạo hai file PKL thừa trong Downloads.

> [!meo]
> Packing List J.Lindeberg có header `JL PO#` tự gộp dọc Net Wt, Gross Wt, No of
> Carton và CBM cho các dòng liền nhau cùng PO + Style khi số liệu giống nhau.
> Packing List CORPORATE OFFICE - TRUEWERK tự gộp bốn cột tương ứng của dòng PO và
> `ADD`/`- ADD` liền nhau khi mỗi cột chỉ có một số khác 0, rồi đưa số đó lên ô đầu
> vùng gộp.

> [!meo]
> Nếu file cùng tên đang mở trong Excel, app tự lưu tên kế tiếp, ví dụ
> `INV-001 (2).xlsx`; không cần tải lại hai report.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không có Buyer để chọn | Nút `↻` sẽ nhấp nháy màu vàng khi kho Buyer còn rỗng. Mở đúng phiên WFX rồi bấm `↻`. Ứng dụng không tự quét vì thao tác này mở hẳn form Sale ASN New trên Chrome. |
| Ô Buyer viền vàng, không có dấu ✓ | Tên đang gõ chưa khớp Buyer nào. Gõ lại và chọn đúng dòng trong danh sách gợi ý. |
| File có lỗi | Đọc vị trí ô hoặc dòng trong thông báo, sửa file rồi chọn lại. |
| Báo một ô số `quá lớn` | Ô Qty, Carton, NW, GW, CBM hoặc giá đang chứa giá trị vượt ngoài phạm vi thực tế (thường do dán nhầm hoặc Excel đổi sang dạng `1E+...`). Nhập lại đúng số rồi chọn file lại. |
| Có nhiều dòng sau tiêu chí cuối | Ứng dụng chỉ tự chọn tất cả khi tổng `Dispatched Qty` khớp `Qty` file. Nếu không khớp, popup giữ nguyên để bạn chọn lại và bấm `Add & Continue` hoặc `OK`. |
| Không tìm thấy PO | Kiểm tra `Tiêu chí tìm PO` trong `Tùy chọn nâng cao` cùng PO No., Style và (nếu có) Destination trong file; bạn có thể tìm và chọn thủ công trên cửa sổ đang mở. |
| Đã đóng cửa sổ Add PO | Hủy phiên đang chuẩn bị và chạy lại từ file để tránh bỏ sót dòng. |
| Không xuất được form Order Details | Mở đúng chứng từ có PO và vào tab Order Details rồi bấm xuất lại. |
| PO trong form Order Details hoặc form 22 cột không có trên trang | Mở đúng Sale ASN có đủ PO rồi bấm thử lại; app không tự thêm PO khi bước Thêm PO đã được bỏ chọn. |
| Order Details, Style Details hoặc cả tab Shipping Info bị lỗi | Giữ nguyên form WFX, sửa trạng thái/ô đang vướng rồi bấm `Thử lại bước này` ngay trong dòng bước đó; hoặc bấm `Bỏ qua ...` nếu muốn tự điền bước đó. Một field riêng lẻ trong Shipping Info sẽ tự được bỏ qua và báo lại trong thẻ kết quả. |
