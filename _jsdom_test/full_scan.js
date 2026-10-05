// 全量扫描：index.html 模板表达式引用的标识符（函数调用 + 数据读取）vs app.js setup return
const fs = require('fs');
const html = fs.readFileSync('F:/one-cedric5/one_cedric/gateway/webui/index.html', 'utf8');
const js = fs.readFileSync('F:/one-cedric5/one_cedric/gateway/webui/app.js', 'utf8');

const mountIdx = js.indexOf("}).mount('#app')");
const retStart = js.lastIndexOf('return {', mountIdx);
const retEnd = js.indexOf('\n    };', retStart);
const retBlock = js.slice(retStart + 8, retEnd);
const returned = new Set();
for (const line of retBlock.split('\n')) {
  for (const m of line.matchAll(/[a-zA-Z_$][\w$]*/g)) returned.add(m[0]);
}
['const','computed','methods','state','//'].forEach(x => returned.delete(x));

const exprRe = /@[\w.]+="([^"]*)"|:[\w.-]+="([^"]*)"|v-(if|for|show|html|cloak|model)="([^"]*)"|\{\{([^}]*)\}\}/g;
const used = new Map(); // name -> 示例
let mm;
while ((mm = exprRe.exec(html)) !== null) {
  const expr = (mm[1] || mm[2] || mm[4] || mm[5] || '');
  for (const id of expr.matchAll(/([a-zA-Z_$][\w$]*)/g)) {
    const n = id[1];
    if (!used.has(n)) used.set(n, expr.slice(0, 80));
  }
}
// v-for 变量、字面量、JS 内建排除
const ignore = new Set(['Number','filter','gradient','hsl','in','indexOf','round','some','toFixed','trim','parseInt','parseFloat','Math','JSON','Object','Array','String','Date','encodeURIComponent','decodeURIComponent','isNaN','isFinite','RegExp','Promise','true','false','null','undefined','length','class','style','key','title','id','s','m','i','q','qj','tc','tt','c','p','g','gi','th','rec','item','it','x','y','n','idx','total','index','params','opt','oi','j','e','evt','event','$event','msgId','node','w','h','d','v','k','t']);
// v-for 声明的变量（模板自身绑定）
const vforVars = new Set();
for (const m of html.matchAll(/v-for="[^"]*?\(([^)]*)\)[^"]*"?\s+in/g)) {}
for (const m of html.matchAll(/v-for="([^"]+)"/g)) {
  const head = m[1].split(' in ')[0];
  for (const part of head.split(',')) {
    const id = part.trim().match(/[a-zA-Z_$][\w$]*/);
    if (id) vforVars.add(id[1]);
  }
}
const missing = [...used.keys()]
  .filter(n => !returned.has(n) && !ignore.has(n) && !vforVars.has(n))
  .sort();
console.log('=== 模板引用但 setup 未暴露（函数或数据）===');
for (const n of missing) {
  console.log(' ', n, '| 例:', used.get(n));
}
console.log(missing.length === 0 ? '(无 —— 全部暴露)' : '');
