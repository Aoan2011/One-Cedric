/* 双语文案（M2 新界面从第一天就只有一个入口，不再到处写三元）。
 *
 * 用法：
 *   t('action.send')                    -> "发送"
 *   applyI18n(document)                 -> 刷所有 data-i18n 标记
 * 缺键回退顺序：当前语言 -> zh -> 键名（并在 console 里提醒一次）。
 */

const ZH = {
  'app.name': 'One Cedric',
  'app.tagline': '本地文件智能体',
  'nav.sessions': '会话',
  'nav.search': '搜索',
  'nav.favorites': '收藏',
  'nav.outline': '大纲',
  'action.newSession': '新建会话',
  'action.send': '发送',
  'action.stop': '停止',
  'action.retry': '重试',
  'action.copy': '复制',
  'action.copied': '已复制',
  'action.delete': '删除',
  'action.rename': '重命名',
  'action.cancel': '取消',
  'action.confirm': '确认',
  'action.save': '保存',
  'action.close': '关闭',
  'action.undo': '撤销',
  'action.compact': '压缩上下文',
  'action.clear': '清空会话',
  'action.export': '导出',
  'action.settings': '设置',
  'action.stats': '统计',
  'action.help': '帮助',
  'action.switchTheme': '切换主题',
  'action.switchLang': '切换语言',
  'composer.placeholder': '问点什么…「这个项目的技术栈是什么？」',
  'composer.hint.agents': 'shift+tab 模式',
  'composer.hint.commands': 'ctrl+p 命令',
  'composer.hint.stop': 'esc 停止',
  'composer.attach': '添加文件',
  'composer.image': '粘贴图片',
  'mode.build': 'Build',
  'mode.plan': 'Plan',
  'mode.ask': 'Ask',
  'context.title': 'Context',
  'context.tokens': 'tokens',
  'context.used': '已用',
  'context.model': '模型',
  'context.provider': '服务商',
  'context.cost': '成本',
  'context.compress': '压缩',
  'context.gettingStarted': '快速开始',
  'context.connect': '连接服务商',
  'context.tip': 'One Cedric 自带本地模型即可开始；也可以接入 DeepSeek / Kimi / Ollama 等 OpenAI 兼容后端。',
  'msg.thought': '思考',
  'msg.thinking': '正在思考',
  'msg.done': '完成',
  'msg.failed': '失败',
  'msg.interrupted': '已中断',
  'msg.empty': '还没有消息，从下面开始吧。',
  'msg.welcome': '你好，我是 One Cedric。',
  'msg.toolRunning': '运行中',
  'ask.title': '模型提问',
  'ask.custom': '自定义回答…',
  'ask.submit': '提交回答',
  'ask.answered': '已回答',
  'ask.sent': '已提交回答',
  'panel.settings': '设置',
  'panel.stats': '统计',
  'panel.cron': '定时任务',
  'panel.dream': 'Dream',
  'panel.diagnose': '诊断',
  'panel.tools': '工具目录',
  'panel.models': '模型',
  'toast.saved': '已保存',
  'toast.gatewayToken': '网关需要 Token：请在设置的权限区填入',
  'toast.sessionBusy': '会话正忙，稍后再试',
  'status.offline': '网关未连接',
  'status.busy': '回复中',
  'status.idle': '就绪',
  'label.searchPlaceholder': '搜索会话…',
  'label.noSessions': '还没有会话',
  'label.today': '今天',
  'label.yesterday': '昨天',
  'label.earlier': '更早',
  'label.loading': '加载中…',
  'label.askAnything': '问点什么…',
  'cmd.palette': '命令面板',
  'cmd.placeholder': '输入命令或搜索…',
};

