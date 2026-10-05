// 双窗口广播循环测试：验证“会话已在另一个窗口更新”不会无限循环
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const WEBUI = 'F:/one-cedric5/one_cedric/gateway/webui';
const read = p => fs.readFileSync(path.join(WEBUI, p), 'utf8');

let html = read('index.html');
const inline = (re, file) => {
  html = html.replace(re, (m) => {
    const srcMatch = m.match(/(?:href|src)="([^"]+)"/);
    const src = srcMatch ? srcMatch[1] : '';
    if (src && src.includes(file)) {
      return file.endsWith('.css') ? `<style>${read(file)}</style>` : `<script>${read(file)}</script>`;
    }
    return m;
  });
};
inline(/<link[^>]*rel="stylesheet"[^>]*>/g, 'style.css');
inline(/<link[^>]*rel="stylesheet"[^>]*>/g, 'hljs-theme.min.css');
inline(/<script[^>]*src="[^"]*vue\.min\.js[^"]*"[^>]*><\/script>/g, 'vue.min.js');
inline(/<script[^>]*src="[^"]*marked\.min\.js[^"]*"[^>]*><\/script>/g, 'marked.min.js');
inline(/<script[^>]*src="[^"]*highlight\.min\.js[^"]*"[^>]*><\/script>/g, 'highlight.min.js');
inline(/<script[^>]*src="[^"]*app\.js[^"]*"[^>]*><\/script>/g, 'app.js');

// 共享 BroadcastChannel（跨窗口真实分发）
class SharedBC {
  static reg = new Map();
  static count = { post: 0, deliver: 0 };
  constructor(name) {
    this.name = name;
    this.onmessage = null;
    if (!SharedBC.reg.has(name)) SharedBC.reg.set(name, new Set());
    SharedBC.reg.get(name).add(this);
  }
  postMessage(data) {
    SharedBC.count.post++;
    for (const other of SharedBC.reg.get(this.name)) {
      if (other !== this) {
        SharedBC.count.deliver++;
        if (other.onmessage) other.onmessage({ data });
      }
    }
  }
  close() {
    const s = SharedBC.reg.get(this.name);
    if (s) s.delete(this);
  }
}

const sessions = [];
function buildNodes(msgs) {
  const nodes = {};
  let prev = null, leafId = null;
  for (const m of msgs) {
    const node = { id: m.id, role: m.role, content: m.content,
      reasoning: m.reasoning || '', toolCalls: [], meta: '',
      streaming: false, _expanded: false,
      parent: prev || null, children: [], createdAt: Date.now() };
    nodes[node.id] = node;
    if (prev && nodes[prev]) nodes[prev].children.push(node.id);
    prev = node.id; leafId = node.id;
  }
  return { nodes, leafId };
}
sessions.push({ id: 's1', title: '你好', tree: buildNodes([
  { id: 'u1', role: 'user', content: '你好，介绍一下自己' },
  { id: 'a1', role: 'assistant', content: '我是 One Cedric。' },
  { id: 'u2', role: 'user', content: '统计一下代码量' },
  { id: 'a2', role: 'assistant', content: '共 42 个文件。' },
]), asks: [], pinned: [], turnCounter: 2, createdAt: 1, updatedAt: 2 });
sessions.push({ id: 's2', title: '这个目录里有什么文件', tree: buildNodes([]),
  asks: [], pinned: [], turnCounter: 0, createdAt: 1, updatedAt: 2 });

