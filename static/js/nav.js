(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.bottom-nav')) {
            return;
        }

        fetch('/api/messages/unread_count', {
            credentials: 'same-origin'
        })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(function (data) {
                if (!data) return;

                const friendsLink = document.querySelector('.bottom-nav [data-nav="friends"]');
                const messagesLink = document.querySelector('.bottom-nav [data-nav="messages"]');

                if (friendsLink && data.friend_requests > 0 && !friendsLink.querySelector('.nav-badge')) {
                    const badge = document.createElement('span');
                    badge.className = 'nav-badge';
                    friendsLink.appendChild(badge);
                }

                if (messagesLink && data.messages > 0 && !messagesLink.querySelector('.nav-badge')) {
                    const badge = document.createElement('span');
                    badge.className = 'nav-badge';
                    messagesLink.appendChild(badge);
                }
            })
            .catch(function () {});
    });
})();