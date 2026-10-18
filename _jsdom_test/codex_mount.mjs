/* Shell B（Codex 皮肤）无头挂载检查。
 *
 * jsdom 不执行 <script type="module">，所以这里手工把 jsdom 的 DOM 桥到
 * Node 全局，再 import codex/app.js，验证：模块能加载、启动流程能跑完、
 * 会话/消息/用量/状态都真的渲染进 DOM、并且没有抛错。
 */
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const require = createRequire('F:/one-cedric3/_jsdom_test/');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = 'F:/one-cedric3/one_cedric/gateway/webui';
const html = readFileSync(`${ROOT}/codex/index.html`, 'utf8');

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => errors.push('jsdomError: ' + (e.message || e)));
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));
vc.on('warn', (...a) => errors.push('console.warn: ' + a.join(' ')));

const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:2043/codex',
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  virtualConsole: vc,
});
const { window } = dom;

// ---- 桥接浏览器全局 ----
const g = globalThis;
g.window = window;
g.document = window.document;
// Node ≥21 自带只读 navigator，得用 defineProperty 覆盖
Object.defineProperty(g, 'navigator', {
  value: window.navigator, configurable: true, writable: true });
g.localStorage = window.localStorage;
g.CustomEvent = window.CustomEvent;
g.Event = window.Event;
g.DOMParser = window.DOMParser;
g.HTMLElement = window.HTMLElement;
g.Node = window.Node;
g.URL = window.URL;
g.Blob = window.Blob;
g.FormData = window.FormData;
g.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
g.cancelAnimationFrame = (id) => clearTimeout(id);
g.AbortController = window.AbortController;
g.setInterval = () => 0;          // 别让 15s 心跳拖着进程
g.fetch = makeFetch();

// marked / hljs 的最小替身（真浏览器里由 <script> 注入全局）
window.marked = { parse: (md) => '<p>' + String(md) + '</p>' };
window.hljs = { highlightElement: () => {} };
g.marked = window.marked;
g.hljs = window.hljs;

