// Run with: node addons/coop_portal/tests/test_pwa_worker.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../controllers/pwa.py'), 'utf8')
  .match(/SERVICE_WORKER = """([\s\S]*?)"""/)[1];
const handlers = {};
const stored = new Map();
const deleted = [];
let offline = false;
let claimed = false;
const context = {
  URL, Response, Promise,
  self: {
    location: {origin: 'https://example.test'},
    addEventListener: (event, fn) => { handlers[event] = fn; },
    skipWaiting() {},
    clients: {claim: async () => { claimed = true; }},
  },
  caches: {
    keys: async () => ['coopeapp-v1', 'unrelated-app'],
    delete: async key => { deleted.push(key); },
    open: async () => ({put: async (req, res) => stored.set(req.url, res)}),
    match: async req => stored.get(req.url),
  },
  fetch: async req => {
    if (offline) throw new Error('offline');
    return new Response(req.url.includes('/static/') ? 'asset' : 'PRIVATE PAYROLL');
  },
};
vm.runInNewContext(source, context);
async function get(pathname, mode = 'navigate') {
  let response;
  handlers.fetch({
    request: {url: 'https://example.test' + pathname, method: 'GET', mode},
    respondWith: p => { response = p; },
  });
  return response;
}
(async () => {
  let activation;
  handlers.activate({waitUntil: p => { activation = p; }});
  await activation;
  assert.deepEqual(deleted, ['coopeapp-v1']);
  assert.equal(claimed, true);
  assert.equal(await (await get('/app/plata')).text(), 'PRIVATE PAYROLL');
  assert.equal(stored.size, 0, 'authenticated HTML must never enter shared cache');
  await get('/coop_portal/static/img/icon.svg', 'cors');
  assert.equal(stored.size, 1);
  offline = true;
  const page = await (await get('/app/plata')).text();
  assert.ok(page.includes('Sin señal'));
  assert.ok(!page.includes('PRIVATE PAYROLL'));
  const queued = await (await get('/app/cargar/encolado')).text();
  assert.ok(queued.includes('Guardado en este teléfono'));
  assert.equal(await (await get('/coop_portal/static/img/icon.svg', 'cors')).text(), 'asset');
  assert.equal(await get('/app/cargar/sync', 'cors'), undefined);
  console.log('PASS: PWA cache privacy, migration, public assets and offline fallback');
})().catch(error => { console.error(error); process.exitCode = 1; });
