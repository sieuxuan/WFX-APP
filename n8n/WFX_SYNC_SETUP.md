# Cài WFX Smart PostgreSQL Sync API trên n8n

Flow gồm hai API:

- `POST /webhook/wfx-sync-publish`: máy Admin thay toàn bộ snapshot.
- `GET /webhook/wfx-sync-latest`: app người dùng lấy snapshot mới nhất.

Article có đúng ba cột nghiệp vụ: `article_code`, `article_name` và
`buyer_reference`. Dữ liệu Style dùng danh sách option chung và một danh sách
riêng cho quan hệ Product Group → Sub-category.

## 1. Tạo database/schema

Khuyến nghị tạo database riêng tên `wfx_shared`. Nếu n8n và PostgreSQL chạy bằng
Docker, database phải có thể truy cập từ container n8n; không dùng `localhost`
trừ khi PostgreSQL nằm trong chính container đó.

Mở pgAdmin/DBeaver/psql, kết nối vào database cần dùng và chạy toàn bộ file:

```text
n8n/wfx-sync-schema.sql
```

Script tạo schema `wfx_sync`, bốn bảng và hai PostgreSQL function. Mỗi lần
publish, function thay cả bundle trong một transaction. Nếu một bước lỗi, dữ
liệu cũ vẫn còn nguyên.

## 2. Import workflow

Trong n8n:

1. Chọn **Workflows → Import from File**.
2. Chọn `n8n/wfx-sync-api.json`.
3. Mở hai node PostgreSQL và chọn cùng credential PostgreSQL:
   - `Publish Bundle to PostgreSQL`
   - `Read Latest from PostgreSQL`
4. Test connection rồi Save.

## 3. Tạo hai API key

Không dùng chung key ghi và key đọc.

### Admin Publish

Mở node `Admin Publish`, tạo credential **Header Auth**:

```text
Name:  x-wfx-admin-key
Value: một chuỗi ngẫu nhiên dài ít nhất 32 ký tự
```

Chỉ máy Admin được giữ key này.

### User Get Latest

Mở node `User Get Latest`, tạo credential **Header Auth** khác:

```text
Name:  x-wfx-read-key
Value: một chuỗi ngẫu nhiên khác, dài ít nhất 32 ký tự
```

Key này chỉ có quyền gọi flow đọc. App desktop tuyệt đối không được chứa Admin
key hoặc thông tin đăng nhập PostgreSQL.

Sau đó Save và **Activate** workflow. Dùng Production URL, không dùng Test URL.

## 4. Payload Admin publish

```json
{
  "company_id": "77400",
  "division_key": "01",
  "version": "2026-08-01T12:00:00Z",
  "articles": [
    {
      "article_code": "SWN000123",
      "article_name": "Men Training Tee",
      "buyer_reference": "BUYER-TEE-01"
    }
  ],
  "style_options": [
    {
      "material_type": "",
      "field_name": "material_type",
      "option_value": "KNIT",
      "option_label": "KNIT"
    },
    {
      "material_type": "KNIT",
      "field_name": "product_group",
      "option_value": "TOP",
      "option_label": "Top"
    },
    {
      "material_type": "KNIT",
      "field_name": "buyer",
      "option_value": "10045",
      "option_label": "NIKE"
    },
    {
      "material_type": "KNIT",
      "field_name": "division",
      "option_value": "01",
      "option_label": "APPAREL"
    },
    {
      "material_type": "KNIT",
      "field_name": "color_card",
      "option_value": "20010",
      "option_label": "STANDARD COLOR"
    },
    {
      "material_type": "KNIT",
      "field_name": "size_range",
      "option_value": "30008",
      "option_label": "MEN SIZE"
    },
    {
      "material_type": "KNIT",
      "field_name": "season",
      "option_value": "SS27",
      "option_label": "SS27"
    }
  ],
  "style_subcategories": [
    {
      "material_type": "KNIT",
      "product_group": "TOP",
      "sub_category": "T-SHIRT"
    },
    {
      "material_type": "KNIT",
      "product_group": "TOP",
      "sub_category": "POLO"
    }
  ]
}
```

