/* CADENCE 窶・繧ｪ繝輔Λ繧､繝ｳ蟇ｾ蠢・*/
const VERSION = 'v13';
const SHELL = `shell-${VERSION}`;
const DATA = `data-${VERSION}`;

// 繧｢繝励Μ譛ｬ菴薙ゅう繝ｳ繧ｹ繝医・繝ｫ譎ゅ↓蜈郁ｪｭ縺ｿ縺吶ｋ縲・
const SHELL_FILES = [
  './', './index.html', './matcher.js',
  './manifest.webmanifest', './icon-192.png', './icon-512.png',
];
// 繝・・繧ｿ縲る㍾縺・・縺ｧ蛻晏屓繧｢繧ｯ繧ｻ繧ｹ譎ゅ↓繧ｭ繝｣繝・す繝･縺吶ｋ縲・
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
  if (url.origin !== self.location.origin) return;   // 隧ｦ閨ｴ髻ｳ貅舌↑縺ｩ縺ｯ邏騾壹＠

  const isData = DATA_FILES.some(f => url.pathname.endsWith(f));

  if (isData) {
    // 繝・・繧ｿ縺ｯ蜊ｳ蠎ｧ縺ｫ繧ｭ繝｣繝・す繝･繧定ｿ斐＠縺､縺､縲∬｣上〒譖ｴ譁ｰ縺吶ｋ
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

  // 譛ｬ菴薙・繝阪ャ繝医Ρ繝ｼ繧ｯ蜆ｪ蜈医ょ恟螟悶↑繧峨く繝｣繝・す繝･縺ｸ關ｽ縺ｨ縺吶・
  e.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok) caches.open(SHELL).then(c => c.put(req, res.clone()));
        return res;
      })
      .catch(() => caches.match(req).then(r => r || caches.match('./index.html')))
  );
});


