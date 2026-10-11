const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const data = {
 pages: Array.from({length:6}, (_,i)=>({id:`report-page-${i+1}`,charts:i===3?12:i===4?6:0})),
 headings: {'fastp-details':'report-page-4'},
 links: Array.from({length:6}, (_,i)=>({href:`#report-page-${i+1}`,'aria-controls':`report-page-${i+1}`})),
 toc: [{ 'data-scroll-target':'#fastp-details' }]
};
const nodes = new Map();
const events = {}; const documentEvents = {};
let resized = 0;
let diagramRenders = 0;
let diagramReplaced = false;
let diagramClaimed = false;
function node(attrs, page) {
  return {id: attrs.id, attrs, hidden: false, dataset: {}, hash: attrs.href,
    getAttribute(k) { return this.attrs[k]; },
    setAttribute(k,v) { this.attrs[k]=v; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(k,fn) { this[k]=fn; },
    closest(k) { return k === '.report-page' ? page || this : this.li; },
    scrollIntoView() { this.scrolled=true; },
  };
}
const pages = data.pages.map(p => {
  const n=node({id:p.id});
  n.querySelectorAll=()=>Array.from({length:p.charts},()=>({_fullLayout:{}}));
  nodes.set(p.id,n); return n;
});
for (const [id,page] of Object.entries(data.headings)) nodes.set(id,node({id},nodes.get(page)));
const diagram = node({}, pages[2]);
diagram.textContent = 'graph LR; A-->B';
diagram.classList = {remove(name){assert.strictEqual(name, 'mermaid-js');diagramClaimed = true;}};
diagram.replaceWith = () => {diagramReplaced = true;};
const links=data.links.map(a=>node(a));
const toc=data.toc.map(a=>{const n=node(a);n.li={hidden:false};return n;});
const context={document:{
 documentElement:{style:{setProperty(){}}},
 querySelector(){return {getBoundingClientRect(){return {height:64};}};},
 readyState:"complete", body:{classList:{add(){}}},
  querySelectorAll(q) { return q==='.report-page'?pages:q==='.report-navbar a'?links:q==='pre.mermaid-js'?[diagram]:toc; },
  createElement(){return {querySelector(){return {classList:{add(){}},removeAttribute(){}};}};},
  getElementById(id) { return nodes.get(id); },
  addEventListener(k,fn) { documentEvents[k]=fn; }
},location:{hash:''},history:{pushState(_,__,hash){context.location.hash=hash;}},window:{
  mermaid:{mermaidAPI:{async render(){
    assert(diagramClaimed);
    assert.strictEqual(pages[2].hidden, false);
    diagramRenders++;
    return {svg:'<svg viewBox="0 0 100 100"></svg>'};
  }}},
  Plotly:{Plots:{resize(){resized++;}}},
  addEventListener(k,fn){events[k]=fn;},dispatchEvent(){}
},requestAnimationFrame(fn){fn();},Event:function(){}};
const source=fs.readFileSync('templates/theme/report-pages.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInNewContext(source,context);
function check(index){
 assert.deepStrictEqual(pages.map(p=>p.hidden),pages.map((_,i)=>i!==index));
 assert.strictEqual(links.filter(l=>l.attrs['aria-current']==='page').length,1);
 assert.strictEqual(links[index].attrs['aria-current'],'page');
 assert.strictEqual(pages.filter(p=>p.dataset.active==='true').length,1);
 for(const l of toc){const h=nodes.get(l.attrs['data-scroll-target'].slice(1));assert.strictEqual(l.li.hidden,h.closest('.report-page')!==pages[index]);}
}
check(0);
assert.strictEqual(diagramRenders, 0);
for(let i=0;i<6;i++){context.location.hash='#'+pages[i].id;links[i].click({button:0,preventDefault(){},stopPropagation(){}});check(i);}
const heading=Object.entries(data.headings).find(([id,p])=>p===pages[3].id);
context.location.hash='#'+encodeURIComponent(heading[0]);events.hashchange();check(3);
context.location.hash='#%invalid';events.hashchange();check(0);
context.location.hash='#missing';events.hashchange();check(0);
context.location.hash='#'+pages[2].id;events.popstate();check(2);
assert(resized>=18);
setImmediate(() => {
 assert.strictEqual(diagramRenders, 1);
 assert(diagramReplaced);
 console.log('Single-file navigation and visible flowchart checks passed');
});
