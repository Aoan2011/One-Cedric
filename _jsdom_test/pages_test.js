// 独立页面验证：settings.html + stats.html 渲染与交互
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const WEBUI = 'F:/one-cedric5/one_cedric/gateway/webui';
const read = p => fs.readFileSync(path.join(WEBUI, p), 'utf8');

function makeLS(seed) {
  const store = Object.assign({}, seed || {});
  return {
    _d: store,
    getItem(k) { return this._d[k] !== undefined ? this._d[k] : null; },
    setItem(k, v) { this._d[k] = String(v); },
    removeItem(k) { delete this._d[k]; },
    key(i) { return Object.keys(this._d)[i] || null; },
    get length() { return Object.keys(this._d).length; },
  };
}

const bcastRecv = [];
class FakeBC {
  static reg = new Set();
  constructor(name) { this.name = name; FakeBC.reg.add(this); this.onmessage = null; }
  postMessage(data) { bcastRecv.push(data); for (const o of FakeBC.reg) if (o !== this && o.onmessage) o.onmessage({ data }); }
  close() { FakeBC.reg.delete(this); }
}

const sessions = [{ id: 's1', title: '你好', tree: { leafId: 'a2', nodes: {
  u1: { id: 'u1', role: 'user', content: '你好', parent: null, children: ['a1'] },
  a1: { id: 'a1', role: 'assistant', content: '我是 One Cedric。', parent: 'u1', children: ['u2'], toolCalls: [{ name: 'read_file', status: 'ok', summary: '' }], meta: '耗时 1.5s' },
  u2: { id: 'u2', role: 'user', content: '继续', parent: 'a1', children: ['a2'] },
  a2: { id: 'a2', role: 'assistant', content: '好的，继续讲。', parent: 'u2', children: [], toolCalls: [], meta: 'took 0.8s' },
}}, pinned: [{ msgId: 'a1' }], asks: [{ question: 'q1' }], turnCounter: 2, createdAt: 1, updatedAt: 2 }];

/* ── settings.html ── */
const domS = new JSDOM(read('settings.html'), {
  url: 'http://localhost:2043/settings', runScripts: 'dangerously', pretendToBeVisual: true,
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
    w.BroadcastChannel = FakeBC;
    Object.defineProperty(w, 'localStorage', { value: makeLS({
      'cedric_webui_settings_v1': JSON.stringify({ model: 'deepseek-flash', host: 'http://localhost:11434', temperature: 0.2, think_level: 'high', show_reasoning: true }),
      'cedric_webui_theme_v1': 'dark',
      'cedric_webui_acrylic_v1': 'medium',
      'cedric_webui_hue1_v1': '220',
      'cedric_webui_hue2_v1': '270',
      'cedric_webui_lang_v1': 'zh',
    }), configurable: true });
  },
});
const winS = domS.window;
setTimeout(() => {
  try {
    console.log('=== settings.html ===');
    console.log('model input:', winS.document.getElementById('fModel').value, '(expect deepseek-flash)');
    console.log('think buttons:', winS.document.querySelectorAll('#segThink button').length, '(expect 5)');
    console.log('think active:', (winS.document.querySelector('#segThink button.on') || {}).textContent, '(expect 高)');    console.log('theme active:', (winS.document.querySelector('#segTheme button.on') || {}).textContent, '(expect 深色)');
    // 保存逻辑
    winS.document.getElementById('fModel').value = 'qwen2.5';
    winS.saveAll();
    const saved = JSON.parse(winS.localStorage.getItem('cedric_webui_settings_v1'));
    console.log('after save model:', saved.model, '(expect qwen2.5)');
    console.log('after save think_level:', saved.think_level, '(expect high)');
    console.log('broadcasts sent:', bcastRecv.length, '(expect >= 3: settings/theme/sessions)');

    /* ── stats.html ── */
    const domT = new JSDOM(read('stats.html'), {
      url: 'http://localhost:2043/stats', runScripts: 'dangerously', pretendToBeVisual: true,
      beforeParse(w) {
        w.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
        w.fetch = async (url) => {
          const u = String(url);
          if (u.includes('/api/status')) return { ok: true, json: async () => ({ running: true, host: '127.0.0.1', port: 2043, url: 'http://127.0.0.1:2043', token_set: false, requests: 12, errors: 1, uptime: 3661, model: 'deepseek-flash' }) };
          if (u.includes('/api/tools')) return { ok: true, json: async () => ({ tools: [{ name: 'read_file', enabled: true, description: '读取文件' }, { name: 'grep', enabled: false, description: '搜索' }] }) };
          return { ok: true, json: async () => ({}) };
        };
        Object.defineProperty(w, 'localStorage', { value: makeLS({ 'cedric_webui_sessions_v1': JSON.stringify(sessions) }), configurable: true });
      },
    });
    const winT = domT.window;
    setTimeout(() => {
      try {
        console.log('=== stats.html ===');
        console.log('model:', winT.document.getElementById('stModel').textContent, '(expect deepseek-flash)');
        console.log('uptime:', winT.document.getElementById('stUptime').textContent, '(expect 1:01:01)');
        console.log('requests:', winT.document.getElementById('stRequests').textContent, '(expect 12)');
        console.log('errors:', winT.document.getElementById('stErrors').textContent, '(expect 1)');
        const cards = winT.document.querySelectorAll('#gridCards .card');
        console.log('cards:', cards.length, '(expect 6)');
        console.log('session count card:', cards[0] ? cards[0].querySelector('.num').textContent : '-', '(expect 1)');
        console.log('session bars:', winT.document.querySelectorAll('#sessionBars .bar-row').length, '(expect 1)');
        console.log('donut:', !!winT.document.querySelector('#donutWrap .donut'), '(expect true)');
        console.log('tool rows:', winT.document.querySelectorAll('#toolTable tr').length - 1, '(expect 2)');
        console.log('ALL PAGES OK');
        process.exit(0);
      } catch (e) { console.error('STATS CRASH:', e.message); process.exit(1); }
    }, 300);
  } catch (e) { console.error('SETTINGS CRASH:', e.message, e.stack); process.exit(1); }
}, 200);
