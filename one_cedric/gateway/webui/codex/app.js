/* One Cedric — Codex shell 前端入口（零构建 ES modules，无框架）。
 *
 * 为什么不用 Vue：旧 app.js 4600 行单组件、必须 unsafe-eval（模板编译）才
 * 能跑。这里用原生模块 + 脏块对账，同样能流式渲染，还能把
 * script-src 的 'unsafe-eval' 去掉。所有 innerHTML 都过 core/render.js
 * 的白名单。
 */

import { apiFetch, getJSON, postJSON, setToken, getToken, EVENT_401 }
  from '../core/transport.js';
import {
  state, on, emit, activeMessages, messagesOf, refreshSessions, openSession,
  closeTab, newSession, deleteSession, send, stop, sessionAction, loadModels,
  loadConfig, setLang, setTheme, setMode, answerAsk, MODES,
} from '../core/store.js';
import {
  renderMarkdown, highlight, renderToolOutput, escapeHtml, timeAgo,
  formatTokens,
} from '../core/render.js';
import { t, applyI18n, setLang as i18nSetLang } from '../core/i18n.js';

const $ = (sel) => document.querySelector(sel);

const MODE_LABEL = MODES.reduce((acc, m) => (acc[m] = m[0].toUpperCase()
  + m.slice(1), acc), {});
const DEFAULT_LIMIT = 200000;

let searchTerm = '';
const blockEls = new Map();     // block.id -> element
let pendingFrame = 0;

/* ------------------------------------------------------------------ *
 * 主题 / 语言
 * ------------------------------------------------------------------ */
function loadPrefs() {
  let theme = 'dark';
  let lang = 'zh';
  try {
    theme = localStorage.getItem('cedric_codex_theme') || theme;
    lang = localStorage.getItem('cedric_codex_lang') || lang;
  } catch (err) { /* 忽略 */ }
  i18nSetLang(lang);
  setLang(lang);
  setTheme(theme);
  applyI18n(document);
}

function toggleTheme() {
  const next = state.theme === 'dark' ? 'light' : 'dark';
  setTheme(next);
  try { localStorage.setItem('cedric_codex_theme', next); } catch (err) {}
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content',
    next === 'light' ? '#f6f7fb' : '#0b0d12');
}

function toggleLang() {
  const next = state.lang === 'en' ? 'zh' : 'en';
  i18nSetLang(next);
  setLang(next);
  try { localStorage.setItem('cedric_codex_lang', next); } catch (err) {}
  applyI18n(document);
  renderTabs();
  renderSessions();
  renderTranscript(true);
}

/* ------------------------------------------------------------------ *
 * 顶栏：tabs / 状态 / 用量
 * ------------------------------------------------------------------ */
function renderTabs() {
  const host = $('#cx-tabs');
  const parts = state.tabs.map((id) => {
    const row = state.sessions.find((s) => s.id === id);
    const title = (row && row.title) || shortId(id);
    const active = state.activeId === id;
    return '<button class="cx-tab" role="tab" data-id="' + escapeHtml(id) +
      '" aria-selected="' + (active ? 'true' : 'false') + '">' +
      '<span class="cx-tab-title">' + escapeHtml(title) + '</span>' +
      '<span class="cx-tab-close" data-close="' + escapeHtml(id) +
      '" role="button" aria-label="关闭">×</span></button>';
  });
  if (!state.tabs.length) {
    parts.push('<span class="cx-mono cx-dim" style="padding:0 8px">' +
      escapeHtml(t('label.noSessions')) + '</span>');
  }
  host.innerHTML = parts.join('');
}

function shortId(id) {
  return String(id || '').slice(0, 8);
}

