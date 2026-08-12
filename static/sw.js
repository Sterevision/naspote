/* Картометр — service worker */
var CACHE = 'kartometr-v1';

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys
                    .filter(function (k) { return k !== CACHE; })
                    .map(function (k) { return caches.delete(k); })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', function (event) {
    var req = event.request;

    if (req.method !== 'GET') return;

    var url = new URL(req.url);
    if (url.origin !== self.location.origin) return;

    // API и авторизацию никогда не кешируем
    if (url.pathname.indexOf('/api/') === 0) return;

    // Страницы: сначала сеть, офлайн — аккуратная заглушка
    if (req.mode === 'navigate') {
        event.respondWith(
            fetch(req).then(function (res) {
                var copy = res.clone();
                caches.open(CACHE).then(function (cache) {
                    cache.put('/pwa-cache' + url.pathname, copy);
                });
                return res;
            }).catch(function () {
                return caches.match('/pwa-cache' + url.pathname).then(function (hit) {
                    if (hit) return hit;

                    return new Response(
                        '<!doctype html><html lang="ru"><head><meta charset="utf-8">' +
                        '<meta name="viewport" content="width=device-width, initial-scale=1">' +
                        '<title>Картометр</title></head>' +
                        '<body style="margin:0;font-family:sans-serif;background:#f4f5f7;color:#0f172a;' +
                        'display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px;">' +
                        '<div><div style="font-size:44px;">📍</div><b>Нет связи</b>' +
                        '<p style="color:#64748b;">Картометр вернётся, когда появится сеть.</p></div>' +
                        '</body></html>',
                        { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                    );
                });
            })
        );
        return;
    }

    // Статика: сначала кеш, с фоновым обновлением
    if (url.pathname.indexOf('/static/') === 0) {
        event.respondWith(
            caches.match(req).then(function (hit) {
                var network = fetch(req).then(function (res) {
                    if (res && res.ok) {
                        var copy = res.clone();
                        caches.open(CACHE).then(function (cache) {
                            cache.put(req, copy);
                        });
                    }
                    return res;
                }).catch(function () {
                    return hit;
                });

                return hit || network;
            })
        );
        return;
    }
});