const EN = {
  'app.tagline': 'local file-smart agent',
  'nav.sessions': 'Sessions',
  'nav.search': 'Search',
  'nav.favorites': 'Favorites',
  'nav.outline': 'Outline',
  'action.newSession': 'New session',
  'action.send': 'Send',
  'action.stop': 'Stop',
  'action.retry': 'Retry',
  'action.copy': 'Copy',
  'action.copied': 'Copied',
  'action.delete': 'Delete',
  'action.rename': 'Rename',
  'action.cancel': 'Cancel',
  'action.confirm': 'Confirm',
  'action.save': 'Save',
  'action.close': 'Close',
  'action.undo': 'Undo',
  'action.compact': 'Compact',
  'action.clear': 'Clear',
  'action.export': 'Export',
  'action.settings': 'Settings',
  'action.stats': 'Stats',
  'action.help': 'Help',
  'action.switchTheme': 'Toggle theme',
  'action.switchLang': 'Toggle language',
  'composer.placeholder': 'Ask anything… "What is the tech stack of this project?"',
  'composer.hint.agents': 'shift+tab mode',
  'composer.hint.commands': 'ctrl+p commands',
  'composer.hint.stop': 'esc stop',
  'composer.attach': 'Attach file',
  'composer.image': 'Paste image',
  'mode.build': 'Build',
  'mode.plan': 'Plan',
  'mode.ask': 'Ask',
  'context.title': 'Context',
  'context.tokens': 'tokens',
  'context.used': 'used',
  'context.model': 'Model',
  'context.provider': 'Provider',
  'context.cost': 'Cost',
  'context.compress': 'Compact',
  'context.gettingStarted': 'Getting started',
  'context.connect': 'Connect provider',
  'context.tip': 'One Cedric ships with local models so you can start immediately. Connect DeepSeek / Kimi / Ollama via any OpenAI-compatible host.',
  'msg.thought': 'Thought',
  'msg.thinking': 'Thinking',
  'msg.done': 'done',
  'msg.failed': 'failed',
  'msg.interrupted': 'interrupted',
  'msg.empty': 'No messages yet — start below.',
  'msg.welcome': 'Hi, I am One Cedric.',
  'msg.toolRunning': 'running',
  'ask.title': 'Agent question',
  'ask.custom': 'Type a custom answer…',
  'ask.submit': 'Submit',
  'ask.answered': 'Answered',
  'ask.sent': 'Answer sent',
  'panel.settings': 'Settings',
  'panel.stats': 'Stats',
  'panel.cron': 'Cron',
  'panel.dream': 'Dream',
  'panel.diagnose': 'Diagnose',
  'panel.tools': 'Tools',
  'panel.models': 'Models',
  'toast.saved': 'Saved',
  'toast.gatewayToken': 'Gateway needs a token — set it in Settings → Access',
  'toast.sessionBusy': 'Session busy, try again shortly',
  'status.offline': 'Gateway offline',
  'status.busy': 'Replying',
  'status.idle': 'Ready',
  'label.searchPlaceholder': 'Search sessions…',
  'label.noSessions': 'No sessions yet',
  'label.today': 'Today',
  'label.yesterday': 'Yesterday',
  'label.earlier': 'Earlier',
  'label.loading': 'Loading…',
  'label.askAnything': 'Ask anything…',
  'cmd.palette': 'Command palette',
  'cmd.placeholder': 'Type a command or search…',
};

const MISSING = new Set();
let lang = 'zh';

export function getLang() { return lang; }

export function setLang(next) {
  lang = next === 'en' ? 'en' : 'zh';
  return lang;
}

export function t(key, vars) {
  const table = lang === 'en' ? EN : ZH;
  let value = Object.prototype.hasOwnProperty.call(table, key)
    ? table[key] : ZH[key];
  if (value === undefined) {
    if (!MISSING.has(key)) {
      MISSING.add(key);
      console.warn('[i18n] missing key:', key);
    }
    return key;
  }
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replaceAll('{' + k + '}', String(v));
    }
  }
  return value;
}

/** 刷 DOM 上带 data-i18n / data-i18n-ph / data-i18n-title 的节点。 */
export function applyI18n(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  root.querySelectorAll('[data-i18n-ph]').forEach((el) => {
    el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
  });
  root.querySelectorAll('[data-i18n-title]').forEach((el) => {
    el.setAttribute('title', t(el.getAttribute('data-i18n-title')));
  });
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
}