function renderStatus() {
  const dot = $('#cx-status');
  const text = $('#cx-status-text');
  const label = state.offline ? t('status.offline')
    : (state.busy ? t('status.busy') : t('status.idle'));
  dot.dataset.state = state.offline ? 'offline' : (state.busy ? 'busy' : 'idle');
  dot.title = label;
  if (text) {
    text.textContent = label;
    text.dataset.state = dot.dataset.state;
  }
  $('#cx-model-name').textContent = state.model || '—';
  $('#cx-model-line').textContent = (state.model || '—') +
    (state.config.host ? ' · ' + String(state.config.host).replace(
      /^https?:\/\//, '') : '');
  const tokens = state.context.tokens || 0;
  const limit = state.context.limit || DEFAULT_LIMIT;
  const pct = Math.min(100, Math.round((tokens / limit) * 100));
  $('#cx-ctx-tokens').textContent = formatTokens(tokens);
  $('#cx-ctx-pct').textContent = pct + '%';
  $('#cx-ctx-bar').style.width = pct + '%';
  $('#cx-c-tokens').textContent = tokens.toLocaleString();
  $('#cx-c-pct').textContent = pct + '%';
  $('#cx-c-bar').style.width = pct + '%';
  $('#cx-c-model').textContent = state.model || '—';
  $('#cx-c-host').textContent = state.config.host || '—';
  const cost = Number(state.cost.usd || 0);
  $('#cx-cost').textContent = cost.toFixed(4);
  $('#cx-c-cost').textContent = '$' + cost.toFixed(4);
  const busy = state.busy;
  const box = $('#cx-box');
  box.dataset.busy = busy ? '1' : '0';
  const sendBtn = $('#cx-send');
  sendBtn.dataset.mode = busy ? 'stop' : 'send';
  sendBtn.title = busy ? t('action.stop') : t('action.send');
  const modeEl = $('#cx-mode');
  modeEl.textContent = MODE_LABEL[state.mode] || 'Build';
  modeEl.dataset.mode = state.mode || 'build';
}

/* ------------------------------------------------------------------ *
 * 侧栏
 * ------------------------------------------------------------------ */
function renderSessions() {
  const host = $('#cx-session-list');
  const rows = state.sessions.filter((s) => {
    if (!searchTerm) return true;
    return String(s.title || '').toLowerCase()
      .includes(searchTerm.toLowerCase());
  });
  if (!rows.length) {
    host.innerHTML = '<div class="cx-dim cx-mono" style="padding:8px">' +
      escapeHtml(t('label.noSessions')) + '</div>';
    return;
  }
  const groups = groupByDay(rows);
  let html = '';
  for (const [label, items] of groups) {
    html += '<div class="cx-group-title">' + escapeHtml(label) + '</div>';
    for (const s of items) {
      const active = s.id === state.activeId;
      html += '<div class="cx-session" role="button" tabindex="0" data-id="' +
        escapeHtml(s.id) + '" aria-current="' + (active ? 'true' : 'false') +
        '"><span class="cx-session-title">' +
        escapeHtml(s.title || shortId(s.id)) + '</span>' +
        '<span class="cx-session-meta"><span>' + (s.messages || 0) +
        ' 条</span><span>' + escapeHtml(timeAgo(s.updated_at)) + '</span></span>' +
        '<span class="cx-session-actions">' +
        '<button data-del="' + escapeHtml(s.id) + '" title="' +
        escapeHtml(t('action.delete')) + '">×</button></span></div>';
    }
  }
  host.innerHTML = html;
}

function groupByDay(rows) {
  const sorted = rows.slice().sort(
    (a, b) => (b.updated_at || 0) - (a.updated_at || 0));
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(),
    now.getDate()).getTime() / 1000;
  const buckets = [[t('label.today'), []], [t('label.yesterday'), []],
                   [t('label.earlier'), []]];
  for (const s of sorted) {
    const ts = s.updated_at || 0;
    if (ts >= startOfToday) buckets[0][1].push(s);
    else if (ts >= startOfToday - 86400) buckets[1][1].push(s);
    else buckets[2][1].push(s);
  }
  return buckets.filter(([, items]) => items.length);
}

/* ------------------------------------------------------------------ *
 * Transcript（脏块对账：只更新变化的那一块）
 * ------------------------------------------------------------------ */
function renderTranscript(force = false) {
  const host = $('#cx-stream');
  const blocks = activeMessages();
  if (!blocks.length) {
    blockEls.clear();
    host.innerHTML =
      '<div class="cx-empty"><div class="cx-wordmark">' +
      escapeHtml(t('app.name')) + '</div>' +
      '<div class="cx-empty-sub">' + escapeHtml(t('app.tagline')) + '</div>' +
      '<div class="cx-empty-sub cx-mono">' +
      escapeHtml(t('composer.placeholder')) + '</div></div>';
    return;
  }
  if (host.querySelector('.cx-empty')) host.innerHTML = '';
  if (force) {
    host.innerHTML = '';
    blockEls.clear();
  }
  let prev = null;
  for (const block of blocks) {
    let el = blockEls.get(block.id);
    if (!el) {
      el = document.createElement('article');
      el.className = 'cx-msg';
      el.dataset.id = block.id;
      el.dataset.role = block.role;
      blockEls.set(block.id, el);
      host.appendChild(el);
    }
    if (prev && prev.nextElementSibling !== el) {
      host.insertBefore(el, prev.nextSibling);
    }
    prev = el;
    paintBlock(el, block);
  }
  for (const [id, el] of Array.from(blockEls.entries())) {
    if (!blocks.some((b) => b.id === id)) {
      el.remove();
      blockEls.delete(id);
    }
  }
  scrollToBottom();
}

function paintBlock(el, block) {
  if (block.role === 'user') {
    el.innerHTML = '<div class="cx-msg-body">' +
      escapeHtml(block.text) + '</div>';
    return;
  }
  const parts = [];
  if (block.reasoning) {
    const live = block.streaming && !block.text;
    parts.push('<details class="cx-thought"' +
      (live ? ' data-live="1"' : '') + '>' +
      '<summary><span>' + escapeHtml(t('msg.thought')) + ' · ' +
      escapeHtml(durationLabel(block)) + '</span></summary>' +
      '<div class="cx-thought-body">' + escapeHtml(block.reasoning) +
      '</div></details>');
  }
  for (const tool of block.tools || []) {
    const st = tool.done ? (tool.failed ? 'failed' : 'done') : 'running';
    parts.push('<details class="cx-tool" data-state="' + st + '">' +
      '<summary><span class="cx-tool-name">' + escapeHtml(tool.name) +
      '</span><span class="cx-tool-status">' +
      escapeHtml(tool.status || t('msg.toolRunning')) + '</span>' +
      (tool.ms ? '<span class="cx-tool-ms">' + tool.ms + 'ms</span>' : '') +
      '</summary><div class="cx-tool-body">' +
      renderToolOutput(tool.result || tool.args || '') + '</div></details>');
  }
  if (block.ask) {
    parts.push(renderAskCard(block.ask));
  }
  if (block.error) {
    parts.push('<div class="cx-error">' + escapeHtml(block.error) + '</div>');
  }
  if (block.text || block.streaming) {
    const html = renderMarkdown(block.text || '');
    parts.push('<div class="cx-msg-body">' + html +
      (block.streaming ? '<span class="cx-caret"></span>' : '') + '</div>');
  }
  if (block.aborted) {
    parts.push('<div class="cx-dim cx-mono">[' +
      escapeHtml(t('msg.interrupted')) + ']</div>');
  }
  el.innerHTML = parts.join('') || '<div class="cx-dim">…</div>';
  highlight(el);
}

/* ask_user 卡片：内核暂停等人工确认（写文件 / 危险命令等）。
 *
 * 交互：选项点一下即选中（radio 语义）；已选项会写进 block.ask.draft，
 * 自由输入框直接编辑 draft。点「提交回答」一次性把 {key: value} 推给
 * 内核 —— answer_ask 是一次性事件，不存在逐题渐进提交。
 * paintBlock 每次重绘整个块，所以选中状态必须读自 draft，而不是 DOM。
 */
function renderAskCard(ask) {
  const draft = ask.draft || {};
  const answered = !!ask.answered;
  const rows = (ask.questions || []).map((q, qi) => {
    const buttons = (q.options || []).map((opt, oi) => {
      const chosen = draft[q.key] === opt;
      return '<button class="cx-ask-opt" data-ask-opt="' + qi + ':' + oi +
        '" data-chosen="' + (chosen ? '1' : '0') + '"' +
        (answered ? ' disabled' : '') + '>' + escapeHtml(opt) + '</button>';
    }).join('');
    const value = draft[q.key] || '';
    return '<div class="cx-ask-q"><div class="cx-ask-title">' +
      escapeHtml(q.question || q.key || '?') + '</div>' +
      '<div class="cx-ask-opts">' + buttons + '</div>' +
      '<div class="cx-ask-inputrow"><input class="cx-ask-input" ' +
      'data-ask-input="' + qi + '" value="' + escapeHtml(value) + '"' +
      ' placeholder="' + escapeHtml(t('ask.custom')) + '"' +
      (answered ? ' disabled' : '') + '><button class="cx-btn" ' +
      'data-ask-submit="' + qi + '"' + (answered ? ' disabled' : '') + '>' +
      escapeHtml(answered ? t('ask.answered') : t('ask.submit')) +
      '</button></div></div>';
  }).join('');
  return '<div class="cx-ask" data-answered="' + (answered ? '1' : '0') +
    '"><div class="cx-ask-head">' +
    escapeHtml(ask.header || t('ask.title')) +
    (answered ? '' : '<span class="cx-ask-live" aria-hidden="true"></span>') +
    '</div>' + rows + '</div>';
}

async function submitAsk(block, index, customText) {
  const ask = block.ask;
  if (!ask || ask.answered) return;
  const q = ask.questions[index];
  if (q && customText !== undefined && customText !== '') {
    ask.draft[q.key] = customText;
    emit('messages', state.activeId);
  }
  const answers = {};
  let missing = false;
  for (const item of ask.questions) {
    const v = ask.draft[item.key];
    if (v === undefined || v === '') {
      missing = true;
      continue;
    }
    answers[item.key] = v;
  }
  if (missing && !ask.questions.some((item) => item.options.length)) {
    return;   // 全自由输入且有题未答：等用户补完
  }
  // 未作答的题交给内核的 default 兜底
  ask.answered = true;
  try {
    await answerAsk(ask.id, answers);
    toast('ok', t('ask.sent'));
  } catch (err) {
    ask.answered = false;
    toast('error', String(err && err.message || err));
  }
  const el = blockEls.get(block.id);
  if (el) paintBlock(el, block);
}

function durationLabel(block) {
  if (block.duration !== undefined) {
    return Math.round(block.duration * 1000) + 'ms';
  }
  if (block.startedAt) {
    return Math.round(Date.now() - block.startedAt) + 'ms';
  }
  return '—';
}

function scrollToBottom() {
  const host = $('#cx-transcript');
  const near = host.scrollHeight - host.scrollTop - host.clientHeight < 160;
  if (near) host.scrollTop = host.scrollHeight;
}

/* ------------------------------------------------------------------ *
 * Composer
 * ------------------------------------------------------------------ */
function submit() {
  const input = $('#cx-input');
  const text = input.value;
  if (!text.trim()) return;
  if (state.busy) { stop(); return; }
  if (text.trim().startsWith('/')) {
    if (handleSlash(text.trim())) { input.value = ''; autoGrow(); return; }
  }
  send(text, { autoApprove: false });
  addCostSample(text.length);
  input.value = '';
  autoGrow();
  emit('context', {});
}

function autoGrow() {
  const input = $('#cx-input');
  input.style.height = 'auto';
  input.style.height = Math.min(240, Math.max(52, input.scrollHeight)) + 'px';
}

function handleSlash(cmd) {
  const [name, ...rest] = cmd.slice(1).split(/\s+/);
  const arg = rest.join(' ');
  switch (name) {
    case 'new': newSession(); return true;
    case 'clear': sessionAction('clear'); return true;
    case 'compact': sessionAction('compact'); return true;
    case 'undo': sessionAction('undo'); return true;
    case 'settings': openPanel('settings'); return true;
    case 'stats': openPanel('stats'); return true;
    case 'tools': openPanel('tools'); return true;
    case 'models': openPanel('models'); return true;
    case 'diagnose': openPanel('diagnose'); return true;
    case 'cron': openPanel('cron'); return true;
    case 'theme': toggleTheme(); return true;
    case 'lang': toggleLang(); return true;
    case 'help': openPanel('help'); return true;
    case 'export': exportSession(); return true;
    case 'model':
      if (arg) setModel(arg); else openPanel('models');
      return true;
    case 'search':
      $('#cx-search').focus();
      return true;
    default:
      return false;   // 未知命令当普通消息发出去，别静默吞掉
  }
}

function exportSession() {
  const blocks = activeMessages();
  const blob = new Blob([JSON.stringify({
    session: state.activeId, model: state.model, messages: blocks,
  }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'one-cedric-' + (state.activeId || 'session') + '.json';
  a.click();
  URL.revokeObjectURL(url);
  toast('ok', t('action.export'));
}

function addCostSample(chars) {
  // 前端只做粗略预估；权威成本走 /api/costs（M0-6 接上后这里直接显示）
  state.cost.usd = Number(state.cost.usd || 0) + chars * 0.0000004;
  state.cost.calls = Number(state.cost.calls || 0) + 1;
}

async function setModel(id) {
  try {
    await postJSON('/api/config', { model: id });
    state.model = id;
    state.config.model = id;
    renderStatus();
    toast('ok', t('toast.saved'));
  } catch (err) {
    toast('error', '模型切换失败：' + err.message);
  }
}

/* ------------------------------------------------------------------ *
 * 面板
 * ------------------------------------------------------------------ */
function openPanel(name) {
  const overlay = $('#cx-overlay');
  const title = $('#cx-panel-title');
  const body = $('#cx-panel-body');
  const renderers = {
    settings: renderSettingsPanel,
    stats: renderStatsPanel,
    tools: renderToolsPanel,
    models: renderModelsPanel,
    diagnose: renderDiagnosePanel,
    cron: renderCronPanel,
    help: renderHelpPanel,
  };
  const render = renderers[name] || renderers.help;
  title.textContent = t('panel.' + name) === 'panel.' + name
    ? name : t('panel.' + name);
  body.innerHTML = '<div class="cx-dim">' + escapeHtml(t('label.loading')) +
    '</div>';
  overlay.dataset.open = '1';
  overlay.dataset.panel = name;
  lastFocused = document.activeElement;
  $('#cx-panel-close').focus();
  Promise.resolve(render(body)).catch((err) => {
    body.innerHTML = '<div class="cx-error">' + escapeHtml(String(err)) +
      '</div>';
  });
}

let lastFocused = null;

function closePanel() {
  const overlay = $('#cx-overlay');
  overlay.dataset.open = '0';
  overlay.dataset.panel = '';
  if (lastFocused && lastFocused.focus) lastFocused.focus();
}

async function renderSettingsPanel(body) {
  const cfg = state.config || {};
  body.innerHTML =
    '<div class="cx-grid-2">' +
    field('host', 'Host', cfg.host || '') +
    field('model', t('context.model'), cfg.model || '') +
    field('api_key', 'API Key', '', 'password') +
    field('gateway_token', 'Gateway Token', getToken(), 'password') +
    '</div>' +
    '<div class="cx-grid-2">' +
    '<div class="cx-field"><label>主题</label><select id="cx-set-theme">' +
    '<option value="dark">dark</option><option value="light">light</option>' +
    '</select></div>' +
    '<div class="cx-field"><label>语言</label><select id="cx-set-lang">' +
    '<option value="zh">中文</option><option value="en">English</option>' +
    '</select></div>' +
    '</div>' +
    '<div class="cx-row"><button class="cx-btn" id="cx-set-save"' +
    ' data-variant="primary">' + escapeHtml(t('action.save')) +
    '</button><span class="cx-mono cx-dim" id="cx-set-msg"></span></div>';

  const sel = (id, value) => {
    const el = body.querySelector(id);
    if (el) el.value = value;
  };
  sel('#cx-set-theme', state.theme);
  sel('#cx-set-lang', state.lang);

  body.querySelector('#cx-set-save').addEventListener('click', async () => {
    const payload = {
      host: body.querySelector('#cx-set-host').value.trim(),
      model: body.querySelector('#cx-set-model').value.trim(),
    };
    const key = body.querySelector('#cx-set-api_key').value.trim();
    if (key && !key.includes('…')) payload.api_key = key;
    const token = body.querySelector('#cx-set-gateway_token').value.trim();
    setToken(token);
    try {
      await postJSON('/api/config', payload);
      Object.assign(state.config, payload);
      state.model = payload.model || state.model;
      renderStatus();
      body.querySelector('#cx-set-msg').textContent = t('toast.saved');
    } catch (err) {
      body.querySelector('#cx-set-msg').textContent = '失败：' + err.message;
    }
  });
}

function field(id, label, value, type = 'text') {
  return '<div class="cx-field"><label for="cx-set-' + id + '">' +
    escapeHtml(label) + '</label><input id="cx-set-' + id + '" type="' +
    type + '" value="' + escapeHtml(value) + '" autocomplete="off"></div>';
}

async function renderStatsPanel(body) {
  const rows = state.sessions.slice(0, 20);
  let html = '<div class="cx-grid-2">' +
    '<div class="cx-card"><h3>会话</h3><div class="cx-kv"><span>总数</span>' +
    '<span>' + state.sessions.length + '</span></div>' +
    '<div class="cx-kv"><span>本次花费</span><span>$' +
    Number(state.cost.usd || 0).toFixed(4) + '</span></div>' +
    '<div class="cx-kv"><span>请求数</span><span>' +
    (state.cost.calls || 0) + '</span></div></div>' +
    '<div class="cx-card"><h3>上下文</h3><div class="cx-kv"><span>tokens</span>' +
    '<span>' + (state.context.tokens || 0).toLocaleString() + '</span></div>' +
    '<div class="cx-kv"><span>估算上限</span><span>' +
    (state.context.limit || DEFAULT_LIMIT).toLocaleString() +
    '</span></div></div></div>';
  try {
    const data = await getJSON('/api/status');
    html += '<div class="cx-card"><h3>网关</h3><pre class="cx-mono">' +
      escapeHtml(JSON.stringify(data, null, 2).slice(0, 2000)) +
      '</pre></div>';
  } catch (err) { /* 旧网关没有该端点时忽略 */ }
  html += '<div class="cx-list">' + rows.map((s) =>
    '<div class="cx-list-item"><span class="cx-spacer">' +
    escapeHtml(s.title || shortId(s.id)) + '</span><span class="cx-badge">' +
    (s.messages || 0) + '</span><span class="cx-dim cx-mono">' +
    escapeHtml(timeAgo(s.updated_at)) + '</span></div>').join('') + '</div>';
  body.innerHTML = html;
}

async function renderToolsPanel(body) {
  const data = await getJSON('/api/tools');
  const tools = data.tools || [];
  body.innerHTML = '<div class="cx-dim cx-mono">共 ' + tools.length +
    ' 个工具</div><div class="cx-list">' + tools.slice(0, 300).map((tool) => {
      const name = tool.name || tool.id || '?';
      const desc = (tool.description || '').slice(0, 120);
      const enabled = tool.enabled !== false;
      return '<div class="cx-list-item"><span class="cx-mono">' +
        escapeHtml(name) + '</span><span class="cx-dim">' +
        escapeHtml(desc) + '</span><span class="cx-spacer"></span>' +
        '<button class="cx-btn" data-tool-toggle="' + escapeHtml(name) +
        '">' + (enabled ? '关闭' : '开启') + '</button></div>';
    }).join('') + '</div>';
  body.querySelectorAll('[data-tool-toggle]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.toolToggle;
      try {
        await postJSON('/api/tools/' + encodeURIComponent(name) + '/toggle', {});
        btn.textContent = btn.textContent === '关闭' ? '开启' : '关闭';
      } catch (err) {
        toast('error', '切换失败：' + err.message);
      }
    });
  });
}

async function renderModelsPanel(body) {
  const [models, mine] = await Promise.all([
    getJSON('/api/models').catch(() => ({ models: [] })),
    getJSON('/api/my-models').catch(() => ({ profiles: [] })),
  ]);
  const list = models.models || [];
  body.innerHTML = '<div class="cx-list">' + list.map((id) =>
    '<div class="cx-list-item"><span class="cx-mono">' + escapeHtml(id) +
    '</span><span class="cx-spacer"></span>' +
    (id === state.model ? '<span class="cx-badge">当前</span>' :
      '<button class="cx-btn" data-pick="' + escapeHtml(id) + '">切换</button>') +
    '</div>').join('') + '</div>' +
    '<div class="cx-card"><h3>已保存的服务商</h3>' +
    ((mine.profiles || []).map((p) =>
      '<div class="cx-kv"><span>' + escapeHtml(p.name || '') +
      '</span><span class="cx-mono">' + escapeHtml(p.model || '') +
      ' · ' + escapeHtml(p.api_key || '') + '</span></div>').join('')
      || '<span class="cx-dim">（空）</span>') + '</div>';
  body.querySelectorAll('[data-pick]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await setModel(btn.dataset.pick);
      renderModelsPanel(body);
    });
  });
}

