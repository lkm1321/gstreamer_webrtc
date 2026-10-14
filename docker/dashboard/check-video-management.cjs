const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function check(available) {
  const elements = {
    'videoCard-title': {},
    'head-view-tab': {disabled: true},
    'torso-view-tab': {},
    'torso-view': {classList: {contains: () => true}},
    'orbbec-image': {},
    'orbbec-depth': {},
  };
  const switched = [];
  const context = vm.createContext({
    document: {getElementById: id => elements[id]},
    console: {warn: () => {}},
    fetch: async () => ({ok: available, json: async () => ({rgb: 'rgb', depth: 'depth'})}),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'video-management.js'), 'utf8'), context);
  context.showTab = tab => switched.push(tab);
  vm.runInContext('getOrbbecRGB()', context);
  await new Promise(setImmediate);
  assert.equal(elements['head-view-tab'].disabled, false);
  assert.equal(elements['videoCard-title'].textContent, 'Camera view');
  assert.equal(elements['torso-view-tab'].disabled, !available);
  if (available) {
    assert.equal(elements['torso-view-tab'].textContent, 'Torso');
    assert.equal(elements['orbbec-image'].src, 'data:image/jpeg;base64,rgb');
  } else {
    assert.equal(elements['torso-view-tab'].textContent, 'Torso (unavailable)');
    assert.deepEqual(switched, ['head-view']);
  }
}
(async () => { await check(false); await check(true); console.log('Dashboard camera availability checks passed'); })();
