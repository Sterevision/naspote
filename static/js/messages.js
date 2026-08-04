(function () {
    'use strict';

    var pollTimer = null;

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

    function formatTime(iso) {
        if (!iso) {
            return '';
        }

        var date = new Date(iso);

        if (isNaN(date.getTime())) {
            return '';
        }

        var now = new Date();

        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        return date.toLocaleDateString([], {
            day: '2-digit',
            month: '2-digit'
        });
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

    function renderConversations(list, conversations) {
        list.innerHTML = '';

        if (!Array.isArray(conversations) || conversations.length === 0) {
            renderEmptyState(
                list,
                '🤝',
                'Пока нет чатов. Добавьте друзей, чтобы начать переписку.'
            );
            return;
        }

        conversations.forEach(function (conversation) {
            if (!conversation.username) {
                return;
            }

            var link = document.createElement('a');
            link.className = 'row-card';
            link.href = '/messages/' + encodeURIComponent(conversation.username);

            var avatar = document.createElement('div');
            avatar.className = 'avatar';

            var avatarUrl = safeUrl(conversation.avatar_url);

            if (avatarUrl) {
                var img = document.createElement('img');
                img.src = avatarUrl;
                img.alt = '';
                avatar.appendChild(img);
            } else {
                avatar.textContent = (conversation.display_name || conversation.username || '?')
                    .charAt(0)
                    .toUpperCase();
            }

            var info = document.createElement('div');
            info.className = 'info';

            var name = document.createElement('div');
            name.className = 'name';
            name.textContent = conversation.display_name || conversation.username || 'Без имени';

            var sub = document.createElement('div');
            sub.className = 'sub';

            if (conversation.last_message_text) {
                var prefix = conversation.last_message_mine ? 'Вы: ' : '';
                sub.textContent = prefix + conversation.last_message_text;
            } else {
                sub.textContent = 'Нет сообщений';
            }

            info.appendChild(name);
            info.appendChild(sub);

            var right = document.createElement('div');
            right.style.cssText = 'display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;';

            var time = document.createElement('div');
            time.className = 'hint';
            time.textContent = formatTime(conversation.last_message_at);
            right.appendChild(time);

            if (conversation.unread_count > 0) {
                var badge = document.createElement('span');
                badge.textContent = conversation.unread_count;
                badge.style.cssText = [
                    'background:var(--mine)',
                    'color:#fff',
                    'border-radius:999px',
                    'padding:2px 8px',
                    'font-size:12px',
                    'font-weight:700',
                    'line-height:1.2',
                    'min-width:22px',
                    'text-align:center'
                ].join(';');

                right.appendChild(badge);
            }

            link.appendChild(avatar);
            link.appendChild(info);
            link.appendChild(right);

            list.appendChild(link);
        });
    }

    async function loadConversations(list, silent) {
        if (!silent) {
            if (!list.querySelector('.row-card')) {
                renderEmptyState(list, '⏳', 'Загрузка...');
            }
        }

        try {
            var response = await fetch('/api/conversations', {
                credentials: 'same-origin'
            });

            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }

            if (!response.ok) {
                throw new Error('conversations failed');
            }

            var conversations = await response.json();
            renderConversations(list, conversations);
        } catch (error) {
            if (!silent) {
                renderEmptyState(
                    list,
                    '⚠️',
                    'Не удалось загрузить чаты. Попробуйте обновить страницу.'
                );
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var list = document.getElementById('conversationsList');

        if (!list) {
            return;
        }

        loadConversations(list, false);

        pollTimer = setInterval(function () {
            if (!document.hidden) {
                loadConversations(list, true);
            }
        }, 30000);
    });
})();