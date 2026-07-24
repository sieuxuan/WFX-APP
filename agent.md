# Nhiệm vụ cho AI sửa WFX Chrome Extension

## Phạm vi

Đọc toàn bộ `claude.md` trước khi sửa. Đối chiếu nguồn chuẩn trong `login.py`, sau đó
sửa:

- `wfx-tampermonkey.user.js`
- `chrome-extension/src/*`
- script build nếu cần
- build lại `chrome-extension/dist/WFX-Smart-Chrome-Extension`

Không sửa trực tiếp `dist` mà bỏ qua `src`. Không xóa thay đổi hiện có của người dùng.

## Lỗi phải xử lý

### 1. Master chỉ mở ở lần 4

Log 1.7.1 chứng minh click đầu làm document frame `left` reload. Bỏ cách thử lần lượt
`span -> img -> li`. Mỗi vòng phải resolve lại frame/document và click lại exact
actionable `Master`. Thành công chỉ khi **Catalog Grid mới** có URL
`wfxcataloglist` xuất hiện.

### 2. Filter chưa mở nhưng báo đã mở

Không coi một `Code Filter Input` tồn tại là đủ. Phải xác nhận:

- grid thuộc document mới;
- `.ag-root-wrapper` có thật;
- loading đã hết;
- có row thật hoặc no-rows overlay visible ổn định;
- `#showfloatingfilter` đã được click nếu input chưa visible;
- Code Filter visible, enabled và thuộc đúng grid.

Mode `prepare` chỉ được success sau toàn bộ các xác nhận trên.

### 3. UI có 1 nhưng script đếm 32

Không đếm toàn bộ DOM của AG Grid. Chỉ lấy node đang render trong viewport, bỏ loading
row/ghost/aria-hidden, rồi deduplicate Code không phân biệt hoa thường. Pinned columns
và virtual buffer không được làm tăng số kết quả.

### 4. Filter không hoạt động

Xóa cả hai filter cũ, dùng native setter tương đương `fill`, phát đúng chuỗi event
Angular cần, xác nhận `input.value`, chờ debounce/loading, rồi xác nhận tất cả giá trị
đang render chứa query. Hỗ trợ cả `code` và `buyer_reference`.

### 5. Hotkey

Giữ manifest command `toggle-panel` nhưng không đặt default `Ctrl+Alt+X`. Người dùng
gán phím ở `chrome://extensions/shortcuts`. Kiểm tra service worker chuyển command
tới đúng tab WFX và panel nhận được lệnh toggle.

## Quy tắc triển khai bắt buộc

1. Tạo snapshot/generation marker cho `left` và grid trước click Catalog.
2. Không chấp nhận frame/grid cũ.
3. Master retry theo tổng deadline, mỗi attempt chờ ngắn và reacquire document.
4. Không chọn candidate bằng global score giữa nhiều grid.
5. Mọi selector filter/result phải scope vào cùng `.ag-root-wrapper`.
6. Mọi success message phải đi sau assertion trạng thái UI.
7. Log có `runId`, stage, elapsed, frame generation và số raw/rendered/unique.
8. Log phải loại SessionID/LoginID/IP/password/cookie.
9. Giữ popup tracking để mở Article, Costsheet và BOM.
10. Không làm hỏng panel/login/settings/hotkey đã có.

## Thứ tự làm việc

1. Đọc `claude.md`, `login.py`, log đính kèm và code v1.7.1 hiện tại.
2. Viết lại state machine Catalog; không chắp thêm retry vào logic candidate cũ.
3. Tách helper:
   - snapshot/is-new-document
   - resolve-left
   - exact-master
   - resolve-new-grid
   - grid-settled
   - ensure-floating-filter
   - fill-and-confirm-filter
   - read-rendered-unique-results
4. Chạy syntax/lint hiện có.
5. Build extension từ `src`.
6. So sánh hash/nội dung `main.js` build với userscript nguồn.
7. Test thủ công trên WFX bằng checklist bên dưới.

## Checklist test

| Test | Kết quả bắt buộc |
|---|---|
| Prepare Apparel khi left reload một lần | Reacquire và mở Master, không click IMG/LI |
| Grid đang loading, row=0 | Chưa được báo success |
| Grid thực sự không có dữ liệu | Chỉ ready khi no-rows overlay visible ổn định |
| Floating Filter đang đóng | Có log click nút và input visible sau click |
| Code exact, UI 1 row, DOM có clone | `unique_count=1`, mở đúng Article |
| Code gần đúng nhiều row | Không tự mở |
| Buyer Reference | Filter đúng cột, Code trả về deduplicate |
| Row đổi lúc click | Trả `RESULT_DETACHED`, không click nhầm |
| Popup bị chặn | Báo `ARTICLE_OPEN_NOT_CONFIRMED` |
| Costsheet/BOM | Chờ đúng `ArticleTop`, mở đúng tab |
| Chrome shortcut | `Ctrl+Alt+X` gán ở shortcuts toggle được panel |

## Definition of done

- Không còn false-success ở Master/Grid/Floating Filter.
- Số kết quả trùng với số unique Code thực người dùng thấy.
- Code và Buyer Reference filter đều hoạt động.
- Bản unpacked extension load được, manifest hợp lệ.
- Build ZIP phiên bản mới được tạo từ `src`.
- Changelog ghi rõ nguyên nhân gốc, không chỉ ghi “thêm retry”.
- Log test cuối cùng đủ để xác minh từng state nhưng không chứa dữ liệu nhạy cảm.