async function renderDiagnosePanel(body) {
  const data = await getJSON('/api/diagnose');
  body.innerHTML = '<pre class="cx-mono" style="white-space:pre-wrap">' +
    escapeHtml(JSON.stringify(data, null, 2).slice(0, 8000)) + '</pre>';
}

async function renderCronPanel(body) {
  const data = await getJSON('/api/cron');
  const jobs = data.jobs || [];
  body.innerHTML = jobs.length ? '<div class="cx-list">' + jobs.map((j) =>
    '<div class="cx-list-item"><span class="cx-mono">' +
    escapeHtml(j.id || j.name || '') + '</span><span class="cx-dim">' +
    escapeHtml(j.schedule || j.cron || '') + '</span>' +
    '<span class="cx-spacer"></span>' +
    '<button class="cx-btn" data-run="' + escapeHtml(j.id || '') +
    '">运行</button></div>').join('') + '</div>'
    : '<div class="cx-dim">暂无定时任务</div>';
  body.querySelectorAll('[data-run]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        await postJSON('/api/cron/' + encodeURIComponent(btn.dataset.run) +
          '/run', {});
        toast('ok', '已触发');
      } catch (err) {
        toast('error', err.message);
      }
    });
  });
}

function renderHelpPanel(body) {
  const rows = [
    ['Ctrl+P', t('cmd.palette')],
    ['Ctrl+K', t('nav.search')],
    ['Ctrl+B', '会话栏'],
    ['Shift+Tab', t('composer.hint.agents')],
    ['Esc', t('action.stop')],
    ['/new /clear /compact /undo', '会话命令'],
    ['/settings /stats /tools /models /cron /diagnose', '面板命令'],
    ['/theme /lang /export /search', '快捷命令'],
    ['@path', '引用工作区文件'],
  ];
  body.innerHTML = '<div class="cx-list">' + rows.map(([k, v]) =>
    '<div class="cx-list-item"><kbd class="cx-mono">' + escapeHtml(k) +
    '</kbd><span class="cx-spacer"></span><span class="cx-dim">' +
    escapeHtml(v) + '</span></div>').join('') + '</div>';
}

