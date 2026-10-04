/* ═══════════════════════════════════════════════════════════════ */
/*  One Cedric WebUI · app.js                                       */
/* ═══════════════════════════════════════════════════════════════ */
const { createApp, ref, reactive, computed, onMounted, nextTick, watch } = Vue;

const LS_SETTINGS  = 'cedric_webui_settings_v1';
const LS_SESSIONS  = 'cedric_webui_sessions_v1';
const LS_LANG      = 'cedric_webui_lang_v1';
const LS_THEME     = 'cedric_webui_theme_v1';
const MAX_SESSIONS = 40;

const I18N = {
  zh: {
    'topbar.toggleSidebar': '切换侧栏 (Ctrl+B)',
    'topbar.model': '模型',
    'topbar.stats': '{req} 请求 · {err} 错误',
    'topbar.switchLang': '切换语言',
    'topbar.newSession': '新会话 (Ctrl+K)',
    'topbar.settings': '设置 (Ctrl+,)',
    'topbar.help': '快捷键 (?)',
    'sidebar.title': '会话',
    'sidebar.new': '新会话',
    'sidebar.untitled': '新会话',
    'sidebar.msgs': '条',
    'sidebar.delete': '删除',
    'sidebar.empty': '暂无会话',
    'sidebar.connected': '已连接',
    'sidebar.disconnected': '未连接',
    'welcome.sub': '本地文件助手 · HTTP Gateway',
    'welcome.suggestions': ['这个目录里有什么文件', '读一下 README.md 讲讲项目', '统计一下项目代码量', '帮我搜索一下今天的新闻'],
    'msg.copy': '复制',
    'msg.edit': '编辑并重发',
    'msg.regenerate': '重新生成',
    'msg.reasoning': '思考过程',
    'msg.chars': '{n} 字',
    'msg.scrollBottom': '回到底部',
    'input.placeholder': '输入消息… (Enter 发送 · Shift+Enter 换行 · ↑ 翻历史)',
    'input.autoApprove': '自动确认',
    'input.send': '发送',
    'input.stop': '停止',
    'settings.title': '设置',
    'settings.model': '模型',
    'settings.host': 'API 地址',
    'settings.apiKey': 'API Key',
    'settings.apiKeyHint': '（可选）',
    'settings.temperature': '温度',
    'settings.thinkLevel': '思考模式',
    'settings.think.minimal': 'minimal · 直接回答',
    'settings.think.low': 'low · 简短推理',
    'settings.think.medium': 'medium · 标准',
    'settings.think.max': 'max · 深入',
    'settings.think.xhigh': 'xhigh · 多角度',
    'settings.think.ultra': 'ultra · 穷尽',
    'settings.showReasoning': '显示推理过程',
    'settings.tools': '工具',
    'settings.toolsLoading': '加载中…',
    'settings.data': '数据',
    'settings.clearMessages': '清空当前会话消息',
    'settings.clearAllSessions': '删除所有本地会话',
    'settings.clear': '清空',
    'settings.delete': '删除',
    'settings.done': '完成',
    'help.title': '快捷键',
    'help.send': '发送消息',
    'help.newline': '换行',
    'help.historyUp': '上一条历史',
    'help.historyDown': '下一条历史',
    'help.newSession': '新会话',
    'help.toggleSidebar': '切换侧栏',
    'help.openSettings': '打开设置',
    'help.closeLayer': '关闭弹层',
    'help.thisHelp': '本帮助',
    'toast.copied': '消息已复制',
    'toast.codeCopied': '代码已复制',
    'toast.copyFailed': '复制失败',
    'toast.settingsSaved': '设置已保存',
    'toast.toolOn': '{name} 已启用',
    'toast.toolOff': '{name} 已禁用',
    'toast.opFailed': '操作失败',
    'toast.stopped': '已停止',
    'toast.langSwitched': '已切换为中文',
    'confirm.clearMessages': '清空当前会话的所有消息？',
    'confirm.clearAll': '删除所有本地会话？此操作不可撤销。',
    'time.justNow': '刚刚',
    'time.minutesAgo': '{n} 分钟前',
    'time.hoursAgo': '{n} 小时前',
    'time.daysAgo': '{n} 天前',
    'err.httpStatus': 'HTTP {status}',
  },
  en: {
    'topbar.toggleSidebar': 'Toggle sidebar (Ctrl+B)',
    'topbar.model': 'Model',
    'topbar.stats': '{req} requests · {err} errors',
    'topbar.switchLang': 'Switch language',
    'topbar.newSession': 'New session (Ctrl+K)',
    'topbar.settings': 'Settings (Ctrl+,)',
    'topbar.help': 'Shortcuts (?)',
    'sidebar.title': 'Sessions',
    'sidebar.new': 'New session',
    'sidebar.untitled': 'New session',
    'sidebar.msgs': 'msgs',
    'sidebar.delete': 'Delete',
    'sidebar.empty': 'No sessions yet',
    'sidebar.connected': 'Connected',
    'sidebar.disconnected': 'Disconnected',
    'welcome.sub': 'Local file assistant · HTTP Gateway',
    'welcome.suggestions': ['What files are in this directory', 'Read README.md and explain the project', 'Count lines of code in the project', 'Search for today\'s news'],
    'msg.copy': 'Copy',
    'msg.edit': 'Edit & resend',
    'msg.regenerate': 'Regenerate',
    'msg.reasoning': 'Reasoning',
    'msg.chars': '{n} chars',
    'msg.scrollBottom': 'Scroll to bottom',
    'input.placeholder': 'Type a message… (Enter to send · Shift+Enter for newline · ↑ for history)',
    'input.autoApprove': 'Auto-confirm',
    'input.send': 'Send',
    'input.stop': 'Stop',
    'settings.title': 'Settings',
    'settings.model': 'Model',
    'settings.host': 'API endpoint',
    'settings.apiKey': 'API Key',
    'settings.apiKeyHint': '(optional)',
    'settings.temperature': 'Temperature',
    'settings.thinkLevel': 'Think level',
    'settings.think.minimal': 'minimal · direct',
    'settings.think.low': 'low · brief',
    'settings.think.medium': 'medium · standard',
    'settings.think.max': 'max · deep',
    'settings.think.xhigh': 'xhigh · multi-angle',
    'settings.think.ultra': 'ultra · exhaustive',
    'settings.showReasoning': 'Show reasoning trace',
    'settings.tools': 'Tools',
    'settings.toolsLoading': 'Loading…',
    'settings.data': 'Data',
    'settings.clearMessages': 'Clear current session messages',
    'settings.clearAllSessions': 'Delete all local sessions',
    'settings.clear': 'Clear',
    'settings.delete': 'Delete',
    'settings.done': 'Done',
    'help.title': 'Keyboard shortcuts',
    'help.send': 'Send message',
    'help.newline': 'Newline',
    'help.historyUp': 'Previous input',
    'help.historyDown': 'Next input',
    'help.newSession': 'New session',
    'help.toggleSidebar': 'Toggle sidebar',
    'help.openSettings': 'Open settings',
    'help.closeLayer': 'Close overlay',
    'help.thisHelp': 'This help',
    'toast.copied': 'Copied',
    'toast.codeCopied': 'Code copied',
    'toast.copyFailed': 'Copy failed',
    'toast.settingsSaved': 'Settings saved',
    'toast.toolOn': '{name} enabled',
    'toast.toolOff': '{name} disabled',
    'toast.opFailed': 'Operation failed',
    'toast.stopped': 'Stopped',
    'toast.langSwitched': 'Switched to English',
    'confirm.clearMessages': 'Clear all messages in the current session?',
    'confirm.clearAll': 'Delete all local sessions? This cannot be undone.',
    'time.justNow': 'just now',
    'time.minutesAgo': '{n}m ago',
    'time.hoursAgo': '{n}h ago',
    'time.daysAgo': '{n}d ago',
    'err.httpStatus': 'HTTP {status}',
  },
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}
function fmtBytes(value) {
  let size = Math.max(0, Number(value) || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit++;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}
function loadLocalSettings() {
  try { return JSON.parse(localStorage.getItem(LS_SETTINGS) || '{}'); }
  catch { return {}; }
}
function persistSettings(s) {
  try { localStorage.setItem(LS_SETTINGS, JSON.stringify(s)); } catch {}
}
function loadLocalSessions() {
  try {
    const a = JSON.parse(localStorage.getItem(LS_SESSIONS) || '[]');
    return Array.isArray(a) ? a : [];
  } catch { return []; }
}
function persistSessions(list) {
  try { localStorage.setItem(LS_SESSIONS, JSON.stringify(list.slice(0, MAX_SESSIONS))); } catch {}
}

/* ── Marked renderer ── */
const renderer = new marked.Renderer();
renderer.code = ({ text, lang }) => {
  const language = (lang || '').trim().toLowerCase();
  let highlighted;
  try {
    if (language && window.hljs && hljs.getLanguage(language)) {
      highlighted = hljs.highlight(text, { language }).value;
    } else if (window.hljs) {
      highlighted = hljs.highlightAuto(text).value;
    } else {
      highlighted = escapeHtml(text);
    }
  } catch { highlighted = escapeHtml(text); }
  const langLabel = language || 'text';
  const encoded = encodeURIComponent(text);
  return `<div class="code-block">
    <div class="code-head">
      <span class="code-lang">${escapeHtml(langLabel)}</span>
      <button class="copy-code" data-code="${encoded}" type="button">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        <span class="copy-code-label">COPY</span>
      </button>
    </div>
    <pre><code class="hljs language-${escapeHtml(langLabel)}">${highlighted}</code></pre>
  </div>`;
};
renderer.link = ({ href, title, text }) => {
  const t = title ? ` title="${escapeHtml(title)}"` : '';
  return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer"${t}>${text}</a>`;
};
marked.setOptions({ renderer, breaks: true, gfm: true });

/* ═══════════════════════════════════════════════════════════════ */
/*  Vue App                                                         */
/* ═══════════════════════════════════════════════════════════════ */
createApp({
  setup() {
    /* ── i18n ── */
    const lang = ref(localStorage.getItem(LS_LANG) || 'zh');
    function t(key, params) {
      const table = I18N[lang.value] || I18N.zh;
      let s = table[key];
      if (s === undefined) s = I18N.zh[key];
      if (s === undefined) return key;
      if (params && typeof s === 'string') {
        for (const k in params) {
          s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), params[k]);
        }
      }
      return s;
    }
    function setLang(l) {
      lang.value = (l === 'en' ? 'en' : 'zh');
      localStorage.setItem(LS_LANG, lang.value);
      document.documentElement.lang = lang.value === 'zh' ? 'zh-CN' : 'en';
    }
    function toggleLang() {
      setLang(lang.value === 'zh' ? 'en' : 'zh');
      toast(t('toast.langSwitched'));
    }

    /* ── theme ── */
    const theme = ref(localStorage.getItem(LS_THEME) ||
      (window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
    function toggleTheme() {
      theme.value = theme.value === 'dark' ? 'light' : 'dark';
      localStorage.setItem(LS_THEME, theme.value);
    }
    const largeText = ref(localStorage.getItem('cedric_webui_large_text') === 'true');
    function toggleLargeText() {
      largeText.value = !largeText.value;
      localStorage.setItem('cedric_webui_large_text', String(largeText.value));
    }

    /* ── state ── */
    const messages = ref([]);
    const input = ref('');
    const streaming = ref(false);
    const showSettings = ref(false);
    const showHelp = ref(false);
    const showSearch = ref(false);
    const sidebarOpen = ref(true);
    const sidebarTab = ref('sessions');
    const sessions = ref([]);
    const currentSessionId = ref('');
    const gatewayOnline = ref(false);
    const gatewayStats = ref({ requests: 0, errors: 0, uptime: 0 });
    const autoApprove = ref(false);
    const tools = ref([]);
    const toolsFilter = ref('');
    const toolsCategory = ref('all');
    const showScrollBtn = ref(false);
    const toasts = ref([]);
    const inputHistory = ref([]);
    const historyIndex = ref(-1);
    const askUser = ref(null);
    const askThreadExpanded = ref({});
    const searchQuery = ref('');
    const appliedSearch = ref('');
    const searchActive = computed(() => appliedSearch.value.trim().length > 0);
    const matchedMessageCount = ref(0);
    const streamSpeed = ref(0);
    const ctxMenu = reactive({ show: false, x: 0, y: 0, msgId: '', role: '', content: '' });

    const savedSettings = loadLocalSettings();
    const settings = reactive({
      model: savedSettings.model || '',
      host: savedSettings.host || '',
      api_key: savedSettings.api_key || '',
      temperature: savedSettings.temperature ?? 0.2,
      think_level: savedSettings.think_level || 'medium',
      show_reasoning: savedSettings.show_reasoning !== false,
    });

    const messagesEl = ref(null);
    const inputEl = ref(null);
    const searchInputEl = ref(null);
    let abortController = null;
    let streamStartTime = 0;
    let streamCharCount = 0;
    let streamSpeedTimer = null;

    /* ── computed ── */
    const model = computed(() => settings.model || '(未设置)');
    const currentSession = computed(() =>
      sessions.value.find(s => s.id === currentSessionId.value)
    );
    const suggestions = computed(() => t('welcome.suggestions'));
    const lastUserIndex = computed(() => {
      for (let i = messages.value.length - 1; i >= 0; i--) {
        if (messages.value[i].role === 'user') return i;
      }
      return -1;
    });
    const lastUserIndexInAll = lastUserIndex;
    const askCount = computed(() => {
      const s = currentSession.value;
      return s && s.asks ? s.asks.length : 0;
    });
    const askThreads = computed(() => {
      const s = currentSession.value;
      if (!s || !s.asks || !s.asks.length) return [];
      const map = {};
      const order = [];
      for (const rec of s.asks) {
        const th = rec.thread || rec.id;
        if (!map[th]) {
          map[th] = { id: th, records: [], header: rec.header || '' };
          order.push(th);
        }
        map[th].records.push(rec);
      }
      return order.map(id => map[id]);
    });

    function _evalShowIf(si, answers) {
      if (!si || typeof si !== 'object') return true;
      if (Array.isArray(si.all)) return si.all.every(x => _evalShowIf(x, answers));
      if (Array.isArray(si.any)) {
        if (si.any.length === 0) return true;
        return si.any.some(x => _evalShowIf(x, answers));
      }
      const dep = si.key || '';
      if (!dep) return true;
      const val = String(answers[dep] ?? '');
      if ('equals' in si) return val === String(si.equals);
      if ('not_equals' in si) return val !== String(si.not_equals);
      if (Array.isArray(si.in)) return si.in.map(String).includes(val);
      return true;
    }

    const visibleAskQuestions = computed(() => {
      const ask = askUser.value;
      if (!ask) return [];
      const answers = {};
      const vis = [];
      for (const q of ask.questions) {
        let v = '';
        if (q.selected >= 0 && q.selected < q.options.length) v = q.options[q.selected];
        else if (q.answer && q.answer.trim()) v = q.answer.trim();
        else if (q.default) v = q.default;
        const visible = _evalShowIf(q.show_if, answers);
        q._visible = visible;
        if (visible) vis.push(q);
        answers[q.key] = v;
      }
      return vis;
    });

    const filteredTools = computed(() => {
      let list = tools.value;
      const q = toolsFilter.value.trim().toLowerCase();
      if (q) list = list.filter(x => x.name.toLowerCase().includes(q));
      if (toolsCategory.value === 'on') list = list.filter(x => x.enabled);
      else if (toolsCategory.value === 'off') list = list.filter(x => !x.enabled);
      return list;
    });

    const filteredMessages = computed(() => {
      const q = appliedSearch.value.trim().toLowerCase();
      if (!q) {
        matchedMessageCount.value = 0;
        return messages.value;
      }
      const match = messages.value.filter(m =>
        (m.content || '').toLowerCase().includes(q)
      );
      matchedMessageCount.value = match.length;
      return messages.value;
    });

    function isMatch(m) {
      const q = appliedSearch.value.trim().toLowerCase();
      if (!q) return true;
      return (m.content || '').toLowerCase().includes(q);
    }

    /* ── toast ── */
    function toast(text) {
      const id = uid();
      toasts.value.push({ id, text });
      setTimeout(() => {
        toasts.value = toasts.value.filter(x => x.id !== id);
      }, 1800);
    }

    /* ── copy ── */
    async function copyText(text, msg = t('toast.copied')) {
      try {
        await navigator.clipboard.writeText(text);
        toast(msg);
      } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); toast(msg); }
        catch { toast(t('toast.copyFailed')); }
        document.body.removeChild(ta);
      }
    }

    function renderMarkdown(text) {
      if (!text) return '';
      try { return marked.parse(text); }
      catch { return escapeHtml(text); }
    }

    function fmtTime(ts) {
      if (!ts) return '';
      const diff = (Date.now() - ts) / 1000;
      if (diff < 60) return t('time.justNow');
      if (diff < 3600) return t('time.minutesAgo', { n: Math.floor(diff / 60) });
      if (diff < 86400) return t('time.hoursAgo', { n: Math.floor(diff / 3600) });
      if (diff < 86400 * 7) return t('time.daysAgo', { n: Math.floor(diff / 86400) });
      return new Date(ts).toLocaleDateString();
    }

    /* ── sessions ── */
    function newSession() {
      if (streaming.value) return;
      const id = uid();
      sessions.value.unshift({
        id, title: '', messages: [], asks: [], turnCounter: 0,
        createdAt: Date.now(), updatedAt: Date.now(),
      });
      persistSessions(sessions.value);
      currentSessionId.value = id;
      messages.value = [];
      nextTick(() => inputEl.value?.focus());
    }
    function ensureSession() {
      if (!currentSessionId.value) newSession();
    }
    function saveCurrentSession() {
      const s = currentSession.value;
      if (!s) return;
      s.messages = messages.value.map(m => ({
        role: m.role, content: m.content, reasoning: m.reasoning,
        toolCalls: m.toolCalls, meta: m.meta,
      }));
      s.updatedAt = Date.now();
      if (!s.title) {
        const firstUser = messages.value.find(m => m.role === 'user');
        if (firstUser) {
          s.title = firstUser.content.slice(0, 24) + (firstUser.content.length > 24 ? '…' : '');
        }
      }
      persistSessions(sessions.value);
    }
    function switchSession(id) {
      if (streaming.value || id === currentSessionId.value) return;
      const s = sessions.value.find(x => x.id === id);
      if (!s) return;
      saveCurrentSession();
      currentSessionId.value = id;
      messages.value = (s.messages || []).map(m => ({
        _id: uid(),
        role: m.role,
        content: m.content || '',
        reasoning: m.reasoning || '',
        toolCalls: (m.toolCalls || []).map(tc => ({ ...tc })),
        streaming: false,
        meta: m.meta || '',
        _expanded: false,
      }));
      if (!Array.isArray(s.asks)) s.asks = [];
      if (typeof s.turnCounter !== 'number') s.turnCounter = 0;
      nextTick(() => scrollToBottom(true));
    }
    function deleteSession(id) {
      if (streaming.value) return;
      const idx = sessions.value.findIndex(s => s.id === id);
      if (idx === -1) return;
      sessions.value.splice(idx, 1);
      persistSessions(sessions.value);
      if (id === currentSessionId.value) {
        if (sessions.value.length > 0) switchSession(sessions.value[0].id);
        else newSession();
      }
    }
    function clearMessages() {
      if (streaming.value) return;
      if (!confirm(t('confirm.clearMessages'))) return;
      messages.value = [];
      const s = currentSession.value;
      if (s) { s.messages = []; s.updatedAt = Date.now(); persistSessions(sessions.value); }
      showSettings.value = false;
    }
    function clearAllSessions() {
      if (!confirm(t('confirm.clearAll'))) return;
      sessions.value = [];
      persistSessions([]);
      showSettings.value = false;
      newSession();
    }

    /* ── edit/regenerate ── */
    function editMessage(index) {
      if (streaming.value) return;
      const m = messages.value[index];
      if (!m || m.role !== 'user') return;
      messages.value = messages.value.slice(0, index);
      input.value = m.content;
      nextTick(() => { autoResize(); inputEl.value?.focus(); });
    }
    function regenerate() {
      if (streaming.value) return;
      const idx = lastUserIndex.value;
      if (idx === -1) return;
      const userMsg = messages.value[idx];
      messages.value = messages.value.slice(0, idx);
      send(userMsg.content);
    }

    /* ── scroll ── */
    function isNearBottom() {
      const el = messagesEl.value;
      if (!el) return true;
      return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }
    function onMessagesScroll() {
      showScrollBtn.value = !isNearBottom();
    }
    function scrollToBottom(force = false) {
      nextTick(() => {
        const el = messagesEl.value;
        if (!el) return;
        if (force || isNearBottom()) el.scrollTop = el.scrollHeight;
      });
    }

    /* ── input ── */
    function autoResize() {
      const el = inputEl.value;
      if (!el) return;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 220) + 'px';
    }
    function onKeydown(e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault(); send(); return;
      }
      if (e.key === 'ArrowUp' && !e.shiftKey && input.value.trim() === '') {
        if (inputHistory.value.length === 0) return;
        e.preventDefault();
        const idx = historyIndex.value === -1
          ? inputHistory.value.length - 1
          : Math.max(0, historyIndex.value - 1);
        historyIndex.value = idx;
        input.value = inputHistory.value[idx];
        nextTick(autoResize);
        return;
      }
      if (e.key === 'ArrowDown' && !e.shiftKey && historyIndex.value !== -1) {
        e.preventDefault();
        const idx = historyIndex.value + 1;
        if (idx >= inputHistory.value.length) {
          historyIndex.value = -1; input.value = '';
        } else {
          historyIndex.value = idx;
          input.value = inputHistory.value[idx];
        }
        nextTick(autoResize);
      }
    }

    /* ── 事件委托：代码复制 / 右键 ── */
    function onChatClick(e) {
      const btn = e.target.closest('.copy-code');
      if (btn) {
        const code = decodeURIComponent(btn.dataset.code || '');
        copyText(code, t('toast.codeCopied'));
        btn.classList.add('copied');
        const span = btn.querySelector('.copy-code-label');
        const old = span ? span.textContent : '';
        if (span) span.textContent = lang.value === 'zh' ? '已复制' : 'COPIED';
        setTimeout(() => {
          btn.classList.remove('copied');
          if (span) span.textContent = old || 'COPY';
        }, 1200);
        e.stopPropagation();
      }
    }

    function onChatRightClick(e) {
      const el = e.target.closest('.msg');
      if (!el) return;
      const id = el.dataset.msgId;
      const m = messages.value.find(x => x._id === id);
      if (!m) return;
      ctxMenu.show = true;
      ctxMenu.x = e.clientX;
      ctxMenu.y = e.clientY;
      ctxMenu.msgId = id;
      ctxMenu.role = m.role;
      ctxMenu.content = m.content || '';
      // 防止超出屏幕
      nextTick(() => {
        const el2 = document.querySelector('.ctx-menu');
        if (!el2) return;
        const r = el2.getBoundingClientRect();
        if (r.right > window.innerWidth) ctxMenu.x = window.innerWidth - r.width - 8;
        if (r.bottom > window.innerHeight) ctxMenu.y = window.innerHeight - r.height - 8;
      });
    }
    function closeCtxMenu() { ctxMenu.show = false; }
    function ctxCopy() {
      copyText(ctxMenu.content, t('toast.copied'));
      closeCtxMenu();
    }
    function ctxCopyAll() {
      const all = messages.value.map(m =>
        `[${m.role}]\n${m.content || ''}`
      ).join('\n\n---\n\n');
      copyText(all, '会话已复制');
      closeCtxMenu();
    }
    function ctxExport() {
      exportSession('md');
      closeCtxMenu();
    }
    function ctxQuote() {
      const snippet = ctxMenu.content.split('\n').slice(0, 5).join('\n');
      input.value = `> ${snippet}\n\n`;
      nextTick(() => { autoResize(); inputEl.value?.focus(); });
      closeCtxMenu();
    }
    function ctxRegenerate() {
      closeCtxMenu();
      regenerate();
    }

    /* ── 搜索 ── */
    function openSearch() {
      showSearch.value = true;
      nextTick(() => searchInputEl.value?.focus());
    }
    function closeSearch() { showSearch.value = false; }
    function applySearch() {
      appliedSearch.value = searchQuery.value;
      showSearch.value = false;
    }
    function clearSearch() {
      searchQuery.value = '';
      appliedSearch.value = '';
    }

    /* ── backend ── */
    async function checkHealth() {
      try {
        const r = await fetch('/health');
        if (r.ok) {
          const data = await r.json();
          gatewayOnline.value = true;
          if (data.model && !settings.model) settings.model = data.model;
        } else { gatewayOnline.value = false; }
      } catch { gatewayOnline.value = false; }
    }
    async function loadStatus() {
      try {
        const r = await fetch('/api/status');
        if (r.ok) gatewayStats.value = await r.json();
      } catch {}
    }
    async function loadTools() {
      try {
        const r = await fetch('/api/tools');
        if (r.ok) {
          const data = await r.json();
          tools.value = (data.tools || []).map(x => ({
            ...x,
            description: x.description || '',
          }));
        }
      } catch {}
    }
    async function toggleTool(tool) {
      const target = !tool.enabled;
      tool.enabled = target;
      try {
        const r = await fetch(`/api/tools/${encodeURIComponent(tool.name)}/toggle`, {
          method: 'POST',
        });
        if (r.ok) {
          const data = await r.json();
          tool.enabled = data.enabled;
          toast(t(tool.enabled ? 'toast.toolOn' : 'toast.toolOff', { name: tool.name }));
        } else {
          tool.enabled = !target;
          toast(t('toast.opFailed'));
        }
      } catch {
        tool.enabled = !target;
        toast(t('toast.opFailed'));
      }
    }

    /* ── send ── */
    async function send(text) {
      const content = (text !== undefined ? text : input.value).trim();
      if (!content || streaming.value) return;
      ensureSession();
      const sess = currentSession.value;
      if (sess) sess.turnCounter = (sess.turnCounter || 0) + 1;
      if (text === undefined) {
        inputHistory.value.push(content);
        if (inputHistory.value.length > 100) inputHistory.value.shift();
        historyIndex.value = -1;
      }
      input.value = '';
      nextTick(() => { autoResize(); inputEl.value?.focus(); });
      messages.value.push({ _id: uid(), role: 'user', content });
      const assistantMsg = reactive({
        _id: uid(), role: 'assistant', content: '', reasoning: '',
        toolCalls: [], streaming: true, meta: '', _expanded: false,
      });
      messages.value.push(assistantMsg);
      scrollToBottom(true);
      streaming.value = true;
      streamStartTime = Date.now();
      streamCharCount = 0;
      streamSpeed.value = 0;
      streamSpeedTimer = setInterval(() => {
        const elapsed = (Date.now() - streamStartTime) / 1000;
        if (elapsed > 0.5) {
          streamSpeed.value = (streamCharCount / 2.5) / elapsed;
        }
      }, 400);
      abortController = new AbortController();

      try {
        const resp = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: content,
            auto_approve: autoApprove.value,
          }),
          signal: abortController.signal,
        });
        if (!resp.ok) {
          const err = await resp.text();
          assistantMsg.streaming = false;
          messages.value.push({
            _id: uid(), role: 'error',
            content: t('err.httpStatus', { status: resp.status }) + ': ' + err.slice(0, 300),
          });
          return;
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            const data = line.slice(5).trim();
            if (data === '[DONE]') continue;
            try { handleEvent(JSON.parse(data), assistantMsg); } catch {}
          }
          scrollToBottom();
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          assistantMsg.content = (assistantMsg.content || '') + '\n\n_(' + t('toast.stopped') + ')_';
        } else {
          messages.value.push({ _id: uid(), role: 'error', content: String(e) });
        }
      } finally {
        if (streamSpeedTimer) { clearInterval(streamSpeedTimer); streamSpeedTimer = null; }
        streamSpeed.value = 0;
        assistantMsg.streaming = false;
        streaming.value = false;
        abortController = null;
        saveCurrentSession();
        scrollToBottom();
      }
    }
    function handleEvent(evt, msg) {
      if (!evt || !evt.type) return;
      switch (evt.type) {
        case 'reasoning':
          msg.reasoning += evt.delta || '';
          break;
        case 'content':
          msg.content += evt.delta || '';
          streamCharCount += (evt.delta || '').length;
          break;
        case 'tool_call':
          {
            const running = msg.toolCalls.filter(tc =>
              tc.status === 'running' && tc.name === (evt.name || '?')
            );
            const completed = evt.call_id
              ? running.find(tc => tc.callId === evt.call_id)
              : running.find(tc => tc.target === (evt.target || '')) || running[0];
            if (completed) {
              completed.summary = evt.summary || '';
              completed.status = evt.status || 'ok';
              completed.output = evt.result || '';
              completed.progress = 100;
            } else {
              msg.toolCalls.push({
                callId: evt.call_id || '', name: evt.name || '?',
                target: evt.target || '', summary: evt.summary || '',
                status: evt.status || 'ok', output: evt.result || '',
              });
            }
          }
          break;
        case 'tool_start':
          msg.toolCalls.push({
            callId: evt.call_id || '', name: evt.name || '?',
            target: evt.target || '', summary: '',
            status: 'running',
          });
          break;
        case 'tool_progress': {
          const running = msg.toolCalls.find(tc =>
            tc.status === 'running' && tc.name === (evt.name || 'download')
          );
          if (running) {
            running.progress = Math.max(0, Math.min(100, Number(evt.percent) || 0));
            const done = Number(evt.done) || 0;
            const total = Number(evt.total) || 0;
            running.progressText = total
              ? `${fmtBytes(done)} / ${fmtBytes(total)}`
              : fmtBytes(done);
          }
          break;
        }
        case 'done':
          msg.streaming = false;
          if (evt.duration) msg.meta = (lang.value === 'zh' ? '耗时 ' : 'took ') + evt.duration + 's';
          break;
        case 'error':
          msg.streaming = false;
          messages.value.push({ _id: uid(), role: 'error', content: evt.message || 'Error' });
          break;
        case 'ask_user': {
          const sess = currentSession.value;
          const rec = {
            id: evt.id, ts: Date.now(),
            turn: sess ? (sess.turnCounter || 1) : 1,
            thread: null, parent_id: null,
            header: evt.header || '', timeout: evt.timeout || 0,
            questions: (evt.questions || []).map(q => ({
              key: q.key, question: q.question, options: q.options || [],
              default: q.default || '', allow_custom: q.allow_custom !== false,
              show_if: q.show_if || null, answer: '', selected: -1, _visible: true,
            })),
          };
          if (sess) {
            if (!Array.isArray(sess.asks)) sess.asks = [];
            const prev = sess.asks.length ? sess.asks[sess.asks.length - 1] : null;
            if (prev && prev.turn === rec.turn) {
              rec.thread = prev.thread || prev.id;
              rec.parent_id = prev.id;
            } else { rec.thread = rec.id; }
            sess.asks.push(rec);
          } else { rec.thread = rec.id; }
          askUser.value = rec;
          nextTick(() => {
            const el = document.querySelector('.ask-option, .ask-input');
            if (el) el.focus();
          });
          break;
        }
      }
    }
    function stopStream() {
      if (abortController) abortController.abort();
    }

    /* ── ask 交互 ── */
    function selectAskOption(qi, oi) {
      const q = askUser.value?.questions[qi];
      if (!q) return;
      q.selected = oi;
      q.answer = '';
    }
    function onAskInput(qi, e) {
      const q = askUser.value?.questions[qi];
      if (!q) return;
      q.answer = e.target.value;
      if (q.answer.trim()) q.selected = -1;
    }
    function submitAskAnswer() {
      if (!askUser.value) return;
      const visible = visibleAskQuestions.value;
      const payload = {};
      for (const q of visible) {
        let v = '';
        if (q.selected >= 0 && q.selected < q.options.length) v = q.options[q.selected];
        else if (q.answer && q.answer.trim()) v = q.answer.trim();
        else if (q.default) v = q.default;
        if (!v) { toast(`请回答：${q.question.slice(0, 20)}`); return; }
        payload[q.key] = v;
        q.answer = v;
        q.selected = -1;
      }
      const askId = askUser.value.id;
      askUser.value = null;
      fetch('/api/ask/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: askId, answers: payload }),
      }).catch(() => toast('提交失败'));
      setTimeout(loadPendingAsks, 300);
    }
    function cancelAsk() {
      if (!askUser.value) return;
      const visible = visibleAskQuestions.value;
      const askId = askUser.value.id;
      const payload = {};
      for (const q of visible) {
        const v = q.default || '';
        payload[q.key] = v;
        q.answer = v;
      }
      askUser.value = null;
      fetch('/api/ask/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: askId, answers: payload }),
      }).catch(() => {});
      setTimeout(loadPendingAsks, 300);
    }
    async function loadPendingAsks() {
      try {
        const r = await fetch('/api/ask/pending');
        if (!r.ok) return;
        const data = await r.json();
        const pending = data.pending || [];
        if (pending.length === 0) return;
        const first = pending[0];
        const sess = currentSession.value;
        let rec = sess && sess.asks ? sess.asks.find(x => x.id === first.id) : null;
        if (!rec) {
          rec = {
            id: first.id,
            ts: (first.created_at || Date.now() / 1000) * 1000,
            turn: sess ? (sess.turnCounter || 1) : 1,
            thread: null, parent_id: null,
            header: first.header || '', timeout: first.timeout || 0,
            questions: (first.questions || []).map(q => ({
              key: q.key, question: q.question, options: q.options || [],
              default: q.default || '', allow_custom: q.allow_custom !== false,
              show_if: q.show_if || null, answer: '', selected: -1, _visible: true,
            })),
          };
          if (sess) {
            if (!Array.isArray(sess.asks)) sess.asks = [];
            const prev = sess.asks.length ? sess.asks[sess.asks.length - 1] : null;
            if (prev && prev.turn === rec.turn) {
              rec.thread = prev.thread || prev.id;
              rec.parent_id = prev.id;
            } else { rec.thread = rec.id; }
            sess.asks.push(rec);
          } else { rec.thread = rec.id; }
        }
        askUser.value = rec;
        toast(`恢复 ${pending.length} 个等待中的提问`);
        nextTick(() => {
          const el = document.querySelector('.ask-option, .ask-input');
          if (el) el.focus();
        });
      } catch {}
    }
    function toggleAskThread(id) {
      askThreadExpanded.value[id] = !isAskThreadExpanded(id);
    }
    function isAskThreadExpanded(id) {
      return askThreadExpanded.value[id] !== false;
    }

    /* ── 导出 ── */
    function _asksToMarkdown(asks) {
      const lines = ['# 问答历史', '', `- 记录数：${asks.length}`, ''];
      const threads = {}; const order = [];
      for (const rec of asks) {
        const th = rec.thread || rec.id;
        if (!threads[th]) { threads[th] = []; order.push(th); }
        threads[th].push(rec);
      }
      for (let i = 0; i < order.length; i++) {
        lines.push(`## Thread ${i + 1}`); lines.push('');
        for (const rec of threads[order[i]]) {
          const tstr = new Date(rec.ts || 0).toLocaleString();
          lines.push(`### ${tstr} — ${rec.header || '模型提问'}`); lines.push('');
          for (const q of rec.questions || []) {
            lines.push(`**${q.key}**: ${q.question}`);
            if (q.options && q.options.length) {
              for (const o of q.options) lines.push(`- ${o === q.default ? '★ ' : ''}${o}`);
            }
            lines.push(''); lines.push(`**回答**：${q.answer || '（未答）'}`); lines.push('');
          }
        }
      }
      return lines.join('\n');
    }
    function _asksToCSV(asks) {
      const rows = [[
        'ts', 'time', 'thread', 'turn', 'parent_id', 'header',
        'key', 'question', 'options', 'default', 'answer',
      ]];
      for (const rec of asks) {
        const ts = rec.ts || 0;
        const tstr = new Date(ts).toISOString();
        for (const q of rec.questions || []) {
          rows.push([
            ts, tstr, rec.thread || '', rec.turn || '',
            rec.parent_id || '', rec.header || '',
            q.key || '', q.question || '',
            (q.options || []).join(' | '), q.default || '', q.answer || '',
          ]);
        }
      }
      return rows.map(r => r.map(c => {
        const s = String(c == null ? '' : c).replace(/"/g, '""');
        return /[,"\n]/.test(s) ? `"${s}"` : s;
      }).join(',')).join('\n');
    }
    function _downloadBlob(content, filename, mime) {
      const blob = new Blob([content], { type: `${mime};charset=utf-8` });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
    function exportAsks(fmt) {
      const s = currentSession.value;
      if (!s || !s.asks || !s.asks.length) { toast('无问答历史'); return; }
      let content, mime, ext;
      if (fmt === 'json') { content = JSON.stringify(s.asks, null, 2); mime = 'application/json'; ext = 'json'; }
      else if (fmt === 'csv') { content = _asksToCSV(s.asks); mime = 'text/csv'; ext = 'csv'; }
      else { content = _asksToMarkdown(s.asks); mime = 'text/markdown'; ext = 'md'; }
      _downloadBlob(content, `asks-${s.id}.${ext}`, mime);
      toast(`已导出 ${ext.toUpperCase()}`);
    }
    function exportSession(fmt) {
      const s = currentSession.value;
      if (!s) return;
      if (fmt === 'json') {
        _downloadBlob(JSON.stringify(s, null, 2), `session-${s.id}.json`, 'application/json');
      } else {
        const lines = [`# ${s.title || '会话'}`, '', `- 导出：${new Date().toLocaleString()}`, ''];
        for (const m of messages.value) {
          if (m.role === 'user') { lines.push('## 用户', '', m.content || '', ''); }
          else if (m.role === 'assistant') {
            if (m.reasoning) { lines.push('<details><summary>思考过程</summary>', '', m.reasoning, '', '</details>', ''); }
            if (m.content) { lines.push('## 助手', '', m.content, ''); }
          } else if (m.role === 'error') { lines.push(`> ⚠ ${m.content}`, ''); }
        }
        _downloadBlob(lines.join('\n'), `session-${s.id}.md`, 'text/markdown');
      }
      toast('已导出');
    }

    /* ── settings ── */
    function saveSettings() {
      persistSettings({ ...settings });
      showSettings.value = false;
      toast(t('toast.settingsSaved'));
    }
    function toggleSidebar() { sidebarOpen.value = !sidebarOpen.value; }

    /* ── 全局快捷键 ── */
    function onGlobalKeydown(e) {
      const meta = e.ctrlKey || e.metaKey;
      const inInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA';

      if (meta && e.key.toLowerCase() === 'k') { e.preventDefault(); newSession(); return; }
      if (meta && e.key.toLowerCase() === 'b') { e.preventDefault(); toggleSidebar(); return; }
      if (meta && e.key.toLowerCase() === 'j') { e.preventDefault(); toggleTheme(); return; }
      if (meta && e.key.toLowerCase() === 'f') { e.preventDefault(); openSearch(); return; }
      if (meta && e.key === ',') { e.preventDefault(); showSettings.value = !showSettings.value; return; }
      if (e.key === 'Escape') {
        if (ctxMenu.show) { closeCtxMenu(); return; }
        if (showSearch.value) { closeSearch(); return; }
        if (showSettings.value) { showSettings.value = false; return; }
        if (showHelp.value) { showHelp.value = false; return; }
        return;
      }
      if (e.key === '?' && !inInput && !meta) {
        e.preventDefault(); showHelp.value = !showHelp.value;
      }
    }

    /* ── 初始化 ── */
    onMounted(async () => {
      setLang(lang.value);
      const saved = loadLocalSessions();
      sessions.value = saved;
      if (saved.length > 0) {
        currentSessionId.value = saved[0].id;
        messages.value = (saved[0].messages || []).map(m => ({
          _id: uid(), role: m.role,
          content: m.content || '', reasoning: m.reasoning || '',
          toolCalls: (m.toolCalls || []).map(tc => ({ ...tc })),
          streaming: false, meta: m.meta || '', _expanded: false,
        }));
        if (!Array.isArray(saved[0].asks)) saved[0].asks = [];
      } else {
        newSession();
      }
      await checkHealth();
      await loadStatus();
      await loadTools();
      await loadPendingAsks();
      setInterval(loadStatus, 5000);
      setInterval(checkHealth, 15000);
      window.addEventListener('keydown', onGlobalKeydown);
      nextTick(() => { inputEl.value?.focus(); scrollToBottom(true); });
    });

    watch(messages, () => {
      if (!streaming.value) saveCurrentSession();
    }, { deep: true });

    return {
      // state
      lang, theme, largeText, toggleLargeText, messages, input, streaming, showSettings, showHelp, showSearch,
      sidebarOpen, sidebarTab, sessions, currentSessionId,
      gatewayOnline, gatewayStats, autoApprove, tools, toolsFilter, toolsCategory,
      showScrollBtn, toasts, settings, messagesEl, inputEl, searchInputEl,
      askUser, searchQuery, matchedMessageCount, streamSpeed, ctxMenu,
      // computed
      model, currentSession, suggestions, lastUserIndex, lastUserIndexInAll,
      askCount, askThreads, visibleAskQuestions, filteredTools, filteredMessages,
      searchActive,
      // methods
      t, setLang, toggleLang, toggleTheme,
      renderMarkdown, fmtTime, isMatch,
      send, stopStream, newSession, switchSession, deleteSession,
      editMessage, regenerate, clearMessages, clearAllSessions,
      toggleTool, saveSettings, toggleSidebar,
      copyText, scrollToBottom, onKeydown, autoResize,
      onMessagesScroll, onChatClick, onChatRightClick,
      closeCtxMenu, ctxCopy, ctxCopyAll, ctxExport, ctxQuote, ctxRegenerate,
      openSearch, closeSearch, applySearch, clearSearch,
      selectAskOption, onAskInput, submitAskAnswer, cancelAsk, loadPendingAsks,
      toggleAskThread, isAskThreadExpanded,
      exportAsks, exportSession,
    };
  },
}).mount('#app');