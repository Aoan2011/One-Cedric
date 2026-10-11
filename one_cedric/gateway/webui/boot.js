/* 版本自检徽标：显示浏览器实际加载的 app.js 版本号，用于排查缓存问题。
 *
 * 这段代码原先内联在 index.html 里，会迫使 CSP 放开 script-src 的
 * inline 许可（等于放开了内联事件处理器，XSS 防护形同虚设）。
 * 抽成独立文件后，网关可以下发 `script-src 'self'` 的严格策略。 */
(function () {
  try {
    var s = document.querySelector('script[src*="app.js"]');
    var v = s ? ((s.src.match(/v=([\w]+)/) || [])[1] || '?') : 'NO-JS';
    var b = document.createElement('div');
    b.id = 'ver-badge';
    b.textContent = '\u25cf app.js v=' + v;
    b.style.cssText = 'position:fixed !important;left:12px !important;'
      + 'top:12px !important;right:auto !important;bottom:auto !important;'
      + 'z-index:2147483647 !important;background:#0b3d0b !important;'
      + 'color:#7dff7d !important;font:bold 13px Consolas,monospace !important;'
      + 'padding:4px 10px !important;border-radius:6px !important;'
      + 'border:2px solid #4ade80 !important;box-shadow:0 0 12px #4ade8066 !important;'
      + 'pointer-events:none !important;opacity:.98 !important;';
    document.body.appendChild(b);
  } catch (e) { /* 静默 */ }
})();
