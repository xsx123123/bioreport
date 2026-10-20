// Execute the real shell with gzip decoding and a bounded two-frame DOM model.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
assert(/\.loading\[hidden\]\s*\{\s*display:\s*none\s*;?\s*\}/.test(source));
const script = source.match(new RegExp('<script>(.*?)</script>', 's'))[1];
const payloads = Object.fromEntries([...source.matchAll(
  new RegExp('<script id="(edition-[^"]+)" type="application/octet-stream">(.*?)</script>', 'gs')
)].map(match => [match[1], {textContent: match[2]}]));
function environment(supported = true) {
  const events = {}, children = [];
  const loading = {hidden:false, append(node) {this.retry=node;}};
  let decodes=0;
  function makeFrame() {
    const button = {attrs:{}, setAttribute(k,v) {this.attrs[k]=v;}};
    const result = {id:'', hidden:false, assignments:0,
      contentWindow:{location:{hash:''}},
      contentDocument:{documentElement:{dataset:{reportTheme:'light'}},querySelector(sel) {return sel==='[data-report-language]'?button:null;}},
      setAttribute() {}, removeAttribute() {}, remove() {children.splice(children.indexOf(this),1);},
      set srcdoc(value) {this.source=value;this.assignments++;queueMicrotask(()=>this.onload?.());}, button};
    return result;
  }
  const first=makeFrame();first.id='report';children.push(first);
  const document={documentElement:{},body:{append(node) {children.push(node);}},
    getElementById(id) {return id==='loading'?loading:payloads[id]||children.find(n=>n.id===id);},
    createElement(tag) {return tag==='iframe'?makeFrame():{};},
    addEventListener(event,callback) {events[event]=callback;}};
  function Decoder(format) {decodes++;return new DecompressionStream(format);}
  vm.runInNewContext(script,{document,atob,Uint8Array,Response,Blob,
    DecompressionStream:supported?Decoder:undefined,requestAnimationFrame:fn=>setTimeout(fn,0),setTimeout:(fn)=>setTimeout(fn,0)});
  return {document,children,events,loading,get decodes(){return decodes;}};
}
async function until(check) {
  for(let i=0;i<200;i++) {if(check())return;await new Promise(resolve=>setTimeout(resolve,10));}
  throw Error('Shell timed out');
}
(async()=>{
  const env=environment();env.events.DOMContentLoaded();
  await until(()=>env.loading.hidden);
  const active=()=>env.document.getElementById('report');
  assert(active().button.attrs['aria-label'].includes('当前语言'));
  active().contentWindow.location.hash='#report-page-4';
  for(let i=0;i<10;i++) {
    active().button.onclick();
    await until(()=>env.loading.hidden);
    assert(active().source.includes(`lang="${i%2===0?'en':'zh'}`));
    assert.equal(active().contentWindow.location.hash,'#report-page-4');
    assert.equal(env.children.filter(n=>!n.hidden).length,1);
  }
  assert.equal(env.children.length,2,'No unbounded frame creation');
  assert.equal(env.decodes,2,'Each language must decompress once');
  assert(env.children.every(n=>n.assignments===1),'Warm switching must preserve live DOM');
  const unsupported=environment(false);unsupported.events.DOMContentLoaded();
  await until(()=>unsupported.loading.retry);
  assert(unsupported.loading.textContent.includes('此浏览器'));
  assert(unsupported.loading.textContent.includes('This browser'));
  assert(!unsupported.loading.hidden);
  const original=payloads['edition-zh'].textContent;
  payloads['edition-zh'].textContent='invalid';
  const broken=environment();broken.events.DOMContentLoaded();
  await until(()=>broken.loading.retry);
  assert(broken.loading.textContent.includes('Report could not load'));
  payloads['edition-zh'].textContent=original;
  broken.loading.retry.onclick();
  await until(()=>broken.loading.hidden);
  assert(broken.document.getElementById('report').source.includes('lang="zh'));
  const english=payloads['edition-en'].textContent;
  payloads['edition-en'].textContent='invalid';
  const second=environment();second.events.DOMContentLoaded();
  await until(()=>second.loading.hidden);
  second.document.getElementById('report').button.onclick();
  await until(()=>second.loading.retry);
  payloads['edition-en'].textContent=english;
  second.loading.retry.onclick();
  await until(()=>second.loading.hidden);
  assert(second.document.getElementById('report').source.includes('lang="en'));
  console.log('PASS: decode cache, ten warm switches, bounded DOM and bilingual fallback');
})().catch(error=>{console.error(error);process.exitCode=1;});
