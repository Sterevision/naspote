(function () {
    'use strict';

    function esc(value) {
        var div = document.createElement('div');
        div.textContent = value === null || value === undefined ? '' : String(value);
        return div.innerHTML;
    }

    function renderComments(listEl, comments) {
        if (!comments.length) {
            listEl.innerHTML = '<p class="hint">Пока нет комментариев</p>';
            return;
        }
        listEl.innerHTML = comments.map(function (c) {
            var name = c.user ? (c.user.display_name || c.user.username || '?') : '?';
            var initial = esc(name.charAt(0).toUpperCase());
            return '<div class="feed-comment-row">' +
                '<div class="avatar">' + initial + '</div>' +
                '<div><div class="c-name">' + esc(name) + '</div>' +
                '<div class="c-text">' + esc(c.text) + '</div></div>' +
                '</div>';
        }).join('');
    }

    async function loadComments(spotId) {
        var listEl = document.getElementById('feed-comments-list-' + spotId);
        if (!listEl) return;
        try {
            var res = await fetch('/api/spots/' + spotId + '/comments', { credentials: 'same-origin' });
            if (!res.ok) return;
            var data = await res.json();
            renderComments(listEl, data);
        } catch (e) { /* silent */ }
    }

    async function sendComment(spotId) {
        var input = document.getElementById('feed-comment-input-' + spotId);
        if (!input) return;
        var text = input.value.trim();
        if (!text) return;
        input.value = '';
        try {
            await fetch('/api/spots/' + spotId + '/comments', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            loadComments(spotId);
        } catch (e) { /* silent */ }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.feed-comments-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var spotId = btn.dataset.spotId;
                var box = document.getElementById('feed-comments-' + spotId);
                var isHidden = box.hidden;
                box.hidden = !isHidden;
                if (isHidden) loadComments(spotId);
            });
        });

        document.querySelectorAll('.feed-comment-send').forEach(function (btn) {
            btn.addEventListener('click', function () { sendComment(btn.dataset.spotId); });
        });

        document.querySelectorAll('.feed-comment-input').forEach(function (input) {
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    var spotId = input.id.replace('feed-comment-input-', '');
                    sendComment(spotId);
                }
            });
        });
    });
})();