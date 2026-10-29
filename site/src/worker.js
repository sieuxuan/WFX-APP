// Worker của website WFX Smart: phục vụ trang tĩnh trong public/ và API cho
// trang Tải về (bản phát hành mới nhất trên GitHub) cùng Đề xuất tính năng
// (D1 lưu đề xuất và luồng trả lời, KV lưu ảnh). Không ai cần tài khoản: trả
// lời ký bằng tên + bộ phận; người gửi tự đánh dấu xong bằng mã chủ đề xuất
// trình duyệt nhận lúc gửi; đổi trạng thái khác và xóa cần ADMIN_KEY.

const PRIORITIES = new Set(["nice", "need", "urgent"]);
const FREQUENCIES = new Set(["", "daily", "weekly", "monthly", "rare"]);
const STATUSES = new Set(["new", "reviewing", "planned", "done", "declined"]);

const MAX_IMAGES = 6;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_REQUESTS_PER_HOUR = 8;
const RELEASE_CACHE_SECONDS = 600;
const SETUP_ASSET = /^WFX-Smart-Setup-v(\d+\.\d+\.\d+)\.exe$/i;
const PORTABLE_ASSET = /^WFX-Smart-v(\d+\.\d+\.\d+)-win64\.zip$/i;

const MAX_COMMENTS_PER_HOUR = 40;

const LIMITS = { name: 80, team: 60, title: 140, wish: 3000, current_flow: 3000, comment: 2000 };
const ID_PATTERN = "(FR-[0-9]{6}-[A-Z0-9]{4})";

let moduleNames = null;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      return await route(request, env, ctx, url);
    } catch (error) {
      console.error("unhandled", url.pathname, error && error.stack ? error.stack : error);
      return fail(500, "Máy chủ đang gặp lỗi. Thử lại sau ít phút.");
    }
  },
};

async function route(request, env, ctx, url) {
  const path = url.pathname;
  const method = request.method;

  if (path === "/api/release" && method === "GET") return getRelease(env, ctx);
  if (path === "/api/requests" && method === "GET") return listRequests(env);
  if (path === "/api/requests" && method === "POST") return createRequest(request, env);

  let match = path.match(new RegExp(`^/api/requests/${ID_PATTERN}/vote$`));
  if (match && method === "POST") return vote(request, env, match[1]);

  match = path.match(new RegExp(`^/api/requests/${ID_PATTERN}/comments$`));
  if (match && method === "POST") return addComment(request, env, match[1]);

  match = path.match(/^\/api\/images\/([a-z0-9]{32})$/);
  if (match && method === "GET") return getImage(env, match[1]);

  if (path.startsWith("/api/admin/")) {
    if (!(await isAdmin(request, env))) return fail(401, "Mã quản trị không đúng.");
    if (path === "/api/admin/check" && method === "GET") return json({ ok: true });
    match = path.match(new RegExp(`^/api/admin/requests/${ID_PATTERN}$`));
    if (match && method === "DELETE") return deleteRequest(env, match[1]);
  }

  return fail(404, "Không tìm thấy địa chỉ này.");
}

/* ---------------- Tải về ---------------- */

