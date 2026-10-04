/* ═══════════════════════════════════════════════════════════════ */
/*  One Cedric WebUI · app.js                                       */
/* ═══════════════════════════════════════════════════════════════ */
const { createApp, ref, reactive, computed, onMounted, onUnmounted,
        nextTick, watch } = Vue;

const LS_SETTINGS  = 'cedric_webui_settings_v1';
const LS_SESSIONS  = 'cedric_webui_sessions_v1';
const LS_LANG      = 'cedric_webui_lang_v1';
const LS_THEME     = 'cedric_webui_theme_v1';
const LS_ACRYLIC   = 'cedric_webui_acrylic_v1';
const LS_HUE1      = 'cedric_webui_hue1_v1';
const LS_HUE2      = 'cedric_webui_hue2_v1';
const LS_CUSTOM_CMDS = 'cedric_webui_custom_cmds_v1';
const MAX_SESSIONS = 40;

/* ═══════════════════════════════════════════════════════════════ */
/*  i18n                                                            */
/* ═══════════════════════════════════════════════════════════════ */
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
    'welcome.suggestions': ['这个目录里有什么文件', '读一下 README.md 讲讲项目',
                            '统计一下项目代码量', '帮我搜索一下今天的新闻'],
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
    'settings.acrylicStrength': '亚克力强度',
    'settings.acrylicOff': '关',
    'settings.acrylicLow': '低',
    'settings.acrylicMedium': '中',
    'settings.acrylicHigh': '高',
    'settings.particleColor': '粒子颜色（ultra 模式）',
    'settings.customCommands': '自定义命令',
    'settings.addCommand': '＋ 添加命令',
    'settings.exportAll': '导出全部会话',
    'settings.importSessions': '从文件导入会话',
    'settings.export': '导出',
    'settings.import': '导入',
    'settings.exportCurrent': '导出当前会话',
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
    'help.search': '搜索消息',
    'help.theme': '切换主题',
    'help.commandPanel': '命令面板',
    'help.completion': '补全列表',
    'toast.copied': '消息已复制',
    'toast.codeCopied': '代码已复制',
    'toast.copyFailed': '复制失败',
    'toast.settingsSaved': '设置已保存',
    'toast.toolOn': '{name} 已启用',
    'toast.toolOff': '{name} 已禁用',
    'toast.opFailed': '操作失败',
    'toast.stopped': '已停止',
    'toast.langSwitched': '已切换为中文',
    'toast.synced': '已同步 {n} 项到服务器',
    'toast.syncFailed': '同步失败',
    'toast.uploaded': '已上传 {n} 个文件',
    'toast.uploadFailed': '上传失败 {name}',
    'toast.uploadTooBig': '跳过 {name}（超过 25MB）',
    'toast.pinned': '已收藏',
    'toast.unpinned': '已取消收藏',
    'toast.pinsCleared': '已清空收藏',
    'toast.exported': '已导出 {fmt}',
    'toast.sessionUpdated': '会话已在另一个窗口更新',
    'toast.noAsks': '无问答历史',
    'confirm.clearMessages': '清空当前会话的所有消息？',
    'confirm.clearAll': '删除所有本地会话？此操作不可撤销。',
    'confirm.clearPins': '清空所有收藏？',
    'confirm.deleteSession': '删除会话 {title}？',
    'time.justNow': '刚刚',
    'time.minutesAgo': '{n} 分钟前',
    'time.hoursAgo': '{n} 小时前',
    'time.daysAgo': '{n} 天前',
    'err.httpStatus': 'HTTP {status}',
    'search.placeholder': '搜索消息内容…',
    'search.hint': '回车应用过滤 · Esc 关闭 · 匹配 {n} 条',
    'search.banner': '搜索：{q}（{n} 条匹配）',
    'search.clear': '清除',
    'search.regex': '正则表达式',
    'search.caseSensitive': '区分大小写',
    'tabs.sessions': '会话',
    'tabs.asks': '问答',
    'tabs.tools': '工具',
    'tabs.outline': '大纲',
    'tabs.pinned': '收藏',
    'tools.searchPlaceholder': '搜索工具…',
    'tools.all': '全部',
    'tools.on': '已启用',
    'tools.off': '已禁用',
    'tools.noMatch': '无匹配工具',
    'outline.searchPlaceholder': '搜索大纲…',
    'outline.empty': '当前会话无内容',
    'outline.noHeading': '（无标题）',
    'pinned.empty': '暂无收藏',
    'pinned.role': '我',
    'pinned.roleAsst': '助手',
    'tree.title': '消息树',
    'tree.empty': '当前会话无消息',
    'ask.cancel': '取消',
    'ask.submit': '提交',
    'ask.recommend': '推荐',
    'ask.customInput': '或输入自定义回答…',
    'ask.input': '输入回答…',
    'ask.enterDefault': '回车使用推荐：',
    'ask.timeoutHint': '{n} 秒后未提交将使用默认值',
    'ask.title': '模型提问',
    'ask.titleBatch': '模型提问（{n} 个）',
    'param.title': '参数',
    'param.hint': '回车确认 · 留空会保留占位符',
    'param.cancel': '取消',
    'param.insert': '插入',
    'drop.hint': '松开鼠标上传文件',
    'drop.sub': '支持多文件 · 单个最大 25MB',
    'ctx.copy': '复制内容',
    'ctx.copyAll': '复制整段会话',
    'ctx.export': '导出到 MD',
    'ctx.quote': '引用回复',
    'ctx.regenerate': '重新生成',
    'err.retry': '重试',
    'notify.enabled': '桌面通知已开启',
    'notify.disabled': '桌面通知已关闭',
    'notify.denied': '浏览器已拒绝通知权限',
    'notify.title': 'One Cedric 完成',
    'notify.titleAsk': 'One Cedric 提问',
    'notify.titleFail': 'One Cedric',
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
    'welcome.suggestions': ['What files are in this directory',
                            'Read README.md and explain the project',
                            'Count lines of code in the project',
                            "Search for today's news"],
    'msg.copy': 'Copy',
    'msg.edit': 'Edit & resend',
    'msg.regenerate': 'Regenerate',
    'msg.reasoning': 'Reasoning',
    'msg.chars': '{n} chars',
    'msg.scrollBottom': 'Scroll to bottom',
    'input.placeholder': 'Type a message… (Enter to send · Shift+Enter newline · ↑ history)',
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
    'settings.showReasoning': 'Show reasoning',
    'settings.tools': 'Tools',
    'settings.toolsLoading': 'Loading…',
    'settings.data': 'Data',
    'settings.clearMessages': 'Clear current session',
    'settings.clearAllSessions': 'Delete all sessions',
    'settings.clear': 'Clear',
    'settings.delete': 'Delete',
    'settings.done': 'Done',
    'settings.acrylicStrength': 'Acrylic strength',
    'settings.acrylicOff': 'Off',
    'settings.acrylicLow': 'Low',
    'settings.acrylicMedium': 'Med',
    'settings.acrylicHigh': 'High',
    'settings.particleColor': 'Particle color (ultra)',
    'settings.customCommands': 'Custom commands',
    'settings.addCommand': '+ Add command',
    'settings.exportAll': 'Export all sessions',
    'settings.importSessions': 'Import from file',
    'settings.export': 'Export',
    'settings.import': 'Import',
    'settings.exportCurrent': 'Export current session',
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
    'help.search': 'Search messages',
    'help.theme': 'Toggle theme',
    'help.commandPanel': 'Command panel',
    'help.completion': 'Completion list',
    'toast.copied': 'Copied',
    'toast.codeCopied': 'Code copied',
    'toast.copyFailed': 'Copy failed',
    'toast.settingsSaved': 'Settings saved',
    'toast.toolOn': '{name} enabled',
    'toast.toolOff': '{name} disabled',
    'toast.opFailed': 'Operation failed',
    'toast.stopped': 'Stopped',
    'toast.langSwitched': 'Switched to English',
    'toast.synced': 'Synced {n} items to server',
    'toast.syncFailed': 'Sync failed',
    'toast.uploaded': 'Uploaded {n} files',
    'toast.uploadFailed': 'Upload failed: {name}',
    'toast.uploadTooBig': 'Skipped {name} (>25MB)',
    'toast.pinned': 'Pinned',
    'toast.unpinned': 'Unpinned',
    'toast.pinsCleared': 'Pins cleared',
    'toast.exported': 'Exported {fmt}',
    'toast.sessionUpdated': 'Sessions updated in another window',
    'toast.noAsks': 'No Q&A history',
    'confirm.clearMessages': 'Clear all messages in the current session?',
    'confirm.clearAll': 'Delete all local sessions? Cannot be undone.',
    'confirm.clearPins': 'Clear all pins?',
    'confirm.deleteSession': 'Delete session {title}?',
    'time.justNow': 'just now',
    'time.minutesAgo': '{n}m ago',
    'time.hoursAgo': '{n}h ago',
    'time.daysAgo': '{n}d ago',
    'err.httpStatus': 'HTTP {status}',
    'search.placeholder': 'Search messages…',
    'search.hint': 'Enter to apply · Esc to close · {n} matches',
    'search.banner': 'Search: {q} ({n} matches)',
    'search.clear': 'Clear',
    'search.regex': 'Regex',
    'search.caseSensitive': 'Case sensitive',
    'tabs.sessions': 'Sessions',
    'tabs.asks': 'Q&A',
    'tabs.tools': 'Tools',
    'tabs.outline': 'Outline',
    'tabs.pinned': 'Pinned',
    'tools.searchPlaceholder': 'Search tools…',
    'tools.all': 'All',
    'tools.on': 'On',
    'tools.off': 'Off',
    'tools.noMatch': 'No matching tools',
    'outline.searchPlaceholder': 'Search outline…',
    'outline.empty': 'No content in this session',
    'outline.noHeading': '(no heading)',
    'pinned.empty': 'No pins yet',
    'pinned.role': 'Me',
    'pinned.roleAsst': 'Assistant',
    'tree.title': 'Message tree',
    'tree.empty': 'No messages',
    'ask.cancel': 'Cancel',
    'ask.submit': 'Submit',
    'ask.recommend': 'Recommended',
    'ask.customInput': 'Or type a custom answer…',
    'ask.input': 'Type your answer…',
    'ask.enterDefault': 'Enter to use recommended:',
    'ask.timeoutHint': 'Will use default after {n}s',
    'ask.title': 'Model question',
    'ask.titleBatch': 'Model questions ({n})',
    'param.title': 'Parameters',
    'param.hint': 'Enter to confirm · leave empty to keep placeholder',
    'param.cancel': 'Cancel',
    'param.insert': 'Insert',
    'drop.hint': 'Drop files to upload',
    'drop.sub': 'Multiple files · max 25MB each',
    'ctx.copy': 'Copy',
    'ctx.copyAll': 'Copy whole session',
    'ctx.export': 'Export as MD',
    'ctx.quote': 'Quote reply',
    'ctx.regenerate': 'Regenerate',
    'err.retry': 'Retry',
    'notify.enabled': 'Desktop notifications enabled',
    'notify.disabled': 'Desktop notifications disabled',
    'notify.denied': 'Browser denied notification permission',
    'notify.title': 'One Cedric finished',
    'notify.titleAsk': 'One Cedric asks',
    'notify.titleFail': 'One Cedric',
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
  try {
    localStorage.setItem(LS_SESSIONS,
      JSON.stringify(list.slice(0, MAX_SESSIONS)));
  } catch {}
}
function loadCustomCommands() {
  try {
    const a = JSON.parse(localStorage.getItem(LS_CUSTOM_CMDS) || '[]');
    return Array.isArray(a) ? a : [];
  } catch { return []; }
}

