/* 会话/消息状态机（与皮肤无关）。
 *
 * 设计要点：
 *  1. 一会话一份状态 —— 服务端已按 session_id 分发（M0），前端按 id 缓存；
 *  2. 流式增量只发事件，不整篇重排 —— 上层只重渲染"脏块"；
 *  3. 每个 block 有稳定 id，DOM 复用靠 id 对账，避免长会话抖动。
 */

import { SSEClient, getJSON, postJSON, apiFetch } from './transport.js';

const listeners = new Map();

export function on(evt, fn) {
  if (!listeners.has(evt)) listeners.set(evt, new Set());
  listeners.get(evt).add(fn);
  return () => listeners.get(evt).delete(fn);
}

export function emit(evt, payload) {
  const set = listeners.get(evt);
  if (!set) return;
  for (const fn of set) {
    try { fn(payload); } catch (err) { console.error(evt, err); }
  }
}

let blockSeq = 0;
function nextId(prefix) { blockSeq += 1; return prefix + '-' + blockSeq; }

export const state = {
  ready: false,
  lang: 'zh',
  theme: 'dark',
  sessions: [],
  tabs: [],              // 打开的会话 id
  activeId: '',
  models: [],
  model: '',
  config: {},
  context: { tokens: 0, limit: 0, percent: 0 },
  cost: { usd: 0, calls: 0 },
  busy: false,
  mode: 'build',         // build | plan | ask（copilot 级，POST /api/config）
  offline: false,
  /** session_id -> 消息块数组 */
  messages: new Map(),
  /** session_id -> 在途 SSE 连接 */
  streams: new Map(),
};

export function messagesOf(sessionId) {
  if (!state.messages.has(sessionId)) state.messages.set(sessionId, []);
  return state.messages.get(sessionId);
}

export function activeMessages() {
  return messagesOf(state.activeId || 'default');
}

/* ------------------------------------------------------------------ *
 * 会话操作
 * ------------------------------------------------------------------ */

export async function refreshSessions() {
  try {
    const data = await getJSON('/api/sessions');
    state.sessions = data.sessions || [];
    if (!state.activeId && data.current) state.activeId = data.current;
    state.offline = false;
  } catch (err) {
    state.offline = true;
  }
  emit('sessions', state.sessions);
}

export async function openSession(id) {
  if (!id) return;
  // 注意：emit('active') 会让视图立刻读一次 activeMessages()，而
  // messagesOf() 会给该会话建一个空数组。所以「是否已加载」必须在
  // emit 之前判定，否则永远命中下面的早退分支、历史永远拉不下来。
  const alreadyLoaded = state.messages.has(id);
  if (!state.tabs.includes(id)) state.tabs.push(id);
  state.activeId = id;
  emit('tabs', state.tabs);
  emit('active', id);
  if (alreadyLoaded) return;
  try {
    const data = await getJSON(
      '/api/sessions/' + encodeURIComponent(id) + '/messages');
    const blocks = [];
    for (const m of data.messages || []) {
      if (m.role === 'user') {
        blocks.push({ id: nextId('u'), role: 'user',
                      text: m.content || '' });
      } else if (m.role === 'assistant') {
        blocks.push({ id: nextId('a'), role: 'assistant',
                      text: m.content || '', reasoning: '',
                      tools: [], usage: null });
      }
    }
    state.messages.set(id, blocks);
    if (data.title) {
      const row = state.sessions.find((s) => s.id === id);
      if (row) row.title = data.title;
    }
    emit('messages', id);
    emit('context', {});
  } catch (err) {
    emit('toast', { kind: 'error', text: '会话读取失败：' + err.message });
  }
}

export function closeTab(id) {
  state.tabs = state.tabs.filter((t) => t !== id);
  if (state.activeId === id) {
    state.activeId = state.tabs[state.tabs.length - 1] || '';
    emit('active', state.activeId);
  }
  emit('tabs', state.tabs);
}

export async function newSession() {
  try {
    const data = await postJSON('/api/sessions', {});
    await refreshSessions();
    await openSession(data.id);
    return data.id;
  } catch (err) {
    emit('toast', { kind: 'error', text: '新建会话失败：' + err.message });
    return '';
  }
}

export async function deleteSession(id) {
  try {
    await apiRaw('/api/sessions/' + encodeURIComponent(id), 'DELETE');
    state.messages.delete(id);
    closeTab(id);
    await refreshSessions();
    emit('toast', { kind: 'ok', text: '会话已删除' });
  } catch (err) {
    emit('toast', { kind: 'error', text: '删除失败：' + err.message });
  }
}