/* ------------------------------------------------------------------ *
 * 命令面板
 * ------------------------------------------------------------------ */
const COMMANDS = [
  { id: 'new', label: '新建会话', key: 'Ctrl+N', run: () => newSession() },
  { id: 'clear', label: '清空当前会话', run: () => sessionAction('clear') },
  { id: 'compact', label: '压缩上下文', run: () => sessionAction('compact') },
  { id: 'undo', label: '撤销上一步', run: () => sessionAction('undo') },
  { id: 'settings', label: '打开设置', run: () => openPanel('settings') },
  { id: 'stats', label: '打开统计', run: () => openPanel('stats') },
  { id: 'tools', label: '工具目录', run: () => openPanel('tools') },
  { id: 'models', label: '切换模型', run: () => openPanel('models') },
  { id: 'diagnose', label: '诊断', run: () => openPanel('diagnose') },
  { id: 'cron', label: '定时任务', run: () => openPanel('cron') },
  { id: 'theme', label: '切换主题', run: toggleTheme },
  { id: 'lang', label: '切换语言', run: toggleLang },
  { id: 'export', label: '导出会话', run: exportSession },
  { id: 'help', label: '帮助', key: '?', run: () => openPanel('help') },
];

let paletteIndex = 0;
let paletteRows = COMMANDS;

