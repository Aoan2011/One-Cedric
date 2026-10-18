/* Shell B（Codex 皮肤）ask_user 卡片无头检查。
 *
 * 场景：SSE 流里来一个 ask_user 事件（两个问题：一个带选项、一个自由
 * 输入）→ 卡片渲染 → 点选项选中 → 输入自定义答案 → 提交 → 断言
 * /api/ask/answer 收到 {key: value} 且卡片进入已回答态。
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

const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:2043/codex',
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  virtualConsole: vc,
});
const { window } = dom;

const g = globalThis;
g.window = window;
g.document = window.document;
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
g.setInterval = () => 0;
g.fetch = makeFetch();

window.marked = { parse: (md) => '<p>' + String(md) + '</p>' };
window.hljs = { highlightElement: () => {} };
g.marked = window.marked;
g.hljs = window.hljs;

const 写入回答 = { answers: null };
function makeFetch() {
  return async (url, opts = {}) => {
    const path = String(url).replace('http://127.0.0.1:2043', '');
    const json = (data, extra = {}) => new globalThis.Response(
      JSON.stringify(data), {
        status: 200, headers: { 'Content-Type': 'application/json' },
        ...extra,
      });
    if (path === '/api/config') {
      return json({ host: 'http://127.0.0.1:11434/v1', model: 'm1',
                    context_limit: 128000 });
    }
    if (path === '/api/sessions') {
      return json({ sessions: [
        { id: 's1', title: 'ask 测试', messages: 0,
          updated_at: Math.floor(Date.now() / 1000) },
      ], current: 's1' });
    }
    if (path.startsWith('/api/sessions/')) {
      return json({ id: 's1', title: 'ask 测试', messages: [] });
    }
    if (path === '/api/models') return json({ models: ['m1'] });
    if (path === '/api/my-models') return json({ profiles: [] });
    if (path.startsWith('/api/ask/answer')) {
      写入回答.answers = JSON.parse(String(opts.body || '{}'));
      return json({ ok: true });
    }
    if (path === '/api/chat/stream') {
      const askEvt = {
        type: 'ask_user', id: 'ask_123_deadbeef', header: '写文件确认',
        timeout: 60,
        questions: [
          { key: 'approve', question: '允许写入 notes.md 吗？',
            options: ['允许', '拒绝'], default: '拒绝' },
          { key: 'style', question: '用哪种风格？', options: [],
            default: '' },
        ],
      };
      const frames = [
        ['content', { type: 'content', text: '我需要写一个文件。' }],
        ['ask_user', askEvt],
        ['done', { type: 'done' }],
      ].map(([name, payload]) =>
        `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`).join('');
      const enc = new TextEncoder();
      return new globalThis.Response(new ReadableStream({
        start(c) {
          c.enqueue(enc.encode(frames));
          c.close();
        },
      }), { status: 200,
           headers: { 'Content-Type': 'text/event-stream' } });
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

  // 发起一条消息触发 SSE
  const input = q('#cx-input');
  input.value = '帮我写文件';
  q('#cx-send').dispatchEvent(new window.Event('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 350));

  check('ask card rendered', !!q('.cx-ask'), String(!!q('.cx-ask')));
  check('ask header shown',
        (q('.cx-ask-head') || {}).textContent?.includes('写文件确认'));
  check('option buttons rendered',
        doc.querySelectorAll('.cx-ask-opt').length === 2,
        String(doc.querySelectorAll('.cx-ask-opt').length));

  // 选中「允许」，另一问题输入自定义答案
  q('.cx-ask-opt').dispatchEvent(
    new window.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 50));
  check('option marked chosen',
        q('.cx-ask-opt')?.dataset.chosen === '1');
  const askInput = doc.querySelectorAll('.cx-ask-input')[1];
  askInput.value = '朴素风';
  askInput.dispatchEvent(new window.KeyboardEvent('keydown', {
    key: 'Enter', bubbles: true }));
  await new Promise((r) => setTimeout(r, 120));

  check('answer posted', 写入回答.answers !== null,
        JSON.stringify(写入回答.answers));
  const answers = 写入回答.answers && 写入回答.answers.answers || {};
  check('option answer carried', answers.approve === '允许',
        JSON.stringify(answers));
  check('custom answer carried', answers.style === '朴素风',
        JSON.stringify(answers));
  check('card answered state', q('.cx-ask')?.dataset.answered === '1');
  check('inputs disabled after answer', !!q('.cx-ask-input[disabled]'));

  // 二次提交应当无效（不再发请求）
  写入回答.answers = null;
  q('[data-ask-submit]').dispatchEvent(
    new window.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 80));
  check('re-submit blocked', 写入回答.answers === null);
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
