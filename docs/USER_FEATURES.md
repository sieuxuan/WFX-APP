# Danh sách chức năng WFX Smart

> File này được sinh tự động từ `wfx_panel/manual/`. Đừng sửa tay —
> sửa nội dung trong `wfx_panel/manual/` rồi chạy
> `python scripts/generate_user_features.py`.

Phiên bản: 1.0.19

## 1. Bắt đầu

Cài đặt, mở ứng dụng và kết nối tài khoản WFX.

### Mở và đóng bảng điều khiển

Ba cách gọi WFX Smart ra màn hình.

Dùng để làm gì WFX Smart nằm sẵn bên cạnh trình duyệt để bạn gọi ra bất cứ lúc nào mà không phải tìm trong Start Menu. Các bước Nhấn tổ hợp phím Ctrl + Shift + X ở bất kỳ đâu, kể cả khi bạn đang làm việc trong màn hình WFX trên trình duyệt. Bảng điều khiển hiện ra ở mép phải màn hình. Nhấn lại tổ hợp đó, hoặc bấm nút dấu nhân ở góc trên, để thu bảng lại. Hai cách gọi khác: Bấm vào biểu tượng tròn nhỏ luôn nổi trên màn hình. Bấm đúp vào biểu tượng WFX Smart ở khay hệ thống, cạnh đồng hồ Windows. Mẹo Mẹo Bảng điều khiển tự thu lại khi bạn bấm sang cửa sổ khác. Nếu một tác vụ đang chạy, bảng chờ tác vụ xong mới thu. Mẹo Đổi tổ hợp phím trong Cài đặt, thẻ Tự động hóa, dòng `Phím tắt mở bảng điều khiển`. Lưu ý Bật Mở ẩn trong khay hệ thống nếu bạn muốn ứng dụng khởi động yên lặng cùng Windows và chỉ hiện khi được gọi. Mẹo Bật Luôn trên cùng trong Cài đặt, thẻ Giao diện, nếu bạn muốn bảng điều khiển không bị cửa sổ khác che mất. Gặp lỗi thì sao Hiện tượng Cách xử lý Nhấn phím tắt không thấy gì Cửa sổ đang dùng chạy quyền quản trị cao hơn ứng dụng. Bấm biểu tượng tròn nổi hoặc biểu tượng ở khay hệ thống. Không thấy biểu tượng ở khay Bấm mũi tên mở rộng cạnh đồng hồ Windows để xem các biểu tượng bị ẩn.

### Đăng nhập tài khoản WFX

Lưu tài khoản một lần, ứng dụng tự giữ phiên.

Dùng để làm gì Lưu tài khoản WFX một lần để ứng dụng tự đăng nhập và tự giữ phiên, bạn không phải nhập lại mỗi ngày. Các bước Bấm biểu tượng bánh răng ở góc trên bảng điều khiển. Chọn thẻ Tài khoản. Nhập Tên đăng nhập WFX và Mật khẩu. Bấm Lưu và đăng nhập WFX . Chờ dòng trạng thái dưới cùng báo đã kết nối. Mẹo Mẹo Sau lần đăng nhập đầu tiên, ứng dụng tự kiểm tra và duy trì phiên mỗi bốn phút khi trình duyệt đang rảnh. Bạn gần như không bao giờ phải nhập lại. Lưu ý Mật khẩu được mã hóa và lưu riêng trên máy này, không hiển thị lại và không được gửi đi đâu. Gặp lỗi thì sao Hiện tượng Cách xử lý Ứng dụng mở lại màn hình nhập tài khoản WFX đã từ chối phiên cũ. Nhập lại mật khẩu rồi bấm lưu. Báo chưa có trình duyệt Bấm Mở trình duyệt trên dải thông báo màu ở đầu bảng điều khiển.

### Cài đặt ứng dụng

Tải bộ cài và cài cho riêng máy bạn.

Dùng để làm gì Cài WFX Smart cho tài khoản Windows của bạn để mở nhanh từ Desktop hoặc Start Menu mà không cần quyền quản trị. Các bước Tải file WFX-Smart-Setup-v[phiên bản].exe từ nơi công ty phát hành. Mở file vừa tải. Giữ các lựa chọn tạo lối tắt nếu bạn muốn mở ứng dụng từ Desktop và Start Menu. Bấm Cài đặt . Chờ bộ cài hoàn tất rồi mở WFX Smart. Mẹo Mẹo Khi cài bản mới, các cài đặt và dữ liệu đã lưu trên máy vẫn được giữ nguyên. Gặp lỗi thì sao Hiện tượng Cách xử lý Windows không cho mở file Kiểm tra lại file có đúng do công ty phát hành hay không rồi thử lại. Không thấy lối tắt Desktop Mở Start Menu, tìm WFX Smart và chọn ứng dụng từ kết quả.

### Khởi động cùng Windows

Để ứng dụng sẵn sàng ngay khi bật máy.

Dùng để làm gì Để WFX Smart sẵn sàng ngay khi bạn đăng nhập Windows mà không phải mở lại mỗi ngày. Các bước Bấm biểu tượng bánh răng ở góc trên bảng điều khiển. Chọn thẻ Tự động hóa. Bật Khởi động cùng Windows . Bật Mở ẩn trong khay hệ thống nếu bạn muốn ứng dụng khởi động yên lặng. Đóng Cài đặt để tiếp tục làm việc. Mẹo Mẹo Bản cài mới bật Khởi động cùng Windows sẵn. Nếu bạn tắt, ứng dụng ghi nhớ lựa chọn đó cho những lần mở sau. Lưu ý Khi mở ẩn, bạn gọi bảng điều khiển bằng phím tắt, biểu tượng nổi hoặc biểu tượng WFX Smart cạnh đồng hồ Windows. Gặp lỗi thì sao Hiện tượng Cách xử lý Bật máy nhưng không thấy bảng điều khiển Kiểm tra biểu tượng cạnh đồng hồ Windows. Nếu đã bật mở ẩn, bảng điều khiển chưa hiện ra cho tới khi bạn gọi. Ứng dụng không tự mở Mở WFX Smart, vào Cài đặt, thẻ Tự động hóa rồi tắt và bật lại Khởi động cùng Windows .

### Chọn Division

Chọn đúng Division trước khi thao tác.

Dùng để làm gì Chọn đúng Division để mọi danh sách và thao tác sau đó dùng đúng khu vực làm việc của bạn trên WFX. Các bước Mở bảng điều khiển WFX Smart. Bấm WOVEN , KNIT hoặc PSSG ở đầu bảng điều khiển. Chờ nút vừa chọn được tô màu. Chờ dòng trạng thái dưới cùng xác nhận đã đổi Division. Mẹo Mẹo Chọn Division trước khi mở module để tránh phải quay lại danh sách từ đầu. Gặp lỗi thì sao Hiện tượng Cách xử lý Báo chưa xác nhận được Division Chờ WFX ổn định rồi bấm lại đúng Division một lần. Nút đã chọn nhưng dữ liệu chưa đổi Bấm nút kiểm tra lại ở góc dưới rồi chọn lại Division.

### Mở trình duyệt làm việc

Ứng dụng cần một cửa sổ trình duyệt để thao tác trên WFX.

Dùng để làm gì Mở cửa sổ trình duyệt mà WFX Smart dùng để thực hiện công việc trên WFX. Các bước Tìm dải thông báo Chưa có trình duyệt làm việc ở đầu bảng điều khiển. Bấm Mở trình duyệt . Chờ Chrome, Edge, Brave hoặc Chromium mở ra. Đăng nhập WFX nếu trình duyệt yêu cầu. Chờ hai đèn Chrome và WFX ở thanh dưới cùng chuyển sang trạng thái đã kết nối. Mẹo Mẹo Bạn có thể để cửa sổ trình duyệt mở trong suốt ngày làm việc. WFX Smart dùng lại cửa sổ đó cho các tác vụ tiếp theo. Gặp lỗi thì sao Hiện tượng Cách xử lý Bấm mở nhưng chưa thấy trình duyệt Chờ vài giây rồi bấm Kiểm tra lại trên dải thông báo. Đèn Chrome sáng nhưng đèn WFX chưa sáng Mở cửa sổ trình duyệt và đăng nhập WFX, sau đó bấm nút kiểm tra lại ở góc dưới.

## 2. Dùng hằng ngày

Những thao tác bạn lặp lại mỗi ngày trên bảng điều khiển.

### Tìm và mở module

Gõ vài chữ là ra đúng màn hình cần dùng.

Dùng để làm gì Tìm nhanh đúng module bạn cần mà không phải đọc từng thẻ trên bảng điều khiển. Các bước Mở bảng điều khiển WFX Smart. Bấm vào ô Tìm nhanh module... . Gõ một phần tên module. Bấm thẻ module trong kết quả để mở màn hình làm việc. Mẹo Mẹo Bạn không cần gõ đủ tên. Gõ vài chữ dễ nhớ như OC, Sample hoặc Supplier là đủ để thu gọn danh sách. Gặp lỗi thì sao Hiện tượng Cách xử lý Không thấy module cần dùng Xóa nội dung ô tìm rồi kiểm tra lại toàn bộ danh sách. Một số module chỉ hiện khi tài khoản của bạn có quyền. Danh sách vẫn đang bị lọc Bấm dấu xóa trong ô tìm hoặc bôi đen nội dung rồi nhấn Backspace.

### Ghim module hay dùng

Đưa module quen thuộc lên đầu.

Dùng để làm gì Đưa những module bạn dùng thường xuyên lên khu Yêu thích ở đầu bảng điều khiển. Các bước Mở danh sách module trên bảng điều khiển. Tìm thẻ module bạn hay dùng. Bấm nút ngôi sao trên thẻ đó. Kiểm tra module đã xuất hiện trong khu Yêu thích phía trên ô tìm kiếm. Mẹo Mẹo Module đã ghim chỉ hiện trong khu Yêu thích và không lặp lại ở nhóm bên dưới. Mẹo Bấm lại ngôi sao để bỏ ghim. Gặp lỗi thì sao Hiện tượng Cách xử lý Chưa thấy khu Yêu thích Ghim ít nhất một module rồi quay lại đầu danh sách. Muốn đổi thứ tự Bỏ ghim các module rồi ghim lại theo thứ tự bạn muốn dùng.

### Dừng một tác vụ đang chạy

Dừng an toàn mà không làm hỏng dữ liệu đang ghi.

Dùng để làm gì Dừng một tác vụ đang chạy tại điểm an toàn tiếp theo khi bạn chọn nhầm hoặc không muốn chờ tiếp. Các bước Nhìn thanh trạng thái dưới cùng khi tác vụ đang chạy. Bấm Stop . Chờ ứng dụng hoàn tất bước an toàn đang làm. Chờ dòng trạng thái báo tác vụ đã dừng. Mẹo Mẹo Nút Stop chỉ hiện trong lúc có tác vụ đang chạy. Lưu ý Ứng dụng không cắt ngang khi WFX đang lưu dữ liệu. Vì vậy tác vụ có thể cần thêm một lúc ngắn mới dừng hẳn. Lưu ý Không đóng trình duyệt để ép dừng. Làm vậy có thể khiến bạn khó biết WFX đã lưu tới đâu. Gặp lỗi thì sao Hiện tượng Cách xử lý Đã bấm Stop nhưng tác vụ chưa dừng ngay Chờ bước lưu hiện tại hoàn tất. Ứng dụng sẽ dừng ở điểm an toàn kế tiếp. Không thấy nút Stop Tác vụ đã xong hoặc chưa bắt đầu. Đọc dòng trạng thái để biết kết quả.

### Đọc thanh trạng thái

Biết ứng dụng đang làm gì và đã kết nối chưa.