function makeFetch() {
  return async (url, opts = {}) => {
    const path = String(url).replace('http://127.0.0.1:2043', '');
    const json = (data) => new globalThis.Response(JSON.stringify(data), {
      status: 200, headers: { 'Content-Type': 'application/json' } });
    if (path === '/api/config') {
      return json({ host: 'http://127.0.0.1:11434/v1', model: 'test-model',
                    context_limit: 128000 });
    }
    if (path === '/api/sessions') {
      return json({ sessions: [
        { id: 's-default', title: '你好问候', messages: 3,
          updated_at: Math.floor(Date.now() / 1000) },
        { id: 's-2', title: '老会话', messages: 9,
          updated_at: Math.floor(Date.now() / 1000) - 90000 },
      ], current: 's-default' });
    }
    if (path.startsWith('/api/sessions/')) {
      return json({ id: 's-default', title: '你好问候', model: 'test-model',
                    busy: false, messages: [
        { role: 'user', content: '你好' },
        { role: 'assistant', content: '你好！我可以帮你做什么？' },
      ] });
    }
    if (path === '/api/models') return json({ models: ['test-model', 'other'] });
    if (path === '/api/my-models') return json({ profiles: [] });
    if (path === '/api/status') return json({ status: 'ok' });
    if (path === '/api/tools') return json({ tools: [] });
    if (path === '/api/chat/stream') {
      const frames = [
        ['reasoning', { type: 'reasoning', text: '先想一下' }],
        ['content', { type: 'content', text: '你好' }],
        ['content', { type: 'content', text: '，世界' }],
        ['tool_start', { type: 'tool_start', call_id: 'c1', name: 'read_file',
                         target: 'a.py', status: 'running' }],
        ['tool_call', { type: 'tool_call', call_id: 'c1', name: 'read_file',
                        target: 'a.py', summary: '3 行', status: 'ok',
                        result: 'print(1)', duration: 0.12 }],
        ['usage', { type: 'usage', prompt_tokens: 120, completion_tokens: 8,
                    total_tokens: 128 }],
        ['done', { type: 'done' }],
      ].map(([name, payload]) =>
        `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`).join('');
      const enc = new TextEncoder();
      const body = new ReadableStream({
        start(c) {
          c.enqueue(enc.encode(frames));
          c.close();
        },
      });
      return new globalThis.Response(body, {
        status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    }
    return json({});
  };
}

const results = [];
const check = (name, ok, extra = '') => {
  results.push([name, ok, extra]);
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (extra ? '  ' + extra : ''));
};

try {
  await import(pathToFileURL(`${ROOT}/codex/app.js`).href);
  await new Promise((r) => setTimeout(r, 400));
  const doc = window.document;
  const q = (s) => doc.querySelector(s);

  check('shell mounted (no #app needed)', !!q('.cx') && !!q('#cx-stream'));
  check('sessions rendered', doc.querySelectorAll('.cx-session').length === 2,
        String(doc.querySelectorAll('.cx-session').length));
  check('day groups present',
        !!q('.cx-group-title') && doc.querySelectorAll('.cx-group-title').length >= 1);
  check('tabs rendered', doc.querySelectorAll('.cx-tab').length >= 1);
  check('transcript rendered',
        doc.querySelectorAll('.cx-msg').length === 2,
        String(doc.querySelectorAll('.cx-msg').length));
  check('assistant body has text',
        (q('.cx-msg[data-role="assistant"] .cx-msg-body') || {}).textContent
          ?.includes('你好'));
  check('model shown', (q('#cx-model-name') || {}).textContent === 'test-model');
  check('context tokens shown',
        (q('#cx-c-tokens') || {}).textContent === '0' ||
        (q('#cx-c-tokens') || {}).textContent === '0');
  check('status dot idle', q('#cx-status')?.dataset.state === 'idle');
  check('i18n applied', !!q('[data-i18n]')?.textContent?.trim());

  // 交互：命令面板能开、能过滤、能跑命令
  window.document.dispatchEvent(new window.KeyboardEvent('keydown',
    { key: 'p', ctrlKey: true, bubbles: true }));
  check('palette opens', q('#cx-palette')?.dataset.open === '1');
  const pinput = q('#cx-palette-input');
  pinput.value = 'export';
  pinput.dispatchEvent(new window.Event('input', { bubbles: true }));
  check('palette filters', doc.querySelectorAll('.cx-palette-item').length === 1,
        String(doc.querySelectorAll('.cx-palette-item').length));
  window.document.dispatchEvent(new window.KeyboardEvent('keydown',
    { key: 'Escape', bubbles: true }));
  check('palette closes on Esc', q('#cx-palette')?.dataset.open === '0');

  // 面板：设置面板要能真的渲染出字段
  q('#cx-settings').dispatchEvent(new window.Event('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 100));
  check('settings panel opens', q('#cx-overlay')?.dataset.open === '1');
  check('settings fields rendered', !!q('#cx-set-host'),
        (q('#cx-set-host') || {}).value);

  // 流式：发一条消息，验证 reasoning / 工具卡 / 正文 / 用量都落进 DOM
  q('#cx-panel-close').dispatchEvent(new window.Event('click', { bubbles: true }));
  const input = q('#cx-input');
  input.value = '你好';
  q('#cx-send').dispatchEvent(new window.Event('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 350));

  check('stream: user + assistant blocks',
        doc.querySelectorAll('.cx-msg').length === 4,
        String(doc.querySelectorAll('.cx-msg').length));
  check('stream: reasoning rendered', !!q('.cx-thought'),
        (q('.cx-thought summary') || {}).textContent);
  check('stream: tool card closed as done',
        q('.cx-tool')?.dataset.state === 'done',
        String(q('.cx-tool')?.dataset.state));
  check('stream: content accumulated',
        (q('.cx-msg[data-role="assistant"]:last-child .cx-msg-body') || {})
          .textContent?.includes('你好，世界'));
  check('stream: usage fed the context meter',
        (q('#cx-c-tokens') || {}).textContent === '128',
        (q('#cx-c-tokens') || {}).textContent);
  check('stream: caret removed when done', !q('.cx-caret'));
} catch (err) {
  check('module import + boot', false, String(err && err.stack || err));
}

const failed = results.filter(([, ok]) => !ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
if (errors.length) {
  console.log('console/jsdom errors (' + errors.length + '):');
  errors.slice(0, 12).forEach((e) => console.log('   - ' + String(e).slice(0, 240)));
}
dom.window.close();
process.exit(failed ? 1 : 0);