function openPalette() {
  const el = $('#cx-palette');
  el.dataset.open = '1';
  const input = $('#cx-palette-input');
  input.value = '';
  paletteIndex = 0;
  renderPalette('');
  input.focus();
}

function closePalette() {
  $('#cx-palette').dataset.open = '0';
}

function renderPalette(query) {
  const q = query.toLowerCase();
  paletteRows = COMMANDS.filter((c) =>
    !q || c.label.toLowerCase().includes(q) || c.id.includes(q));
  paletteIndex = Math.min(paletteIndex, Math.max(0, paletteRows.length - 1));
  $('#cx-palette-list').innerHTML = paletteRows.map((c, i) =>
    '<button class="cx-palette-item" data-i="' + i + '" aria-selected="' +
    (i === paletteIndex ? 'true' : 'false') + '">' +
    escapeHtml(c.label) + (c.key ? '<kbd>' + escapeHtml(c.key) + '</kbd>' : '') +
    '</button>').join('') || '<div class="cx-dim" style="padding:8px">无匹配</div>';
}

function runPalette() {
  const cmd = paletteRows[paletteIndex];
  closePalette();
  if (cmd) cmd.run();
}

/* ------------------------------------------------------------------ *
 * Toast
 * ------------------------------------------------------------------ */
function toast(kind, text) {
  const host = $('#cx-toasts');
  const el = document.createElement('div');
  el.className = 'cx-toast';
  el.dataset.kind = kind;
  el.textContent = text;
  host.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 200);
  }, 3200);
}

