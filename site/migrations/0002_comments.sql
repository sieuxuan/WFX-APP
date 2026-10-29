-- Luồng trả lời theo từng đề xuất và quyền đánh dấu xong của người gửi.
-- owner_hash: SHA-256 của mã chủ đề xuất trả về cho trình duyệt đã gửi;
-- người gửi dùng mã đó để tự đánh dấu xong/mở lại mà không cần tài khoản.
ALTER TABLE requests ADD COLUMN owner_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE requests ADD COLUMN done_at TEXT;

CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  name TEXT NOT NULL,
  team TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'user',     -- user | owner | admin
  kind TEXT NOT NULL DEFAULT 'comment',  -- comment | done | reopen | status
  status TEXT NOT NULL DEFAULT '',       -- trạng thái mới khi kind là done/reopen/status
  body TEXT NOT NULL DEFAULT '',
  ip_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_comments_request ON comments (request_id, created_at);
CREATE INDEX IF NOT EXISTS idx_comments_ip ON comments (ip_hash, created_at);