Dùng để làm gì Theo dõi ứng dụng đang làm gì, Chrome đã mở chưa và phiên WFX còn hoạt động hay không. Các bước Đọc thông báo ở góc trái thanh dưới cùng. Kiểm tra đèn Chrome để biết trình duyệt đã sẵn sàng. Kiểm tra đèn WFX để biết tài khoản còn kết nối. Bấm nút kiểm tra lại ở góc phải nếu trạng thái chưa cập nhật. Mẹo Mẹo Bật Trở về List sau khi thao tác trong Cài đặt, thẻ Tự động hóa, nếu bạn muốn bảng điều khiển quay về danh sách module sau mỗi tác vụ. Mẹo Bật Đưa Chrome lên khi chạy module nếu bạn muốn chuyển ngay sang cửa sổ WFX khi bấm một nút thao tác. Gặp lỗi thì sao Hiện tượng Cách xử lý Đèn Chrome chưa sáng Bấm Mở trình duyệt trên dải thông báo ở đầu bảng điều khiển. Đèn WFX chưa sáng Mở trình duyệt, đăng nhập WFX rồi bấm nút kiểm tra lại.

### Giao diện và thông báo

Chọn nền sáng tối và bật tắt thông báo.

Dùng để làm gì Chọn cách WFX Smart hiển thị và quyết định những thông báo bạn muốn nhận. Các bước Bấm biểu tượng bánh răng ở góc trên bảng điều khiển. Chọn thẻ Giao diện. Bấm Sáng , Tối hoặc Tự động trong dòng Giao diện. Bật hoặc tắt Thông báo khi xong việc . Bấm Thử thông báo để kiểm tra ngay trên màn hình hiện tại. Đóng Cài đặt để tiếp tục làm việc. Mẹo Mẹo Chọn Tự động để giao diện đi theo chế độ sáng hoặc tối của Windows. Mẹo Bật Mở file Costing sau khi tải trong thẻ Tự động hóa nếu bạn muốn file vừa xuất tự mở bằng Excel hoặc ứng dụng mặc định. Lưu ý Chế độ quản trị chỉ hiện khi tài khoản được cấp quyền. Bật mục này để xem các module Admin dành cho bạn. Gặp lỗi thì sao Hiện tượng Cách xử lý Không thấy thông báo khi xong việc Bật Thông báo khi xong việc , sau đó bấm Thử thông báo . WFX Smart dùng notification native của Windows, không lấy focus và lưu trong Notification Center; kiểm tra thêm cài đặt thông báo/Không làm phiền của Windows nếu vẫn không thấy. Không thấy Chế độ quản trị Tài khoản hiện tại chưa được cấp quyền quản trị hoặc ứng dụng chưa nhận lại quyền mới.

## 3. Catalog

Tìm Style và mở các phần dữ liệu liên quan trong WFX.

### Tìm Style

Tìm theo mã Article, Buyer Reference hoặc tên Article.

Dùng để làm gì Tìm đúng Style trong Catalog bằng thông tin bạn đang có và mở Style đó trên WFX. Các bước Chọn đúng Division ở đầu bảng điều khiển. Mở module Catalog. Chọn Category phù hợp với Style. Bấm Mở Catalog nếu bạn muốn mở danh sách Catalog trước. Chọn Article Code, Buyer Reference hoặc Article Name trong dòng kiểu tìm. Nhập nội dung vào ô tìm. Chọn một gợi ý nếu danh sách gợi ý xuất hiện. Bấm Tìm . Mẹo Mẹo Article Code dùng được với mọi Category. Buyer Reference dành cho Apparel. Article Name dành cho các Category còn lại. Mẹo Gõ từ hai ký tự để nhận tối đa 20 gợi ý từ Thư viện Article. Mẹo Bạn không cần kéo Code, Buyer Reference hoặc Article Name về vị trí cũ. Ứng dụng tự tìm cột theo layout Catalog riêng của tài khoản và xóa filter cũ. Lưu ý Nếu chỉ có một kết quả, ứng dụng tự mở Style. Nếu có nhiều kết quả, bạn bấm đúng dòng cần dùng trên màn hình WFX. Gặp lỗi thì sao Hiện tượng Cách xử lý Không tìm thấy kết quả Kiểm tra lại Category, kiểu tìm và nội dung đã nhập rồi bấm Tìm lần nữa. Có nhiều Style gần giống nhau Đọc Article Code trên WFX và bấm đúng dòng bạn cần. Catalog chưa sẵn sàng Bấm Mở Catalog , chờ danh sách hiện đủ rồi tìm lại.

### Mở Costing

Đi thẳng từ Style đã tìm tới khu Costing.

Dùng để làm gì Mở Costing của Style vừa tìm để xem, xuất hoặc cập nhật file Costing. Các bước Mở module Catalog. Chọn Category và nhập thông tin Style. Bấm Costing . Chờ ứng dụng tìm và mở đúng Style trên WFX. Chờ bảng điều khiển chuyển sang khu Costing. Mẹo Mẹo Nếu Style đã được tìm và mở, bạn có thể bấm Costing ngay mà không nhập lại. Gặp lỗi thì sao Hiện tượng Cách xử lý Không mở được Costing Kiểm tra Style đã chọn đúng chưa, rồi tìm lại Style trước khi bấm Costing . WFX báo chưa có Costing Tạo hoặc mở Costing trực tiếp trên WFX rồi quay lại thao tác.

### Mở BOM

Mở danh sách nguyên phụ liệu của Style.

Dùng để làm gì Mở BOM của Style để xem danh sách nguyên phụ liệu trên WFX. Các bước Mở module Catalog. Chọn Category và nhập thông tin Style. Bấm BOM . Chờ ứng dụng mở đúng Style. Kiểm tra màn hình BOM trên WFX. Mẹo Mẹo Dùng Article Code nếu bạn đã biết mã chính xác để giảm khả năng có nhiều kết quả. Gặp lỗi thì sao Hiện tượng Cách xử lý BOM chưa mở Chờ WFX tải xong Style rồi bấm BOM lại một lần. Có nhiều kết quả Chọn đúng Style trên WFX, sau đó bấm BOM .

### Tải file đính kèm

Xem và tải các file đang gắn với Style.

Dùng để làm gì Xem và tải những file đang đính kèm với Style trong Catalog. Các bước Mở module Catalog. Chọn Category và nhập thông tin Style. Bấm File . Chờ ứng dụng kiểm tra bốn nhóm file của Style. Bấm file bạn muốn tải trong danh sách kết quả. Chọn nơi lưu nếu ứng dụng hỏi. Chờ thư mục chứa file tự mở. Mẹo Mẹo Nếu chỉ có một Style phù hợp, ứng dụng tự mở Style và kiểm tra file ngay. Gặp lỗi thì sao Hiện tượng Cách xử lý Không có file trong một nhóm Style chưa được đính kèm file ở nhóm đó. Kiểm tra nhóm khác trong kết quả. Tải file không thành công Kiểm tra kết nối mạng, chọn lại file và thử tải lần nữa. Đường dẫn file không hợp lệ Mở Style trên WFX và kiểm tra file đính kèm còn tồn tại.

### Thư viện Article

Dùng danh sách Article tự cập nhật để nhận gợi ý nhanh.

Dùng để làm gì Nhận gợi ý Article Code, Article Name và Buyer Reference khi bạn tìm Catalog hoặc điền file Costing. Các bước Mở module Catalog. Chọn Category. Nhập từ hai ký tự vào ô tìm. Đọc tối đa 20 gợi ý phù hợp. Bấm đúng gợi ý để điền Article Code chính xác. Mẹo Mẹo Dữ liệu được lấy từ PostgreSQL qua n8n tối đa một lần mỗi 30 ngày. Muốn lấy ngay bản mới, mở Cài đặt > Tài khoản và bấm Đồng bộ ngay . Mẹo Khi mất mạng, ứng dụng tiếp tục dùng danh sách gần nhất đã lưu trên máy. Gặp lỗi thì sao Hiện tượng Cách xử lý Chưa có gợi ý Bạn vẫn có thể nhập Article Code hoặc tên Article bằng tay. Gợi ý chưa có Article mới Bấm Đồng bộ ngay ; nếu server chưa có, báo Admin publish snapshot mới. Dành cho Admin Đăng nhập tài khoản WFX có quyền quản trị. Mở Cài đặt > Tài khoản . Nhập Admin key một lần và bấm Lưu key . Key được mã hóa bằng Windows DPAPI, chỉ dùng được bởi đúng tài khoản Windows trên máy đó. Sau khi cache Article và dropdown Style đã đúng, bấm Publish dữ liệu hiện tại và xác nhận. User khác sẽ nhận snapshot mới ở lần tự đồng bộ tháng kế tiếp hoặc ngay khi họ bấm Đồng bộ ngay .

### Cây thư mục Catalog

Chọn vị trí Apparel mặc định và làm mới thư mục.

Dùng để làm gì Chọn vị trí Apparel mà bạn thường dùng và làm mới danh sách thư mục Catalog khi WFX có thay đổi. Các bước Mở module Catalog. Bấm nút biểu tượng nhỏ cạnh Mở Catalog . Chọn vị trí Apparel bạn muốn dùng mặc định. Bấm nút xác nhận trong hộp chọn. Bấm Quét lại thư mục Catalog khi bạn cần đọc lại danh sách thư mục từ WFX. Mẹo Mẹo Vị trí mặc định được ghi nhớ cho lần mở Catalog tiếp theo. Gặp lỗi thì sao Hiện tượng Cách xử lý Không thấy thư mục cần chọn Bấm Quét lại thư mục Catalog , chờ danh sách tải xong rồi mở lại hộp chọn. Mở thư mục quá lâu Kiểm tra phiên WFX còn kết nối rồi thử lại.

### Tạo Style Apparel hàng loạt

Tạo Style từ Excel với picker Group, dropdown phụ thuộc và Auto Save tùy chọn.

Dùng để làm gì Tạo nhiều Style Apparel từ một file Excel trong đúng Group bạn đã chọn. Ứng dụng chuẩn bị từng Style trên WFX. Tự động Save luôn mặc định tắt; bạn chỉ bật khi muốn app Save ngay sau khi điền xong từng dòng. Các bước Mở module Catalog. Chọn tab Tạo Style . Bấm nút làm mới nhỏ cạnh Group bắt buộc nếu cây Group chưa hiện. Mở ô chọn Group, gõ tên hoặc đường dẫn để tìm rồi chọn đúng một Group Apparel. Bấm Tải form Excel . Điền dữ liệu trong sheet Tạo Style rồi lưu file. Bấm Chọn file & kiểm tra và chọn file vừa lưu. Đọc dòng đang chờ rồi bấm Chuẩn bị dòng đầu tiên . Nếu Tự động Save đang tắt, kiểm tra toàn bộ trường trên WFX, tự bấm Save , rồi chọn Tôi đã Save · Chuẩn bị dòng tiếp theo . Nếu Tự động Save đang bật, app Save đúng một lần sau khi điền xong và nút chuẩn bị chuyển thẳng sang dòng kế tiếp. Cách điền file Cột Cách dùng Type Chọn New hoặc Copy . Style copy Bắt buộc với Copy . Mã bắt đầu bằng SWN/SKN được tìm theo Article Code; giá trị khác được tìm theo Buyer Reference. Material Type Chọn KNIT hoặc WOVEN . Các cột còn lại New cần điền đủ. Với Copy , ô trống giữ nguyên dữ liệu Style nguồn. Các cột Material Type, Buyer, Division, Product Group, Sub-Category, Color Card, Size Range và Season có dropdown lấy từ cache dùng chung. Sub-Category tự đổi danh sách theo Product Group của đúng dòng. Lưu ý App luôn đặt Purchase UOM là Pcs , Price Per là Article và Color Definition là Single Colors . Lưu ý Tự động Save mặc định tắt mỗi lần mở app. Khi bật, hãy kiểm tra file trước vì Style sẽ được ghi lên WFX ngay sau khi điền xong. Mẹo Dropdown ưu tiên snapshot PostgreSQL dùng chung và chỉ tự tải tối đa một lần mỗi 30 ngày. Nút Đồng bộ ngay nằm trong Cài đặt > Tài khoản . Nếu server tạm lỗi, app giữ nguyên cache gần nhất; Group đã chọn vẫn dùng để quét WFX khi cần làm mới trực tiếp. Lưu ý Bấm Tải form Excel sẽ hỏi nơi lưu file ngay. Nếu dữ liệu dropdown đã quá 30 ngày, app lấy danh sách mới sau khi bạn chọn xong nơi lưu, nên bước này có thể chờ thêm một lúc. Lúc quét, app tự mở rồi tự đóng một cửa sổ Style trên trình duyệt làm việc; cửa sổ đó chỉ để đọc danh sách và không ghi gì lên WFX. Mẹo Nếu tìm Copy ra nhiều Style, chọn đúng Style nguồn ngay trong bảng điều khiển. Gặp lỗi thì sao Hiện tượng Cách xử lý Chưa chọn được Group Bấm nút làm mới nhỏ, tìm bằng tên/đường dẫn rồi chọn lại. Chưa quét được dropdown Giữ Chrome đăng nhập, chọn Group có quyền tạo Style rồi tải lại form. App vẫn ưu tiên cache gần nhất khi server hoặc WFX tạm lỗi. File báo sai header Tải form mới và sao chép dữ liệu vào đúng cột. New báo thiếu trường Điền đủ các cột từ Material Type đến Internal Style Ref. Không tìm thấy Style nguồn Kiểm tra Style copy ; SWN/SKN phải là Article Code, giá trị khác phải là Buyer Reference. Một danh sách Style nguồn xuất hiện Chọn đúng dòng theo Article Code và Buyer Reference. Không điền được một trường Giữ nguyên màn hình WFX, chụp ảnh lỗi trong Lịch sử và gửi cho nhóm hỗ trợ.

