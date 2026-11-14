// Check the actual generated HTML: brand identity must agree before/after JS,
// with public mission content and no founder-only source material in the output.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { restaurantJsonLd, websiteJsonLd, PRERENDER_ROUTES } from '../dist-ssr/entry-server.js';

const expected = restaurantJsonLd();
assert.ok(expected.sameAs.includes('https://g.page/r/CT3sD6yYtneQECA'));
assert.equal(expected['@id'], `${expected.url}/#business`);
assert.match(expected.description, /student ecosystem/);
for (const route of [...PRERENDER_ROUTES, '/app-shell.html', '/404.html']) {
  const file = route.endsWith('.html') ? `dist${route}` : route === '/' ? 'dist/index.html' : `dist${route}/index.html`;
  const html = readFileSync(file, 'utf8');
  const blocks = [...html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g)].map(m => JSON.parse(m[1]));
  const businesses = blocks.filter(b => b['@type'] === 'Restaurant');
  assert.equal(businesses.length, 1, `${route}: exactly one business identity`);
  assert.deepEqual(businesses[0], expected, `${route}: static identity equals browser builder`);
  assert.deepEqual(blocks.filter(b => b['@type'] === 'WebSite'), [websiteJsonLd()], `${route}: shared site name and publisher`);
  assert.doesNotMatch(html, /Founder &amp; Leadership|CONFIDENTIAL|HP breakage|behavioral intelligence|seventy million/i);
}
const story = readFileSync('dist/our-story/index.html', 'utf8');
assert.match(story, /student ecosystem built around connection/);
assert.match(story, /To strengthen the connections between students/);
assert.match(story, /A connected campus network/);
const review = story.match(/<a[^>]*href="([^"]+)"[^>]*>Leave a Google review<\/a>/);
assert.ok(review, 'review action is in the prerendered page');
const reviewUrl = new URL(review[1]);
assert.equal(reviewUrl.protocol, 'https:');
assert.ok(['g.page', 'g.co', 'google.com', 'www.google.com', 'search.google.com', 'maps.google.com', 'maps.app.goo.gl'].includes(reviewUrl.hostname));
assert.match(readFileSync('dist/faq/index.html', 'utf8'), /student ecosystem built around connection/);
console.log('PASS: public brand/mission/vision and Google links prerendered; one consistent business identity; founder-only material excluded');