/* 网关带 token 时，/api/* 一律要求 Authorization。这里必须走
 * transport.apiFetch（带鉴权头 + 401 广播），裸 fetch 会直接 401。
 */
async function apiRaw(url, method) {
  const res = await apiFetch(url, { method: method });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

/* ------------------------------------------------------------------ *
 * 发送 / 流
 * ------------------------------------------------------------------ */

export function send(text, opts = {}) {
  const trimmed = (text || '').trim();
  if (!trimmed || state.busy) return;
  const sid = state.activeId || 'default';
  const blocks = messagesOf(sid);

  blocks.push({ id: nextId('u'), role: 'user', text: trimmed });
  const assistant = { id: nextId('a'), role: 'assistant', text: '',
                      reasoning: '', tools: [], usage: null,
                      streaming: true, startedAt: Date.now() };
  blocks.push(assistant);
  state.busy = true;
  emit('messages', sid);
  emit('busy', true);

  const client = new SSEClient('/api/chat/stream', {
    onEvent: (evt) => handleEvent(sid, assistant, evt),
    onDone: () => {
      assistant.streaming = false;
      state.busy = false;
      state.streams.delete(sid);
      emit('messages', sid);
      emit('busy', false);
      refreshSessions();
    },
    onError: (err) => {
      assistant.streaming = false;
      assistant.error = String(err && err.message || err);
      state.busy = false;
      state.streams.delete(sid);
      emit('messages', sid);
      emit('busy', false);
      emit('toast', { kind: 'error', text: '连接中断：' + assistant.error });
    },
  });
  state.streams.set(sid, client);
  client.start({
    message: trimmed,
    session_id: state.activeId === 'default' ? '' : sid,
    auto_approve: !!opts.autoApprove,
  });
}

function handleEvent(sid, assistant, evt) {
  const type = evt.type || 'message';
  switch (type) {
    case 'content':
      assistant.text += evt.delta || evt.text || '';
      emit('delta', { sid, blockId: assistant.id });
      break;
    case 'reasoning':
      assistant.reasoning = (assistant.reasoning || '') +
        (evt.delta || evt.text || '');
      emit('delta', { sid, blockId: assistant.id, reasoning: true });
      break;
    case 'tool_start':
    case 'tool_call':
    case 'tool_progress': {
      // call_id 才是同一次调用的身份：同一个工具会被调用多次，
      // 用 name 当 key 会把多次调用揉进一张卡。
      const key = evt.call_id || evt.tool || evt.name || evt.tool_name ||
        'tool';
      let tool = assistant.tools.find((t) => t.key === key && !t.done);
      if (!tool) {
        tool = { key, name: evt.name || evt.tool || key, args: '',
                 status: 'running', ms: 0 };
        assistant.tools.push(tool);
      }
      if (evt.target !== undefined) tool.args = evt.target;
      if (evt.args !== undefined) tool.args = evt.args;
      if (evt.message) tool.status = evt.message;
      if (evt.delta) tool.status = evt.delta;
      if (type === 'tool_call') {
        // core.py:_log_tool 里 tool_call 是「收尾」事件（带
        // result/summary/status/duration），不是开始事件。
        tool.done = true;
        tool.failed = String(evt.status || '').toLowerCase() === 'error';
        tool.result = evt.result || '';
        tool.status = evt.summary || evt.status || 'done';
      }
      if (evt.duration !== undefined) tool.ms = Math.round(evt.duration * 1000);
      emit('messages', sid);
      break;
    }
    case 'usage':
      assistant.usage = evt;
      state.context = {
        tokens: evt.total_tokens || state.context.tokens,
        limit: state.context.limit,
        percent: state.context.limit
          ? Math.round((evt.total_tokens / state.context.limit) * 100)
          : state.context.percent,
      };
      emit('context', state.context);
      break;
    case 'ask_user':
      // 内核通过网关提问（写文件 / 危险 shell 的确认)。问题挂到当前
      // 助手块上，UI 渲染成可点击的选项卡；回答走 /api/ask/answer。
      assistant.ask = {
        id: evt.id,
        header: evt.header || '',
        questions: (evt.questions || []).map((q) => ({
          key: q.key ?? '',
          question: q.question ?? q.title ?? '',
          options: Array.isArray(q.options) ? q.options : [],
          default: q.default ?? '',
          allow_custom: q.allow_custom !== false,
        })),
        draft: {},
        answered: false,
      };
      emit('ask', { sid, blockId: assistant.id, ask: assistant.ask });
      emit('messages', sid);
      break;
    case 'error':
      assistant.error = evt.message || '未知错误';
      assistant.streaming = false;
      emit('messages', sid);
      break;
    case 'aborted':
      assistant.aborted = true;
      assistant.streaming = false;
      break;
    case 'done':
      if (evt.answer) assistant.text = evt.answer;
      if (evt.usage) assistant.usage = evt.usage;
      if (evt.duration !== undefined) {
        assistant.duration = evt.duration;
      }
      break;
    default:
      break;
  }
}

export function stop() {
  const sid = state.activeId || 'default';
  const client = state.streams.get(sid);
  if (client) client.stop();
  apiFetch('/api/chat/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sid === 'default' ? '' : sid }),
  }).catch(() => {});
  state.busy = false;
  emit('busy', false);
}

