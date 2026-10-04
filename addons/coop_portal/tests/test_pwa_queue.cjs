// Run with: node addons/coop_portal/tests/test_pwa_queue.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../views/portal_templates.xml'), 'utf8')
  .match(/<script t-att-data-queue-uid=[\s\S]*?>([\s\S]*?)<\/script>/)[1];
const storage = new Map([
  ['coopeapp_cola_avances', '[{"item_id":99}]'],
  ['coopeapp_cola_avances_8', '[{"item_id":88}]'],
]);
const listeners = {};
const documentListeners = {};
class TestFormData extends FormData {
  constructor(form) {
    super();
    for (const [key, value] of Object.entries(form?.fields || {})) this.set(key, value);
  }
}
const requests = [];
let finish;
const context = {
  navigator: {onLine: true}, FormData: TestFormData, crypto: require('node:crypto').webcrypto,
  document: {
    currentScript: {getAttribute: name => name === 'data-queue-uid' ? '7' : 'fresh-csrf'},
    getElementById: () => null,
    addEventListener: (name, fn) => { documentListeners[name] = fn; },
  },
  window: {addEventListener: (name, fn) => { listeners[name] = fn; }},
  localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
  fetch: (url, args) => {
    requests.push({url, args});
    return new Promise(resolve => { finish = () => resolve({json: async () => ({ok: true})}); });
  },
};
(async () => {
  vm.runInNewContext(script, context);
  assert.equal(requests.length, 0, 'another user and legacy queue must stay untouched');
  storage.set('coopeapp_cola_avances_7', '[{"item_id":1,"csrf_token":"old"}]');
  listeners.online();
  listeners.online();
  assert.equal(requests.length, 1, 'online events must not duplicate an active sync');
  assert.equal(requests[0].args.body.get('queue_uid'), '7');
  const token = requests[0].args.body.get('sync_token');
  assert.match(token, /^[a-f0-9]{32}$/);
  assert.equal(JSON.parse(storage.get('coopeapp_cola_avances_7'))[0].sync_token, token);
  assert.equal(requests[0].args.body.get('csrf_token'), 'fresh-csrf');
  storage.set('coopeapp_cola_avances_7', JSON.stringify([
    {item_id: 1, sync_token: token}, {item_id: 2, sync_token: 'b'.repeat(32)},
  ]));
  finish();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(JSON.parse(storage.get('coopeapp_cola_avances_7')), [{item_id: 2, sync_token: 'b'.repeat(32)}],
    'new entries queued while syncing must survive');
  listeners.online();
  // Another tab has acknowledged item 2, then the user queued item 3.
  storage.set('coopeapp_cola_avances_7', JSON.stringify([
    {item_id: 3, sync_token: 'c'.repeat(32)},
  ]));
  finish();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(JSON.parse(storage.get('coopeapp_cola_avances_7')),
    [{item_id: 3, sync_token: 'c'.repeat(32)}],
    'acknowledging an already removed item must not drop a new one');
  assert.equal(storage.get('coopeapp_cola_avances_8'), '[{"item_id":88}]');
  assert.equal(storage.get('coopeapp_cola_avances'), '[{"item_id":99}]');
  context.navigator.onLine = false;
  let prevented = false;
  documentListeners.submit({
    target: {getAttribute: () => '1', fields: {item_id: '4', cantidad: '2'}},
    preventDefault: () => { prevented = true; },
  });
  assert.equal(prevented, true);
  const enqueued = JSON.parse(storage.get('coopeapp_cola_avances_7')).at(-1);
  assert.equal(enqueued.item_id, '4');
  assert.match(enqueued.sync_token, /^[a-f0-9]{32}$/,
    'a new item must have its stable token before any sync starts');
  console.log('PASS: offline queue account isolation, fresh CSRF, overlapping sync and concurrent enqueue');
})().catch(error => { console.error(error); process.exitCode = 1; });