/* ─── 消息树辅助 ─────────────────────────── */
function _makeTreeNode(msg, parentId) {
  return {
    id: msg._id || uid(),
    role: msg.role,
    content: msg.content || '',
    reasoning: msg.reasoning || '',
    toolCalls: (msg.toolCalls || []).map(tc => ({ ...tc })),
    meta: msg.meta || '',
    streaming: false,
    _expanded: false,
    parent: parentId || null,
    children: [],
    createdAt: Date.now(),
  };
}
function _pathFromLeaf(nodes, leafId) {
  const path = [];
  let cur = leafId;
  const guard = new Set();
  while (cur && nodes[cur] && !guard.has(cur)) {
    guard.add(cur);
    path.unshift(cur);
    cur = nodes[cur].parent;
  }
  return path;
}
function _deepestLeaf(nodes, startId) {
  let cur = startId;
  const guard = new Set();
  while (cur && nodes[cur] && !guard.has(cur)) {
    guard.add(cur);
    const kids = nodes[cur].children || [];
    if (!kids.length) return cur;
    cur = kids[0];
  }
  return cur;
}
function _siblingsOf(nodes, nodeId) {
  const node = nodes[nodeId];
  if (!node) return [];
  if (!node.parent) {
    return Object.values(nodes).filter(n => !n.parent).map(n => n.id);
  }
  const p = nodes[node.parent];
  return (p && p.children) ? p.children.slice() : [nodeId];
}
function _linearToTree(messages) {
  const nodes = {};
  let leafId = null;
  let prev = null;
  for (const m of messages) {
    const node = _makeTreeNode(m, prev);
    nodes[node.id] = node;
    if (prev && nodes[prev]) nodes[prev].children.push(node.id);
    prev = node.id;
    leafId = node.id;
  }
  return { nodes, leafId };
}
function _treeToLinear(nodes, leafId) {
  const path = _pathFromLeaf(nodes, leafId);
  return path.map(id => nodes[id]).filter(Boolean);
}

