// Run the generated bilingual shell script, including its real gzip decoding.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
assert(/\.loading\[hidden\]\s*\{\s*display:\s*none\s*;?\s*\}/.test(source),
  'Loading overlay must honor hidden even though .loading sets display:grid');
const events = {};
const loading = {hidden: false};
const buttons = ['zh', 'en'].map(language => ({
  dataset: {edition: language}, attrs: {},
  setAttribute(key, value) { this.attrs[key] = value; },
  addEventListener(key, callback) { this[key] = callback; },
}));
const frame = {
  contentWindow: {location: {hash: ''}},
  contentDocument: {head: {append() {}}, createElement() { return {}; }},
  set srcdoc(value) { this.source = value; queueMicrotask(() => this.onload()); },
};
const payloads = Object.fromEntries([...source.matchAll(
  new RegExp('<script id="(edition-[^"]+)" type="application/octet-stream">(.*?)</script>', 'gs')
)].map(match => [match[1], {textContent: match[2]}]));
const document = {
  documentElement: {},
  getElementById(id) { return id === 'report' ? frame : id === 'loading' ? loading : payloads[id]; },
  querySelectorAll() { return buttons; },
  addEventListener(event, callback) { events[event] = callback; },
};
vm.runInNewContext(source.match(new RegExp('<script>(.*?)</script>', 's'))[1],
  {document, atob, Uint8Array, Response, Blob, DecompressionStream});
async function waitForEdition(language) {
  for (let i = 0; i < 200; i++) {
    if (frame.source?.includes(`lang="${language}`) && loading.hidden) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error('Edition did not finish loading: ' + language + ': ' + loading.textContent);
}
(async () => {
  events.DOMContentLoaded();
  await waitForEdition('zh');
  assert.equal(buttons[0].attrs['aria-pressed'], 'true');
  frame.contentWindow.location.hash = '#report-page-4';
  await buttons[1].click();
  await waitForEdition('en');
  assert.equal(buttons[1].attrs['aria-pressed'], 'true');
  assert.equal(frame.contentWindow.location.hash, '#report-page-4');
  await buttons[0].click();
  await waitForEdition('zh');
  console.log('Initial load and both language switches hide the loading overlay');
})().catch(error => { console.error(error); process.exitCode = 1; });
