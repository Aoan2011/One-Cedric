/* 与皮肤无关的传输层：鉴权头、401 广播、SSE v2 客户端。
 *
 * 这一层是四个界面共用的（Codex WebUI / 桌面壳 / 未来迁移的 Glass）。
 * 旧 app.js 里这些逻辑是散落的内联 fetch + 一次性 IIFE，这里收拢成一处。
 */

export const TOKEN_KEY = 'cedric_gateway_token_v1';
export const EVENT_401 = 'cedric-gateway-401';

let token = '';
try {
  token = localStorage.getItem(TOKEN_KEY) || '';
} catch (err) {
  token = '';
}

/* 桌面壳 / 内嵌启动器通过 `?gwtoken=<hex>` 注入一次性会话令牌。
 *
 * 桌面壳起网关用的是随机端口 + 随机 token，localStorage 里还没有这份
 * 记录，首次加载必然 401。这里从 URL 收下令牌、落进 localStorage，
 * 然后立刻从地址栏清掉：不留在可见 URL、也不进历史记录/Referer。
 * 令牌格式收紧为 8~128 位十六进制，避免 query 串注入任意 Authorization。
 */
try {
  const q = new URLSearchParams(window.location.search).get('gwtoken');
  if (q && /^[a-zA-Z0-9]{8,128}$/.test(q)) {
    token = q;
    try { localStorage.setItem(TOKEN_KEY, token); } catch (err) { /* */ }
    const clean = new URL(window.location.href);
    clean.searchParams.delete('gwtoken');
    window.history.replaceState(null, '', clean.toString());
  }
} catch (err) { /* jsdom / 隐私模式下没有 history，只保留内存令牌 */ }

export function getToken() { return token; }

export function setToken(value) {
  token = (value || '').trim();
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch (err) { /* 隐私模式下 localStorage 可能抛错，忽略 */ }
}

function headers(extra) {
  const h = Object.assign({}, extra || {});
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

export async function apiFetch(url, opts = {}) {
  const res = await fetch(url, Object.assign({}, opts, {
    headers: headers(opts.headers),
  }));
  if (res.status === 401 && url.startsWith('/api/')) {
    window.dispatchEvent(new CustomEvent(EVENT_401));
  }
  return res;
}

export async function getJSON(url) {
  const res = await apiFetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

export async function postJSON(url, body) {
  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

/* ------------------------------------------------------------------ *
 * SSE 客户端
 * ------------------------------------------------------------------ */

/**
 * 逐帧解析 `event:` / `data:` 的 SSE 流。
 *
 * 与手写 `res.body.getReader()` 相比，这里多做三件事：
 *  - 顶掉 `:` 心跳注释（服务端每 15s 发一次，弱网下别当数据）；
 *  - 记录单调 `seq`，断线重连时能判断有没有丢帧；
 *  - `[DONE]` 之前的所有 JSON 都带 `seq`/`session_id`，直接抛给上层。
 */
export class SSEClient {
  constructor(url, { onEvent, onDone, onError } = {}) {
    this.url = url;
    this.onEvent = onEvent || (() => {});
    this.onDone = onDone || (() => {});
    this.onError = onError || (() => {});
    this.seq = 0;
    this.controller = null;
    this.closed = false;
  }

  async start(body) {
    this.controller = new AbortController();
    try {
      const res = await apiFetch(this.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
        signal: this.controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error('HTTP ' + res.status);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (!this.closed) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          this._handleFrame(frame);
          boundary = buffer.indexOf('\n\n');
        }
      }
      if (!this.closed) this.onDone();
    } catch (err) {
      if (err && err.name === 'AbortError') return this.onDone();
      this.onError(err);
    }
  }

  _handleFrame(frame) {
    let name = 'message';
    const dataLines = [];
    for (const rawLine of frame.split('\n')) {
      const line = rawLine.replace(/\r$/, '');
      if (!line || line.startsWith(':')) continue;  // 心跳 / 注释
      if (line.startsWith('event:')) name = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    const payload = dataLines.join('\n');
    if (payload === '[DONE]') { this.closed = true; return; }
    let evt;
    try {
      evt = JSON.parse(payload);
    } catch (err) {
      return;
    }
    if (typeof evt.seq === 'number') this.seq = evt.seq;
    if (!evt.type) evt.type = name;
    this.onEvent(evt);
  }

  stop() {
    this.closed = true;
    if (this.controller) this.controller.abort();
  }
}
