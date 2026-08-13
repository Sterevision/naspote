(function () {
    'use strict';

    var POLL_INTERVAL = 25000;
    var LS_KEY = 'kartometr_notified_v1';

    // ---------- бейджи в навигации ----------

    function setBadge(link, count) {
        if (!link) return;

        var existing = link.querySelector('.nav-count');

        if (!count || count <= 0) {
            if (existing) existing.remove();
            return;
        }

        if (!existing) {
            existing = document.createElement('span');
            existing.className = 'nav-count';
            link.appendChild(existing);
        }

        existing.textContent = count > 99 ? '99+' : String(count);
    }

    async function refreshBadges() {
        var nav = document.querySelector('.bottom-nav');
        if (!nav) return;

        var links = nav.querySelectorAll('.nav-item');
        var friendsLink = null;
        var messagesLink = null;

        links.forEach(function (a) {
            if (a.href && a.href.indexOf('/friends') > -1) friendsLink = a;
            if (a.href && a.href.indexOf('/messages') > -1) messagesLink = a;
        });

        try {
            var response = await fetch('/api/messages/unread_count', {
                credentials: 'same-origin',
                cache: 'no-store'
            });

            if (response.status === 401 || !response.ok) return;

            var data = await response.json();
            setBadge(friendsLink, data.friend_requests || 0);
            setBadge(messagesLink, data.messages || 0);
        } catch (e) {
            // silent
        }
    }

    // ---------- тихие уведомления ----------

    function saveState(state) {
        try {
            var keys = Object.keys(state);

            if (keys.length > 300) {
                keys.slice(0, keys.length - 300).forEach(function (k) {
                    delete state[k];
                });
            }

            localStorage.setItem(LS_KEY, JSON.stringify(state));
        } catch (e) {
            // silent
        }
    }

    function toast(text) {
        var stack = document.querySelector('.toast-stack');

        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'toast-stack';
            document.body.appendChild(stack);
        }

        var el = document.createElement('div');
        el.className = 'toast';
        el.textContent = text;
        stack.appendChild(el);

        setTimeout(function () { el.classList.add('toast-out'); }, 4200);
        setTimeout(function () { el.remove(); }, 4700);
    }

    async function collectMarkers() {
        var markers = {};

        // 1. Новые личные сообщения
        try {
            var cr = await fetch('/api/conversations', { credentials: 'same-origin', cache: 'no-store' });
            if (cr.ok) {
                (await cr.json() || []).forEach(function (c) {
                    if (!c.unread_count || !c.last_message_at || c.last_message_mine) return;

                    var name = c.display_name || c.username || 'Кто-то';
                    var text = c.last_message_text || 'новое сообщение';
                    if (text.length > 60) text = text.slice(0, 60) + '…';

                    markers['msg:' + c.friend_id] = name + '|' + text + '|' + c.last_message_at;
                });
            }
        } catch (e) { /* silent */ }

        // 2. Новые заявки в друзья
        try {
            var fr = await fetch('/api/friend_requests', { credentials: 'same-origin', cache: 'no-store' });
            if (fr.ok) {
                (await fr.json() || []).forEach(function (r) {
                    markers['req:' + r.id] = r.display_name || r.username || 'Кто-то';
                });
            }
        } catch (e) { /* silent */ }

        // 3. Свежие метки друзей (моложе 15 минут)
        try {
            var fl = await fetch('/api/friends_list', { credentials: 'same-origin', cache: 'no-store' });
            if (fl.ok) {
                var friends = await fl.json();
                var names = {};

                (friends || []).forEach(function (f) {
                    names[f.id] = f.display_name || f.username || 'Друг';
                });

                var sr = await fetch('/api/spots', { credentials: 'same-origin', cache: 'no-store' });
                if (sr.ok) {
                    var now = Date.now();

                    (await sr.json() || []).forEach(function (s) {
                        if (!names[s.owner_id] || !s.created_at) return;

                        var age = now - new Date(s.created_at).getTime();
                        if (age > 0 && age < 15 * 60 * 1000) {
                            markers['spot:' + s.id] = names[s.owner_id] + '|' + (s.title || 'метка');
                        }
                    });
                }
            }
        } catch (e) { /* silent */ }

        return markers;
    }

    async function quietNotify() {
        try {
            var markers = await collectMarkers();

            var prev = {};
            try {
                var raw = localStorage.getItem(LS_KEY);
                prev = raw ? JSON.parse(raw) : {};
            } catch (e) { prev = {}; }

            // Первый запуск: тихо запоминаем, без тостов
            if (!prev.__seeded) {
                prev = { __seeded: 1 };
                Object.keys(markers).forEach(function (k) {
                    prev[k] = markers[k];
                });
                saveState(prev);
                return;
            }

            var shown = 0;

            Object.keys(markers).forEach(function (k) {
                if (prev[k] === markers[k]) return;

                prev[k] = markers[k];

                if (shown >= 2) return;
                shown++;

                if (k.indexOf('msg:') === 0) {
                    var p1 = markers[k].split('|');
                    toast('💬 ' + p1[0] + ': ' + (p1[1] || 'новое сообщение'));
                } else if (k.indexOf('req:') === 0) {
                    toast('🤝 ' + markers[k] + ' — хочет добавить вас в друзья');
                } else if (k.indexOf('spot:') === 0) {
                    var p2 = markers[k].split('|');
                    toast('📍 ' + p2[0] + ' отметил(а): «' + (p2[1] || 'метка') + '»');
                }
            });

            saveState(prev);
        } catch (e) {
            // silent
        }
    }

    // ---------- старт ----------

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.bottom-nav')) return;

        refreshBadges();
        quietNotify();

        setInterval(function () {
            if (!document.hidden) {
                refreshBadges();
                quietNotify();
            }
        }, POLL_INTERVAL);

        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) {
                refreshBadges();
                quietNotify();
            }
        });
    });
})();