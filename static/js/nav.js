(function () {
    'use strict';

    function addBadge(link) {
        if (!link) {
            return;
        }

        if (link.querySelector('.nav-badge')) {
            return;
        }

        var badge = document.createElement('span');
        badge.className = 'nav-badge';

        var icon = link.querySelector('.ic');

        if (icon) {
            icon.insertAdjacentElement('afterend', badge);
        } else {
            link.appendChild(badge);
        }
    }

    function updateBadges() {
        var bottomNav = document.querySelector('.bottom-nav');

        if (!bottomNav) {
            return;
        }

        fetch('/api/messages/unread_count', {
            credentials: 'same-origin'
        })
            .then(function (response) {
                if (!response.ok) {
                    return null;
                }

                return response.json();
            })
            .then(function (data) {
                if (!data) {
                    return;
                }

                var friendsLink = document.querySelector('.bottom-nav a[href="/friends"]');
                var messagesLink = document.querySelector('.bottom-nav a[href="/messages"]');

                if (data.friend_requests > 0) {
                    addBadge(friendsLink);
                }

                if (data.messages > 0) {
                    addBadge(messagesLink);
                }
            })
            .catch(function () {
                // silent
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        updateBadges();

        setInterval(function () {
            if (!document.hidden) {
                updateBadges();
            }
        }, 60000);
    });
})();