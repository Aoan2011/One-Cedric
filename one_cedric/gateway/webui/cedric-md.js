/* ═══════════════════════════════════════════════════════════════════════
   One Cedric WebUI · Markdown 扩展层（cedric-md.js）
   ═══════════════════════════════════════════════════════════════════════

   零构建：经典 <script>，依赖 window.marked（解析）与 window.katex（公式）。

   新增语法：
     $x^2$  \(x^2\)             行内公式（KaTeX 渲染）
     $$…$$  \[…\]  ```math       独立公式（居中，KaTeX 渲染）
     ==文字==                    普通高亮（<mark>）
     !!!文字!!!                  关键结论：绿色打底 + 手写波浪线，只在
                                 极其重要、必须让用户一眼看到的场合用

   安全边界：marked 扩展只产出“占位符”（data-tex / cedric-key），
   KaTeX 的产物在 sanitizeHtml() 之后由 CedricMD.hydrate() 注入 DOM。
   这样净化白名单永远看不到 KaTeX 的内联样式，也不给模型输出增加
   任何新的注入面（KaTeX 自身对 TeX 文本做转义，trust 默认关闭）。
   ─────────────────────────────────────────────────────────────────────── */
(function (global) {
  'use strict';

  var INSTALLED = false;

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* 数学公式占位符：内层先放原始 TeX（katex 未加载时的降级显示），
     hydrate() 阶段再整体替换为 KaTeX 的输出。 */
  function mathPlaceholder(tex, display) {
    var tag = display ? 'div' : 'span';
    var cls = display ? 'md-math-block' : 'md-math';
    return '<' + tag + ' class="' + cls + '"' +
      ' data-tex="' + escapeHtml(tex) + '"' +
      ' data-display="' + (display ? '1' : '0') + '">' +
      '<span class="md-math-raw">' + escapeHtml(tex) + '</span>' +
      '</' + tag + '>';
  }

  /* ── 公式：词法规则 ─────────────────────────────────────────────── */
  var RE_MATH_PAREN = /^\\\(([\s\S]+?)\\\)/;         // \( … \)
  var RE_MATH_BRACKET = /^\\\[([\s\S]+?)\\\]/;       // \[ … \]
  var RE_MATH_DOLLAR2 = /^\$\$([^\n$]+)\$\$/;        // $$ … $$（同一行）
  var RE_MATH_DOLLAR = /^\$((?:\\\$|[^$\n])+)\$/;    // $ … $

  function matchInlineMath(src) {
    var ch = src.charAt(0);
    var m = null, tex = '', display = false;

    if (ch === '\\') {
      if ((m = RE_MATH_PAREN.exec(src))) {
        tex = m[1];
      } else if ((m = RE_MATH_BRACKET.exec(src))) {
        tex = m[1];
        display = true;
      } else {
        return null;
      }
    } else if (ch === '$') {
      if ((m = RE_MATH_DOLLAR2.exec(src))) {
        tex = m[1];
        display = true;
      } else if ((m = RE_MATH_DOLLAR.exec(src))) {
        tex = m[1];
        // 收尾 $ 后紧跟数字（$x$2）多半是价格写法，不当公式
        var after = src.charAt(m[0].length);
        if (after >= '0' && after <= '9') return null;
      } else {
        return null;
      }
      if (!tex || /^\s|\s$/.test(tex)) return null;   // 起止不留空白
    }

    tex = tex.trim();
    if (!tex) return null;
    return { raw: m[0], text: tex, display: display };
  }

  /* ── 公式：块级规则（$$…$$ / \[…\] / ```math） ──────────────────── */
  var RE_MATH_BLOCK = /^ {0,3}\$\$([\s\S]+?)\$\$[ \t]*(?:\n+|$)/;
  var RE_MATH_BRACKET_BLOCK = /^ {0,3}\\\[([\s\S]+?)\\\][ \t]*(?:\n+|$)/;
  var RE_MATH_FENCE = new RegExp(
    '^ {0,3}(`{3,}|~{3,})[ \\t]*(?:math|katex|latex|tex)[ \\t]*\\n' +
    '([\\s\\S]*?)\\n?[ \\t]*\\1[ \\t]*(?:\\n+|$)');

  function matchBlockMath(src) {
    var m = RE_MATH_BLOCK.exec(src);
    var tex = m ? m[1] : '';
    if (!m) {
      m = RE_MATH_BRACKET_BLOCK.exec(src);
      tex = m ? m[1] : '';
    }
    if (!m) {
      m = RE_MATH_FENCE.exec(src);
      tex = m ? m[2] : '';            // 围栏：m[1] 是围栏本身，m[2] 才是内容
    }
    if (!m) return null;
    tex = (tex || '').trim();
    if (!tex) return null;
    return { raw: m[0], text: tex };
  }

  /* ── 关键结论：!!!文字!!! ───────────────────────────────────────── */
  var RE_KEY = /^!!!([\s\S]+?)!!!/;

  /* ── 高亮：==文字== ────────────────────────────────────────────── */
  var RE_MARK = /^==([\s\S]+?)==/;

  function firstIndex(src, chars) {
    var best = -1;
    for (var i = 0; i < chars.length; i++) {
      var idx = src.indexOf(chars[i]);
      if (idx !== -1 && (best === -1 || idx < best)) best = idx;
    }
    return best;
  }

  var LABELS = { keyTitle: '关键结论' };

  function setLabels(labels) {
    if (!labels) return;
    if (typeof labels.keyTitle === 'string' && labels.keyTitle) {
      LABELS.keyTitle = labels.keyTitle;
    }
  }

  /* ── marked 扩展 ────────────────────────────────────────────────── */
  function startHint(src, chars) {
    return firstIndex(src, chars);
  }

  function sketchExtension(spec) {
    var ext = {
      name: spec.name,
      level: spec.level,
      tokenizer: function (src) {
        var hit = spec.match(src);
        if (!hit) return undefined;
        var token = {
          type: spec.name,
          raw: hit.raw,
          text: hit.text,
          display: !!hit.display,
          tokens: [],
        };
        if (spec.inlineChildren && this.lexer && this.lexer.inlineTokens) {
          this.lexer.inlineTokens(hit.text, token.tokens);
        }
        return token;
      },
      renderer: function (token) {
        var inner;
        if (this.parser && this.parser.parseInline && token.tokens
            && token.tokens.length) {
          inner = this.parser.parseInline(token.tokens);
        } else {
          inner = escapeHtml(token.text);
        }
        return spec.render(token, inner);
      },
    };
    /* 只给行内扩展挂 start 提示：块级提示会让 marked 把段落提前切断再
       用 \n 拼回去，公式会被换行撕开（$a+b$ 不再匹配）。块级 tokenizer
       本来就会在每个块起点被调用，提示纯属性能优化，不挂更安全。 */
    if (spec.level === 'inline' && spec.starts) {
      ext.start = function (src) { return startHint(src, spec.starts); };
    }
    return ext;
  }

  var EXTENSIONS = [
    sketchExtension({
      name: 'cedricMathBlock',
      level: 'block',
      match: matchBlockMath,
      inlineChildren: false,
      render: function (token) { return mathPlaceholder(token.text, true); },
    }),
    sketchExtension({
      name: 'cedricMathInline',
      level: 'inline',
      starts: ['$', '\\'],
      match: matchInlineMath,
      inlineChildren: false,
      render: function (token) {
        return mathPlaceholder(token.text, token.display);
      },
    }),
    sketchExtension({
      name: 'cedricKey',
      level: 'inline',
      starts: ['!'],
      match: function (src) {
        var m = RE_KEY.exec(src);
        if (!m) return null;
        var text = m[1].trim();
        if (!text) return null;
        return { raw: m[0], text: text };
      },
      inlineChildren: true,
      render: function (token, inner) {
        return '<span class="cedric-key" title="' +
          escapeHtml(LABELS.keyTitle) + '">' + inner + '</span>';
      },
    }),
    sketchExtension({
      name: 'cedricMark',
      level: 'inline',
      starts: ['='],
      match: function (src) {
        var m = RE_MARK.exec(src);
        if (!m) return null;
        var text = m[1];
        if (!text || /^\s|[\s=]$/.test(text)) return null;
        return { raw: m[0], text: text };
      },
      inlineChildren: true,
      render: function (token, inner) { return '<mark>' + inner + '</mark>'; },
    }),
  ];

  function install() {
    var marked = global.marked;
    if (!marked || typeof marked.use !== 'function') return false;
    if (INSTALLED) return true;
    marked.use({ extensions: EXTENSIONS });
    INSTALLED = true;
    return true;
  }

  /* ── KaTeX 水合：把占位符换成真正的公式 ─────────────────────────── */
  function renderTex(tex, display) {
    var katex = global.katex;
    if (!katex || typeof katex.renderToString !== 'function') return '';
    try {
      return katex.renderToString(tex, {
        displayMode: !!display,
        output: 'htmlAndMathml',
        throwOnError: false,
        strict: false,
        trust: false,
        errorColor: '#e06c75',
      });
    } catch (err) {
      return '';
    }
  }

  function hydrate(html) {
    install();
    var host = document.createElement('div');
    host.innerHTML = String(html == null ? '' : html);
    var nodes = host.querySelectorAll('[data-tex]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var display = el.getAttribute('data-display') === '1' ||
        el.classList.contains('md-math-block');
      var out = renderTex(el.getAttribute('data-tex') || '', display);
      if (!out) continue;
      el.innerHTML = out;
      el.setAttribute('data-math', display ? 'block' : 'inline');
      // 渲染完就不需要原始 TeX 了，顺手把占位数据从 DOM 里抹掉
      el.removeAttribute('data-tex');
      el.removeAttribute('data-display');
    }
    return host.innerHTML;
  }

  global.CedricMD = {
    install: install,
    hydrate: hydrate,
    renderTex: renderTex,
    setLabels: setLabels,
    version: '1.0.0',
  };

  install();
})(window);
