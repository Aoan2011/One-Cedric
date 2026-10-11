/* 用 jsdom 真实加载 WebUI，检查 Vue 是否挂载、启动屏是否被移除、有无 JS 错误。
   jsdom 不执行 CSP，因此这里通过 = 说明问题出在 CSP；这里报错 = 代码问题。 */
const { JSDOM, VirtualConsole } = require(
  'F:/one-cedric3/_jsdom_test/node_modules/jsdom');

const URL_ = process.argv[2] || 'http://127.0.0.1:2043/';

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => errors.push('jsdomError: ' + (e.message || e)));
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));
vc.on('warn', (...a) => errors.push('console.warn: ' + a.join(' ')));

(async () => {
  const dom = await JSDOM.fromURL(URL_, {
    runScripts: 'dangerously',
    resources: 'usable',
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const { window } = dom;
  // 给 Vue 挂载与 onMounted 留时间
  await new Promise((r) => setTimeout(r, 6000));

  const doc = window.document;
  const splash = doc.getElementById('boot-splash');
  const app = doc.getElementById('app');
  const badge = doc.getElementById('ver-badge');

  console.log('boot-splash removed :', !splash);
  console.log('ver-badge present   :', !!badge);
  console.log('app has v-cloak     :', app ? app.hasAttribute('v-cloak') : 'NO #app');
  console.log('app child elements  :', app ? app.children.length : -1);
  console.log('topbar rendered     :', !!doc.querySelector('.topbar'));
  console.log('composer rendered   :', !!doc.querySelector('.input-wrapper, .glass-input'));
  console.log('Vue global present  :', typeof window.Vue);
  console.log('errors (' + errors.length + '):');
  errors.slice(0, 12).forEach((e) => console.log('   - ' + String(e).slice(0, 220)));
  dom.window.close();
  process.exit(0);
})().catch((e) => {
  console.log('FATAL', e && e.message);
  process.exit(1);
});
