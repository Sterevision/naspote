(function () {
    'use strict';

    var POLL_INTERVAL = 20000;

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

        // Если число большое — показываем "99+", если 1 — маленькую точку
        if (count > 99) {
            existing.textContent = '99+';
        } else {
            existing.textContent = String(count);
        }
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

            if (response.status === 401) {
                return;
            }

            if (!response.ok) {
                return;
            }

            var data = await response.json();

            setBadge(friendsLink, data.friend_requests || 0);
            setBadge(messagesLink, data.messages || 0);
        } catch (e) {
            // silent
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.bottom-nav')) return;

        refreshBadges();

        setInterval(function () {
            if (!document.hidden) {
                refreshBadges();
            }
        }, POLL_INTERVAL);

        // При возвращении на вкладку — сразу обновляем
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) {
                refreshBadges();
            }
        });
    });
})();