## 4. File Costing

Xuất, kiểm tra và áp dụng thay đổi Costing bằng file Excel.

### Xuất file Costing

Tải dữ liệu Costing đang mở thành file Excel.

Dùng để làm gì Tải Costing đang mở trên WFX thành file Excel để bạn kiểm tra hoặc chỉnh sửa. Các bước Mở đúng Costing của Style trên WFX. Mở module Catalog trên bảng điều khiển. Chuyển sang khu Costing. Bấm Tải XLSX . Kiểm tra Style Code, Style Name và trạng thái Costing trong hộp lưu file. Chọn thư mục và bấm nút lưu. Chờ thư mục chứa file tự mở. Mẹo Mẹo Bạn có thể xuất file ở mọi trạng thái Costing. Mẹo Tên file mặc định dùng Style Name. Hộp lưu nhớ thư mục bạn đã chọn lần trước. Gặp lỗi thì sao Hiện tượng Cách xử lý Ứng dụng chưa nhận ra Style Đưa đúng Costing lên trước trên WFX rồi bấm Tải XLSX lại. Có nhiều Costing đang mở Bấm vào đúng Costing cần xuất trên WFX, sau đó thử lại. Chưa đọc xong dữ liệu Chờ màn hình Costing tải đầy đủ rồi bấm tải lại.

### Kiểm tra file Costing

Soát lỗi trong file trước khi làm việc với WFX.

Dùng để làm gì Soát cấu trúc và dữ liệu trong file Excel trước khi bạn nhập thay đổi vào WFX. Các bước Mở module Catalog. Chuyển sang khu Costing. Bấm Kiểm tra file . Chọn file Excel cần soát. Đọc kết quả kiểm tra trên bảng điều khiển. Mở đúng sheet và ô được báo để sửa lỗi. Mẹo Mẹo Nút Kiểm tra file chỉ đọc file Excel. Nút này không mở Costing và không thay đổi dữ liệu trên WFX. Gặp lỗi thì sao Hiện tượng Cách xử lý Báo thiếu sheet Costing Dùng file được tải từ nút Tải XLSX , không đổi tên hoặc xóa sheet. Báo lỗi ở một ô Mở đúng địa chỉ ô được báo, sửa giá trị rồi kiểm tra file lại. Không chọn được file Kiểm tra file có đuôi .xlsx và không bị hỏng.

### Nhập file Costing

Đọc file và lập bản xem trước thay đổi.

Dùng để làm gì Đọc file Costing đã chỉnh sửa và lập bản xem trước để bạn kiểm tra trước khi ghi lên WFX. Các bước Mở đúng Costing trên WFX. Kiểm tra trạng thái Costing là Open. Mở module Catalog và chuyển sang khu Costing. Bấm Import . Chọn file Excel đã chỉnh sửa. Chờ ứng dụng đọc lại dữ liệu đang có trên WFX. Đọc bản xem trước những thay đổi sẽ được áp dụng. Mẹo Mẹo Bước Import chỉ kiểm tra và lập bản xem trước. Chưa có dữ liệu nào được ghi lên WFX ở bước này. Lưu ý Import chỉ dùng được khi Costing đang ở trạng thái Open. Nếu chưa có Costing hoặc trạng thái khác Open, bạn phải tự tạo hoặc mở Costing trên WFX trước. Gặp lỗi thì sao Hiện tượng Cách xử lý Nút Import không chạy Kiểm tra Costing hiện tại có đúng trạng thái Open hay không. File đã cũ so với WFX Tải file mới từ Costing hiện tại, sửa lại rồi Import lần nữa. File có ô không hợp lệ Bấm Kiểm tra file , sửa đúng ô được báo rồi Import lại.

### Áp dụng và lưu Costing

Xem trước rồi ghi những thay đổi đã kiểm tra lên WFX.

Dùng để làm gì Ghi bản thay đổi đã xem trước vào Costing trên WFX và kiểm tra lại kết quả sau khi lưu. Các bước Hoàn tất bước Import để có bản xem trước. Đọc số dòng thêm mới, cập nhật và xóa trong bản xem trước. Bấm Áp dụng & Save . Chờ ứng dụng điền dữ liệu và lưu Costing. Chờ dòng trạng thái xác nhận các giá trị đã được đọc lại. Mẹo Mẹo Bản xem trước có hiệu lực trong 15 phút. Nếu quá thời gian, Import file lại để ứng dụng kiểm tra Costing hiện tại. Mẹo Bấm nút dấu nhân trên bản xem trước nếu bạn muốn hủy và chọn file khác. Lưu ý Ô để trống nghĩa là giữ nguyên giá trị đang có. Ghi __CLEAR__ khi bạn thật sự muốn xóa giá trị. Cột Action để trống nghĩa là thêm mới hoặc cập nhật. Gặp lỗi thì sao Hiện tượng Cách xử lý Costing đã đổi sau khi Import Import lại file để tạo bản xem trước mới từ dữ liệu hiện tại. WFX hiện cảnh báo khi lưu Đọc nội dung cảnh báo trên WFX, sửa dữ liệu được nhắc rồi thực hiện lại. Không xác nhận được giá trị đã ghi Mở Costing trên WFX và kiểm tra trước khi quyết định thử lại.

### Color Mapping và Size Mapping

Nối màu và cỡ vật tư với màu và cỡ của Style.

Dùng để làm gì Nối từng màu hoặc cỡ của vật tư với màu hoặc cỡ tương ứng của Style trong file Costing. Các bước Mở file Excel đã tải từ Costing. Tìm cột Color Mapping hoặc Size Mapping của dòng vật tư. Chọn Material Color hoặc Material Size từ danh sách trong ô. Nhập liên kết theo dạng Vật tư => Style 1 | Style 2 . Lặp lại cho từng màu hoặc cỡ cần nối. Lưu file rồi bấm Import trong WFX Smart. Mẹo Mẹo Tên màu hoặc cỡ của Style được ghi trong phần chú thích của ô để bạn đối chiếu trước khi nhập. Mẹo Mỗi dòng bên trái dấu mũi tên là một màu hoặc cỡ vật tư. Bên phải là một hoặc nhiều giá trị Style, ngăn cách bằng dấu gạch đứng. Gặp lỗi thì sao Hiện tượng Cách xử lý Giá trị vật tư không có trong danh sách Mở Costing trên WFX và thêm màu hoặc cỡ cho đúng Article trước khi thử lại. Liên kết không được nhận Kiểm tra lại dấu mũi tên, dấu gạch đứng và tên giá trị có đúng như danh sách hay không.

### Xóa toàn bộ phụ thuộc

Xóa các liên kết màu và cỡ trong Costing đang mở.

Dùng để làm gì Xóa toàn bộ liên kết phụ thuộc màu và cỡ trong Costing đang mở rồi lưu lại một lần. Các bước Mở đúng Costing trên WFX. Kiểm tra trạng thái Costing là Open. Mở module Catalog và chuyển sang khu Costing. Bấm Clear All Dependency . Đọc câu hỏi xác nhận trên bảng điều khiển. Bấm nút xác nhận xóa. Chờ ứng dụng xóa các liên kết và lưu Costing. Mẹo Lưu ý Thao tác này xóa toàn bộ phụ thuộc trong Costing hiện tại. Chỉ xác nhận khi bạn đã kiểm tra đúng Style. Gặp lỗi thì sao Hiện tượng Cách xử lý Costing không ở trạng thái Open Mở một Costing đang Open rồi thực hiện lại. Style đã đổi trước khi xác nhận Dừng thao tác, mở lại đúng Style và bấm Clear All Dependency lần nữa. Không xóa được một liên kết Kiểm tra quyền sửa Costing của tài khoản và trạng thái WFX.

### Quét lại danh sách chi phí

Làm mới danh sách CM, Production và Indirect cho lần kế tiếp.

Dùng để làm gì Làm mới danh sách CM Costs, Production Costs và Indirect Costs khi WFX vừa có thêm hoặc đổi lựa chọn. Các bước Mở module Catalog. Chuyển sang khu Costing. Bật Quét lại chi phí trên cùng hàng với Clear All Dependency . Bấm Tải XLSX hoặc Import cho Costing kế tiếp. Chờ ứng dụng quét và lưu danh sách mới. Kiểm tra công tắc đã tự tắt sau khi hoàn tất. Mẹo Mẹo Công tắc mặc định tắt vì danh sách dùng chung được lưu trong bảy ngày. Mẹo Mỗi lần bật chỉ ép quét cho lần xuất hoặc nhập Costing kế tiếp rồi tự tắt. Gặp lỗi thì sao Hiện tượng Cách xử lý Công tắc chưa tự tắt Lần quét chưa hoàn tất. Chờ tác vụ xong và đọc dòng trạng thái. Danh sách mới chưa xuất hiện Bật lại công tắc rồi tải một file Costing mới.

## 5. Đơn hàng và chứng từ

Làm việc với OC, GDN Dispatch, Sample List và Sale ASN.

### Tìm OC

Mở OC List và tìm theo số OC hoặc Style.

Dùng để làm gì Mở OC List và tìm đúng OC bằng số OC hoặc Style. Các bước Mở module OC List. Bấm Mở List . Chọn OC No. hoặc Style trong dòng tìm kiếm. Nhập nội dung vào ô bên cạnh. Bấm Tìm . Chờ danh sách WFX hiển thị kết quả phù hợp. Mẹo Mẹo Bạn có thể nhập điều kiện rồi bấm Tìm ngay. Ứng dụng tự mở OC List nếu cần. Gặp lỗi thì sao Hiện tượng Cách xử lý Không có kết quả Kiểm tra lại kiểu tìm và nội dung đã nhập rồi thử lại. Danh sách chưa sẵn sàng Bấm Mở List , chờ WFX tải xong rồi bấm Tìm .

### Upload OC New

Kiểm tra file và tạo OC mới sau khi bạn xác nhận.