function makeStubs(window, errors) {
  window.fetch = async (url) => {
    if (String(url).includes('/api/status')) return { ok: true, json: async () => ({ running: true, host: '127.0.0.1', port: 2043, url: 'http://127.0.0.1:2043', token_set: false, requests: 0, errors: 0, uptime: 42 }) };
    if (String(url).includes('/health')) return { ok: true, json: async () => ({ status: 'ok', model: 'deepseek-flash', root: 'F:\\one-cedric5' }) };
    if (String(url).includes('/api/tools')) return { ok: true, json: async () => ({ tools: [] }) };
    if (String(url).includes('/api/ask/pending')) return { ok: true, json: async () => [] };
    if (String(url).includes('/api/config')) return { ok: true, json: async () => ({ ui: { theme: 'dark', acrylic: 'medium', think_level: 'medium' }, model: 'deepseek-flash', host: 'http://localhost:11434' }) };
    return { ok: true, json: async () => ({}) };
  };
  window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  window.Notification = function () {};
  window.Notification.permission = 'denied';
  window.Notification.requestPermission = async () => 'denied';
  window.BroadcastChannel = SharedBC;
  window.HTMLCanvasElement.prototype.getContext = () => ({
    clearRect() {}, fillRect() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
    moveTo() {}, lineTo() {}, createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    measureText: () => ({ width: 0 }), setTransform() {}, save() {}, restore() {}, fillText() {},
  });
  window.crypto = window.crypto || {};
  window.crypto.randomUUID = () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16); });
  Object.defineProperty(window, 'localStorage', {
    value: {
      _d: { cedric_webui_sessions_v1: JSON.stringify(sessions) },
      getItem(k) { return this._d[k] !== undefined ? this._d[k] : null; },
      setItem(k, v) { this._d[k] = String(v); },
      removeItem(k) { delete this._d[k]; },
      key(i) { return Object.keys(this._d)[i] || null; },
      get length() { return Object.keys(this._d).length; },
    },
    configurable: true,
  });
  window.addEventListener('error', e => errors.push('ERR ' + (e.message || '') + ' @ ' + (e.lineno || '')));
}

const errA = [], errB = [];
const domA = new JSDOM(html, { url: 'http://localhost:2043/', runScripts: 'dangerously', pretendToBeVisual: true, beforeParse: w => makeStubs(w, errA) });
const domB = new JSDOM(html, { url: 'http://localhost:2043/', runScripts: 'dangerously', pretendToBeVisual: true, beforeParse: w => makeStubs(w, errB) });
const winA = domA.window, winB = domB.window;

function toastCount(w) {
  return w.document.querySelectorAll('.toast').length;
}

setTimeout(() => {
  const t0 = SharedBC.count.post;
  const toastsB0 = toastCount(winB);
  console.log('=== 初始 ===');
  console.log('A toasts:', toastCount(winA), 'B toasts:', toastsB0);

  // 窗口 A 模拟用户切换会话（触发保存 + 广播）
  const proxyA = winA.document.getElementById('app')._vnode.component.proxy;
  proxyA.switchSession('s2');
  const t1 = SharedBC.count.post;
  console.log('=== A 切换会话后 ===');
  console.log('A broadcast:', t1 - t0, '(expect 1: 切换时的 save)');

  // 等待 B 处理广播 + 可能的回环
  setTimeout(() => {
    const t2 = SharedBC.count.post;
    const t3 = SharedBC.count.post;
    console.log('=== 400ms 后 ===');
    console.log('broadcast delta 400ms:', t2 - t1, '(expect 0 无回环)');
    console.log('B toasts now:', toastCount(winB), '(expect 1 仅一次提示)');
    console.log('A toasts now:', toastCount(winA), '(expect 0)');
    setTimeout(() => {
      const t4 = SharedBC.count.post;
      console.log('=== 再等 800ms ===');
      console.log('broadcast delta 800ms:', t4 - t3, '(expect 0 稳定)');
      console.log('B toasts final:', toastCount(winB), '(expect 1)');
      console.log('JS errors A:', errA.length, errA[0] || '');
      console.log('JS errors B:', errB.length, errB[0] || '');
      // B 的消息渲染
      const msgsB = winB.document.querySelectorAll('.msg');
      console.log('B messages rendered:', msgsB.length, '(expect 4 s1 消息)');
      console.log(errA.length + errB.length === 0 ? 'NO JS ERRORS' : 'HAS ERRORS');
      process.exit(0);
    }, 800);
  }, 400);
}, 1800);
