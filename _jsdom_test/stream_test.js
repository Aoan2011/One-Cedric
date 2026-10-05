// 流式输出复现测试：发送消息 → SSE 流式 → 检查完成后消息是否显示
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

const errors = [];
let sseCursor = 0;
const sseEvents = [
  'data: {"type":"reasoning","delta":"让我想想"}\n\n',
  'data: {"type":"content","delta":"你好，"}\n\n',
  'data: {"type":"content","delta":"我是 One Cedric"}\n\n',
  'data: {"type":"content","delta":"，本地文件助手。"}\n\n',
  'data: {"type":"done","duration":1.24}\n\n',
  'data: [DONE]\n\n',
];

const dom = new JSDOM(html, {
  url: 'http://localhost:2043/',
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  beforeParse(window) {
    const encoder = new TextEncoder();
    window.fetch = async (url) => {
      const u = String(url);
      if (u.includes('/api/chat/stream')) {
        return {
          ok: true,
          body: {
            getReader() {
              return {
                async read() {
                  if (sseCursor < sseEvents.length) {
                    return { done: false, value: encoder.encode(sseEvents[sseCursor++]) };
                  }
                  return { done: true, value: undefined };
                },
              };
            },
          },
        };
      }
      if (u.includes('/api/status')) return { ok: true, json: async () => ({ running: true, host: '127.0.0.1', port: 2043, url: 'http://127.0.0.1:2043', token_set: false, requests: 0, errors: 0, uptime: 5 }) };
      if (u.includes('/health')) return { ok: true, json: async () => ({ status: 'ok', model: 'deepseek-flash', root: 'F:\\one-cedric5' }) };
      if (u.includes('/api/tools')) return { ok: true, json: async () => ({ tools: [] }) };
      if (u.includes('/api/ask/pending')) return { ok: true, json: async () => [] };
      if (u.includes('/api/config')) return { ok: true, json: async () => ({ ui: { theme: 'dark', acrylic: 'medium', think_level: 'medium' }, model: 'deepseek-flash', host: 'http://localhost:11434' }) };
      return { ok: true, json: async () => ({}) };
    };
    window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
    window.TextDecoder = TextDecoder;
    window.TextEncoder = TextEncoder;
    window.Notification = function () {};
    window.Notification.permission = 'denied';
    window.Notification.requestPermission = async () => 'denied';
    window.BroadcastChannel = class { constructor() {} postMessage() {} close() {} };
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
        _d: {},
        getItem(k) { return this._d[k] !== undefined ? this._d[k] : null; },
        setItem(k, v) { this._d[k] = String(v); },
        removeItem(k) { delete this._d[k]; },
        key(i) { return Object.keys(this._d)[i] || null; },
        get length() { return Object.keys(this._d).length; },
      },
      configurable: true,
    });
    window.addEventListener('error', e => errors.push('ERR ' + (e.message || '') + ' @ ' + (e.filename || '') + ':' + (e.lineno || '')));
  },
});
const win = dom.window;

setTimeout(async () => {
  try {
    const proxy = win.document.getElementById('app')._vnode.component.proxy;
    // 发一条消息，走完整流式
    await proxy.send('你好，介绍一下自己');
    // 流式完成后检查
    const msgs = win.document.querySelectorAll('.msg');
    console.log('=== 流式完成后 ===');
    console.log('messages:', msgs.length, '(expect 2: user + assistant)');
    msgs.forEach(m => {
      console.log('  ', m.className, '|', (m.textContent || '').replace(/\s+/g, ' ').slice(0, 60));
    });
    const welcome = win.document.querySelector('.welcome');
    console.log('welcome:', !!welcome, '(expect false)');
    // 内容完整性
    const last = msgs[msgs.length - 1];
    const content = last ? last.textContent : '';
    console.log('assistant content complete:', content.includes('我是 One Cedric，本地文件助手'), content.slice(0, 60));
    // localStorage 是否保存了会话
    const stored = JSON.parse(win.localStorage.getItem('cedric_webui_sessions_v1') || '[]');
    console.log('stored sessions:', stored.length, '(expect 1)');
    if (stored.length) {
      const nodes = stored[0].tree.nodes;
      console.log('stored node count:', Object.keys(nodes).length, '(expect 2)');
      console.log('stored assistant content:', (nodes[Object.keys(nodes)[1]] || {}).content || '');
    }
    console.log('JS errors:', errors.length, errors[0] || '');
    process.exit(0);
  } catch (e) {
    console.error('CRASH:', e.message, e.stack);
    console.log('JS errors:', errors.join('\n'));
    process.exit(1);
  }
}, 1500);
