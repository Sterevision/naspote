(function () {
    'use strict';

    function safeUrl(url) {
        if (!url) {
            return '';
        }

        var value = String(url);

        if (/^https?:\/\//i.test(value)) {
            return value;
        }

        return '';
    }

    function renderEmptyState(list, emoji, text) {
        list.innerHTML = '';

        var empty = document.createElement('div');
        empty.className = 'empty-state';

        var em = document.createElement('span');
        em.className = 'em';
        em.textContent = emoji;

        var p = document.createElement('p');
        p.textContent = text;

        empty.appendChild(em);
        empty.appendChild(p);

        list.appendChild(empty);
    }

    function renderConversations(list, friends) {
        list.innerHTML = '';

        friends.sort(function (a, b) {
            var nameA = (a.display_name || a.username || '').toLowerCase();
            var nameB = (b.display_name || b.username || '').toLowerCase();

            return nameA.localeCompare(nameB, 'ru');
        });

        friends.forEach(function (friend) {
            if (!friend.username) {
                return;
            }

            var link = document.createElement('a');
            link.className = 'row-card';
            link.href = '/messages/' + encodeURIComponent(friend.username);

            var avatar = document.createElement('div');
            avatar.className = 'avatar';

            var avatarUrl = safeUrl(friend.avatar_url);

            if (avatarUrl) {
                var img = document.createElement('img');
                img.src = avatarUrl;
                img.alt = '';
                avatar.appendChild(img);
            } else {
                avatar.textContent = (friend.display_name || friend.username || '?')
                    .charAt(0)
                    .toUpperCase();
            }

            var info = document.createElement('div');
            info.className = 'info';

            var name = document.createElement('div');
            name.className = 'name';
            name.textContent = friend.display_name || friend.username || 'Без имени';

            var sub = document.createElement('div');
            sub.className = 'sub';
            sub.textContent = '@' + friend.username;

            info.appendChild(name);
            info.appendChild(sub);

            var arrow = document.createElement('div');
            arrow.className = 'hint';
            arrow.textContent = '💬';

            link.appendChild(avatar);
            link.appendChild(info);
            link.appendChild(arrow);

            list.appendChild(link);
        });
    }

    async function loadConversations(list) {
        try {
            var response = await fetch('/api/friends_list', {
                credentials: 'same-origin'
            });

            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }

            if (!response.ok) {
                throw new Error('friends_list failed');
            }

            var friends = await response.json();

            if (!Array.isArray(friends) || friends.length === 0) {
                renderEmptyState(
                    list,
                    '🤝',
                    'Пока нет чатов. Добавьте друзей, чтобы начать переписку.'
                );
                return;
            }

            renderConversations(list, friends);
        } catch (error) {
            renderEmptyState(
                list,
                '⚠️',
                'Не удалось загрузить чаты. Попробуйте обновить страницу.'
            );
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var list = document.getElementById('conversationsList');

        if (!list) {
            return;
        }

        loadConversations(list);
    });
})();