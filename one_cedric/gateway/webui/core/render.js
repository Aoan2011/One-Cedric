/* Markdown / 代码 / diff 渲染 + 消毒（与皮肤无关）。
 *
 * 依赖以经典 <script> 引入的 window.marked / window.hljs（保持零构建）。
 * 安全边界：marked 产出的一律当不可信 HTML，先过白名单再进 DOM；
 * 唯一的 innerHTML 入口是 sanitizeMarkdown()。
 */

const ALLOWED_TAGS = new Set([
  'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'del', 's', 'code', 'pre',
  'blockquote', 'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div', 'img',
  'sup', 'sub', 'details', 'summary', 'kbd', 'input', 'mark',
]);

const ALLOWED_ATTRS = new Set([
  'href', 'title', 'alt', 'src', 'class', 'colspan', 'rowspan', 'start',
  'lang', 'type', 'checked', 'disabled', 'data-lang', 'data-line',
  'loading', 'width', 'height', 'target', 'rel',
]);

const SAFE_URL = /^(https?:|mailto:|#|\/|\.\/|\.\.\/|data:image\/)/i;

export function escapeHtml(text) {
  return String(text == null ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** 把不可信 HTML 过一遍白名单；不合法标签拆掉、属性剥掉、协议校验。 */
export function sanitizeHtml(html) {
  const doc = new DOMParser().parseFromString(
    '<div id="root">' + html + '</div>', 'text/html');
  const root = doc.getElementById('root');
  if (!root) return '';
  const walk = (node) => {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.COMMENT_NODE) {
        child.remove();
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      const tag = child.tagName.toLowerCase();
      if (!ALLOWED_TAGS.has(tag)) {
        // 危险标签（script/style/iframe/svg…）整棵丢弃，其余拆壳保留文字
        if (tag === 'script' || tag === 'style' || tag === 'iframe' ||
            tag === 'object' || tag === 'embed' || tag === 'svg' ||
            tag === 'math' || tag === 'form' || tag === 'link' ||
            tag === 'meta' || tag === 'base') {
          child.remove();
          continue;
        }
        const text = doc.createTextNode(child.textContent || '');
        child.replaceWith(text);
        continue;
      }
      for (const attr of Array.from(child.attributes)) {
        const name = attr.name.toLowerCase();
        const value = attr.value || '';
        if (!ALLOWED_ATTRS.has(name) && !name.startsWith('aria-')) {
          child.removeAttribute(attr.name);
          continue;
        }
        if ((name === 'href' || name === 'src') && !SAFE_URL.test(value)) {
          child.removeAttribute(attr.name);
        }
      }
      if (tag === 'a') {
        child.setAttribute('rel', 'noopener noreferrer');
      }
      walk(child);
    }
  };
  walk(root);
  return root.innerHTML;
}

export function renderMarkdown(text) {
  const src = String(text == null ? '' : text);
  if (!window.marked) return escapeHtml(src).replace(/\n/g, '<br>');
  try {
    const html = window.marked.parse(src, { gfm: true, breaks: true });
    return sanitizeHtml(html);
  } catch (err) {
    return escapeHtml(src).replace(/\n/g, '<br>');
  }
}

export function highlight(root) {
  if (!window.hljs || !root) return;
  root.querySelectorAll('pre code:not([data-hl])').forEach((el) => {
    el.setAttribute('data-hl', '1');
    try { window.hljs.highlightElement(el); } catch (err) { /* 语言未知 */ }
  });
}

/** 工具结果：像 diff 就渲染 diff，否则当代码块。 */
export function renderToolOutput(text) {
  const src = String(text == null ? '' : text);
  if (looksLikeDiff(src)) return renderDiff(src);
  return '<pre class="tool-pre"><code>' + escapeHtml(src) + '</code></pre>';
}

export function looksLikeDiff(text) {
  const lines = text.split('\n').slice(0, 40);
  let marks = 0;
  for (const line of lines) {
    if (/^(\+\+\+|---|@@|\+[^+]|-[^-])/.test(line)) marks += 1;
  }
  return marks >= 3;
}

export function renderDiff(text) {
  const rows = String(text).split('\n').map((line) => {
    let cls = 'ctx';
    if (/^\+\+\+|^---/.test(line)) cls = 'meta';
    else if (/^@@/.test(line)) cls = 'hunk';
    else if (line.startsWith('+')) cls = 'add';
    else if (line.startsWith('-')) cls = 'del';
    return '<div class="diff-line ' + cls + '">' +
      escapeHtml(line) + '</div>';
  });
  return '<div class="diff-view">' + rows.join('') + '</div>';
}

export function timeAgo(ts) {
  if (!ts) return '';
  const seconds = Math.max(0, (Date.now() / 1000) - Number(ts));
  if (seconds < 60) return '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + ' 分钟前';
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + ' 小时前';
  const days = Math.floor(hours / 24);
  return days + ' 天前';
}

export function formatTokens(n) {
  const value = Number(n || 0);
  if (value >= 1000) return (value / 1000).toFixed(1) + 'K';
  return String(value);
}