Dùng để làm gì Kiểm tra file OC mới trên máy, xem lại số liệu rồi tạo OC trên WFX sau khi bạn xác nhận. Các bước Mở module OC List. Bấm Tải file mẫu trong thẻ Upload OC New. Mở file và chỉ nhập dữ liệu trong sheet OC INPUT. Lưu file Excel. Bấm Chọn file trong thẻ Upload OC New. Đọc bảng Review trước khi Upload. Kiểm tra Buyer, Season, số PO, số Style, Sum of Units và số dòng. Bấm Xác nhận Upload để bắt đầu tạo OC trên WFX. Mẹo Mẹo Mỗi file chỉ được chứa một Buyer. Buyer và Factory có thể được nhập thêm nếu danh sách gợi ý chưa có giá trị mới. Lưu ý Ngày Buyer Order phải trước ngày Raw Material ETA. Ngày Raw Material ETA phải trước ngày Buyer Delivery và OC Delivery. Lưu ý Chọn file chỉ kiểm tra trên máy và hiện Review. Chỉ nút Xác nhận Upload mới bắt đầu thao tác trên WFX. Bấm Hủy thì không có dữ liệu nào được gửi đi. Gặp lỗi thì sao Hiện tượng Cách xử lý Báo file có nhiều Buyer Tách dữ liệu thành từng file, mỗi file chỉ giữ một Buyer. Báo sai ngày hoặc số lượng Mở đúng ô được báo, sửa giá trị rồi chọn lại file. WFX chưa sẵn sàng nhận file Giữ file đã sửa, kiểm tra phiên WFX rồi thực hiện Upload lại.

### Revise OC

Xuất báo cáo WFX, sửa file và cập nhật OC cũ.

Dùng để làm gì Xuất dữ liệu OC cũ từ báo cáo WFX, sửa trong Excel và gửi bản cập nhật trở lại WFX. Các bước Mở module OC List. Bấm Mở report trong thẻ Revise OC. Chọn tham số trên báo cáo WFX. Xuất báo cáo thành file Excel. Sửa dữ liệu cần thay đổi trong file. Giữ nguyên các cột nhận dạng của OC gốc. Bấm Chọn file trong thẻ Revise OC. Kiểm tra bảng Review rồi bấm Xác nhận Upload . Mẹo Mẹo Ứng dụng chỉ mở đúng báo cáo. Bạn tự chọn tham số và xuất Excel trên WFX để bảo đảm lấy đúng OC cần sửa. Lưu ý Không xóa hoặc đổi các cột nhận dạng OC gốc. WFX cần các cột này để biết OC nào sẽ được cập nhật. Gặp lỗi thì sao Hiện tượng Cách xử lý Báo cáo chưa mở Chờ khu Reporting & Analytic tải xong rồi bấm Mở report lại. File thiếu thông tin OC gốc Xuất lại báo cáo WFX và sửa trên file mới. Review không đúng OC Bấm Hủy , kiểm tra file rồi chọn lại đúng bản Revise.

### (GDN) Dispatch

Tạo Dispatch từ Invoice GRN sau thời gian chờ bắt buộc.

Dùng để làm gì Tạo (GDN) Dispatch từ Invoice GRN sau khi hàng thành phẩm đã nhập kho trên WFX. Các bước Hoàn tất (GRN) nhập kho hàng thành phẩm trên WFX. Chờ ít nhất 15 phút để dữ liệu được đồng bộ. Mở module (GDN) Dispatch trong WFX Smart. Nhập đúng Invoice GRN . Đánh dấu xác nhận GRN đã hoàn tất ít nhất 15 phút. Bấm Submit & tạo Dispatch . Theo dõi sáu bước ngay trong thẻ Tiến độ GDN . WFX Smart sẽ tự tải report, làm mới file Excel, Process Package và chọn giao dịch Pending mới nhất theo Processed ON . Các bước hiển thị lần lượt là: mở báo cáo, tải Excel, chuẩn hóa XLSX, mở EDI, Process Package, rồi tạo và xác nhận transaction. Lưu ý Chờ đủ 15 phút Không Submit ngay sau khi nhập GRN. Dữ liệu chưa đồng bộ có thể làm package lỗi hoặc không tạo được Dispatch. Gặp lỗi thì sao Gặp lỗi thì sao Nếu WFX báo invoice đã được import, hãy kiểm tra GDN hiện có trước khi chạy lại. Nếu thông báo nói chưa xác nhận được kết quả, không Submit lại. Bấm Mở EDI kiểm tra trong thẻ tiến độ, rồi kiểm tra giao dịch mới nhất để tránh tạo trùng.

### Sample List

Mở, lọc nhiều điều kiện và tạo Sample Order.

Dùng để làm gì Mở Sample List, lọc Sample Order theo một hoặc nhiều điều kiện và tạo Sample Order mới. Các bước Mở module Sample List. Bấm List để mở danh sách trên WFX. Nhập một hoặc nhiều điều kiện: Sample Order No., Style, Created By và Buyer. Bấm Tìm theo các điều kiện đã nhập . Nếu cần kiểm tra file, bấm Check File theo các điều kiện đã nhập để dùng đúng bộ điều kiện đó. Bấm New nếu bạn muốn mở màn hình tạo Sample Order mới. Mẹo Mẹo Bạn có thể bấm Tìm ngay. Ứng dụng tự mở danh sách nếu cần. Mẹo Bạn có thể sắp xếp cột theo cách làm việc riêng. Ứng dụng tự quét ngang để tìm Sample Order No., Style, Created By hoặc Buyer, xóa filter cũ trước khi tìm và kết hợp các điều kiện đã nhập. Gặp lỗi thì sao Hiện tượng Cách xử lý New chưa mở Chờ WFX tải xong rồi bấm New lại một lần. Không thấy Sample Kiểm tra các điều kiện đã nhập và cách viết nội dung trên WFX.

### Kiểm tra file Sample

Tìm Sample rồi xem các file có thể tải.

Dùng để làm gì Tìm một Sample Order và xem các file đính kèm có thể tải về. Các bước Mở module Sample List. Chọn kiểu tìm và nhập nội dung Sample. Bấm Check File . Chờ ứng dụng tìm Sample trước. Chọn một dòng nếu có nhiều kết quả. Bấm file cần tải trong danh sách kết quả. Mẹo Mẹo Nếu chỉ có một kết quả, ứng dụng tự mở Style và liệt kê file. Nếu có nhiều kết quả, bạn chọn đúng Sample rồi ứng dụng tiếp tục ngay từ danh sách đang mở. Mẹo Check File vẫn tìm được khi cột Sample No., Style hoặc Created By đã được kéo sang vị trí khác trong layout riêng của tài khoản. Gặp lỗi thì sao Hiện tượng Cách xử lý Không hỗ trợ xem file Mở Sample trên WFX và kiểm tra Style đã có file đính kèm hay chưa. Không mở được Sample đã chọn Tìm lại, chọn đúng dòng và bấm Check File lần nữa. Không có kết quả Kiểm tra Sample Order No., Style hoặc Created By đã nhập.

### Sale ASN

Tạo Sale ASN nhiều PO từ Excel, hoặc mở và tìm chứng từ cũ.

Dùng để làm gì Tìm Sale ASN cũ hoặc tạo Sale ASN mới từ một file Excel có nhiều PO. Các bước ### Tạo Sale ASN từ Excel Mở module Sale ASN . Chọn thẻ Tạo New . Bấm ↻ nếu danh sách Buyer chưa có hoặc cần cập nhật. Gõ vài chữ và chọn đúng Buyer trong danh sách. Bấm Tải form Excel nếu bạn chưa có form 19 cột. Điền dữ liệu theo thứ tự từ trên xuống dưới trong file. Bấm Chọn file & kiểm tra . Kiểm tra Invoice No., số PO, số Style và Destination trong phần review. Bấm Bắt đầu tạo Sale ASN . Khi ứng dụng báo cần chọn, chọn đúng dòng PO trên WFX rồi bấm Add & Continue . Đánh dấu xác nhận trong ứng dụng và bấm Tiếp tục dòng kế . Sau khi ứng dụng điền xong, kiểm tra toàn bộ Sale ASN trên WFX rồi tự bấm Save . Ứng dụng xử lý riêng từng bước Thêm PO , Order Details , Style Details và Shipping Info . Nếu một bước chưa hoàn tất, form WFX hiện tại được giữ nguyên: bấm Thử lại bước này sau khi đã xử lý nguyên nhân, hoặc bấm Bỏ qua ... để chuyển sang bước sau. Bỏ qua chỉ áp dụng cho ba bước điền dữ liệu; bước thêm PO không thể bỏ qua để tránh tạo chứng từ thiếu đơn hàng. Riêng trong Shipping Info , từng trường được xử lý độc lập. Nếu file thiếu dữ liệu hoặc WFX không có lựa chọn tương ứng (ví dụ Factory), ứng dụng bỏ qua đúng trường đó, tiếp tục điền các trường còn lại và liệt kê toàn bộ cảnh báo khi hoàn tất để bạn bổ sung thủ công trước khi Save. Lưu ý Ứng dụng không tự bấm Save. Bạn luôn có bước kiểm tra cuối trên WFX. Mẹo Nếu Sale ASN New đã mở sẵn hoặc đã chọn Buyer, ứng dụng refresh form trước khi bắt đầu để danh sách PO được tải mới. Ứng dụng dùng Add & Continue cho các PO trước. Với PO cuối, ứng dụng giữ dòng đang chọn rồi bấm OK để vừa thêm PO cuối vừa đóng Add Order Details. Quy tắc của file Excel Mỗi file chỉ chứa một Invoice No. và một FTY. Chỉ dòng có PO No mới được tính và xử lý; dòng tổng hoặc ghi chú không có PO sẽ được bỏ qua. Với mỗi dòng có PO, Style No , Destination và FTY là dữ liệu bắt buộc. SEASON , DESCRIPTION , HS CODE , Qty , Carton , NW , GW , CBM , FOB Price và Service Price có thể để trống. Nếu một ngày bị trống, ứng dụng lấy ngày có dữ liệu đầu tiên trong file. Nếu cả file không có ngày, ứng dụng dùng ngày hiện tại. Nếu Shipping Bill No. bị trống, ứng dụng dùng Invoice No. PO luôn được xử lý đúng thứ tự dòng trong file. Tìm Sale ASN và tải Documents Chọn thẻ Tra cứu & Invoice/PKL . Chọn Invoice No. hoặc Buyer Order Ref/OC . Nhập nội dung rồi bấm Tìm . Bấm Xuất Buyer Invoice + Packing List để lấy hai báo cáo trong cùng một file Excel. Lưu ý Report WFX có thể tải chậm. Ứng dụng chờ tối đa ba phút cho từng Packing List hoặc Buyer Invoice; không bấm xuất lại khi trạng thái vẫn đang chạy. Mẹo Khi gộp file, ứng dụng giữ nguyên tên sheet do WFX xuất. Chỉ khi hai report có sheet trùng tên, chúng được đổi theo dạng PKL 1083.26.PS.PSHK_7 và INVOICE 1083.26.PS.PSHK_7 để Excel chấp nhận. Nếu report có nhiều sheet, ứng dụng xếp xen kẽ Invoice 1 , PKL 1 , Invoice 2 , PKL 2 cho đến hết; Invoice luôn đứng trước PKL. Sau khi lưu thành công, Explorer sẽ tự mở và chọn đúng file vừa lưu. Khung, rich text, merged cell và định dạng gốc của cả Invoice lẫn PKL được giữ nguyên khi ghép. Gặp lỗi thì sao Hiện tượng Cách xử lý Không có Buyer để chọn Mở đúng phiên WFX rồi bấm ↻ để quét lại. File có lỗi Đọc vị trí ô hoặc dòng trong thông báo, sửa file rồi chọn lại. Có nhiều dòng PO giống nhau Chọn đúng Style hoặc Qty trên WFX, bấm Add & Continue , rồi tiếp tục trong ứng dụng. Không tìm thấy PO Kiểm tra PO No., Destination và Style trong file; bạn có thể tìm và chọn thủ công trên cửa sổ đang mở. Đã đóng cửa sổ Add PO Hủy phiên đang chuẩn bị và chạy lại từ file để tránh bỏ sót dòng. Order Details, Style Details hoặc cả tab Shipping Info bị lỗi Giữ nguyên form WFX, sửa trạng thái/ô đang vướng rồi bấm Thử lại bước này ; hoặc bấm Bỏ qua ... nếu muốn tự điền bước đó. Một field riêng lẻ trong Shipping Info sẽ tự được bỏ qua và báo lại cuối flow.

