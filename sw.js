/* CADENCE — オフライン対応 */
const VERSION = 'v7';
const SHELL = `shell-${VERSION}`;
const DATA = `data-${VERSION}`;

// アプリ本体。インストール時に先読みする。
const SHELL_FILES = [
  './', './index.html', './matcher.js',
  './manifest.webmanifest', './icon-192.png', './icon-512.png',
];
// データ。重いので初回アクセス時にキャッシュする。
const DATA_FILES = ['songs.json', 'programs.json', 'remixes.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(SHELL)
      .then(c => c.addAll(SHELL_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // 試聴音源などは素通し

  const isData = DATA_FILES.some(f => url.pathname.endsWith(f));

  if (isData) {
    // データは即座にキャッシュを返しつつ、裏で更新する
    e.respondWith(
      caches.open(DATA).then(async cache => {
        const hit = await cache.match(req);
        const net = fetch(req).then(res => {
          if (res.ok) cache.put(req, res.clone());
          return res;
        }).catch(() => hit);
        return hit || net;
      })
    );
    return;
  }

  // 本体はネットワーク優先。圏外ならキャッシュへ落とす。
  e.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok) caches.open(SHELL).then(c => c.put(req, res.clone()));
        return res;
      })
      .catch(() => caches.match(req).then(r => r || caches.match('./index.html')))
  );
});