/* ─── Marked renderer ───────────────────── */
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
  const lines = text.split('\n');
  const lineCount = lines.length;
  const showLineNumbers = lineCount >= 3;
  const collapsible = lineCount > 24;
  const lineNumbers = showLineNumbers
    ? Array.from({ length: lineCount }, (_, i) => i + 1).join('\n')
    : '';
  const classes = ['code-block'];
  if (collapsible) classes.push('collapsible');

  const preAttrs = [
    showLineNumbers ? 'class="has-line-numbers"' : '',
    showLineNumbers ? `data-line-numbers="${lineNumbers}"` : '',
  ].filter(Boolean).join(' ');

  const expandBtn = collapsible
    ? `<button class="code-expand-btn" type="button" data-collapse-btn>
         <span class="chevron">▼</span>
         <span class="expand-label">展开全部 ${lineCount} 行</span>
       </button>`
    : '';

  return `<div class="${classes.join(' ')}">
    <div class="code-head">
      <span class="code-lang">${escapeHtml(langLabel)}</span>
      <button class="copy-code" data-code="${encoded}" type="button">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
        <span class="copy-code-label">COPY</span>
      </button>
    </div>
    <pre ${preAttrs}><code class="hljs language-${escapeHtml(langLabel)}">${highlighted}</code></pre>
    ${expandBtn}
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
    /* ── i18n ───────────────────────────── */
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

    /* ── theme / acrylic / hue ─────────── */
    const theme = ref(localStorage.getItem(LS_THEME) || 'dark');
    const acrylicStrength = ref(localStorage.getItem(LS_ACRYLIC) || 'medium');
    const particleHue1 = ref(parseInt(localStorage.getItem(LS_HUE1) || '220'));
    const particleHue2 = ref(parseInt(localStorage.getItem(LS_HUE2) || '270'));
    const configSyncing = ref(false);
    const hueGradient = computed(() =>
      'linear-gradient(90deg, hsl(0,85%,60%), hsl(60,85%,60%), ' +
      'hsl(120,85%,60%), hsl(180,85%,60%), hsl(240,85%,60%), ' +
      'hsl(300,85%,60%), hsl(360,85%,60%))'
    );

    /* ── state ─────────────────────────── */
    const messages = ref([]);
    const input = ref('');
    const streaming = ref(false);
    const showSettings = ref(false);
    const showHelp = ref(false);
    const showSearch = ref(false);
    const showTreeModal = ref(false);
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
    const searchRegexMode = ref(false);
    const searchCaseSensitive = ref(false);
    const searchError = ref('');
    const matchedMessageCount = ref(0);
    const streamSpeed = ref(0);
    const ctxMenu = reactive({
      show: false, x: 0, y: 0, msgId: '', role: '', content: '',
    });
    const outlineFilter = ref('');
    const dragging = ref(false);
    const uploadQueue = ref([]);
    const paramDialog = reactive({
      show: false, cmdName: '', template: '', params: [],
    });
    const customCommands = ref(loadCustomCommands());
    const customCmdError = ref('');
    const particleProgress = reactive({
      show: false, percent: 0, label: '',
      particles: [], canvasRef: null, raf: null,
    });
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
    const popoverListEl = ref(null);
    let abortController = null;
    let streamStartTime = 0;
    let streamCharCount = 0;
    let streamSpeedTimer = null;
    let _dragDepth = 0;
    let _activeXHRs = new Map();

    /* ── computed ──────────────────────── */
    const model = computed(() => settings.model || '(未设置)');
    const currentSession = computed(() =>
      sessions.value.find(s => s.id === currentSessionId.value));
    const suggestions = computed(() => t('welcome.suggestions'));
    const lastUserIndex = computed(() => {
      for (let i = messages.value.length - 1; i >= 0; i--) {
        if (messages.value[i].role === 'user') return i;
      }
      return -1;
    });
    const lastUserIndexInAll = lastUserIndex;
    const searchActive = computed(() =>
      appliedSearch.value.trim().length > 0);

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
      if (Array.isArray(si.all)) {
        return si.all.every(x => _evalShowIf(x, answers));
      }
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
        if (q.selected >= 0 && q.selected < q.options.length) {
          v = q.options[q.selected];
        } else if (q.answer && q.answer.trim()) {
          v = q.answer.trim();
        } else if (q.default) {
          v = q.default;
        }
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
      else if (toolsCategory.value === 'off') {
        list = list.filter(x => !x.enabled);
      }
      return list;
    });

    const outlineGroups = computed(() => {
      const groups = [];
      let cur = null;
      for (const m of messages.value) {
        if (m.role === 'user') {
          const firstLine = (m.content || '').split('\n')[0].trim();
          cur = {
            id: m._id, msgId: m._id,
            title: firstLine.slice(0, 80), items: [],
          };
          groups.push(cur);
        } else if (m.role === 'assistant' && m.content && cur) {
          for (const line of m.content.split('\n')) {
            const mm = line.match(/^(#{1,3})\s+(.+)$/);
            if (mm) {
              cur.items.push({
                level: mm[1].length,
                text: mm[2].trim().slice(0, 80),
              });
            }
          }
        }
      }
      return groups;
    });
    const outlineExpanded = ref({});
    function toggleOutlineGroup(id) {
      outlineExpanded.value[id] = !isOutlineExpanded(id);
    }
    function isOutlineExpanded(id) {
      return outlineExpanded.value[id] !== false;
    }
    const outlineCount = computed(() =>
      outlineGroups.value.reduce((s, g) => s + 1 + g.items.length, 0));
    const filteredOutlineGroups = computed(() => {
      const q = outlineFilter.value.trim().toLowerCase();
      const groups = outlineGroups.value;
      if (!q) return groups.map(g => ({ ...g, _matchedItems: g.items }));
      const out = [];
      for (const g of groups) {
        const titleHit = (g.title || '').toLowerCase().includes(q);
        const matchedItems = g.items.filter(it =>
          it.text.toLowerCase().includes(q));
        if (titleHit) out.push({ ...g, _matchedItems: g.items });
        else if (matchedItems.length) {
          out.push({ ...g, _matchedItems: matchedItems });
        }
      }
      return out;
    });
    const outlineMatchCount = computed(() =>
      filteredOutlineGroups.value.reduce(
        (s, g) => s + 1 + g._matchedItems.length, 0));

    const pinnedMessages = computed(() => {
      const s = currentSession.value;
      if (!s || !s.pinned) return [];
      return s.pinned.map(p => {
        const node = s.tree && s.tree.nodes && s.tree.nodes[p.msgId];
        return { ...p, _exists: !!node,
                 _content: node ? node.content : '' };
      }).filter(p => p._exists);
    });

    function isPinned(msgId) {
      const s = currentSession.value;
      if (!s || !s.pinned) return false;
      return s.pinned.some(p => p.msgId === msgId);
    }

    /* ── tree layout ─────────────────── */
    const treeLayout = computed(() => {
      const s = currentSession.value;
      if (!s || !s.tree || !s.tree.nodes) {
        return { nodes: [], edges: [], leafId: null };
      }
      const nodes = s.tree.nodes;
      const positions = {};
      const W = 560, rowH = 44, topPad = 30;
      const leafId = s.tree.leafId;

      function depth(id) {
        let d = 0, cur = id;
        const seen = new Set();
        while (cur && nodes[cur] && nodes[cur].parent && !seen.has(cur)) {
          seen.add(cur);
          cur = nodes[cur].parent;
          d++;
        }
        return d;
      }

      const leaves = Object.values(nodes).filter(
        n => !n.children || !n.children.length);
      if (!leaves.length) return { nodes: [], edges: [], leafId };

      const activePath = new Set(_pathFromLeaf(nodes, leafId));
      let xIdx = 0;
      const colOf = {};

      function assignCol(id, visited) {
        if (visited.has(id)) return;
        visited.add(id);
        const node = nodes[id];
        if (!node) return;
        const kids = node.children || [];
        if (!kids.length) {
          colOf[id] = xIdx++;
          return;
        }
        kids.forEach(k => assignCol(k, visited));
        const kidCols = kids.map(k => colOf[k])
          .filter(x => x !== undefined);
        if (kidCols.length) {
          colOf[id] = (Math.min(...kidCols) + Math.max(...kidCols)) / 2;
        } else {
          colOf[id] = xIdx++;
        }
      }
      const roots = Object.values(nodes).filter(n => !n.parent);
      roots.forEach(r => assignCol(r.id, new Set()));

      const maxCol = Math.max(1, xIdx - 1);
      const colW = maxCol > 0 ? (W - 40) / maxCol : 0;

      const items = [];
      const edges = [];
      const nodeMap = {};

      Object.values(nodes).forEach(n => {
        const d = depth(n.id);
        const col = colOf[n.id] || 0;
        const x = 20 + col * colW;
        const y = topPad + d * rowH;
        const onPath = activePath.has(n.id);
        const isLeaf = n.id === leafId;
        const isRoot = !n.parent;
        nodeMap[n.id] = { x, y, node: n, onPath, isLeaf, isRoot };
        items.push({ id: n.id, x, y, node: n, onPath, isLeaf, isRoot });
        if (n.parent && nodeMap[n.parent]) {
          const p = nodeMap[n.parent];
          edges.push({
            from: p, to: { x, y },
            onPath: onPath && activePath.has(n.parent),
          });
        }
      });

      const maxDepth = Math.max(
        ...Object.values(nodes).map(n => depth(n.id)), 0);
      const height = topPad + (maxDepth + 1) * rowH + 20;
      return { nodes: items, edges, leafId, width: W, height };
    });

    function treeNodeClick(id) {
      const s = currentSession.value;
      if (!s || !s.tree) return;
      s.tree.leafId = _deepestLeaf(s.tree.nodes, id);
      showTreeModal.value = false;
      nextTick(() => scrollToBottom());
    }

    /* ── toast ─────────────────────────── */
    function toast(text) {
      const id = uid();
      toasts.value.push({ id, text });
      setTimeout(() => {
        toasts.value = toasts.value.filter(x => x.id !== id);
      }, 1800);
    }

    /* ── copy ──────────────────────────── */
    async function copyText(text, msg) {
      const m = msg || t('toast.copied');
      try {
        await navigator.clipboard.writeText(text);
        toast(m);
      } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); toast(m); }
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

    /* ── theme sync ────────────────────── */
    function _syncAllClasses() {
      const root = document.documentElement;
      root.classList.remove('theme-dark', 'theme-light');
      root.classList.add('theme-' + theme.value);
      root.classList.remove('acrylic-off', 'acrylic-low',
                            'acrylic-medium', 'acrylic-high');
      root.classList.add('acrylic-' + acrylicStrength.value);
      ['minimal', 'low', 'medium', 'max', 'xhigh', 'ultra'].forEach(x => {
        root.classList.remove('think-' + x);
      });
      const tl = settings.think_level || 'medium';
      root.classList.add('think-' + tl);
      if (tl === 'ultra') {
        nextTick(startParticles);
      } else {
        stopParticles();
      }
    }
    function toggleTheme() {
      theme.value = theme.value === 'dark' ? 'light' : 'dark';
      localStorage.setItem(LS_THEME, theme.value);
      _syncAllClasses();
      _broadcast('theme-updated', { theme: theme.value });
    }
    function setAcrylicStrength(v) {
      acrylicStrength.value = v;
      localStorage.setItem(LS_ACRYLIC, v);
      _syncAllClasses();
    }
    function onHueInput() {
      localStorage.setItem(LS_HUE1, String(particleHue1.value));
      localStorage.setItem(LS_HUE2, String(particleHue2.value));
      if (_particleList.length) {
        for (const p of _particleList) {
          p.hue = Math.random() < 0.5 ? particleHue1.value : particleHue2.value;
        }
      }
    }
    function setHuePreset(h1, h2) {
      particleHue1.value = h1;
      particleHue2.value = h2;
      onHueInput();
      toast(`已切换配色 ${h1}° / ${h2}°`);
    }

    /* ── 粒子系统 ─────────────────────── */
    let _particleCvs = null;
    let _particleCtx = null;
    let _particleList = [];
    let _particleRAF = null;
    let _particleResizeHandler = null;
    let _mouse = { x: -9999, y: -9999, active: false };
    let _mouseHandler = null;
    let _mouseLeaveHandler = null;

    function startParticles() {
      if (_particleRAF) return;
      const cvs = document.querySelector('.particle-canvas');
      if (!cvs) return;
      _particleCvs = cvs;
      _particleCtx = cvs.getContext('2d');

      const resize = () => {
        cvs.width = window.innerWidth;
        cvs.height = window.innerHeight;
      };
      resize();
      _particleResizeHandler = resize;
      window.addEventListener('resize', resize);

      _mouseHandler = (e) => {
        _mouse.x = e.clientX;
        _mouse.y = e.clientY;
        _mouse.active = true;
      };
      _mouseLeaveHandler = () => { _mouse.active = false; };
      window.addEventListener('mousemove', _mouseHandler);
      window.addEventListener('mouseleave', _mouseLeaveHandler);

      const isLight = document.documentElement.classList.contains('theme-light');
      const lightness = isLight ? 45 : 72;
      const N = Math.min(90, Math.max(30,
        Math.floor(window.innerWidth / 18)));

      _particleList = [];
      for (let i = 0; i < N; i++) {
        _particleList.push({
          x: Math.random() * cvs.width,
          y: Math.random() * cvs.height,
          r: Math.random() * 2.4 + 0.8,
          vx: (Math.random() - 0.5) * 0.35,
          vy: (Math.random() - 0.5) * 0.35,
          hue: Math.random() < 0.5 ? particleHue1.value : particleHue2.value,
          a: Math.random() * 0.5 + 0.35,
        });
      }

      const REPEL_RADIUS = 130;
      const REPEL_STRENGTH = 0.9;
      const FRICTION = 0.94;

      const tick = () => {
        const ctx = _particleCtx;
        const c = _particleCvs;
        if (!ctx || !c) return;
        ctx.clearRect(0, 0, c.width, c.height);

        for (const p of _particleList) {
          if (_mouse.active) {
            const dx = p.x - _mouse.x;
            const dy = p.y - _mouse.y;
            const d2 = dx * dx + dy * dy;
            if (d2 < REPEL_RADIUS * REPEL_RADIUS && d2 > 1) {
              const d = Math.sqrt(d2);
              const force = (1 - d / REPEL_RADIUS) * REPEL_STRENGTH;
              p.vx += (dx / d) * force;
              p.vy += (dy / d) * force;
            }
          }
          p.vx *= FRICTION;
          p.vy *= FRICTION;
          p.vx += (Math.random() - 0.5) * 0.06;
          p.vy += (Math.random() - 0.5) * 0.06;
          const sp = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
          const maxSp = 4;
          if (sp > maxSp) {
            p.vx = (p.vx / sp) * maxSp;
            p.vy = (p.vy / sp) * maxSp;
          }
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < -20) p.x = c.width + 20;
          if (p.x > c.width + 20) p.x = -20;
          if (p.y < -20) p.y = c.height + 20;
          if (p.y > c.height + 20) p.y = -20;

          const r6 = p.r * 6;
          const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r6);
          g.addColorStop(0, `hsla(${p.hue}, 95%, ${lightness}%, ${p.a})`);
          g.addColorStop(1, `hsla(${p.hue}, 95%, ${lightness}%, 0)`);
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(p.x, p.y, r6, 0, Math.PI * 2);
          ctx.fill();
        }
        _particleRAF = requestAnimationFrame(tick);
      };
      tick();
    }
    function stopParticles() {
      if (_particleRAF) {
        cancelAnimationFrame(_particleRAF);
        _particleRAF = null;
      }
      if (_particleResizeHandler) {
        window.removeEventListener('resize', _particleResizeHandler);
        _particleResizeHandler = null;
      }
      if (_mouseHandler) {
        window.removeEventListener('mousemove', _mouseHandler);
        _mouseHandler = null;
      }
      if (_mouseLeaveHandler) {
        window.removeEventListener('mouseleave', _mouseLeaveHandler);
        _mouseLeaveHandler = null;
      }
      if (_particleCtx && _particleCvs) {
        try {
          _particleCtx.clearRect(0, 0, _particleCvs.width,
                                 _particleCvs.height);
        } catch {}
      }
      _particleList = [];
      _particleCtx = null;
      _particleCvs = null;
    }

    /* ── 会话管理 ─────────────────────── */
    function newSession() {
      if (streaming.value) return;
      const id = uid();
      sessions.value.unshift(reactive({
        id, title: '',
        tree: reactive({ nodes: {}, leafId: null }),
        asks: [], pinned: [], turnCounter: 0,
        createdAt: Date.now(), updatedAt: Date.now(),
      }));
      persistSessions(sessions.value.map(plainifySession));
      currentSessionId.value = id;
      messages.value = [];
      nextTick(() => inputEl.value && inputEl.value.focus());
    }
    function ensureSession() {
      if (!currentSessionId.value) newSession();
    }
    function plainifySession(s) {
      return {
        id: s.id,
        title: s.title,
        tree: {
          nodes: JSON.parse(JSON.stringify(s.tree.nodes || {})),
          leafId: s.tree.leafId,
        },
        asks: JSON.parse(JSON.stringify(s.asks || [])),
        pinned: JSON.parse(JSON.stringify(s.pinned || [])),
        turnCounter: s.turnCounter || 0,
        createdAt: s.createdAt,
        updatedAt: s.updatedAt,
      };
    }
    function saveCurrentSession() {
      const s = currentSession.value;
      if (!s) return;
      s.updatedAt = Date.now();
      if (!s.title) {
        const first = _treeToLinear(s.tree.nodes, s.tree.leafId)
          .find(m => m.role === 'user');
        if (first) {
          s.title = first.content.slice(0, 24)
            + (first.content.length > 24 ? '…' : '');
        }
      }
      persistSessions(sessions.value.map(plainifySession));
      _broadcast('sessions-updated', {});
    }
    function switchSession(id) {
      if (streaming.value || id === currentSessionId.value) return;
      const s = sessions.value.find(x => x.id === id);
      if (!s) return;
      saveCurrentSession();
      currentSessionId.value = id;
      if (!s.tree) {
        s.tree = reactive(_linearToTree(s.messages || []));
      }
      if (!s.tree.nodes) s.tree.nodes = {};
      if (!Array.isArray(s.asks)) s.asks = [];
      if (!Array.isArray(s.pinned)) s.pinned = [];
      if (typeof s.turnCounter !== 'number') s.turnCounter = 0;
      nextTick(() => scrollToBottom(true));
    }
    function deleteSession(id) {
      if (streaming.value) return;
      const idx = sessions.value.findIndex(s => s.id === id);
      if (idx === -1) return;
      const title = sessions.value[idx].title || t('sidebar.untitled');
      if (!confirm(t('confirm.deleteSession', { title }))) return;
      sessions.value.splice(idx, 1);
      persistSessions(sessions.value.map(plainifySession));
      if (id === currentSessionId.value) {
        if (sessions.value.length > 0) {
          switchSession(sessions.value[0].id);
        } else {
          newSession();
        }
      }
    }
    function clearMessages() {
      if (streaming.value) return;
      if (!confirm(t('confirm.clearMessages'))) return;
      messages.value = [];
      const s = currentSession.value;
      if (s) {
        s.tree = reactive({ nodes: {}, leafId: null });
        s.updatedAt = Date.now();
        persistSessions(sessions.value.map(plainifySession));
      }
      showSettings.value = false;
    }
    function clearAllSessions() {
      if (!confirm(t('confirm.clearAll'))) return;
      sessions.value = [];
      persistSessions([]);
      showSettings.value = false;
      newSession();
    }

    /* ── 消息操作 ─────────────────────── */
    function editMessage(index) {
      if (streaming.value) return;
      const s = currentSession.value;
      const allMsgs = messages.value;
      const m = allMsgs[index];
      if (!m || m.role !== 'user') return;
      s.tree.leafId = m.parent || null;
      input.value = m.content;
      nextTick(() => {
        autoResize();
        if (inputEl.value) {
          inputEl.value.focus();
          inputEl.value.setSelectionRange(
            inputEl.value.value.length, inputEl.value.value.length);
        }
      });
    }
    function regenerate() {
      if (streaming.value) return;
      const s = currentSession.value;
      const idx = lastUserIndex.value;
      if (idx === -1) return;
      const userMsg = messages.value[idx];
      s.tree.leafId = userMsg.id;
      nextTick(() => {
        _streamAssistant(s.tree.nodes[userMsg.id]);
      });
    }
    function _createNode(msg, parentId) {
      const node = reactive(_makeTreeNode(msg, parentId));
      const s = currentSession.value;
      s.tree.nodes[node.id] = node;
      if (parentId && s.tree.nodes[parentId]) {
        s.tree.nodes[parentId].children.push(node.id);
      }
      s.tree.leafId = node.id;
      return node;
    }

    /* ── sibling 切换 ─────────────────── */
    function getSiblingInfo(nodeId) {
      const s = currentSession.value;
      if (!s || !s.tree || !s.tree.nodes) return { total: 1, index: 0 };
      const sibs = _siblingsOf(s.tree.nodes, nodeId);
      const idx = sibs.indexOf(nodeId);
      return { total: sibs.length, index: idx < 0 ? 0 : idx };
    }
    function switchSibling(nodeId, direction) {
      const s = currentSession.value;
      if (!s || !s.tree) return;
      const sibs = _siblingsOf(s.tree.nodes, nodeId);
      const idx = sibs.indexOf(nodeId);
      if (idx === -1) return;
      const newIdx = (idx + direction + sibs.length) % sibs.length;
      const targetId = sibs[newIdx];
      s.tree.leafId = _deepestLeaf(s.tree.nodes, targetId);
      nextTick(() => scrollToBottom());
    }

    /* ── 收藏 ─────────────────────────── */
    function togglePin(msgId) {
      const s = currentSession.value;
      if (!s) return;
      if (!Array.isArray(s.pinned)) s.pinned = [];
      const idx = s.pinned.findIndex(p => p.msgId === msgId);
      if (idx >= 0) {
        s.pinned.splice(idx, 1);
        toast(t('toast.unpinned'));
      } else {
        const node = s.tree && s.tree.nodes && s.tree.nodes[msgId];
        if (!node) return;
        s.pinned.push({
          msgId,
          role: node.role,
          snippet: (node.content || '').slice(0, 100),
          ts: Date.now(),
        });
        toast(t('toast.pinned'));
      }
      saveCurrentSession();
    }
    function jumpToPinned(p) {
      jumpToMessage(p.msgId);
    }
    function clearPins() {
      const s = currentSession.value;
      if (!s) return;
      if (!confirm(t('confirm.clearPins'))) return;
      s.pinned = [];
      saveCurrentSession();
      toast(t('toast.pinsCleared'));
    }

    /* ── scroll ───────────────────────── */
    function isNearBottom() {
      const el = messagesEl.value;
      if (!el) return true;
      return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }
    function onMessagesScroll() {
      showScrollBtn.value = !isNearBottom();
    }
    function scrollToBottom(force) {
      nextTick(() => {
        const el = messagesEl.value;
        if (!el) return;
        if (force || isNearBottom()) el.scrollTop = el.scrollHeight;
      });
    }

    /* ── input ─────────────────────────── */
    function autoResize() {
      const el = inputEl.value;
      if (!el) return;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 220) + 'px';
      detectPopover();
    }
    function onKeydown(e) {
      if (e.key === 'Escape' && popover.show) {
        e.preventDefault();
        _hidePopover();
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        send();
        return;
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
      if (e.key === 'ArrowDown' && !e.shiftKey &&
          historyIndex.value !== -1) {
        e.preventDefault();
        const idx = historyIndex.value + 1;
        if (idx >= inputHistory.value.length) {
          historyIndex.value = -1;
          input.value = '';
        } else {
          historyIndex.value = idx;
          input.value = inputHistory.value[idx];
        }
        nextTick(autoResize);
      }
    }

    /* ── popover（命令 / 文件补全） ───── */
    const popover = reactive({
      show: false, kind: '', items: [], selected: 0,
      triggerStart: -1, triggerEnd: -1, query: '',
    });
    let _fileFetchTimer = null;
    let _fileFetchSeq = 0;

    const BUILTIN_COMMANDS = [
      { cmd: 'new', desc: '新会话', run: () => newSession() },
      { cmd: 'clear', desc: '清空当前会话', run: () => clearMessages() },
      { cmd: 'search', desc: '搜索消息', run: () => openSearch() },
      { cmd: 'export', desc: '导出为 Markdown',
        run: () => exportSession('md') },
      { cmd: 'theme', desc: '切换主题', run: () => toggleTheme() },
      { cmd: 'lang', desc: '切换语言', run: () => toggleLang() },
      { cmd: 'settings', desc: '打开设置',
        run: () => { showSettings.value = true; } },
      { cmd: 'sidebar', desc: '切换侧栏', run: () => toggleSidebar() },
      { cmd: 'help', desc: '快捷键', run: () => { showHelp.value = true; } },
    ];
    function getAllCommands() {
      const custom = customCommands.value.map(c => ({
        cmd: c.name,
        desc: c.desc || '自定义命令',
        custom: true,
        template: c.template || '',
      }));
      return [...BUILTIN_COMMANDS, ...custom];
    }

    function detectPopover() {
      const el = inputEl.value;
      if (!el) { _hidePopover(); return; }
      const text = input.value;
      const cursor = el.selectionStart === null ? text.length
        : el.selectionStart;

      let i = cursor - 1;
      while (i >= 0 && !/\s/.test(text[i])) i--;
      const tokenStart = i + 1;
      const token = text.slice(tokenStart, cursor);

      if (token.startsWith('@') && token.length >= 1) {
        const q = token.slice(1);
        _showFilePopover(q, tokenStart, cursor);
        return;
      }
      if (/^\/[a-zA-Z]*$/.test(token)) {
        const q = token.slice(1).toLowerCase();
        const items = getAllCommands()
          .filter(c => !q || c.cmd.toLowerCase().startsWith(q))
          .map(c => ({
            key: c.cmd,
            main: '/' + c.cmd,
            sub: c.custom ? ('★ ' + (c.desc || '自定义命令')) : c.desc,
            cmd: c,
            isCustom: !!c.custom,
          }));
        popover.show = true;
        popover.kind = 'slash';
        popover.items = items;
        popover.selected = Math.min(popover.selected,
          Math.max(0, items.length - 1));
        popover.triggerStart = tokenStart;
        popover.triggerEnd = cursor;
        popover.query = q;
        return;
      }
      _hidePopover();
    }
    function _hidePopover() {
      popover.show = false;
      popover.items = [];
      popover.selected = 0;
      popover.triggerStart = -1;
      popover.triggerEnd = -1;
      hideFilePreview();
    }
    function _showFilePopover(q, start, end) {
      popover.show = true;
      popover.kind = 'file';
      popover.triggerStart = start;
      popover.triggerEnd = end;
      popover.query = q;

      if (_fileFetchTimer) clearTimeout(_fileFetchTimer);
      _fileFetchTimer = setTimeout(async () => {
        const seq = ++_fileFetchSeq;
        try {
          const r = await fetch(
            `/api/files?q=${encodeURIComponent(q)}&limit=30`);
          if (!r.ok) return;
          if (seq !== _fileFetchSeq) return;
          const data = await r.json();
          const files = data.files || [];
          popover.items = files.map(f => ({
            key: f, main: '@' + f, sub: '', path: f,
          }));
          popover.selected = 0;
        } catch {}
      }, 150);
    }
    function selectPopoverItem(idx) {
      if (idx < 0 || idx >= popover.items.length) return;
      const item = popover.items[idx];
      const el = inputEl.value;
      if (!el) return;

      if (popover.kind === 'slash' && item.cmd) {
        if (item.isCustom) {
          const before = input.value.slice(0, popover.triggerStart);
          const after = input.value.slice(popover.triggerEnd).trim();
          const template = item.cmd.template || '';
          const params = parseTemplateParams(template);
          _hidePopover();
          input.value = before;
          autoResize();

          if (params.length === 0) {
            input.value = (before + template).trim();
            nextTick(() => {
              autoResize();
              if (inputEl.value) {
                inputEl.value.focus();
                inputEl.value.setSelectionRange(
                  inputEl.value.value.length, inputEl.value.value.length);
              }
            });
            return;
          }
          if (params.length === 1 && params[0] === 'query') {
            let body = template.replace(/\{query\}/g, after);
            if (!after && template.includes('{query}')) {
              input.value = before + template;
              nextTick(() => {
                autoResize();
                const el2 = inputEl.value;
                if (el2) {
                  const idx2 = el2.value.indexOf('{query}');
                  el2.focus();
                  if (idx2 >= 0) {
                    el2.setSelectionRange(idx2, idx2 + 7);
                  } else {
                    el2.setSelectionRange(el2.value.length,
                                          el2.value.length);
                  }
                }
              });
              return;
            }
            input.value = (before + body).trim();
            nextTick(() => {
              autoResize();
              if (inputEl.value) {
                inputEl.value.focus();
                inputEl.value.setSelectionRange(
                  inputEl.value.value.length, inputEl.value.value.length);
              }
            });
            return;
          }
          openParamDialog(item.cmd.cmd, template);
          if (after && paramDialog.params.length) {
            paramDialog.params[0].value = after;
          }
          return;
        }
        input.value = '';
        autoResize();
        _hidePopover();
        try { item.cmd.run(); }
        catch (e) { toast('执行失败: ' + e); }
        return;
      }

      if (popover.kind === 'file' && item.path) {
        const before = input.value.slice(0, popover.triggerStart);
        const after = input.value.slice(popover.triggerEnd);
        const insert = `@${item.path} `;
        input.value = before + insert + after;
        const newCursor = (before + insert).length;
        nextTick(() => {
          autoResize();
          if (inputEl.value) {
            inputEl.value.focus();
            inputEl.value.setSelectionRange(newCursor, newCursor);
          }
        });
        _hidePopover();
      }
    }
    function onComposerKeydown(e) {
      if (popover.show && popover.items.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          popover.selected = (popover.selected + 1)
            % popover.items.length;
          _scrollPopoverSelectedIntoView();
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          popover.selected = (popover.selected - 1
            + popover.items.length) % popover.items.length;
          _scrollPopoverSelectedIntoView();
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          selectPopoverItem(popover.selected);
          return;
        }
        if (e.key === 'Tab') {
          e.preventDefault();
          selectPopoverItem(popover.selected);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          _hidePopover();
          return;
        }
      }
      onKeydown(e);
    }
    function _scrollPopoverSelectedIntoView() {
      nextTick(() => {
        const list = popoverListEl.value;
        if (!list) return;
        const active = list.querySelector('.popover-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
      });
      if (popover.kind === 'file') {
        scheduleFilePreview(popover.selected);
      } else {
        scheduleSlashPreview();
      }
    }

    /* ── 文件预览 ─────────────────────── */
    const filePreview = reactive({
      show: false, path: '', loading: false, binary: false,
      kind: '', size: 0, total_lines: 0, truncated: false, lines: [],
    });
    let _previewTimer = null;
    let _previewSeq = 0;
    let _lastHoveredPath = '';

    function scheduleFilePreview(idx) {
      if (!popover.show || popover.kind !== 'file') return;
      if (idx < 0 || idx >= popover.items.length) return;
      const path = popover.items[idx].path || '';
      if (!path || path === _lastHoveredPath) return;
      _lastHoveredPath = path;
      if (_previewTimer) clearTimeout(_previewTimer);
      _previewTimer = setTimeout(() => loadFilePreview(path), 320);
    }
    function scheduleSlashPreview() { hideFilePreview(); }
    async function loadFilePreview(path) {
      if (!path) return;
      filePreview.show = true;
      filePreview.loading = true;
      filePreview.path = path;
      filePreview.lines = [];
      filePreview.binary = false;
      filePreview.kind = '';
      filePreview.size = 0;
      filePreview.total_lines = 0;
      filePreview.truncated = false;

      const seq = ++_previewSeq;
      try {
        const r = await fetch(
          `/api/file-preview?path=${encodeURIComponent(path)}&lines=20`);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        if (seq !== _previewSeq) return;
        if (!data.ok) {
          filePreview.binary = true;
          filePreview.kind = data.error || '读取失败';
          filePreview.loading = false;
          return;
        }
        filePreview.binary = !!data.binary;
        filePreview.kind = data.kind || '';
        filePreview.size = data.size || 0;
        filePreview.total_lines = data.total_lines || 0;
        filePreview.truncated = !!data.truncated;
        filePreview.lines = data.lines || [];
        filePreview.loading = false;
      } catch (e) {
        if (seq !== _previewSeq) return;
        filePreview.binary = true;
        filePreview.kind = String(e);
        filePreview.loading = false;
      }
    }
    function hideFilePreview() {
      filePreview.show = false;
      _lastHoveredPath = '';
      if (_previewTimer) {
        clearTimeout(_previewTimer);
        _previewTimer = null;
      }
    }
    const _PREVIEW_LANG_MAP = {
      py: 'python', pyi: 'python',
      js: 'javascript', mjs: 'javascript', cjs: 'javascript',
      jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
      json: 'json', jsonl: 'json', yaml: 'yaml', yml: 'yaml',
      md: 'markdown', markdown: 'markdown',
      html: 'xml', htm: 'xml', xml: 'xml', svg: 'xml',
      css: 'css', scss: 'scss', sass: 'scss', less: 'less',
      sh: 'bash', bash: 'bash', zsh: 'bash', fish: 'bash',
      go: 'go', rs: 'rust', java: 'java', kt: 'kotlin',
      c: 'c', h: 'c', cpp: 'cpp', cc: 'cpp', cxx: 'cpp',
      hpp: 'cpp', hh: 'cpp',
      cs: 'csharp', rb: 'ruby', php: 'php', swift: 'swift',
      sql: 'sql', toml: 'ini', ini: 'ini', conf: 'ini',
      lua: 'lua', pl: 'perl', r: 'r', vue: 'xml', svelte: 'xml',
    };
    const previewHighlighted = computed(() => {
      const fp = filePreview;
      if (!fp.show || fp.binary || !fp.lines || !fp.lines.length) {
        return '';
      }
      const text = fp.lines.join('\n');
      const lower = (fp.path || '').toLowerCase();
      let lang = '';
      const basename = lower.split('/').pop() || '';
      if (basename === 'dockerfile' || basename.startsWith('dockerfile.')) {
        lang = 'dockerfile';
      } else if (basename === 'makefile' ||
                 basename.startsWith('makefile.')) {
        lang = 'makefile';
      } else {
        const ext = lower.includes('.') ? lower.split('.').pop() : '';
        lang = _PREVIEW_LANG_MAP[ext] || '';
      }
      try {
        if (!window.hljs) return escapeHtml(text);
        if (lang && hljs.getLanguage(lang)) {
          return hljs.highlight(text, { language: lang }).value;
        }
        if (text.length > 120) {
          const cands = ['python', 'javascript', 'typescript',
                         'json', 'yaml', 'bash', 'go', 'rust',
                         'java', 'cpp', 'c', 'sql', 'xml', 'css',
                         'markdown', 'ini', 'lua', 'ruby', 'php'];
          return hljs.highlightAuto(text, cands).value;
        }
        return escapeHtml(text);
      } catch { return escapeHtml(text); }
    });
    const previewLineNumbers = computed(() => {
      const fp = filePreview;
      if (!fp.show || fp.binary || !fp.lines || !fp.lines.length) return '';
      return Array.from({ length: fp.lines.length },
        (_, i) => i + 1).join('\n');
    });

    /* ── 上传 ──────────────────────────── */
    function _setupDragUpload() {
      const onEnter = (e) => {
        if (!e.dataTransfer) return;
        const types = Array.from(e.dataTransfer.types || []);
        if (!types.includes('Files')) return;
        e.preventDefault();
        _dragDepth++;
        if (_dragDepth > 0) dragging.value = true;
      };
      const onOver = (e) => {
        if (!e.dataTransfer) return;
        const types = Array.from(e.dataTransfer.types || []);
        if (!types.includes('Files')) return;
        e.preventDefault();
      };
      const onLeave = () => {
        _dragDepth--;
        if (_dragDepth <= 0) {
          _dragDepth = 0;
          dragging.value = false;
        }
      };
      const onDropWin = () => {
        _dragDepth = 0;
        dragging.value = false;
      };
      window.addEventListener('dragenter', onEnter);
      window.addEventListener('dragover', onOver);
      window.addEventListener('dragleave', onLeave);
      window.addEventListener('drop', onDropWin);
    }
    function onDragLeave() {
      _dragDepth--;
      if (_dragDepth <= 0) {
        _dragDepth = 0;
        dragging.value = false;
      }
    }
    function _uploadOne(file, onProgress, itemId) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        _activeXHRs.set(itemId, xhr);
        xhr.open('POST',
          `/api/upload?name=${encodeURIComponent(file.name)}`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
        xhr.onload = () => {
          _activeXHRs.delete(itemId);
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText)); }
            catch { reject(new Error('bad response')); }
          } else {
            reject(new Error(xhr.responseText || ('HTTP ' + xhr.status)));
          }
        };
        xhr.onerror = () => {
          _activeXHRs.delete(itemId);
          reject(new Error('network'));
        };
        xhr.onabort = () => {
          _activeXHRs.delete(itemId);
          const e = new Error('cancelled');
          e.cancelled = true;
          reject(e);
        };
        xhr.send(file);
      });
    }
    async function uploadFiles(files) {
      if (!files.length) return;
      const items = files.map(f => ({
        id: uid(), name: f.name, size: f.size, progress: 0,
        status: f.size > 25 * 1024 * 1024 ? 'skip' : 'pending',
        error: f.size > 25 * 1024 * 1024 ? '超过 25MB' : '',
        _file: f,
      }));
      uploadQueue.value = items;

      const uploaded = [];
      for (const it of items) {
        if (it.status === 'skip') continue;
        it.status = 'uploading';
        try {
          const data = await _uploadOne(
            it._file, (p) => { it.progress = p; }, it.id);
          if (data.ok && data.path) {
            it.status = 'done';
            it.progress = 1;
            uploaded.push(data.path);
          } else {
            it.status = 'error';
            it.error = data.error || '上传失败';
          }
        } catch (err) {
          if (err.cancelled) {
            it.status = 'cancelled';
            it.error = '已取消';
          } else {
            it.status = 'error';
            it.error = String(err).slice(0, 80);
          }
        }
      }

      _insertUploadedRefs(uploaded);
      _scheduleQueueCleanup(items);
    }
    function _insertUploadedRefs(paths) {
      if (!paths || !paths.length) return;
      const refs = paths.map(p => '@' + p).join(' ');
      if (input.value.trim()) {
        input.value = input.value.replace(/\s+$/, '') + ' ' + refs + ' ';
      } else {
        input.value = refs + ' ';
      }
      nextTick(() => {
        autoResize();
        if (inputEl.value) {
          inputEl.value.focus();
          inputEl.value.setSelectionRange(
            inputEl.value.value.length, inputEl.value.value.length);
        }
      });
    }
    function _scheduleQueueCleanup(items) {
      const hasError = items.some(x =>
        x.status === 'error' || x.status === 'skip' ||
        x.status === 'cancelled');
      const delay = hasError ? 8000 : 2000;
      setTimeout(() => {
        if (uploadQueue.value === items) uploadQueue.value = [];
      }, delay);
    }
    function cancelUpload(itemId) {
      const xhr = _activeXHRs.get(itemId);
      if (xhr) { try { xhr.abort(); } catch {} }
      const it = uploadQueue.value.find(x => x.id === itemId);
      if (!it) return;
      if (it.status === 'pending' || it.status === 'uploading') {
        it.status = 'cancelled';
        it.error = '已取消';
      }
    }
    function cancelAllUploads() {
      for (const it of uploadQueue.value) {
        if (it.status === 'pending' || it.status === 'uploading') {
          cancelUpload(it.id);
        }
      }
    }
    async function retryUpload(itemId) {
      const it = uploadQueue.value.find(x => x.id === itemId);
      if (!it) return;
      if (!it._file) {
        it.error = '文件引用已丢失，请重新拖拽';
        it.status = 'error';
        return;
      }
      it.status = 'uploading';
      it.progress = 0;
      it.error = '';
      try {
        const data = await _uploadOne(
          it._file, (p) => { it.progress = p; }, it.id);
        if (data.ok && data.path) {
          it.status = 'done';
          it.progress = 1;
          _insertUploadedRefs([data.path]);
        } else {
          it.status = 'error';
          it.error = data.error || '上传失败';
        }
      } catch (err) {
        if (err.cancelled) {
          it.status = 'cancelled';
          it.error = '已取消';
        } else {
          it.status = 'error';
          it.error = String(err).slice(0, 80);
        }
      }
    }
    function retryAllFailed() {
      for (const it of uploadQueue.value) {
        if (it.status === 'error' && it._file) retryUpload(it.id);
      }
    }
    function clearFinishedUploads() {
      uploadQueue.value = uploadQueue.value.filter(x =>
        x.status === 'pending' || x.status === 'uploading');
    }
    async function onDrop(e) {
      _dragDepth = 0;
      dragging.value = false;
      const files = Array.from((e.dataTransfer && e.dataTransfer.files) || []);
      if (!files.length) return;
      await uploadFiles(files);
    }
    async function onPaste(e) {
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      const files = [];
      for (const it of items) {
        if (it.kind === 'file') {
          const f = it.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length) {
        e.preventDefault();
        await uploadFiles(files);
      }
    }

    /* ── 自定义命令 ───────────────────── */
    function saveCustomCommands() {
      customCmdError.value = '';
      const names = new Set(BUILTIN_COMMANDS.map(c => c.cmd));
      for (const c of customCommands.value) {
        const n = (c.name || '').trim();
        if (!n) {
          customCmdError.value = '命令名不能为空';
          return;
        }
        if (!/^[a-zA-Z][a-zA-Z0-9_-]{0,19}$/.test(n)) {
          customCmdError.value = `命令名 "${n}" 非法`;
          return;
        }
        if (names.has(n)) {
          customCmdError.value = `命令名 "${n}" 冲突`;
          return;
        }
        names.add(n);
      }
      try {
        const clean = customCommands.value.map(c => ({
          name: (c.name || '').trim(),
          template: c.template || '',
          desc: c.desc || '自定义命令',
        }));
        localStorage.setItem(LS_CUSTOM_CMDS, JSON.stringify(clean));
      } catch {}
    }
    function addCustomCommand() {
      customCommands.value.push({
        name: '', template: '', desc: '自定义命令',
      });
    }
    function removeCustomCommand(i) {
      customCommands.value.splice(i, 1);
      saveCustomCommands();
    }
    function parseTemplateParams(template) {
      const params = [];
      const seen = new Set();
      const re = /\{([a-zA-Z_][a-zA-Z0-9_]*|\d+)\}/g;
      let m;
      while ((m = re.exec(template)) !== null) {
        if (!seen.has(m[1])) { seen.add(m[1]); params.push(m[1]); }
      }
      return params;
    }
    function openParamDialog(cmdName, template) {
      const params = parseTemplateParams(template);
      paramDialog.cmdName = cmdName;
      paramDialog.template = template;
      paramDialog.params = params.map(name => ({ name, value: '' }));
      paramDialog.show = true;
      nextTick(() => {
        const el = document.querySelector('.param-modal .field input');
        if (el) el.focus();
      });
    }
    function applyParamDialog() {
      if (!paramDialog.show) return;
      let body = paramDialog.template;
      for (const p of paramDialog.params) {
        const re = new RegExp(
          `\\{${p.name.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\}`,
          'g');
        body = body.replace(re, p.value || '');
      }
      input.value = body.trim();
      paramDialog.show = false;
      nextTick(() => {
        autoResize();
        if (inputEl.value) {
          inputEl.value.focus();
          inputEl.value.setSelectionRange(
            inputEl.value.value.length, inputEl.value.value.length);
        }
      });
    }
    function previewTemplate(template, sample) {
      if (!template) return '';
      const s = template.replace(/\{query\}/g, sample || '');
      return s.length > 80 ? s.slice(0, 77) + '…' : s;
    }

    /* ── 搜索 ─────────────────────────── */
    function openSearch() {
      showSearch.value = true;
      nextTick(() => {
        if (searchInputEl.value) searchInputEl.value.focus();
      });
    }
    function closeSearch() { showSearch.value = false; }
    function applySearch() {
      const q = searchQuery.value.trim();
      searchError.value = '';
      if (!q) {
        appliedSearch.value = '';
        showSearch.value = false;
        return;
      }
      if (searchRegexMode.value) {
        try {
          new RegExp(q, searchCaseSensitive.value ? '' : 'i');
        } catch (e) {
          searchError.value = String(e).slice(0, 60);
          return;
        }
      }
      appliedSearch.value = q;
      showSearch.value = false;
    }
    function clearSearch() {
      searchQuery.value = '';
      appliedSearch.value = '';
      searchError.value = '';
    }
    function _searchRegExp() {
      const q = appliedSearch.value;
      if (!q) return null;
      const flags = searchCaseSensitive.value ? '' : 'i';
      try {
        return searchRegexMode.value
          ? new RegExp(q, flags)
          : new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags);
      } catch { return null; }
    }
    function isMatch(m) {
      if (!appliedSearch.value) return true;
      const rx = _searchRegExp();
      if (!rx) return false;
      return rx.test(m.content || '');
    }
    const filteredMessages = computed(() => {
      if (!appliedSearch.value) {
        matchedMessageCount.value = 0;
        return messages.value;
      }
      const rx = _searchRegExp();
      if (!rx) {
        matchedMessageCount.value = 0;
        return messages.value;
      }
      const match = messages.value.filter(m => rx.test(m.content || ''));
      matchedMessageCount.value = match.length;
      return messages.value;
    });

    /* ── 右键菜单 ─────────────────────── */
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
        return;
      }
      const collapseBtn = e.target.closest('.code-expand-btn');
      if (collapseBtn) {
        const block = collapseBtn.closest('.code-block');
        if (!block) return;
        const expanded = block.classList.toggle('expanded');
        collapseBtn.classList.toggle('expanded', expanded);
        const label = collapseBtn.querySelector('.expand-label');
        if (label) {
          const text = label.textContent;
          if (expanded) {
            label.textContent = text.replace(/^展开/, '折叠')
              .replace(/全部 \d+ 行/, '');
          } else {
            const m = text.match(/\d+/);
            label.textContent = '展开全部 ' + (m ? m[0] : '') + ' 行';
          }
        }
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
      nextTick(() => {
        const el2 = document.querySelector('.ctx-menu');
        if (!el2) return;
        const r = el2.getBoundingClientRect();
        if (r.right > window.innerWidth) {
          ctxMenu.x = window.innerWidth - r.width - 8;
        }
        if (r.bottom > window.innerHeight) {
          ctxMenu.y = window.innerHeight - r.height - 8;
        }
      });
    }
    function closeCtxMenu() { ctxMenu.show = false; }
    function ctxCopy() {
      copyText(ctxMenu.content, t('toast.copied'));
      closeCtxMenu();
    }
    function ctxCopyAll() {
      const all = messages.value.map(m =>
        `[${m.role}]\n${m.content || ''}`).join('\n\n---\n\n');
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
      nextTick(() => {
        autoResize();
        if (inputEl.value) inputEl.value.focus();
      });
      closeCtxMenu();
    }
    function ctxRegenerate() {
      closeCtxMenu();
      regenerate();
    }

    /* ── 大纲跳转 ─────────────────────── */
    function jumpToMessage(msgId, elId) {
      if (appliedSearch.value) clearSearch();
      nextTick(() => {
        let el = null;
        if (msgId) {
          el = document.querySelector(`[data-msg-id="${msgId}"]`);
        }
        if (!el && elId) el = document.getElementById(elId);
        if (!el) return;
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        el.classList.add('msg-flash');
        setTimeout(() => el.classList.remove('msg-flash'), 1400);
      });
    }

    /* ── 通知 ─────────────────────────── */
    const canNotify = ref(typeof Notification !== 'undefined');
    const notifyEnabled = ref(
      localStorage.getItem('cedric_webui_notify') === '1');
    function toggleNotifications() {
      if (!canNotify.value) return;
      if (!notifyEnabled.value) {
        if (Notification.permission === 'granted') {
          notifyEnabled.value = true;
          localStorage.setItem('cedric_webui_notify', '1');
          toast(t('notify.enabled'));
          return;
        }
        if (Notification.permission === 'denied') {
          toast(t('notify.denied'));
          return;
        }
        Notification.requestPermission().then(p => {
          if (p === 'granted') {
            notifyEnabled.value = true;
            localStorage.setItem('cedric_webui_notify', '1');
            toast(t('notify.enabled'));
          } else {
            toast(t('notify.denied'));
          }
        });
      } else {
        notifyEnabled.value = false;
        localStorage.setItem('cedric_webui_notify', '0');
        toast(t('notify.disabled'));
      }
    }
    function _notify(title, body) {
      if (!notifyEnabled.value) return;
      if (typeof Notification === 'undefined') return;
      if (Notification.permission !== 'granted') return;
      if (document.visibilityState === 'visible') return;
      try {
        const n = new Notification(title, {
          body: body.slice(0, 200),
          tag: 'cedric-done',
          renotify: false,
          silent: false,
        });
        n.onclick = () => { window.focus(); n.close(); };
      } catch {}
    }

    /* ── 多窗口同步 ───────────────────── */
    const _bcName = 'cedric_webui_sync';
    let _bc = null;
    function _setupSync() {
      if (typeof BroadcastChannel === 'undefined') return;
      try { _bc = new BroadcastChannel(_bcName); } catch { return; }
      _bc.onmessage = (evt) => {
        const m = evt.data || {};
        if (m.type === 'sessions-updated') {
          const saved = loadLocalSessions();
          _reloadSessionsFromStorage(saved);
          toast(t('toast.sessionUpdated'));
        } else if (m.type === 'settings-updated') {
          const s = loadLocalSettings();
          Object.assign(settings, s);
        } else if (m.type === 'theme-updated') {
          if (m.theme !== theme.value) {
            theme.value = m.theme;
            _syncAllClasses();
          }
        }
      };
    }
    function _broadcast(type, payload) {
      if (!_bc) return;
      try { _bc.postMessage({ type, ...payload }); } catch {}
    }
    function _reloadSessionsFromStorage(saved) {
      const curId = currentSessionId.value;
      sessions.value = (saved || []).map(s => {
        const sess = reactive({
          id: s.id,
          title: s.title || '',
          tree: reactive(s.tree
            ? { nodes: s.tree.nodes || {}, leafId: s.tree.leafId || null }
            : _linearToTree(s.messages || [])),
          asks: Array.isArray(s.asks) ? s.asks : [],
          pinned: Array.isArray(s.pinned) ? s.pinned : [],
          turnCounter: s.turnCounter || 0,
          createdAt: s.createdAt || Date.now(),
          updatedAt: s.updatedAt || Date.now(),
        });
        for (const k in sess.tree.nodes) {
          sess.tree.nodes[k] = reactive(sess.tree.nodes[k]);
        }
        return sess;
      });
      if (sessions.value.find(x => x.id === curId)) {
        currentSessionId.value = curId;
      } else if (sessions.value.length) {
        currentSessionId.value = sessions.value[0].id;
      }
    }

    /* ── 移动端手势 ───────────────────── */
    function _setupTouchGestures() {
      const isMobile = () => window.innerWidth <= 720;
      if (!('ontouchstart' in window)) return;
      let tx = 0, ty = 0, tracking = false;
      let edgeSwipe = false, msgSwipe = false;
      let swipeMsgId = '', swipeMsgEl = null;

      document.addEventListener('touchstart', (e) => {
        if (!isMobile()) return;
        const t0 = e.touches[0];
        tx = t0.clientX; ty = t0.clientY;
        tracking = true; edgeSwipe = false; msgSwipe = false;
        if (t0.clientX < 30 && !sidebarOpen.value) edgeSwipe = true;
        const msgEl = e.target.closest('.msg');
        if (msgEl && msgEl.dataset.msgId) {
          msgSwipe = true;
          swipeMsgId = msgEl.dataset.msgId;
          swipeMsgEl = msgEl;
        }
      }, { passive: true });

      document.addEventListener('touchmove', (e) => {
        if (!tracking) return;
        const t0 = e.touches[0];
        const dx = t0.clientX - tx;
        const dy = t0.clientY - ty;
        if (edgeSwipe && Math.abs(dx) > Math.abs(dy) && dx > 5) {
          const pct = Math.min(dx / 260, 1);
          const sb = document.querySelector('.sidebar');
          if (sb) {
            sb.style.transform = `translateX(${(pct - 1) * 100}%)`;
            sb.style.marginLeft = '0';
          }
        } else if (msgSwipe && swipeMsgEl &&
                   Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 10) {
          const px = Math.max(-80, Math.min(0, dx));
          swipeMsgEl.style.transform = `translateX(${px}px)`;
          swipeMsgEl.style.transition = 'none';
        }
      }, { passive: true });

      document.addEventListener('touchend', (e) => {
        if (!tracking) return;
        tracking = false;
        const t0 = e.changedTouches[0];
        const dx = t0.clientX - tx;
        const dy = t0.clientY - ty;
        if (edgeSwipe) {
          const sb = document.querySelector('.sidebar');
          if (sb) { sb.style.transform = ''; sb.style.marginLeft = ''; }
          if (dx > 100 && !sidebarOpen.value) sidebarOpen.value = true;
          edgeSwipe = false;
        }
        if (msgSwipe && swipeMsgEl) {
          if (dx < -50 && swipeMsgId) togglePin(swipeMsgId);
          swipeMsgEl.style.transform = '';
          swipeMsgEl.style.transition = '';
          swipeMsgEl = null; swipeMsgId = '';
          msgSwipe = false;
        }
      }, { passive: true });
    }

    /* ── 后端 API ─────────────────────── */
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
            ...x, description: x.description || '',
          }));
        }
      } catch {}
    }
    async function toggleTool(tool) {
      const target = !tool.enabled;
      tool.enabled = target;
      try {
        const r = await fetch(
          `/api/tools/${encodeURIComponent(tool.name)}/toggle`,
          { method: 'POST' });
        if (r.ok) {
          const data = await r.json();
          tool.enabled = data.enabled;
          toast(t(tool.enabled ? 'toast.toolOn' : 'toast.toolOff',
                  { name: tool.name }));
        } else {
          tool.enabled = !target;
          toast(t('toast.opFailed'));
        }
      } catch {
        tool.enabled = !target;
        toast(t('toast.opFailed'));
      }
    }
    async function loadConfigFromServer() {
      try {
        const r = await fetch('/api/config');
        if (!r.ok) return;
        const data = await r.json();
        const ui = data.ui || {};
        if (!localStorage.getItem(LS_THEME) && ui.theme) {
          theme.value = ui.theme;
        }
        if (!localStorage.getItem(LS_ACRYLIC) && ui.acrylic) {
          acrylicStrength.value = ui.acrylic;
        }
        if (ui.think_level && ui.think_level !== 'medium' &&
            (!settings.think_level || settings.think_level === 'medium')) {
          settings.think_level = ui.think_level;
        }
        if (!localStorage.getItem(LS_HUE1) &&
            typeof ui.particle_hue1 === 'number') {
          particleHue1.value = ui.particle_hue1;
        }
        if (!localStorage.getItem(LS_HUE2) &&
            typeof ui.particle_hue2 === 'number') {
          particleHue2.value = ui.particle_hue2;
        }
        _syncAllClasses();
      } catch {}
    }
    async function syncConfigToServer() {
      if (configSyncing.value) return;
      configSyncing.value = true;
      try {
        const r = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            theme: theme.value,
            acrylic: acrylicStrength.value,
            think_level: settings.think_level,
            particle_hue1: particleHue1.value,
            particle_hue2: particleHue2.value,
          }),
        });
        if (!r.ok) {
          const err = await r.text();
          toast(t('toast.syncFailed') + ': ' + err.slice(0, 60));
          return;
        }
        const data = await r.json();
        if (data.ok) {
          toast(t('toast.synced', { n: data.changed.length }));
        } else {
          toast(t('toast.syncFailed') + ': ' +
                (data.error || '未知错误'));
        }
      } catch (e) {
        toast(t('toast.syncFailed') + ': ' + String(e).slice(0, 60));
      } finally {
        configSyncing.value = false;
      }
    }

    /* ── ask_user ─────────────────────── */
    function selectAskOption(qi, oi) {
      const q = askUser.value && askUser.value.questions[qi];
      if (!q) return;
      q.selected = oi;
      q.answer = '';
    }
    function onAskInput(qi, e) {
      const q = askUser.value && askUser.value.questions[qi];
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
        if (q.selected >= 0 && q.selected < q.options.length) {
          v = q.options[q.selected];
        } else if (q.answer && q.answer.trim()) {
          v = q.answer.trim();
        } else if (q.default) {
          v = q.default;
        }
        if (!v) {
          toast(`请回答：${q.question.slice(0, 20)}`);
          return;
        }
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
        let rec = sess && sess.asks
          ? sess.asks.find(x => x.id === first.id) : null;
        if (!rec) {
          rec = {
            id: first.id,
            ts: (first.created_at || Date.now() / 1000) * 1000,
            turn: sess ? (sess.turnCounter || 1) : 1,
            thread: null, parent_id: null,
            header: first.header || '',
            timeout: first.timeout || 0,
            questions: (first.questions || []).map(q => ({
              key: q.key, question: q.question,
              options: q.options || [], default: q.default || '',
              allow_custom: q.allow_custom !== false,
              show_if: q.show_if || null,
              answer: '', selected: -1, _visible: true,
            })),
          };
          if (sess) {
            if (!Array.isArray(sess.asks)) sess.asks = [];
            const prev = sess.asks.length
              ? sess.asks[sess.asks.length - 1] : null;
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

    /* ── 导出 ─────────────────────────── */
    function _asksToMarkdown(asks) {
      const lines = ['# 问答历史', '', `- 记录数：${asks.length}`, ''];
      const threads = {};
      const order = [];
      for (const rec of asks) {
        const th = rec.thread || rec.id;
        if (!threads[th]) { threads[th] = []; order.push(th); }
        threads[th].push(rec);
      }
      for (let i = 0; i < order.length; i++) {
        lines.push(`## Thread ${i + 1}`); lines.push('');
        for (const rec of threads[order[i]]) {
          const tstr = new Date(rec.ts || 0).toLocaleString();
          lines.push(`### ${tstr} — ${rec.header || '模型提问'}`);
          lines.push('');
          for (const q of rec.questions || []) {
            lines.push(`**${q.key}**: ${q.question}`);
            if (q.options && q.options.length) {
              for (const o of q.options) {
                lines.push(`- ${o === q.default ? '★ ' : ''}${o}`);
              }
            }
            lines.push(''); lines.push(`**回答**：${q.answer || '（未答）'}`);
            lines.push('');
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
            (q.options || []).join(' | '), q.default || '',
            q.answer || '',
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
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
    function exportAsks(fmt) {
      const s = currentSession.value;
      if (!s || !s.asks || !s.asks.length) {
        toast(t('toast.noAsks'));
        return;
      }
      let content, mime, ext;
      if (fmt === 'json') {
        content = JSON.stringify(s.asks, null, 2);
        mime = 'application/json'; ext = 'json';
      } else if (fmt === 'csv') {
        content = _asksToCSV(s.asks); mime = 'text/csv'; ext = 'csv';
      } else {
        content = _asksToMarkdown(s.asks);
        mime = 'text/markdown'; ext = 'md';
      }
      _downloadBlob(content, `asks-${s.id}.${ext}`, mime);
      toast(t('toast.exported', { fmt: ext.toUpperCase() }));
    }
    function exportSession(fmt) {
      const s = currentSession.value;
      if (!s) return;
      if (fmt === 'json') {
        _downloadBlob(JSON.stringify(s, null, 2),
                      `session-${s.id}.json`, 'application/json');
      } else {
        const lines = [`# ${s.title || '会话'}`, '',
          `- 导出：${new Date().toLocaleString()}`, ''];
        for (const m of messages.value) {
          if (m.role === 'user') {
            lines.push('## 用户', '', m.content || '', '');
          } else if (m.role === 'assistant') {
            if (m.reasoning) {
              lines.push('<details><summary>思考过程</summary>', '',
                          m.reasoning, '', '</details>', '');
            }
            if (m.content) lines.push('## 助手', '', m.content, '');
          } else if (m.role === 'error') {
            lines.push(`> ⚠ ${m.content}`, '');
          }
        }
        _downloadBlob(lines.join('\n'), `session-${s.id}.md`,
                      'text/markdown');
      }
      toast(t('toast.exported', { fmt: fmt.toUpperCase() }));
    }
    function exportAllSessions() {
      if (!sessions.value.length) { toast('无会话可导出'); return; }
      const payload = {
        version: 1,
        exported_at: new Date().toISOString(),
        sessions: sessions.value.map(plainifySession),
      };
      _downloadBlob(JSON.stringify(payload, null, 2),
                    `cedric-sessions-${Date.now()}.json`,
                    'application/json');
      toast(`已导出 ${sessions.value.length} 个会话`);
    }
    function importSessionsFromFile() {
      const inp = document.createElement('input');
      inp.type = 'file';
      inp.accept = '.json,application/json';
      inp.onchange = async (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f) return;
        try {
          const text = await f.text();
          const data = JSON.parse(text);
          const list = Array.isArray(data) ? data : (data.sessions || []);
          if (!Array.isArray(list) || !list.length) {
            toast('文件中无有效会话');
            return;
          }
          const existingIds = new Set(sessions.value.map(s => s.id));
          let added = 0, skipped = 0;
          for (const raw of list) {
            if (!raw || typeof raw !== 'object') { skipped++; continue; }
            let id = raw.id;
            if (existingIds.has(id)) id = id + '_imp_' + uid();
            const sess = reactive({
              id,
              title: (raw.title || '') + (raw.id !== id ? ' (导入)' : ''),
              tree: reactive(raw.tree && raw.tree.nodes
                ? { nodes: raw.tree.nodes || {},
                    leafId: raw.tree.leafId || null }
                : _linearToTree(raw.messages || [])),
              asks: Array.isArray(raw.asks) ? raw.asks : [],
              pinned: Array.isArray(raw.pinned) ? raw.pinned : [],
              turnCounter: raw.turnCounter || 0,
              createdAt: raw.createdAt || Date.now(),
              updatedAt: raw.updatedAt || Date.now(),
            });
            for (const k in sess.tree.nodes) {
              sess.tree.nodes[k] = reactive(sess.tree.nodes[k]);
            }
            sessions.value.push(sess);
            existingIds.add(id);
            added++;
          }
          persistSessions(sessions.value.map(plainifySession));
          toast(`已导入 ${added} 个会话` +
                (skipped ? `，跳过 ${skipped} 个` : ''));
          if (added && !currentSessionId.value) {
            currentSessionId.value = sessions.value[0].id;
          }
        } catch (err) {
          toast('导入失败: ' + String(err).slice(0, 60));
        }
      };
      inp.click();
    }

    /* ── 发送 ─────────────────────────── */
    async function send(text, opts) {
      opts = opts || {};
      const content = (text !== undefined ? text : input.value).trim();
      if (!content || streaming.value) return;
      ensureSession();
      const s = currentSession.value;
      if (!s.tree) s.tree = reactive({ nodes: {}, leafId: null });
      if (s.tree.nodes === undefined) s.tree.nodes = {};
      s.turnCounter = (s.turnCounter || 0) + 1;

      if (text === undefined && !opts.regen) {
        inputHistory.value.push(content);
        if (inputHistory.value.length > 100) inputHistory.value.shift();
        historyIndex.value = -1;
        input.value = '';
        nextTick(() => {
          autoResize();
          if (inputEl.value) inputEl.value.focus();
        });
      }

      const parentId = s.tree.leafId;
      const userNode = _createNode({
        _id: uid(), role: 'user', content,
      }, parentId);
      await _streamAssistant(userNode);
    }
    async function _streamAssistant(userNode) {
      const assistantNode = _createNode({
        _id: uid(), role: 'assistant',
        content: '', reasoning: '', toolCalls: [], meta: '',
        streaming: true,
      }, userNode.id);

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
      showParticleProgress('生成回答');

      try {
        const resp = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userNode.content,
            auto_approve: autoApprove.value,
          }),
          signal: abortController.signal,
        });
        if (!resp.ok) {
          const err = await resp.text();
          assistantNode.streaming = false;
          assistantNode.role = 'error';
          assistantNode.content = t('err.httpStatus',
            { status: resp.status }) + ': ' + err.slice(0, 300);
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
            try { handleEvent(JSON.parse(data), assistantNode); }
            catch {}
          }
          scrollToBottom();
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          assistantNode.content = (assistantNode.content || '')
            + '\n\n_(' + t('toast.stopped') + ')_';
        } else {
          assistantNode.role = 'error';
          assistantNode.content = String(e);
        }
      } finally {
        if (streamSpeedTimer) {
          clearInterval(streamSpeedTimer); streamSpeedTimer = null;
        }
        streamSpeed.value = 0;
        assistantNode.streaming = false;
        streaming.value = false;
        abortController = null;
        saveCurrentSession();
        scrollToBottom();
        setParticleProgress(1);
        setTimeout(hideParticleProgress, 300);
        if (assistantNode.content) {
          const preview = assistantNode.content
            .replace(/[#*`>_~\[\]]/g, '').slice(0, 80);
          _notify(t('notify.title'), preview);
        }
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
          setParticleProgress(Math.min(0.9, msg.content.length / 2000));
          break;
        case 'tool_call':
          msg.toolCalls.push({
            name: evt.name || '?', target: evt.target || '',
            summary: evt.summary || '', status: evt.status || 'ok',
          });
          break;
        case 'done':
          msg.streaming = false;
          if (evt.duration) {
            msg.meta = (lang.value === 'zh' ? '耗时 ' : 'took ')
              + evt.duration + 's';
          }
          break;
        case 'error':
          msg.streaming = false;
          messages.value.push({
            _id: uid(), role: 'error',
            content: evt.message || 'Error',
          });
          break;
        case 'ask_user': {
          const sess = currentSession.value;
          const rec = {
            id: evt.id, ts: Date.now(),
            turn: sess ? (sess.turnCounter || 1) : 1,
            thread: null, parent_id: null,
            header: evt.header || '',
            timeout: evt.timeout || 0,
            questions: (evt.questions || []).map(q => ({
              key: q.key, question: q.question,
              options: q.options || [],
              default: q.default || '',
              allow_custom: q.allow_custom !== false,
              show_if: q.show_if || null,
              answer: '', selected: -1, _visible: true,
            })),
          };
          if (sess) {
            if (!Array.isArray(sess.asks)) sess.asks = [];
            const prev = sess.asks.length
              ? sess.asks[sess.asks.length - 1] : null;
            if (prev && prev.turn === rec.turn) {
              rec.thread = prev.thread || prev.id;
              rec.parent_id = prev.id;
            } else { rec.thread = rec.id; }
            sess.asks.push(rec);
          } else { rec.thread = rec.id; }
          askUser.value = rec;
          _notify(t('notify.titleAsk'), evt.header || '模型需要你的回答');
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

    /* ── 粒子进度条 ───────────────────── */
    let _ppRaf = null;
    function showParticleProgress(label) {
      particleProgress.show = true;
      particleProgress.percent = 0;
      particleProgress.label = label || '';
      particleProgress.particles = [];
      nextTick(() => _initParticleCanvas());
    }
    function setParticleProgress(p) {
      particleProgress.percent = Math.max(0, Math.min(1, p));
      const target = Math.floor(particleProgress.percent * 100);
      while (particleProgress.particles.length < target) {
        particleProgress.particles.push({
          x: 0, y: 0, vx: 0, vy: 0,
          size: 1.5 + Math.random() * 2,
          hue: Math.random() < 0.5 ? 217 : 200,
          trail: [], lastSampleTime: 0,
        });
      }
    }
    function hideParticleProgress() {
      if (particleProgress.raf) {
        cancelAnimationFrame(particleProgress.raf);
        particleProgress.raf = null;
      }
      setTimeout(() => { particleProgress.show = false; }, 600);
    }
    function _initParticleCanvas() {
      const cvs = particleProgress.canvasRef;
      if (!cvs) return;
      const ctx = cvs.getContext('2d');
      const resize = () => {
        const rect = cvs.getBoundingClientRect();
        cvs.width = rect.width * devicePixelRatio;
        cvs.height = rect.height * devicePixelRatio;
        ctx.setTransform(devicePixelRatio, 0, 0,
                          devicePixelRatio, 0, 0);
      };
      resize();
      const w = () => cvs.width / devicePixelRatio;
      const h = () => cvs.height / devicePixelRatio;
      const TRAIL_LENGTH = 12;
      const TRAIL_INTERVAL = 30;
      const loop = () => {
        ctx.clearRect(0, 0, w(), h());
        const cur = particleProgress.percent;
        const total = particleProgress.particles.length;
        const now = performance.now();
        ctx.strokeStyle = 'rgba(217, 119, 87, 0.12)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, h() / 2);
        ctx.lineTo(w(), h() / 2);
        ctx.stroke();
        const doneW = w() * cur;
        if (doneW > 0) {
          const grad = ctx.createLinearGradient(0, 0, doneW, 0);
          grad.addColorStop(0, 'rgba(217, 119, 87, 0.55)');
          grad.addColorStop(1, 'rgba(125, 207, 255, 0.75)');
          ctx.strokeStyle = grad;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(0, h() / 2);
          ctx.lineTo(doneW, h() / 2);
          ctx.stroke();
        }
        for (let i = 0; i < total; i++) {
          const p = particleProgress.particles[i];
          const tt = i / Math.max(1, total - 1);
          const targetX = w() * tt;
          const targetY = h() / 2;
          p.x += (targetX - p.x) * 0.15;
          p.y += (targetY - p.y) * 0.15;
          if (now - p.lastSampleTime > TRAIL_INTERVAL) {
            p.lastSampleTime = now;
            p.trail.push({ x: p.x, y: p.y, t: now });
            if (p.trail.length > TRAIL_LENGTH) p.trail.shift();
          }
          const isCurrent = Math.abs(tt - cur) < 0.03;
          const breathe = isCurrent
            ? 1 + Math.sin(now / 200) * 0.3 : 1;
          if (p.trail.length > 1) {
            for (let j = 0; j < p.trail.length - 1; j++) {
              const t0 = p.trail[j];
              const t1 = p.trail[j + 1];
              const age = j / p.trail.length;
              const alpha = age * 0.55;
              const width = age * p.size * 1.2;
              ctx.strokeStyle =
                `hsla(${p.hue}, 85%, 65%, ${alpha})`;
              ctx.lineWidth = width;
              ctx.lineCap = 'round';
              ctx.beginPath();
              ctx.moveTo(t0.x, t0.y);
              ctx.lineTo(t1.x, t1.y);
              ctx.stroke();
            }
          }
          const glowR = p.size * 4 * breathe;
          const grd = ctx.createRadialGradient(
            p.x, p.y, 0, p.x, p.y, glowR);
          grd.addColorStop(0,
            `hsla(${p.hue}, 90%, 65%, ${isCurrent ? 0.85 : 0.6})`);
          grd.addColorStop(0.5,
            `hsla(${p.hue}, 90%, 65%, ${isCurrent ? 0.35 : 0.2})`);
          grd.addColorStop(1, `hsla(${p.hue}, 90%, 65%, 0)`);
          ctx.fillStyle = grd;
          ctx.beginPath();
          ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = isCurrent
            ? 'rgba(255, 255, 255, 0.95)'
            : `hsla(${p.hue}, 90%, 75%, 0.85)`;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.size * breathe, 0, Math.PI * 2);
          ctx.fill();
        }
        if (cur < 1 && total > 0) {
          const curX = w() * cur;
          const curY = h() / 2;
          const glow = 8 + Math.sin(now / 150) * 3;
          ctx.strokeStyle =
            `rgba(255, 255, 255, ${0.4 + Math.sin(now / 200) * 0.2})`;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(curX, curY, glow, 0, Math.PI * 2);
          ctx.stroke();
          const grd = ctx.createRadialGradient(
            curX, curY, 0, curX, curY, glow);
          grd.addColorStop(0, 'rgba(255, 255, 255, 0.9)');
          grd.addColorStop(1, 'rgba(217, 119, 87, 0)');
          ctx.fillStyle = grd;
          ctx.beginPath();
          ctx.arc(curX, curY, glow, 0, Math.PI * 2);
          ctx.fill();
        }
        particleProgress.raf = requestAnimationFrame(loop);
      };
      loop();
    }

    /* ── 设置 ─────────────────────────── */
    function saveSettings() {
      persistSettings({ ...settings });
      showSettings.value = false;
      toast(t('toast.settingsSaved'));
      _broadcast('settings-updated', {});
    }
    function toggleSidebar() {
      sidebarOpen.value = !sidebarOpen.value;
    }

    /* ── 全局快捷键 ───────────────────── */
    function onGlobalKeydown(e) {
      const meta = e.ctrlKey || e.metaKey;
      const inInput = e.target.tagName === 'INPUT' ||
                      e.target.tagName === 'TEXTAREA';
      if (meta && e.key.toLowerCase() === 'k') {
        e.preventDefault(); newSession(); return;
      }
      if (meta && e.key.toLowerCase() === 'b') {
        e.preventDefault(); toggleSidebar(); return;
      }
      if (meta && e.key.toLowerCase() === 'j') {
        e.preventDefault(); toggleTheme(); return;
      }
      if (meta && e.key.toLowerCase() === 'f') {
        e.preventDefault(); openSearch(); return;
      }
      if (meta && e.key === '/') {
        e.preventDefault();
        input.value = '/';
        nextTick(() => {
          autoResize();
          if (inputEl.value) { inputEl.value.focus(); detectPopover(); }
        });
        return;
      }
      if (meta && e.key === ',') {
        e.preventDefault();
        showSettings.value = !showSettings.value;
        return;
      }
      if (e.key === 'Escape') {
        if (ctxMenu.show) { closeCtxMenu(); return; }
        if (showSearch.value) { closeSearch(); return; }
        if (showSettings.value) { showSettings.value = false; return; }
        if (showHelp.value) { showHelp.value = false; return; }
        return;
      }
      if (e.key === '?' && !inInput && !meta) {
        e.preventDefault();
        showHelp.value = !showHelp.value;
      }
    }

    /* ── init ─────────────────────────── */
    onMounted(async () => {
      setLang(lang.value);
      _syncAllClasses();

      const saved = loadLocalSessions();
      sessions.value = saved.map(s => {
        const sess = reactive({
          id: s.id,
          title: s.title || '',
          tree: reactive(s.tree
            ? { nodes: s.tree.nodes || {},
                leafId: s.tree.leafId || null }
            : _linearToTree(s.messages || [])),
          asks: Array.isArray(s.asks) ? s.asks : [],
          pinned: Array.isArray(s.pinned) ? s.pinned : [],
          turnCounter: s.turnCounter || 0,
          createdAt: s.createdAt || Date.now(),
          updatedAt: s.updatedAt || Date.now(),
        });
        for (const k in sess.tree.nodes) {
          sess.tree.nodes[k] = reactive(sess.tree.nodes[k]);
        }
        return sess;
      });
      if (sessions.value.length > 0) {
        currentSessionId.value = sessions.value[0].id;
      } else {
        newSession();
      }

      await checkHealth();
      await loadStatus();
      await loadTools();
      await loadPendingAsks();
      await loadConfigFromServer();

      setInterval(loadStatus, 5000);
      setInterval(checkHealth, 15000);

      window.addEventListener('keydown', onGlobalKeydown);
      _setupDragUpload();
      _setupSync();
      _setupTouchGestures();

      nextTick(() => {
        if (inputEl.value) inputEl.value.focus();
        scrollToBottom(true);
      });
    });

    onUnmounted(() => {
      try { if (_bc) _bc.close(); } catch {}
      stopParticles();
      if (streamSpeedTimer) clearInterval(streamSpeedTimer);
    });

    watch(messages, () => {
      if (!streaming.value) saveCurrentSession();
    }, { deep: true });

    watch(() => settings.think_level, _syncAllClasses);

    /* ── return ───────────────────────── */
    return {
      // state
      lang, theme, acrylicStrength, particleHue1, particleHue2,
      hueGradient, configSyncing,
      messages, input, streaming, showSettings, showHelp, showSearch,
      showTreeModal,
      sidebarOpen, sidebarTab, sessions, currentSessionId,
      gatewayOnline, gatewayStats, autoApprove, tools, toolsFilter,
      toolsCategory, showScrollBtn, toasts, settings,
      messagesEl, inputEl, searchInputEl, popoverListEl,
      askUser, searchQuery, matchedMessageCount, streamSpeed, ctxMenu,
      outlineFilter, dragging, uploadQueue, paramDialog,
      customCommands, customCmdError, filePreview,
      particleProgress, canNotify, notifyEnabled,
      // computed
      model, currentSession, suggestions, lastUserIndex,
      lastUserIndexInAll, searchActive,
      askCount, askThreads, visibleAskQuestions,
      filteredTools, filteredMessages,
      outlineGroups, outlineExpanded, outlineCount,
      filteredOutlineGroups, outlineMatchCount,
      pinnedMessages,
      treeLayout,
      previewHighlighted, previewLineNumbers,
      // methods
      t, setLang, toggleLang, toggleTheme,
      setAcrylicStrength, onHueInput, setHuePreset,
      renderMarkdown, fmtTime, isMatch,
      send, stopStream, newSession, switchSession, deleteSession,
      editMessage, regenerate, clearMessages, clearAllSessions,
      toggleTool, saveSettings, toggleSidebar,
      copyText, scrollToBottom, onKeydown, onComposerKeydown,
      autoResize, onMessagesScroll, onChatClick, onChatRightClick,
      closeCtxMenu, ctxCopy, ctxCopyAll, ctxExport, ctxQuote,
      ctxRegenerate,
      openSearch, closeSearch, applySearch, clearSearch,
      selectAskOption, onAskInput, submitAskAnswer, cancelAsk,
      loadPendingAsks,
      toggleAskThread, isAskThreadExpanded,
      exportAsks, exportSession, exportAllSessions,
      importSessionsFromFile,
      switchSibling, getSiblingInfo,
      jumpToMessage,
      togglePin, jumpToPinned, clearPins,
      toggleOutlineGroup, isOutlineExpanded,
      treeNodeClick,
      onDragLeave, onDrop, onPaste, uploadFiles,
      cancelUpload, cancelAllUploads, retryUpload, retryAllFailed,
      clearFinishedUploads,
      addCustomCommand, removeCustomCommand, saveCustomCommands,
      parseTemplateParams, openParamDialog, applyParamDialog,
      previewTemplate,
      toggleNotifications,
      syncConfigToServer, loadConfigFromServer,
      selectPopoverItem,
    };
  },
}).mount('#app');