### Tải Documents Sale ASN

Tra cứu và ghép Packing List cùng Buyer Invoice thành một file Excel.

Dùng để làm gì Tải Packing List và Buyer Invoice của một Sale ASN rồi ghép thành một file Excel để gửi hoặc lưu trữ. Các bước Mở module Sale ASN. Chọn Invoice No. và nhập số Invoice. Bấm Tải Packing List + Buyer Invoice . Chờ ứng dụng mở đúng dòng Sale ASN và tải hai báo cáo. Chọn nơi lưu file Excel. Chờ thư mục chứa file tự mở. Mở file và kiểm tra hai sheet Packing List và Buyer Invoice. Mẹo Mẹo Tên file mặc định là Invoice No. thực tế đọc được trên WFX. Mẹo Hai sheet giữ nguyên cách trình bày của báo cáo nguồn. Mẹo Bạn có thể kéo cột Docs tới vị trí bất kỳ; ứng dụng sẽ tự quét ngang bảng để tìm cột, không yêu cầu đưa Docs về vị trí mặc định. Mẹo Nếu ô tìm kiếm để trống, hãy chọn đúng một dòng trên WFX. Ứng dụng đọc Invoice No. từ chính dòng đã chọn, kể cả khi cột này đang nằm ngoài màn hình. Gặp lỗi thì sao Hiện tượng Cách xử lý Không tìm thấy Invoice No. Kiểm tra số Invoice, xóa bộ lọc cũ trên WFX rồi thử lại. Có nhiều dòng phù hợp Chọn đúng một dòng trên WFX rồi bấm tải lại. Đã tìm thấy Invoice nhưng không có nút Docs Kiểm tra dòng đã chọn, trạng thái Sale ASN và quyền Documents của tài khoản trên WFX. Một báo cáo chưa sẵn sàng Chờ WFX tạo báo cáo xong rồi tải lại. Không ghép hoặc lưu được file Chọn một thư mục bạn có quyền ghi và bảo đảm file cũ không đang mở trong Excel.

## 6. Các danh sách khác

Mở và tìm dữ liệu trong các module nghiệp vụ còn lại.

### RMPO List

Tìm RMPO theo nhà cung cấp và số RMPO.

Dùng để làm gì Mở RMPO List hoặc lọc danh sách bằng nhà cung cấp và số RMPO cùng lúc. Các bước Mở module RMPO List. Bấm List nếu bạn chỉ muốn mở danh sách hiện tại. Nhập tên vào ô Supplier nếu bạn muốn lọc theo nhà cung cấp. Nhập số vào ô RMPO No. nếu bạn muốn lọc theo đơn. Bấm Tìm theo các điều kiện đã nhập . Chờ WFX hiển thị các dòng phù hợp với mọi điều kiện đã điền. Mẹo Mẹo Bạn có thể điền một hoặc cả hai điều kiện. Ô để trống không được dùng để lọc. Gặp lỗi thì sao Hiện tượng Cách xử lý Không thấy RMPO Xóa bớt một điều kiện rồi tìm lại để kiểm tra dữ liệu. Danh sách chưa mở Bấm List , chờ WFX tải xong rồi tìm lại.

### Indent List và User Indent

Tìm Indent theo bốn điều kiện kết hợp.

Dùng để làm gì Mở Indent List hoặc User Indent và tìm bằng nhiều thông tin trong một lần. Các bước Mở module Indent List hoặc User Indent. Bấm List nếu bạn chỉ muốn mở danh sách hiện tại. Nhập Supplier nếu cần lọc theo nhà cung cấp. Nhập Article nếu cần lọc theo nguyên phụ liệu. Nhập Indent No. nếu bạn biết số Indent. Nhập Style nếu cần lọc theo Style. Bấm Tìm theo các điều kiện đã nhập . Mẹo Mẹo Bạn không cần điền đủ bốn ô. Ứng dụng chỉ dùng những ô có nội dung. Gặp lỗi thì sao Hiện tượng Cách xử lý Không có kết quả Xóa bớt điều kiện quá chi tiết rồi tìm lại. Kết quả không đúng module Quay lại danh sách module và mở đúng Indent List hoặc User Indent.

### QA và yêu cầu tài chính

Mở, tìm Advance PR/Expense Invoice hoặc đi thẳng tới màn hình tạo mới.

Dùng để làm gì Mở danh sách hoặc tạo mới QA Request, Advance Payment Request và Expense Invoice. Các bước Mở QA List, Advance PR List hoặc Expense Inv List. Bấm List để mở danh sách tương ứng trên WFX. Bấm New nếu bạn muốn tạo yêu cầu hoặc hóa đơn mới. Khi tạo Advance Payment Request, ứng dụng chọn sẵn Advance Type = Against RMPO . Khi tạo Expense Invoice, ứng dụng chọn sẵn Invoice Type = General Expense . Trong Advance PR List, nhập một hoặc nhiều điều kiện Buyer Name, Supplier, Invoice Number và Order No. rồi bấm Tìm theo các điều kiện đã nhập . Trong Expense Inv List, nhập một hoặc nhiều điều kiện Supplier, Invoice No., Created By và Status rồi bấm Tìm theo các điều kiện đã nhập . Chờ WFX mở đúng màn hình rồi nhập dữ liệu nghiệp vụ. Mẹo Mẹo Nút New đi thẳng tới màn hình tạo mới. Bạn không cần bấm List trước. Mẹo Ứng dụng chỉ báo hoàn tất sau khi WFX xác nhận giá trị mặc định đã được chọn. Mẹo Với Advance PR và Expense Invoice, bạn có thể kết hợp nhiều điều kiện; để trống các ô không cần dùng. Gặp lỗi thì sao Hiện tượng Cách xử lý Không thấy module Bật Chế độ quản trị nếu module thuộc quyền quản trị, hoặc nhờ quản trị WFX kiểm tra quyền tài khoản. New chưa mở Chờ WFX tải xong rồi bấm New lại một lần. Search chưa chạy Nhập ít nhất một điều kiện, chờ danh sách WFX tải xong rồi thử lại.

### Buyer List

Mở danh sách và tìm Buyer đầu tiên phù hợp.

Dùng để làm gì Mở Buyers List hoặc tìm theo tên và mở Buyer đầu tiên phù hợp để chỉnh sửa. Các bước Mở module Buyer List. Bấm Buyers List nếu bạn muốn mở toàn bộ danh sách. Nhập tên hoặc một phần tên công ty vào ô Find Buyer. Bấm Tìm và mở Buyer đầu tiên . Chờ WFX mở màn hình chỉnh sửa của Buyer phù hợp đầu tiên. Mẹo Lưu ý Nếu nhiều Buyer có tên gần giống nhau, ứng dụng mở kết quả đầu tiên. Kiểm tra tên Buyer trên WFX trước khi sửa dữ liệu. Gặp lỗi thì sao Hiện tượng Cách xử lý Chưa tìm thấy Buyer Nhập phần tên ngắn hơn rồi tìm lại. Chưa mở được màn chỉnh sửa Bấm Buyers List , kiểm tra quyền sửa rồi thực hiện tìm lại.

### Supplier List

Mở Supplier theo Category hoặc tìm trên mọi Category.

Dùng để làm gì Mở Supplier Master theo một Category hoặc tìm tên nhà cung cấp trên tất cả Category. Các bước Mở module Supplier List. Bấm Mở List . Chọn Category nếu bạn biết nhóm của Supplier. Bấm Đổi Category · mở Master . Nhập tên hoặc một phần tên công ty nếu bạn muốn tìm rộng hơn. Bấm Tìm tất cả Category . Đọc tổng kết kết quả trên bảng điều khiển. Mẹo Mẹo Khi tìm tất cả Category, ứng dụng tiếp tục với nhóm kế tiếp nếu một nhóm gặp lỗi và báo rõ kết quả chỉ hoàn thành một phần. Gặp lỗi thì sao Hiện tượng Cách xử lý Master chưa sẵn sàng Chờ danh sách Supplier tải xong rồi bấm Đổi Category · mở Master lại. Chỉ có kết quả một phần Đọc Category bị lỗi trong thông báo, mở riêng Category đó rồi tìm lại. Không thấy Supplier Nhập phần tên ngắn hơn hoặc kiểm tra cách viết tên công ty.

### Company Setup và FOC

Mở thiết lập công ty và đổi nơi áp dụng FOC.

Dùng để làm gì Mở Company Setup và chuyển nơi áp dụng FOC giữa ASN và GRN. Các bước Mở module Company Setup. Bấm List nếu bạn muốn mở trang Company Setup hiện tại. Bấm Đổi FOC để bắt đầu chuyển lựa chọn. Chờ ứng dụng mở Miscellaneous Settings. Kiểm tra trạng thái FOC hiện tại trên bảng điều khiển. Chờ ứng dụng đổi sang lựa chọn còn lại và lưu. Mẹo Mẹo Bạn không cần mở Company Setup trước. Nút Đổi FOC tự mở đúng màn hình nếu WFX đang ở module khác. Gặp lỗi thì sao Hiện tượng Cách xử lý Chưa đọc được FOC hiện tại Chờ Miscellaneous Settings tải xong rồi bấm Đổi FOC lại. Chưa xác nhận lưu Mở Company Setup trên WFX và kiểm tra lựa chọn trước khi thử lại. Không mở được Company Setup Kiểm tra tài khoản có quyền vào module Admin này hay không.

### Supplier Invoice, Org Structure và System Coding

Lọc nhiều điều kiện và Cancel Supplier Invoice an toàn.

Dùng để làm gì Mở Supplier Inv List, lọc nhiều điều kiện hoặc Cancel Supplier Invoice an toàn. Bạn cũng có thể mở Org Structure và System Coding trên WFX. Các bước Mở Supplier Inv List trong nhóm Finance và bấm List . Nhập một hoặc nhiều điều kiện: Supplier, Invoice No., PO No. và ASN/GRN No. Bấm Tìm theo các điều kiện đã nhập . Để Cancel, nhập đúng Invoice No. vào phần Cancel Supplier Invoice rồi bấm nút Cancel. Nếu chỉ có một dòng, ứng dụng chọn dòng đó rồi bấm Delete khi Status là Save , hoặc Cancel khi Status là Confirm . Nếu có nhiều dòng, chọn đúng invoice trong danh sách của ứng dụng để tiếp tục; ứng dụng kiểm tra lại Status trước khi bấm nút trên WFX. Kiểm tra hộp xác nhận native của WFX trong Chrome trước khi xác nhận thao tác. Để mở Org Structure hoặc System Coding, bật Chế độ quản trị, mở thẻ module cần dùng rồi bấm Mở module trên WFX . Mẹo Mẹo Supplier Inv List nằm trong nhóm Finance. Org Structure và System Coding nằm trong nhóm Admin. Lưu ý Module chỉ hiện khi tài khoản được cấp quyền phù hợp trên WFX. Gặp lỗi thì sao Hiện tượng Cách xử lý Không thấy module Admin Mở Cài đặt, thẻ Giao diện và bật Chế độ quản trị. WFX báo không có quyền Nhờ quản trị WFX kiểm tra quyền của tài khoản hiện tại. Màn hình không đổi Chờ WFX tải xong rồi bấm Mở module trên WFX lại. Status không phải Save/Confirm Ứng dụng dừng, không bấm nút thay đổi hóa đơn. Kiểm tra lại invoice và Status trên WFX. Có nhiều invoice Chọn một dòng trong danh sách ứng dụng rồi Cancel; không thao tác trực tiếp từ kết quả mơ hồ.

## 7. Cài đặt, cập nhật và xử lý sự cố

Xem lịch sử, gửi góp ý, cập nhật và tra mã lỗi.

