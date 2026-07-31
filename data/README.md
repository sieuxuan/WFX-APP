# Article Library server feed

App mặc định kiểm tra:

`https://raw.githubusercontent.com/sieuxuan/WFX-APP/main/data/article-library-manifest.json`

Feed hiện dùng file `Article List.csv` ở thư mục gốc với bốn cột:

- `Article Code`
- `Article Name`
- `Buyer Reference`
- `Article Category`

Khi `Article List.csv` được cập nhật trên nhánh `main`, workflow
`Update Article Library` tự tạo checksum/version mới và publish manifest.
Nếu cần chạy thủ công:

```powershell
python scripts/build_article_library_manifest.py "Article List.csv" `
  --data-url "../Article%20List.csv"
```

Các máy user tự kiểm tra manifest mỗi giờ, chỉ tải CSV khi version đổi và giữ
cache gần nhất để dùng khi mất mạng. User không cần scan hoặc chọn file. Có thể
trỏ sang server HTTPS khác bằng biến môi trường
`WFX_ARTICLE_LIBRARY_MANIFEST_URL`.
