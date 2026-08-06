(function () {
    'use strict';
    var pollTimer = null;

    function safeUrl(url) {
        if (!url) return '';
        var value = String(url);
        return /^https?:\/\//i.test(value) ? value : '';
    }

    function formatTime(iso) {
        if (!iso) return '';
        var date = new Date(iso);
        if (isNaN(date.getTime())) return '';
        var now = new Date();
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        return date.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
    }

    // скелетон вместо иконки — никакого чёрного круга
    function renderSkeleton(list, count) {
        list.innerHTML = '';
        for (var i = 0; i < count; i++) {
            var row = document.createElement('div');
            row.className = 'skeleton-row';
            row.innerHTML = '<div class="skeleton avatar"></div><div class="skeleton lines"></div>';
            list.appendChild(row);
        }
    }

    function renderEmpty(list, text) {
        list.innerHTML = '<div class="empty-state"><p>' + text + '</p></div>';
    }

    function renderConversations(list, conversations) {
        list.innerHTML = '';
        if (!Array.isArray(conversations) || conversations.length === 0) {
            renderEmpty(list, 'Пока нет чатов. Добавьте друзей, чтобы начать переписку.');
            return;
        }
        conversations.forEach(function (c) {
            if (!c.username) return;
            var link = document.createElement('a');
            link.className = 'row-card';
            link.href = '/messages/' + encodeURIComponent(c.username);

            var avatar = document.createElement('div');
            avatar.className = 'avatar';
            var avatarUrl = safeUrl(c.avatar_url);
            if (avatarUrl) {
                var img = document.createElement('img');
                img.src = avatarUrl;
                img.alt = '';
                avatar.appendChild(img);
            } else {
                avatar.textContent = (c.display_name || c.username || '?').charAt(0).toUpperCase();
            }

            var info = document.createElement('div');
            info.className = 'info';
            var name = document.createElement('div');
            name.className = 'name';
            name.textContent = c.display_name || c.username || 'Без имени';
            var sub = document.createElement('div');
            sub.className = 'sub';
            sub.textContent = c.last_message_text
                ? (c.last_message_mine ? 'Вы: ' : '') + c.last_message_text
                : 'Нет сообщений';
            info.appendChild(name);
            info.appendChild(sub);

            var right = document.createElement('div');
            right.style.cssText = 'display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;';
            var time = document.createElement('div');
            time.className = 'hint';
            time.textContent = formatTime(c.last_message_at);
            right.appendChild(time);
            if (c.unread_count > 0) {
                var badge = document.createElement('span');
                badge.textContent = c.unread_count;
                badge.style.cssText = 'background:var(--mine);color:#fff;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700;min-width:22px;text-align:center;';
                right.appendChild(badge);
            }

            link.appendChild(avatar);
            link.appendChild(info);
            link.appendChild(right);
            list.appendChild(link);
        });
    }

    async function loadConversations(list, silent) {
        if (!silent) renderSkeleton(list, 3);
        try {
            var response = await fetch('/api/conversations', { credentials: 'same-origin' });
            if (response.status === 401) { window.location.href = '/login'; return; }
            if (!response.ok) throw new Error('conversations failed');
            var conversations = await response.json();
            renderConversations(list, conversations);
        } catch (error) {
            if (!silent) renderEmpty(list, 'Не удалось загрузить чаты. Попробуйте обновить страницу.');
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var list = document.getElementById('conversationsList');
        if (!list) return;
        loadConversations(list, false);
        pollTimer = setInterval(function () {
            if (!document.hidden) loadConversations(list, true);
        }, 30000);
    });
})();