`option_value` nên là value thật của option WFX; `option_label` là chữ hiển thị
cho người dùng. App chọn theo value nhưng hiển thị label.

PowerShell test publish:

```powershell
$publishUrl = 'https://N8N-CUA-BAN/webhook/wfx-sync-publish'
$headers = @{ 'x-wfx-admin-key' = 'ADMIN_KEY_CUA_BAN' }
$payload = @{
    company_id = '77400'
    division_key = '01'
    version = (Get-Date).ToUniversalTime().ToString('o')
    articles = @(
        @{
            article_code = 'SWN000123'
            article_name = 'Men Training Tee'
            buyer_reference = 'BUYER-TEE-01'
        }
    )
    style_options = @(
        @{
            material_type = ''
            field_name = 'material_type'
            option_value = 'KNIT'
            option_label = 'KNIT'
        }
    )
    style_subcategories = @()
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
    -Method Post `
    -Uri $publishUrl `
    -Headers $headers `
    -ContentType 'application/json; charset=utf-8' `
    -Body $payload
```

Kết quả mong đợi:

```json
{
  "ok": true,
  "version": "2026-08-01T12:00:00Z",
  "published_at": "2026-08-01T12:00:01.000Z",
  "counts": {
    "articles": 1,
    "style_options": 1,
    "style_subcategories": 0
  }
}
```

## 5. Test User Get Latest

Lần đầu hoặc khi muốn buộc tải toàn bộ:

```powershell
$latestUrl = 'https://N8N-CUA-BAN/webhook/wfx-sync-latest'
$headers = @{ 'x-wfx-read-key' = 'READ_KEY_CUA_BAN' }

Invoke-RestMethod `
    -Method Get `
    -Uri ($latestUrl + '?company_id=77400&division_key=01') `
    -Headers $headers
```

Khi app đã có version, gửi thêm `client_version`:

```powershell
$version = [uri]::EscapeDataString('2026-08-01T12:00:00Z')
Invoke-RestMethod `
    -Method Get `
    -Uri ($latestUrl + '?company_id=77400&division_key=01&client_version=' + $version) `
    -Headers $headers
```

Nếu dữ liệu chưa đổi, server chỉ trả metadata:

```json
{
  "ok": true,
  "not_modified": true,
  "version": "2026-08-01T12:00:00Z",
  "published_at": "2026-08-01T12:00:01.000Z",
  "counts": {
    "articles": 1,
    "style_options": 1,
    "style_subcategories": 0
  }
}
```

Nếu version khác, response có thêm ba mảng `articles`, `style_options` và
`style_subcategories`.

## 6. Quy tắc cho app WFX Smart

- Auto sync: kiểm tra tối đa một lần sau 30 ngày.
- Sync Manual: gọi GET ngay, bỏ qua mốc 30 ngày.
- Chỉ thay cache local sau khi nhận `ok=true`, `not_modified=false` và parse đủ
  ba mảng thành công.
- Ghi cache bằng file tạm rồi replace để app không nhận file JSON dở dang.
- Nếu n8n/PostgreSQL offline, tiếp tục dùng cache local gần nhất.
- Admin scan chỉ đọc WFX; sau khi scan xong mới POST toàn bộ bundle.
- Không xóa cache local chỉ vì server trả lỗi hoặc không có mạng.

Nếu snapshot lớn vượt giới hạn request của n8n/reverse proxy, tăng giới hạn body
ở cả hai nơi. Không chia một bundle thành nhiều request trừ khi bổ sung cơ chế
staging/version riêng, vì việc chia nhỏ dễ làm người dùng tải phải dữ liệu nửa cũ
nửa mới.