async function getRelease(env, ctx) {
  const cache = caches.default;
  const cacheKey = new Request("https://wfx-smart.internal/release");
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const repo = env.GITHUB_REPOSITORY || "sieuxuan/WFX-APP";
  const upstream = await fetch(`https://api.github.com/repos/${repo}/releases?per_page=10`, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "wfx-smart-site",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!upstream.ok) {
    console.error("github release", upstream.status);
    return fail(502, "Chưa đọc được bản phát hành từ GitHub. Thử lại sau ít phút.");
  }
  const releases = (await upstream.json()).filter((r) => !r.draft && !r.prerelease);
  const pick = (release, pattern) => {
    const asset = (release.assets || []).find((a) => pattern.test(a.name));
    return asset ? { name: asset.name, url: asset.browser_download_url, size: asset.size } : null;
  };
  const latest = releases.find((r) => pick(r, SETUP_ASSET) || pick(r, PORTABLE_ASSET));
  if (!latest) return fail(404, "Chưa có bản phát hành nào.");

  const body = {
    ok: true,
    version: String(latest.tag_name || "").replace(/^v/i, ""),
    published_at: latest.published_at,
    html_url: latest.html_url,
    setup: pick(latest, SETUP_ASSET),
    portable: pick(latest, PORTABLE_ASSET),
    previous: releases
      .filter((r) => r !== latest)
      .slice(0, 5)
      .map((r) => ({
        version: String(r.tag_name || "").replace(/^v/i, ""),
        published_at: r.published_at,
        html_url: r.html_url,
      })),
  };
  const response = json(body, { "Cache-Control": `public, max-age=${RELEASE_CACHE_SECONDS}` });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

/* ---------------- Đề xuất ---------------- */

async function listRequests(env) {
  const [requestRows, commentRows] = await env.DB.batch([
    env.DB.prepare(
      `SELECT r.id, r.created_at, r.updated_at, r.done_at, r.name, r.team, r.module, r.priority,
              r.title, r.wish, r.current_flow, r.frequency, r.minutes, r.images, r.status,
              (SELECT COUNT(*) FROM votes v WHERE v.request_id = r.id) AS votes
         FROM requests r
        ORDER BY r.created_at DESC
        LIMIT 1000`
    ),
    env.DB.prepare(
      `SELECT id, request_id, created_at, name, team, role, kind, status, body
         FROM comments
        ORDER BY created_at ASC, id ASC`
    ),
  ]);
  const thread = new Map();
  for (const c of commentRows.results) {
    if (!thread.has(c.request_id)) thread.set(c.request_id, []);
    const { request_id: _, ...comment } = c;
    thread.get(c.request_id).push(comment);
  }
  const requests = requestRows.results.map((row) => ({
    ...row,
    images: parseImages(row.images),
    comments: thread.get(row.id) || [],
  }));
  return json({ ok: true, requests }, { "Cache-Control": "no-store" });
}

async function createRequest(request, env) {
  let form;
  try {
    form = await request.formData();
  } catch {
    return fail(400, "Dữ liệu gửi lên không hợp lệ.");
  }
  // Ô ẩn chống bot: người thật không bao giờ điền.
  if (text(form, "website")) return json({ ok: true, id: null });

  const fields = {
    name: text(form, "name"),
    team: text(form, "team"),
    module: text(form, "module"),
    priority: text(form, "priority") || "need",
    title: text(form, "title"),
    wish: text(form, "wish"),
    current_flow: text(form, "current_flow"),
    frequency: text(form, "frequency"),
  };
  const minutesRaw = text(form, "minutes");
  const minutes = minutesRaw ? Number.parseInt(minutesRaw, 10) : null;

  if (!fields.name) return fail(400, "Hãy nhập tên của bạn.");
  if (!fields.title) return fail(400, "Hãy đặt tên cho tính năng bạn cần.");
  if (fields.wish.length < 10) return fail(400, "Hãy mô tả mong muốn ít nhất 10 ký tự.");
  for (const [key, max] of Object.entries(LIMITS)) {
    if (fields[key] && fields[key].length > max) return fail(400, `Nội dung quá dài (tối đa ${max} ký tự).`);
  }
  if (!PRIORITIES.has(fields.priority)) return fail(400, "Mức độ cần thiết không hợp lệ.");
  if (!FREQUENCIES.has(fields.frequency)) return fail(400, "Tần suất không hợp lệ.");
  if (minutes !== null && (!Number.isInteger(minutes) || minutes < 0 || minutes > 600)) {
    return fail(400, "Số phút mỗi lần phải từ 0 tới 600.");
  }
  const modules = await loadModuleNames(env, request.url);
  if (!modules.has(fields.module)) return fail(400, "Hãy chọn module trong danh sách.");

  const files = form.getAll("images").filter((f) => f && typeof f === "object" && f.size > 0);
  if (files.length > MAX_IMAGES) return fail(400, `Chỉ đính kèm tối đa ${MAX_IMAGES} ảnh.`);
  const images = [];
  for (const file of files) {
    if (file.size > MAX_IMAGE_BYTES) return fail(400, `Ảnh "${file.name}" lớn hơn 8 MB.`);
    const bytes = new Uint8Array(await file.arrayBuffer());
    const type = sniffImage(bytes);
    if (!type) return fail(400, `"${file.name}" không phải ảnh PNG, JPG, GIF hoặc WebP.`);
    images.push({ bytes, type });
  }

  const ipHash = await hashIp(request, env);
  const since = new Date(Date.now() - 3600_000).toISOString();
  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM requests WHERE ip_hash = ? AND created_at > ?"
  ).bind(ipHash, since).first();
  if (recent && recent.n >= MAX_REQUESTS_PER_HOUR) {
    return fail(429, "Bạn đã gửi nhiều đề xuất trong một giờ. Thử lại sau nhé.");
  }

  const keys = [];
  for (const image of images) {
    const key = randomKey();
    await env.IMAGES.put(key, image.bytes, { metadata: { type: image.type } });
    keys.push(key);
  }

  const now = new Date().toISOString();
  const ownerToken = randomToken();
  const ownerHash = await hexDigest(ownerToken);
  for (let attempt = 0; attempt < 4; attempt++) {
    const id = requestId();
    try {
      await env.DB.prepare(
        `INSERT INTO requests (id, created_at, updated_at, name, team, module, priority, title,
                               wish, current_flow, frequency, minutes, images, ip_hash, owner_hash)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        id, now, now, fields.name, fields.team, fields.module, fields.priority, fields.title,
        fields.wish, fields.current_flow, fields.frequency, minutes, JSON.stringify(keys), ipHash,
        ownerHash
      ).run();
      return json({ ok: true, id, owner_token: ownerToken }, {}, 201);
    } catch (error) {
      if (!String(error).includes("UNIQUE")) {
        await Promise.all(keys.map((k) => env.IMAGES.delete(k)));
        throw error;
      }
    }
  }
  await Promise.all(keys.map((k) => env.IMAGES.delete(k)));
  return fail(500, "Chưa tạo được mã đề xuất. Bấm Gửi lại.");
}

async function vote(request, env, id) {
  let body;
  try {
    body = await request.json();
  } catch {
    return fail(400, "Dữ liệu không hợp lệ.");
  }
  const voter = String(body.voter || "");
  if (!/^[a-z0-9-]{16,64}$/i.test(voter)) return fail(400, "Thiếu mã trình duyệt.");
  const exists = await env.DB.prepare("SELECT 1 FROM requests WHERE id = ?").bind(id).first();
  if (!exists) return fail(404, "Đề xuất không còn tồn tại.");

  if (body.on === false) {
    await env.DB.prepare("DELETE FROM votes WHERE request_id = ? AND voter = ?").bind(id, voter).run();
  } else {
    await env.DB.prepare(
      "INSERT OR IGNORE INTO votes (request_id, voter, created_at) VALUES (?, ?, ?)"
    ).bind(id, voter, new Date().toISOString()).run();
  }
  const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM votes WHERE request_id = ?").bind(id).first();
  return json({ ok: true, votes: row ? row.n : 0 });
}

async function getImage(env, key) {
  const { value, metadata } = await env.IMAGES.getWithMetadata(key, { type: "arrayBuffer" });
  if (!value) return new Response("Không tìm thấy ảnh.", { status: 404 });
  return new Response(value, {
    headers: {
      "Content-Type": (metadata && metadata.type) || "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
      "Content-Security-Policy": "default-src 'none'; sandbox",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

// Một lượt trả lời trong đề xuất. Ai cũng trả lời được bằng tên + bộ phận đã
// nhập ở form; chỉ quản trị (ADMIN_KEY) hoặc chính người gửi (mã chủ đề xuất)
// mới đánh dấu xong / mở lại, và chỉ quản trị đổi sang trạng thái khác.
async function addComment(request, env, id) {
  let body;
  try {
    body = await request.json();
  } catch {
    return fail(400, "Dữ liệu không hợp lệ.");
  }
  const name = clean(body.name);
  const team = clean(body.team);
  const message = clean(body.body);
  const action = String(body.action || "comment");
  if (!name) return fail(400, "Hãy nhập tên của bạn.");
  if (name.length > LIMITS.name || team.length > LIMITS.team) return fail(400, "Tên hoặc bộ phận quá dài.");
  if (message.length > LIMITS.comment) return fail(400, `Trả lời tối đa ${LIMITS.comment} ký tự.`);

  const row = await env.DB.prepare("SELECT status, owner_hash FROM requests WHERE id = ?").bind(id).first();
  if (!row) return fail(404, "Đề xuất không còn tồn tại.");

  const admin = await isAdmin(request, env);
  const owner = !admin && row.owner_hash && body.owner_token
    ? await sameSecret(row.owner_hash, await hexDigest(String(body.owner_token)))
    : false;
  const role = admin ? "admin" : owner ? "owner" : "user";

  let status = "";
  if (action === "comment") {
    if (!message) return fail(400, "Hãy nhập nội dung trả lời.");
  } else if (action === "done" || action === "reopen") {
    if (!admin && !owner) return fail(403, "Chỉ người gửi đề xuất hoặc quản trị mới đánh dấu được.");
    status = action === "done" ? "done" : "reviewing";
    if (row.status === status) return fail(409, action === "done" ? "Đề xuất đã ở trạng thái xong." : "Đề xuất đang mở.");
  } else if (action === "status") {
    if (!admin) return fail(403, "Chỉ quản trị mới đổi trạng thái.");
    status = String(body.status || "");
    if (!STATUSES.has(status)) return fail(400, "Trạng thái không hợp lệ.");
  } else {
    return fail(400, "Thao tác không hợp lệ.");
  }

  const ipHash = await hashIp(request, env);
  if (!admin) {
    const since = new Date(Date.now() - 3600_000).toISOString();
    const recent = await env.DB.prepare(
      "SELECT COUNT(*) AS n FROM comments WHERE ip_hash = ? AND created_at > ?"
    ).bind(ipHash, since).first();
    if (recent && recent.n >= MAX_COMMENTS_PER_HOUR) {
      return fail(429, "Bạn trả lời hơi nhiều trong một giờ. Thử lại sau nhé.");
    }
  }

  const now = new Date().toISOString();
  const statements = [
    env.DB.prepare(
      `INSERT INTO comments (request_id, created_at, name, team, role, kind, status, body, ip_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(id, now, name, team, role, action, status, message, ipHash),
  ];
  if (status) {
    statements.push(env.DB.prepare(
      "UPDATE requests SET status = ?, updated_at = ?, done_at = ? WHERE id = ?"
    ).bind(status, now, status === "done" ? now : null, id));
  } else {
    statements.push(env.DB.prepare("UPDATE requests SET updated_at = ? WHERE id = ?").bind(now, id));
  }
  await env.DB.batch(statements);
  return json({ ok: true, role, status: status || row.status }, {}, 201);
}

async function deleteRequest(env, id) {
  const row = await env.DB.prepare("SELECT images FROM requests WHERE id = ?").bind(id).first();
  if (!row) return fail(404, "Đề xuất không còn tồn tại.");
  await env.DB.batch([
    env.DB.prepare("DELETE FROM comments WHERE request_id = ?").bind(id),
    env.DB.prepare("DELETE FROM votes WHERE request_id = ?").bind(id),
    env.DB.prepare("DELETE FROM requests WHERE id = ?").bind(id),
  ]);
  await Promise.all(parseImages(row.images).map((key) => env.IMAGES.delete(key)));
  return json({ ok: true });
}

/* ---------------- Tiện ích ---------------- */

async function loadModuleNames(env, requestUrl) {
  if (moduleNames) return moduleNames;
  const response = await env.ASSETS.fetch(new URL("/content/site.json", requestUrl));
  const content = await response.json();
  moduleNames = new Set(content.module_groups.flatMap((g) => g.modules.map((m) => m.name)));
  return moduleNames;
}

async function isAdmin(request, env) {
  const expected = env.ADMIN_KEY || "";
  const header = request.headers.get("Authorization") || "";
  const given = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!expected || !given) return false;
  const [a, b] = await Promise.all([digest(expected), digest(given)]);
  return crypto.subtle.timingSafeEqual(a, b);
}

async function sameSecret(storedHex, givenHex) {
  const [a, b] = await Promise.all([digest(storedHex), digest(givenHex)]);
  return crypto.subtle.timingSafeEqual(a, b);
}

async function hexDigest(value) {
  const bytes = new Uint8Array(await digest(value));
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function randomToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function clean(value) {
  return String(value == null ? "" : value).normalize("NFC").trim();
}

async function hashIp(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "local";
  const bytes = new Uint8Array(await digest(`${ip}|${env.ADMIN_KEY || "wfx-smart"}`));
  return [...bytes.slice(0, 16)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function digest(value) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
}

function sniffImage(b) {
  if (b.length < 12) return null;
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x38) return "image/gif";
  const riff = String.fromCharCode(...b.slice(0, 4));
  const webp = String.fromCharCode(...b.slice(8, 12));
  if (riff === "RIFF" && webp === "WEBP") return "image/webp";
  return null;
}

function requestId() {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Ho_Chi_Minh", year: "2-digit", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const get = (type) => parts.find((p) => p.type === type).value;
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const random = crypto.getRandomValues(new Uint8Array(4));
  const suffix = [...random].map((n) => alphabet[n % alphabet.length]).join("");
  return `FR-${get("year")}${get("month")}${get("day")}-${suffix}`;
}

function randomKey() {
  return [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function parseImages(raw) {
  try {
    const list = JSON.parse(raw || "[]");
    return Array.isArray(list) ? list.filter((k) => /^[a-z0-9]{32}$/.test(k)) : [];
  } catch {
    return [];
  }
}

function text(form, key) {
  const value = form.get(key);
  return typeof value === "string" ? value.normalize("NFC").trim() : "";
}

function json(body, headers = {}, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

function fail(status, error) {
  return json({ ok: false, error }, { "Cache-Control": "no-store" }, status);
}