/* ------------------------------------------------------------------ *
 * 提问回答（ask_user → /api/ask/answer）
 * ------------------------------------------------------------------ */

/** 把一套问题的回答提交给内核。answers 形如 {key: value}。 */
export async function answerAsk(askId, answers) {
  const data = await postJSON('/api/ask/answer', {
    id: askId,
    answers: answers || {},
  });
  if (data && data.ok === false) {
    throw new Error(data.error || '提问已超时或已被回答');
  }
  return data;
}

export async function sessionAction(action) {
  const sid = state.activeId || '';
  const url = '/api/chat/' + action +
    (sid && sid !== 'default'
      ? '?session=' + encodeURIComponent(sid) : '');
  try {
    const res = await apiFetch(url, { method: 'POST' });
    const data = await res.json();
    if (data.busy) {
      emit('toast', { kind: 'warn', text: '会话正忙，稍后再试' });
      return data;
    }
    if (!data.ok) {
      emit('toast', { kind: 'warn', text: data.error || '操作未完成' });
      return data;
    }
    if (action === 'clear') {
      state.messages.set(state.activeId || 'default', []);
      emit('messages', state.activeId || 'default');
    } else {
      await reloadActive();
    }
    emit('toast', { kind: 'ok', text: '已' + ({
      undo: '撤销', compact: '压缩', clear: '清空' }[action] || action) });
    return data;
  } catch (err) {
    emit('toast', { kind: 'error', text: err.message });
    return null;
  }
}

async function reloadActive() {
  const sid = state.activeId;
  if (!sid) return;
  state.messages.delete(sid);
  await openSession(sid);
}

/* ------------------------------------------------------------------ *
 * 模型与配置
 * ------------------------------------------------------------------ */

export async function loadModels() {
  try {
    const data = await getJSON('/api/models');
    state.models = data.models || [];
    emit('models', state.models);
  } catch (err) {
    state.models = [];
  }
}

export async function loadConfig() {
  try {
    state.config = await getJSON('/api/config');
    if (state.config.model) state.model = state.config.model;
    if (state.config.lang) state.lang = state.config.lang;
    if (state.config.theme) state.theme = state.config.theme;
    if (state.config.plan_mode) state.mode = 'plan';
    else if (state.config.access_mode === 'allow') state.mode = 'build';
    emit('config', state.config);
  } catch (err) { /* 首次运行可能还没有配置 */ }
}

export function setLang(lang) {
  state.lang = lang === 'en' ? 'en' : 'zh';
  emit('lang', state.lang);
}

/* ------------------------------------------------------------------ *
 * 模式（Build / Plan / Ask）
 *
 * 内核没有 per-message 的模式参数，模式是 copilot 级别的状态：
 *   plan  -> plan_mode = true   （只读工具 + PLAN system prompt）
 *   build -> plan_mode = false  （完整工具箱）
 *   ask   -> plan_mode = false + access_mode = "ask"（每步都要确认）
 * 切换走 POST /api/config，与 TUI / config.toml 是同一个真相。
 * ------------------------------------------------------------------ */

export const MODES = ['build', 'plan', 'ask'];

const MODE_PAYLOAD = {
  build: { plan_mode: false },
  plan: { plan_mode: true },
  ask: { plan_mode: false, access_mode: 'ask' },
};

export async function setMode(next) {
  if (!MODES.includes(next)) return;
  try {
    await postJSON('/api/config', MODE_PAYLOAD[next]);
  } catch (err) {
    emit('toast', { kind: 'error', text: '模式切换失败：' + err.message });
    return;
  }
  state.mode = next;
  emit('mode', state.mode);
  emit('toast', { kind: 'ok', text: '已切换到 ' + next + ' 模式' });
}

export function setTheme(theme) {
  state.theme = theme === 'light' ? 'light' : 'dark';
  document.documentElement.classList.toggle(
    'theme-light', state.theme === 'light');
  emit('theme', state.theme);
}