### Lịch sử hoạt động và log

Xem lại tác vụ gần đây và sao chép log kỹ thuật.

Dùng để làm gì Xem lại các tác vụ gần đây, đọc chi tiết kỹ thuật và sao chép thông tin khi cần nhờ hỗ trợ. Các bước Bấm biểu tượng danh sách ở góc trên bảng điều khiển. Chọn Tất cả tác vụ để xem công việc gần đây và thời gian thực hiện. Dùng hành động phù hợp như Kiểm tra trên WFX hoặc Thử lại an toàn nếu có. Chọn thẻ Log kỹ thuật để xem, bôi đen và sao chép thông tin chi tiết. Mẹo Mẹo Lịch sử tác vụ được giữ trong bảy ngày rồi tự xóa. Mẹo Các lượt duy trì phiên WFX thành công chạy âm thầm và không chiếm chỗ trong lịch sử. Chỉ thay đổi trạng thái hoặc lỗi cần chú ý mới được hiển thị. Mẹo Log chỉ tự cuộn khi bạn đang ở gần cuối và không bôi đen nội dung. Lưu ý Lịch sử không lưu nội dung bạn đã nhập vào ô tìm. Gặp lỗi thì sao Hiện tượng Cách xử lý Chưa có tác vụ trong lịch sử Thực hiện một thao tác rồi mở lại thẻ Tất cả tác vụ . Không sao chép được log Bôi đen đoạn cần dùng, nhấn Ctrl+C rồi dán vào nơi an toàn.

### Góp ý và báo lỗi

Gửi mô tả cùng chẩn đoán an toàn cho nhóm phát triển.

Dùng để làm gì Gửi góp ý hoặc mô tả lỗi cho nhóm phát triển ngay từ WFX Smart. Các bước Bấm biểu tượng hội thoại ở góc trên bảng điều khiển. Chọn Báo lỗi hoặc Góp ý tính năng trong dòng Loại nội dung. Nhập mô tả từ 5 đến 2.000 ký tự. Giữ hoặc bỏ chọn Đính kèm chẩn đoán an toàn . Đọc lại nội dung. Bấm Gửi . Mẹo Mẹo Mô tả rõ bạn đã bấm nút nào, thấy thông báo gì và vấn đề xảy ra lúc nào. Lưu ý Chẩn đoán an toàn chỉ gồm Windows, trạng thái Chrome và mã lỗi gần đây. Ứng dụng không tự chụp màn hình. Gặp lỗi thì sao Hiện tượng Cách xử lý Nút Gửi chưa bật Nhập ít nhất 5 ký tự và không vượt quá 2.000 ký tự. Gửi chưa thành công Sao chép nội dung, kiểm tra mạng rồi thử gửi lại.

### Cập nhật WFX Smart

Tải và cài bản mới mà không mất cài đặt cá nhân.

Dùng để làm gì Cập nhật WFX Smart lên bản mới để nhận tính năng và sửa lỗi mới nhất. Các bước Đọc dải thông báo có phiên bản mới trên bảng điều khiển. Bấm nút cập nhật trên dải thông báo. Chờ ứng dụng tải bản mới. Cho phép WFX Smart đóng để thay file. Chờ ứng dụng tự mở lại. Kiểm tra phiên bản ở góc trên bảng điều khiển. Mẹo Mẹo Cài đặt cá nhân và dữ liệu WFX Smart trên máy được giữ nguyên khi cập nhật. Mẹo Nếu bạn cài WFX Smart bằng Setup, ứng dụng sẽ nâng cấp bằng bộ cài để giữ shortcut và mục Uninstall. Nếu dùng bản portable, ứng dụng cập nhật trực tiếp các file trong thư mục portable. Lưu ý Hãy chờ tác vụ đang chạy hoàn tất trước khi bắt đầu cập nhật. Gặp lỗi thì sao Hiện tượng Cách xử lý Tải bản mới bị gián đoạn Kiểm tra mạng rồi bấm cập nhật lại. Ứng dụng chưa tự mở lại Mở WFX Smart từ Desktop hoặc Start Menu. Phiên bản vẫn chưa đổi Đóng hẳn WFX Smart, mở lại và kiểm tra dải cập nhật.

### Tra mã lỗi

Tìm ý nghĩa và cách xử lý cho mã kỹ thuật.

Dùng để làm gì Tra ý nghĩa của mã lỗi và xem cách xử lý được đề nghị cho từng trường hợp. Các bước Nhấn Ctrl+F trong cửa sổ hướng dẫn. Nhập mã lỗi đúng như dòng trạng thái hoặc lịch sử hiển thị. Mở kết quả Tra mã lỗi. Đọc cột Nghĩa là gì. Làm theo cột Cách xử lý. Bấm Xem hướng dẫn nếu mã có một mục liên quan chi tiết hơn.

### Quyền riêng tư

Biết thông tin nào được gửi khi ứng dụng báo lỗi.

Dùng để làm gì Biết rõ thông tin WFX Smart có thể gửi khi báo lỗi và những thông tin luôn được giữ riêng trên máy. Các bước Mở hộp Góp ý / Báo lỗi . Đọc dòng quyền riêng tư dưới lựa chọn chẩn đoán. Bỏ chọn Đính kèm chẩn đoán an toàn nếu bạn chỉ muốn gửi phần mô tả. Kiểm tra nội dung không có thông tin bí mật. Bấm Gửi khi bạn đồng ý với nội dung. Mẹo Mẹo Báo lỗi có thể gồm tên thao tác, mã lỗi, Run ID, User ID, Company, Division, phiên bản Windows và trạng thái kết nối. Lưu ý Ứng dụng không gửi mật khẩu, cookie, Session ID, nội dung tìm kiếm hoặc địa chỉ WFX đầy đủ. Ứng dụng cũng không tự chụp màn hình. Gặp lỗi thì sao Hiện tượng Cách xử lý Đã nhập thông tin bí mật trong mô tả Xóa thông tin đó trước khi bấm Gửi . Không muốn gửi chẩn đoán Bỏ chọn Đính kèm chẩn đoán an toàn .

### Giới hạn cần biết

Những trường hợp phụ thuộc Windows, quyền và tốc độ WFX.

Dùng để làm gì Nhận biết những trường hợp WFX Smart cần thêm thời gian hoặc phụ thuộc quyền Windows và trạng thái WFX. Các bước Kiểm tra hai đèn Chrome và WFX trước khi chạy tác vụ. Chờ WFX tải xong màn hình hiện tại. Bấm lại tác vụ một lần nếu thông báo hướng dẫn cho phép thử lại. Tra mã lỗi nếu vấn đề vẫn còn. Gửi báo lỗi kèm chẩn đoán an toàn khi bạn cần hỗ trợ. Mẹo Lưu ý Phím tắt có thể không nhận khi cửa sổ đang dùng chạy quyền quản trị cao hơn WFX Smart. Hãy bấm biểu tượng nổi hoặc biểu tượng cạnh đồng hồ Windows. Lưu ý Một số bước phụ thuộc tốc độ WFX. Danh sách lớn hoặc giờ cao điểm có thể cần chờ lâu hơn bình thường. Gặp lỗi thì sao Hiện tượng Cách xử lý Phím tắt không mở bảng điều khiển Dùng biểu tượng nổi hoặc biểu tượng WFX Smart cạnh đồng hồ. Tác vụ chờ lâu Đọc dòng trạng thái, chờ WFX ổn định và chỉ bấm Stop khi bạn muốn dừng an toàn.

## Bảng tra mã lỗi