/* ------------------------------------------------------------------ *
 * 事件绑定
 * ------------------------------------------------------------------ */
function bind() {
  $('#cx-input').addEventListener('input', autoGrow);
  $('#cx-input').addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter' && !evt.shiftKey) {
      evt.preventDefault();
      submit();
    }
  });
  $('#cx-send').addEventListener('click', submit);
  $('#cx-new').addEventListener('click', () => newSession());
  $('#cx-new-2').addEventListener('click', () => newSession());
  $('#cx-theme').addEventListener('click', toggleTheme);
  $('#cx-help').addEventListener('click', () => openPanel('help'));
  $('#cx-settings').addEventListener('click', () => openPanel('settings'));
  $('#cx-stats').addEventListener('click', () => openPanel('stats'));
  $('#cx-connect').addEventListener('click', () => openPanel('settings'));
  $('#cx-model').addEventListener('click', () => openPanel('models'));
  $('#cx-compact').addEventListener('click', () => sessionAction('compact'));
  $('#cx-undo').addEventListener('click', () => sessionAction('undo'));
  $('#cx-clear').addEventListener('click', () => sessionAction('clear'));
  $('#cx-drawer').addEventListener('click', () => {
    const root = $('#cx');
    root.dataset.drawer = root.dataset.drawer === '1' ? '0' : '1';
  });
  $('#cx-search').addEventListener('input', (evt) => {
    searchTerm = evt.target.value;
    renderSessions();
  });
  $('#cx-tabs').addEventListener('click', (evt) => {
    const close = evt.target.closest('[data-close]');
    if (close) { closeTab(close.dataset.close); return; }
    const tab = evt.target.closest('.cx-tab');
    if (tab) openSession(tab.dataset.id);
  });
  $('#cx-session-list').addEventListener('click', (evt) => {
    const del = evt.target.closest('[data-del]');
    if (del) { deleteSession(del.dataset.del); return; }
    const row = evt.target.closest('.cx-session');
    if (row) {
      openSession(row.dataset.id);
      $('#cx').dataset.drawer = '0';
    }
  });
  $('#cx-session-list').addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter') {
      const row = evt.target.closest('.cx-session');
      if (row) openSession(row.dataset.id);
    }
  });

  // ask_user 卡片：事件委托到流容器（块元素每次重绘 innerHTML）
  const streamHost = $('#cx-stream');
  const findBlock = (el) => activeMessages().find(
    (b) => b.id === (el && el.dataset ? el.dataset.id : ''));
  streamHost.addEventListener('click', (evt) => {
    const optBtn = evt.target.closest('[data-ask-opt]');
    if (optBtn && !optBtn.disabled) {
      const el = optBtn.closest('.cx-msg');
      const block = findBlock(el);
      const [qi, oi] = String(optBtn.getAttribute('data-ask-opt') || '0:0')
        .split(':').map(Number);
      const q = block && block.ask && block.ask.questions[qi];
      if (q) {
        block.ask.draft[q.key] = (q.options || [])[oi] ?? '';
        paintBlock(el, block);
      }
      return;
    }
    const submitBtn = evt.target.closest('[data-ask-submit]');
    if (submitBtn && !submitBtn.disabled) {
      const block = findBlock(submitBtn.closest('.cx-msg'));
      if (block) {
        submitAsk(block, Number(submitBtn.getAttribute('data-ask-submit') || '0'));
      }
    }
  });
  streamHost.addEventListener('keydown', (evt) => {
    if (evt.key !== 'Enter') return;
    const input = evt.target.closest('.cx-ask-input');
    if (!input || input.disabled) return;
    const block = findBlock(input.closest('.cx-msg'));
    if (block) {
      evt.preventDefault();
      submitAsk(block, Number(input.getAttribute('data-ask-input') || '0'),
        input.value);
    }
  });
  $('#cx-panel-close').addEventListener('click', closePanel);
  $('#cx-overlay').addEventListener('click', (evt) => {
    if (evt.target === $('#cx-overlay')) closePanel();
  });
  $('#cx-palette-input').addEventListener('input', (evt) => {
    paletteIndex = 0;
    renderPalette(evt.target.value);
  });
  $('#cx-palette-input').addEventListener('keydown', (evt) => {
    if (evt.key === 'ArrowDown') {
      evt.preventDefault();
      paletteIndex = Math.min(paletteIndex + 1, paletteRows.length - 1);
      renderPalette(evt.target.value);
    } else if (evt.key === 'ArrowUp') {
      evt.preventDefault();
      paletteIndex = Math.max(paletteIndex - 1, 0);
      renderPalette(evt.target.value);
    } else if (evt.key === 'Enter') {
      evt.preventDefault();
      runPalette();
    }
  });
  $('#cx-palette-list').addEventListener('click', (evt) => {
    const item = evt.target.closest('.cx-palette-item');
    if (item) { paletteIndex = Number(item.dataset.i); runPalette(); }
  });
  $('#cx-palette').addEventListener('click', (evt) => {
    if (evt.target === $('#cx-palette')) closePalette();
  });

  $('#cx-attach').addEventListener('click', () => $('#cx-file').click());
  $('#cx-file').addEventListener('change', (evt) => {
    handleFiles(Array.from(evt.target.files || []));
    evt.target.value = '';
  });
  $('#cx-input').addEventListener('paste', (evt) => {
    const files = Array.from(evt.clipboardData?.files || []);
    if (files.length) {
      evt.preventDefault();
      handleFiles(files);
    }
  });
  document.addEventListener('dragover', (evt) => evt.preventDefault());
  document.addEventListener('drop', (evt) => {
    evt.preventDefault();
    const files = Array.from(evt.dataTransfer?.files || []);
    if (files.length) handleFiles(files);
  });

  document.addEventListener('keydown', (evt) => {
    const mod = evt.ctrlKey || evt.metaKey;
    if (mod && evt.key.toLowerCase() === 'p') {
      evt.preventDefault();
      openPalette();
    } else if (mod && evt.key.toLowerCase() === 'k') {
      evt.preventDefault();
      $('#cx-search').focus();
    } else if (mod && evt.key.toLowerCase() === 'b') {
      evt.preventDefault();
      const root = $('#cx');
      root.dataset.drawer = root.dataset.drawer === '1' ? '0' : '1';
    } else if (evt.key === 'Tab' && evt.shiftKey) {
      evt.preventDefault();
      setMode(MODES.indexOf(state.mode) >= 0
        ? MODES[(MODES.indexOf(state.mode) + 1) % MODES.length] : 'build');
    } else if (evt.key === 'Escape') {
      if ($('#cx-palette').dataset.open === '1') closePalette();
      else if ($('#cx-overlay').dataset.open === '1') closePanel();
      else if (state.busy) stop();
    } else if (evt.key === '?' && !mod &&
               !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      openPanel('help');
    }
  });

  // 安全：网关 401 时提示补 token
  window.addEventListener(EVENT_401, () => {
    toast('warn', t('toast.gatewayToken'));
  });
}

