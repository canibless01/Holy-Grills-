/** Execute the production worker's real fetch handler against a warm cache. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
const handlers = {};
let cached = new Response('{"name":"old"}');
let network = () => Promise.resolve(new Response('{"name":"new"}'));
let puts = 0;
runInNewContext(readFileSync('public/service-worker.js', 'utf8'), {
  self: { location: { origin: 'https://app.example' }, addEventListener: (name, handler) => { handlers[name] = handler; } },
  importScripts: () => {}, URL, Response,
  fetch: (...args) => network(...args),
  caches: {
    match: async () => cached?.clone(),
    open: async () => ({ put: async (_, response) => { cached = response; puts++; } }),
  },
});
async function requestManifest() {
  let response;
  const work = [];
  handlers.fetch({request: new Request('https://app.example/manifest.json'), respondWith: promise => { response = promise; }, waitUntil: promise => work.push(promise)});
  const result = await response;
  await Promise.all(work);
  return result;
}
assert.equal(await (await requestManifest()).text(), '{"name":"new"}', 'warm cache must not hide a new manifest');
assert.equal(puts, 1);
network = async () => { throw new TypeError('offline'); };
assert.equal(await (await requestManifest()).text(), '{"name":"new"}', 'offline uses the refreshed copy');
network = async () => new Response('server unavailable', { status: 503 });
assert.equal((await requestManifest()).status, 503, 'hosting failure is not silently reported as success');
assert.equal(puts, 1, 'failed responses do not replace the valid cache');
network = async () => { throw new TypeError('offline'); };cached = null;
assert.equal((await requestManifest()).type, 'error', 'missing offline metadata returns a network error');
console.log('PASS returning-user manifest refresh, offline fallback and failed-response cache protection');