| Mã | Nghĩa là gì | Cách xử lý |
|---|---|---|
| `BUYER_EDIT_NOT_CONFIRMED` | WFX chưa xác nhận màn Edit Buyer | Mở Buyer List, tìm lại Buyer rồi thử mở Edit. |
| `BUYER_EDIT_NOT_FOUND` | Không tìm thấy nút Edit của Buyer | Kiểm tra quyền chỉnh sửa Buyer và cấu trúc dòng kết quả. |
| `BUYER_SEARCH_FAILED` | Không thể tìm Buyer | Mở Log kỹ thuật và kiểm tra Buyer List đang hiển thị. |
| `BUYER_SEARCH_NOT_READY` | Buyer List chưa sẵn sàng | Chờ danh sách tải xong rồi thử tìm lại. |
| `CATALOG_DESTINATION_FAILED` | Không thể mở Costing/BOM | Mở lại style từ Catalog rồi thử lại. |
| `CATALOG_FILES_SCAN_FAILED` | Không thể đọc file đính kèm Catalog | Mở lại Article và kiểm tra tab file đính kèm. |
| `CATALOG_FILE_DOWNLOAD_FAILED` | Không thể tải file Catalog | Kiểm tra phiên WFX và quyền tải file rồi thử lại. |
| `CATALOG_FILE_SAVE_FAILED` | Không thể lưu file Catalog | Kiểm tra quyền ghi thư mục tải xuống và dung lượng ổ đĩa. |
| `CATALOG_FILE_TABS_NOT_FOUND` | Không tìm thấy tab file của Article | Mở lại Article rồi kiểm tra tab Images/Documents. |
| `CATALOG_FILE_URL_INVALID` | WFX trả về liên kết file không hợp lệ | Mở Log kỹ thuật và kiểm tra cấu hình file trên WFX. |
| `CATALOG_FOLDER_OPEN_FAILED` | Không thể mở thư mục Catalog | Quét lại cây folder rồi thử mở lại. |
| `CATALOG_FOLDER_OPEN_TIMEOUT` | WFX phản hồi chậm khi mở thư mục Catalog | Chờ Catalog tải xong rồi thử lại. |
| `CATALOG_FOLDER_SCAN_FAILED` | Không thể quét cây thư mục Catalog | Kiểm tra quyền Catalog của tài khoản rồi thử lại. |
| `CATALOG_FOLDER_SCAN_TIMEOUT` | WFX phản hồi chậm khi tải cây Catalog | Chờ cây Catalog hiển thị rồi quét lại. |
| `CATALOG_NOT_OPEN` | Catalog Master chưa sẵn sàng | Bấm Mở Catalog và chờ Master/Floating Filter hiển thị. |
| `CATALOG_SEARCH_FAILED` | Không thể tìm trong Catalog | Mở lại Catalog Master rồi thử tìm lại. |
| `CATEGORY_FAILED` | Không thể chọn Category | Mở lại module và kiểm tra quyền Category của tài khoản. |
| `CHROME_OPEN_FAILED` | Không thể mở trình duyệt làm việc | Kiểm tra cài đặt Chrome/Edge và quyền chạy ứng dụng. |
| `CODE_FILTER_FAILED` | Không thể thao tác Code Filter | Mở lại Catalog Master và Floating Filter rồi thử lại. |
| `CODE_FILTER_TIMEOUT` | Code Filter phản hồi quá chậm | Chờ grid Catalog ổn định rồi thử lại. |
| `COMPANY_FOC_FAILED` | Không thể đổi cấu hình FOC | Mở lại Company Setup và kiểm tra quyền chỉnh sửa. |
| `COMPANY_FOC_NOT_READY` | Màn cấu hình FOC chưa sẵn sàng | Chờ Miscellaneous Settings tải xong rồi thử lại. |
| `COMPANY_FOC_SAVE_NOT_CONFIRMED` | WFX chưa xác nhận lưu cấu hình FOC | Kiểm tra trạng thái checkbox và bấm Save lại trên WFX. |
| `COMPANY_LIST_OPEN_FAILED` | Không thể tự mở Company Setup | Kiểm tra quyền Company Setup và trạng thái menu WFX rồi thử lại. |
| `COSTING_ACTIVE_TAB_AMBIGUOUS` | Có nhiều cửa sổ Costing cùng hiển thị | Chỉ giữ cửa sổ cần xuất ở trạng thái đang chọn rồi thử lại. |
| `COSTING_ACTIVE_TAB_NOT_FOUND` | Tab đang chọn chưa ở màn Costing | Mở Style > Costing cần xuất và giữ đúng tab đó đang hiển thị. |
| `COSTING_APPLY_FAILED` | Không thể áp dụng Costing | Dry-run lại file và kiểm tra các field WFX trước khi Save. |
| `COSTING_CLEAR_DEPENDENCY_TARGET_CHANGED` | Các section Costing đã thay đổi khi đang Clear Dependency | Chờ Costing tải ổn định rồi bấm Clear All Dependency lại. |
| `COSTING_CLEAR_FAILED` | Không thể Clear toàn bộ Dependency | Giữ đúng CostSheet Open đang chọn, kiểm tra Log rồi thử lại. |
| `COSTING_CLEAR_UNSUPPORTED` | Phiên bản tự động hóa chưa hỗ trợ Clear All Dependency | Cập nhật WFX Smart lên bản mới nhất rồi thử lại. |
| `COSTING_CONTEXT_NOT_FOUND` | Không tìm thấy màn Costing | Mở lại đúng style trong Catalog rồi thử lại. |
| `COSTING_FIELD_APPLY_FAILED` | WFX không nhận một field Costing | Xem field/Article được báo trong Log kỹ thuật rồi kiểm tra lại file. |
| `COSTING_NEW_DIALOG_NOT_FOUND` | Không tìm thấy cửa sổ New Costing | Mở lại Costing của style chưa có Cost Sheet rồi thử lại. |
| `COSTING_NEW_FAILED` | Không thể tạo Costing mới | Kiểm tra quyền tạo Internal Cost Sheet và template FOB. |
| `COSTING_OPEN_NOT_LOADED` | Costing Open chưa tải xong dữ liệu | Chờ lưới Costing hiển thị đầy đủ rồi thử export/import lại. |
| `COSTING_SAVE_ALERT` | WFX từ chối Save Costing | Kiểm tra field bắt buộc trong thông báo WFX rồi dry-run lại. |
| `COSTING_SAVE_NOT_FOUND` | Không tìm thấy nút Save Costing | Mở lại Cost Sheet đang trạng thái Open rồi thử lại. |
| `COSTING_SCAN_FAILED` | Không thể đọc cấu trúc Costing | Mở Log kỹ thuật và kiểm tra Costing của style vẫn đang hiển thị. |
| `COSTING_STYLE_NOT_DETECTED` | Chưa đọc được Style Code từ tab Costing | Giữ phần thông tin Style trên tab Costing rồi thử export lại. |
| `COSTING_VERIFY_FAILED` | WFX chưa xác nhận dữ liệu Costing sau Save | Kiểm tra các field báo sai trong Log rồi dry-run lại. |
| `DIVISION_CHANGE_FAILED` | Không thể đổi Division | Kiểm tra menu Division và phiên đăng nhập rồi thử lại. |
| `DIVISION_CHANGE_NOT_CONFIRMED` | WFX chưa xác nhận đổi Division | Kiểm tra menu Division trên WFX rồi thử lại. |
| `DIVISION_DETECT_FAILED` | Không thể nhận diện Division hiện tại | Kiểm tra màn Home WFX và đăng nhập lại nếu cần. |
| `FILTER_RESULTS_NOT_READY` | Kết quả filter chưa ổn định | Chờ grid tải xong rồi thử tìm lại. |
| `FILTER_VALUE_NOT_CONFIRMED` | WFX chưa nhận giá trị filter | Mở lại Floating Filter rồi nhập lại. |
| `FLOATING_FILTER_NOT_READY` | Floating Filter chưa sẵn sàng | App chưa chuẩn bị được bộ lọc tự động; hãy chờ WFX rồi thử lại. |
| `GDN_DISPATCH_FAILED` | Không thể hoàn tất (GDN) Dispatch | Mở Log kỹ thuật, kiểm tra report và EDI Production Order rồi thử lại. |
| `GDN_DISPATCH_UNSUPPORTED` | Phiên bản chưa hỗ trợ (GDN) Dispatch | Cập nhật WFX Smart lên bản mới nhất rồi thử lại. |
| `GDN_EDI_NOT_READY` | EDI Production Order chưa sẵn sàng | Chờ WFX tải xong và kiểm tra quyền EDI Production Order. |
| `GDN_GRN_WAIT_CONFIRMATION_REQUIRED` | Chưa xác nhận thời gian chờ sau GRN | Chờ đủ 15 phút, đánh dấu xác nhận rồi Submit lại. |
| `GDN_INVOICE_INVALID` | Invoice GRN không hợp lệ | Kiểm tra lại nội dung Invoice GRN rồi Submit lại. |
| `GDN_INVOICE_REQUIRED` | Chưa nhập Invoice GRN | Nhập đúng Invoice GRN trước khi Submit. |
| `GDN_PACKAGE_PROCESS_FAILED` | WFX từ chối Process Package GDN | Kiểm tra lỗi hiển thị trên WFX; invoice có thể đã được import trước đó. |
| `GDN_PENDING_NOT_FOUND` | Không tìm thấy package GDN Pending mới | Kiểm tra Processed ON và Transaction Detail trên EDI Production Order. |
| `GDN_REPORT_DOWNLOAD_FAILED` | Không tải được report Buyer Dispatch | Kiểm tra phiên WFX, quyền report và thử lại sau khi WFX ổn định. |
| `GDN_REPORT_EMPTY` | Report Buyer Dispatch không có dữ liệu | Kiểm tra Invoice GRN và bảo đảm đã chờ đủ thời gian đồng bộ. |
| `GDN_REPORT_NOT_READY` | Report Buyer Dispatch chưa sẵn sàng | Chờ report load xong rồi Submit lại. |
| `GDN_TRANSACTION_FAILED` | WFX báo lỗi khi tạo GDN Dispatch | Xem lỗi WFX và Log kỹ thuật trước khi xử lý lại invoice. |
| `GDN_TRANSACTION_UNCONFIRMED` | Chưa xác nhận được kết quả GDN Dispatch | Không chạy lại ngay; kiểm tra transaction mới nhất trên WFX để tránh tạo trùng. |
| `GDN_WORKBOOK_RELOAD_FAILED` | Không reload được file XLSX GDN | Kiểm tra file report tải về và dung lượng thư mục tạm. |
| `LOGIN_FAILED` | Đăng nhập WFX thất bại | Kiểm tra tài khoản, Company và trạng thái trang đăng nhập. |
| `LOGIN_TIMEOUT` | WFX phản hồi quá chậm khi đăng nhập | Kiểm tra mạng và thử đăng nhập lại. |
| `MASTER_FAILED` | Không thể mở Master | Mở lại Category rồi thử Master lần nữa. |
| `MASTER_NOT_FOUND` | Không tìm thấy mục Master | Kiểm tra quyền truy cập và cây menu của Category. |
| `MODULE_ACCESS_CHECK_FAILED` | Không thể kiểm tra quyền module | Đăng nhập lại và tải lại danh sách quyền. |
| `MODULE_FAILED` | Không thể thao tác module WFX | Mở Log kỹ thuật để xem bước và lỗi gốc cuối cùng. |
| `MODULE_NOT_FOUND` | Không tìm thấy module trên menu WFX | Kiểm tra quyền tài khoản và menu module. |
| `MODULE_OPEN_NOT_CONFIRMED` | WFX chưa xác nhận mở module | Kiểm tra trang có đang tải hoặc có hộp thoại chờ xác nhận rồi thử lại. |
| `MODULE_SEARCH_FAILED` | Không thể thao tác ô tìm kiếm | Mở Log kỹ thuật để xem lỗi gốc rồi thử lại. |
| `MODULE_SEARCH_NOT_CONFIRMED` | WFX chưa xác nhận kết quả tìm kiếm | Kiểm tra màn List và thử lại sau khi grid tải xong. |
| `MODULE_SEARCH_NOT_READY` | Ô tìm kiếm của module chưa sẵn sàng | App đã thử tự mở List; hãy chờ WFX ổn định rồi thử tìm lại. |
| `OC_EDI_FAILED` | Không thể hoàn tất Upload OC trên EDI Buyer PO | Mở Log kỹ thuật, kiểm tra màn EDI Buyer PO và thử lại trước bước Create Transaction. |
| `OC_EDI_NOT_READY` | EDI Buyer PO chưa sẵn sàng | Chờ WFX tải xong, kiểm tra quyền EDI Buyer PO rồi thử upload lại. |
| `OC_REVISION_REPORT_FAILED` | Không thể mở report Revise OC | Mở Log kỹ thuật và kiểm tra quyền Reporting & Analytic của tài khoản. |
| `OC_REVISION_REPORT_NOT_READY` | Report Upload OC from OC_Sale chưa sẵn sàng | Chờ cây báo cáo tải xong rồi bấm Mở report lại. |
| `OC_UPLOAD_FILE_MISSING` | File Upload OC tạm không còn tồn tại | Chọn lại file OC trong app; nếu lỗi lặp lại, dùng Run ID để kiểm tra thư mục tạm. |
| `PANEL_ERROR` | Ứng dụng gặp lỗi khi chạy tác vụ | Mở Log kỹ thuật và dùng Run ID để đối chiếu. |
| `QUICK_SEARCH_FAILED` | Quick Search gặp lỗi | Mở module thủ công và thử lại từng bước. |
| `QUICK_SEARCH_TIMEOUT` | Quick Search phản hồi quá chậm | Chờ WFX tải xong rồi thử lại. |
| `RESULT_DETACHED` | Dòng kết quả đã thay đổi trước khi mở | Tìm lại để lấy dòng kết quả mới. |
| `SALE_ASN_BUYER_NOT_CONFIRMED` | WFX chưa xác nhận Buyer Sale ASN | Kiểm tra danh sách Buyer trên form New rồi thử lại. |
| `SALE_ASN_BUYER_NOT_FOUND` | Buyer không còn trong danh sách WFX | Quét lại Buyer rồi chọn đúng giá trị trước khi chạy. |
| `SALE_ASN_BUYER_REQUIRED` | Chưa chọn Buyer Sale ASN | Gõ và chọn đúng một Buyer trong danh sách trước khi chọn file. |
| `SALE_ASN_BUYER_SCAN_FAILED` | Không quét được Buyer Sale ASN | Mở lại Sale ASN New, chờ danh sách Buyer tải xong rồi quét lại. |
| `SALE_ASN_CREATE_FAILED` | Không thể hoàn tất Sale ASN từ Excel | Giữ màn hình WFX, mở Log kỹ thuật và kiểm tra bước cuối cùng. |
| `SALE_ASN_CREATE_REVIEW_EXPIRED` | Phiên kiểm tra Sale ASN đã hết hiệu lực | Chọn lại file Excel để tạo một review mới. |
| `SALE_ASN_CREATE_STAGE_INVALID` | Checkpoint tạo Sale ASN không hợp lệ | Chọn lại file Excel để bắt đầu một phiên tạo Sale ASN mới. |
| `SALE_ASN_CREATE_STAGE_NOT_SKIPPABLE` | Không thể bỏ qua bước Sale ASN hiện tại | Hoàn tất bước thêm PO hoặc thử lại bước hiện tại trên WFX. |
| `SALE_ASN_DOCS_NOT_AVAILABLE` | Invoice không có nút Docs hoặc tài khoản chưa được cấp quyền | Kiểm tra đúng dòng Sale ASN và quyền Documents trên WFX. |
| `SALE_ASN_DOCUMENTS_SAVE_FAILED` | Không lưu được file Documents Sale ASN | Chọn thư mục có quyền ghi, đóng file cũ nếu đang mở và thử lại. |
| `SALE_ASN_DOCUMENTS_UNSUPPORTED` | Chưa hỗ trợ tải Documents Sale ASN | Cập nhật WFX Smart lên bản mới nhất rồi thử lại. |
| `SALE_ASN_FIELD_NOT_EDITABLE` | Một ô Sale ASN không thể chỉnh sửa | Kiểm tra quyền sửa chứng từ và trạng thái form Sale ASN trên WFX. |
| `SALE_ASN_FIELD_VALUE_NOT_CONFIRMED` | WFX chưa giữ giá trị vừa nhập | Kiểm tra ô Order Details hoặc HS Code được báo trong Log kỹ thuật. |
| `SALE_ASN_FILE_EMPTY` | File Sale ASN chưa có dữ liệu | Điền ít nhất một dòng PO trong form rồi chọn lại file. |
| `SALE_ASN_FILE_FORMULA_ERROR` | File Sale ASN có công thức | Dán dữ liệu thành giá trị trong vùng nhập rồi chọn lại file. |
| `SALE_ASN_FILE_HEADERS_INVALID` | Header file Sale ASN không đúng | Tải form mới và giữ nguyên đủ 19 tên cột. |
| `SALE_ASN_FILE_INVALID` | File Sale ASN không hợp lệ | Lưu lại file bằng định dạng XLSX rồi chọn lại. |
| `SALE_ASN_FILE_NOT_FOUND` | Không tìm thấy file Sale ASN | Lưu và đóng file Excel rồi chọn lại từ vị trí hiện tại. |
| `SALE_ASN_FILE_TOO_LARGE` | File Sale ASN quá lớn | Xóa dữ liệu thừa để file nhỏ hơn 20 MB. |
| `SALE_ASN_FILE_TOO_MANY_ROWS` | File Sale ASN có quá nhiều dòng | Chia file thành các Invoice nhỏ hơn, tối đa 2.000 dòng mỗi file. |
| `SALE_ASN_FILE_TYPE_UNSUPPORTED` | Định dạng file Sale ASN không được hỗ trợ | Chỉ chọn file XLSX được tạo từ form Sale ASN. |
| `SALE_ASN_FILE_UNSAFE` | File Sale ASN chứa macro | Xóa macro hoặc tải form XLSX mới rồi nhập lại dữ liệu. |
| `SALE_ASN_FILE_VALIDATION_FAILED` | Dữ liệu Sale ASN chưa hợp lệ | Sửa các ô và dòng được ứng dụng báo rồi chọn lại file. |
| `SALE_ASN_INVOICE_NOT_FOUND` | Không tìm thấy Invoice No. trên Sale ASN List | Kiểm tra Invoice No., xóa bộ lọc cũ trên WFX rồi thử lại. |
| `SALE_ASN_MULTIPLE_RESULTS` | Có nhiều dòng Sale ASN phù hợp | Chọn đúng một dòng trên WFX rồi bấm tải lại. |
| `SALE_ASN_NEW_FAILED` | Không thể tạo màn Sale ASN mới | Mở lại Sale ASN và kiểm tra quyền tạo mới. |
| `SALE_ASN_NEW_NOT_READY` | Màn Sale ASN mới chưa sẵn sàng | Chờ form tải xong rồi thử lại. |
| `SALE_ASN_ORDER_GRID_NOT_READY` | Bảng Order Details chưa nhận đủ PO | Chờ WFX tải đủ các dòng PO rồi chạy lại. |
| `SALE_ASN_PO_POPUP_NOT_CLOSED` | Cửa sổ chọn PO chưa đóng | Bấm OK trong Add Order Details rồi chạy lại từ form New. |
| `SALE_ASN_PO_SEARCH_NOT_READY` | Ô tìm PO Sale ASN chưa sẵn sàng | Chờ cửa sổ Add Order Details tải xong rồi chạy lại. |
| `SALE_ASN_PO_SELECTION_NOT_CONFIRMED` | WFX chưa xác nhận dòng PO đã chọn | Chọn đúng dòng PO trên WFX rồi bấm Add & Continue. |
| `SALE_ASN_REPORT_DOWNLOAD_FAILED` | Không tải được report Sale ASN | Kiểm tra Packing List, Buyer Invoice và quyền export Excel. |
| `SALE_ASN_REPORT_MERGE_FAILED` | Không ghép được hai report Sale ASN | Mở Log kỹ thuật và dùng Run ID để kiểm tra file report. |
| `SALE_ASN_REPORT_NOT_READY` | Report Sale ASN chưa sẵn sàng | Chờ Documents/Report Viewer load xong rồi thử lại. |
| `SALE_ASN_SELECTION_REQUIRED` | Chưa xác định được dòng Sale ASN cần tải | Nhập Invoice No. chính xác hoặc chọn đúng một dòng trên WFX. |
| `SALE_ASN_SHIPPING_FIELD_FAILED` | Không điền được Shipping Info | Kiểm tra Destination, FTY và danh sách lựa chọn trên WFX. |
| `SALE_ASN_STYLE_HS_CODE_CONFLICT` | Một Style có nhiều HS Code trong file | Dùng cùng một HS Code cho các dòng của cùng Style. |
| `SALE_ASN_TABLE_MAPPING_FAILED` | Không ghép được dòng file với bảng Sale ASN | Kiểm tra PO No. và Style No., sau đó mở Log kỹ thuật. |
| `SALE_ASN_TEMPLATE_EXPORT_FAILED` | Không tạo được form Sale ASN | Chọn thư mục có quyền ghi và thử tải form lại. |
| `SAMPLE_FILES_UNSUPPORTED` | Phiên bản tự động hóa chưa hỗ trợ Check File Sample | Cập nhật WFX Smart lên bản mới nhất rồi thử lại. |
| `SAMPLE_FILE_OPEN_FAILED` | Không thể mở Style từ kết quả Sample | Tìm lại Sample và kiểm tra Style Code trên grid WFX. |
| `SAMPLE_FILE_SEARCH_FAILED` | Không thể đọc kết quả Sample để kiểm tra file | Mở lại Sample List, chờ grid ổn định rồi thử lại. |
| `SAMPLE_NEW_FAILED` | Không thể tạo màn Sample Order mới | Mở lại Sample List và kiểm tra quyền tạo mới. |
| `SAMPLE_NEW_NOT_READY` | Màn Sample Order mới chưa sẵn sàng | Chờ form tải xong rồi thử lại. |
| `SESSION_CHECK_FAILED` | Không thể kiểm tra phiên WFX | Kiểm tra trình duyệt làm việc và đăng nhập lại. |
| `STYLE_COPY_CHOICE_INVALID` | Lựa chọn Style nguồn không còn hợp lệ | Tìm lại và chọn đúng một Style nguồn trong bảng điều khiển. |
| `STYLE_COPY_NOT_FOUND` | Không tìm thấy Style nguồn | Kiểm tra Article Code hoặc Buyer Reference trong cột Style copy. |
| `STYLE_COPY_RESULT_DETACHED` | Kết quả Style nguồn đã thay đổi | Tìm lại Style nguồn rồi chọn lại đúng dòng. |
| `STYLE_FIELD_NOT_AVAILABLE` | Không điền được một trường Style | Giữ form Article đang mở, xem Log kỹ thuật và kiểm tra danh sách giá trị WFX. |
| `STYLE_FILE_EMPTY` | File Tạo Style chưa có dữ liệu | Điền ít nhất một dòng trong sheet Tạo Style rồi chọn lại file. |
| `STYLE_FILE_HEADERS_INVALID` | Header file Tạo Style không đúng | Tải form mới và giữ nguyên tên, thứ tự các cột. |
| `STYLE_FILE_INVALID` | File Tạo Style không hợp lệ | Lưu lại bằng định dạng XLSX rồi chọn lại. |
| `STYLE_FILE_TOO_LARGE` | File Tạo Style quá lớn | Giảm số dòng hoặc dữ liệu thừa để file nhỏ hơn 15 MB. |
| `STYLE_FILE_TYPE_UNSUPPORTED` | Định dạng file Tạo Style không được hỗ trợ | Chỉ chọn file XLSX được tạo từ form của WFX Smart. |
| `STYLE_FILE_UNSAFE` | File Tạo Style có nội dung không an toàn | Xóa macro hoặc tải form XLSX mới rồi nhập lại dữ liệu. |
| `STYLE_FILE_VALIDATION_FAILED` | Dữ liệu Tạo Style chưa hợp lệ | Sửa các dòng được báo trong bảng điều khiển rồi chọn lại file. |
| `STYLE_FORM_NOT_READY` | Form Article chưa sẵn sàng | Chờ WFX tải xong Group và màn New/Copy rồi thử lại. |
| `STYLE_GROUP_REQUIRED` | Chưa chọn Group Apparel | Quét lại Group và chọn đúng một Group trước khi Import. |
| `STYLE_GROUP_STALE` | Group Apparel đã thay đổi | Quét lại danh sách Group, chọn lại rồi Import file lần nữa. |
| `STYLE_IMPORT_EXPIRED` | Danh sách Tạo Style đã hết hạn | Chọn lại file để tạo danh sách chuẩn bị mới. |
| `STYLE_OPTIONS_SCAN_FAILED` | Chưa quét được dropdown Style | Giữ Chrome đăng nhập, chọn Group có quyền tạo Style rồi thử lại. |
| `STYLE_OPTIONS_SCAN_UNSUPPORTED` | Chưa hỗ trợ quét dropdown Style | Cập nhật WFX Smart lên bản mới nhất rồi thử lại. |
| `STYLE_PREPARE_FAILED` | Không chuẩn bị được form Style | Giữ màn hình WFX, xem Log kỹ thuật rồi thử lại dòng hiện tại. |
| `STYLE_PREPARE_UNSUPPORTED` | Phiên bản chưa hỗ trợ Tạo Style | Cập nhật WFX Smart lên bản mới nhất rồi thử lại. |
| `STYLE_REQUIRED_FIELD_MISSING` | Style New còn thiếu trường bắt buộc | Điền đủ các cột của dòng New rồi chọn lại file. |
| `STYLE_ROW_INVALID` | Không tìm thấy dòng Tạo Style | Chọn lại file để làm mới danh sách dòng. |
| `STYLE_TEMPLATE_SHEET_MISSING` | Thiếu sheet Tạo Style | Tải form mới và nhập dữ liệu vào đúng sheet Tạo Style. |
| `SUPPLIER_INVOICE_ACTION_NOT_READY` | Nút Delete/Cancel Supplier Invoice chưa sẵn sàng | Mở lại Supplier Inv List, tìm đúng invoice rồi thử lại. |
| `SUPPLIER_INVOICE_CANCEL_FAILED` | Không thể Cancel Supplier Invoice | Mở Log kỹ thuật, kiểm tra đúng invoice và quyền thao tác trên WFX. |
| `SUPPLIER_INVOICE_NOT_FOUND` | Không tìm thấy Supplier Invoice | Kiểm tra lại Invoice No. trước khi Cancel. |
| `SUPPLIER_INVOICE_NOT_READY` | Supplier Inv List chưa sẵn sàng | Chờ WFX tải xong rồi tìm lại Invoice No. cần Cancel. |
| `SUPPLIER_INVOICE_RESULT_EXPIRED` | Kết quả Supplier Invoice đã thay đổi | Tìm lại Invoice No. rồi chọn đúng một dòng để tiếp tục. |
| `SUPPLIER_INVOICE_STATUS_NOT_CANCELLABLE` | Status Supplier Invoice không thể xử lý | Chỉ tiếp tục khi Status là Save hoặc Confirm. |
| `SUPPLIER_MASTER_NOT_READY` | Supplier Master chưa sẵn sàng | Chờ Supplier List và Category tải xong rồi thử lại. |
| `SUPPLIER_OPEN_FAILED` | Không thể mở Supplier List | Kiểm tra quyền Supplier và menu WFX. |
| `SUPPLIER_SEARCH_FAILED` | Không thể tìm Supplier | Mở Log kỹ thuật và kiểm tra Category đang thao tác. |
| `SUPPLIER_SEARCH_NOT_READY` | Ô tìm Supplier chưa sẵn sàng | Chờ Supplier Master tải xong rồi thử lại. |
| `SUPPLIER_SEARCH_PARTIAL` | Chưa kiểm tra được toàn bộ Category Supplier | Thử lại để kiểm tra các Category bị lỗi hoặc mở từng Category riêng. |