async function handleFiles(files) {
  const host = $('#cx-attachments');
  host.hidden = false;
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      const item = document.createElement('div');
      item.className = 'cx-attach';
      item.innerHTML = '<img src="' + url + '" alt="' +
        escapeHtml(file.name) + '"><button aria-label="移除">×</button>';
      item.querySelector('button').addEventListener('click', () => {
        item.remove();
        if (!host.children.length) host.hidden = true;
      });
      host.appendChild(item);
    }
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await apiFetch('/api/upload', { method: 'POST', body: form });
      const data = await res.json();
      const mention = data.path || data.rel || data.name;
      if (mention) {
        const input = $('#cx-input');
        input.value += (input.value && !input.value.endsWith(' ') ? ' ' : '') +
          '@' + mention + ' ';
        autoGrow();
      }
    } catch (err) {
      toast('error', '上传失败：' + err.message);
    }
  }
}

/* ------------------------------------------------------------------ *
 * 启动
 * ------------------------------------------------------------------ */
function scheduleRepaint(blockId) {
  if (pendingFrame) return;
  pendingFrame = requestAnimationFrame(() => {
    pendingFrame = 0;
    const el = blockEls.get(blockId);
    const block = activeMessages().find((b) => b.id === blockId);
    if (el && block) {
      paintBlock(el, block);
      scrollToBottom();
    } else {
      renderTranscript();
    }
  });
}

