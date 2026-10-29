-- Đề xuất tính năng gửi từ website WFX Smart.
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY,                 -- FR-YYMMDD-XXXX
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  name TEXT NOT NULL,
  team TEXT NOT NULL DEFAULT '',
  module TEXT NOT NULL,
  priority TEXT NOT NULL,              -- nice | need | urgent
  title TEXT NOT NULL,
  wish TEXT NOT NULL,
  current_flow TEXT NOT NULL DEFAULT '',
  frequency TEXT NOT NULL DEFAULT '',  -- daily | weekly | monthly | rare | ''
  minutes INTEGER,
  images TEXT NOT NULL DEFAULT '[]',   -- JSON array khóa ảnh trong KV
  status TEXT NOT NULL DEFAULT 'new',  -- new | reviewing | planned | done | declined
  reply TEXT NOT NULL DEFAULT '',
  ip_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_requests_created ON requests (created_at);
CREATE INDEX IF NOT EXISTS idx_requests_ip ON requests (ip_hash, created_at);

-- "Tôi cũng cần": mỗi trình duyệt một phiếu cho mỗi đề xuất.
CREATE TABLE IF NOT EXISTS votes (
  request_id TEXT NOT NULL,
  voter TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (request_id, voter)
);