async function boot() {
  loadPrefs();
  bind();
  renderStatus();
  renderTranscript();

  on('sessions', () => { renderSessions(); renderTabs(); });
  on('tabs', renderTabs);
  on('active', () => {
    renderTabs();
    renderSessions();
    renderTranscript(true);
    renderStatus();
  });
  on('messages', (sid) => {
    if (sid && sid !== state.activeId) return;
    renderTranscript();
  });
  on('delta', ({ blockId }) => scheduleRepaint(blockId));
  on('busy', renderStatus);
  on('context', renderStatus);
  on('models', renderStatus);
  on('config', renderStatus);
  on('toast', ({ kind, text }) => toast(kind, text));
  on('ask', ({ ask }) => {
    const q0 = ask && ask.questions && ask.questions[0];
    toast('warn', (ask && ask.header ? ask.header + '：' :
      t('ask.title') + '：') + (q0 && q0.question || ''));
  });

  await loadConfig();
  state.context.limit = Number(
    state.config.context_limit || state.config.max_context || 0) ||
    DEFAULT_LIMIT;
  await refreshSessions();
  const first = state.activeId || (state.sessions[0] && state.sessions[0].id);
  if (first) await openSession(first);
  renderStatus();
  loadModels();
  setInterval(renderStatus, 15000);   // 会话中的实时耗时/心跳
}

boot().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML('afterbegin',
    '<pre class="cx-error" style="padding:12px">启动失败：' +
    escapeHtml(String(err && err.message || err)) + '</pre>');
});
