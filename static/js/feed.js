(function () {
'use strict';
function esc(value) {
    var div = document.createElement('div');
    div.textContent = value === null || value === undefined ? '' : String(value);
    return div.innerHTML;
}

/* ---------- комментарии ---------- */
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

/* ---------- реакции ---------- */
async function loadReactions(spotId) {
    var row = document.getElementById('reactions-' + spotId);
    if (!row) return;
    try {
        var res = await fetch('/api/spots/' + spotId + '/reactions', { credentials: 'same-origin' });
        if (!res.ok) return;
        var data = await res.json();
        var byEmoji = {};
        (data || []).forEach(function (r) { byEmoji[r.emoji] = r; });
        row.querySelectorAll('.reaction-btn').forEach(function (btn) {
            var info = byEmoji[btn.dataset.emoji];
            var countEl = btn.querySelector('.r-count');
            if (countEl) countEl.textContent = (info && info.count > 0) ? String(info.count) : '';
            btn.classList.toggle('reacted', !!(info && info.my_reacted));
            btn.classList.toggle('has-count', !!(info && info.count > 0));
        });
    } catch (e) { /* silent */ }
}
async function toggleReaction(spotId, emoji) {
    var row = document.getElementById('reactions-' + spotId);
    var btn = row ? row.querySelector('.reaction-btn[data-emoji="' + emoji + '"]') : null;
    var reacted = !!(btn && btn.classList.contains('reacted'));
    try {
        await fetch('/api/spots/' + spotId + '/reactions/' + encodeURIComponent(emoji), {
            method: reacted ? 'DELETE' : 'POST',
            credentials: 'same-origin'
        });
        await loadReactions(spotId);
    } catch (e) { /* silent */ }
}

/* ---------- мини-карты в ленте (НОВОЕ) ---------- */
function initFeedMaps() {
    if (typeof L === 'undefined') return;
    var maps = document.querySelectorAll('.feed-map');
    if (!maps.length) return;
    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var el = entry.target;
            observer.unobserve(el);
            if (el._mapInit) return;
            el._mapInit = true;
            var lat = parseFloat(el.dataset.lat);
            var lng = parseFloat(el.dataset.lng);
            if (isNaN(lat) || isNaN(lng)) return;
            var mini = L.map(el, {
                zoomControl: false,
                dragging: false,
                scrollWheelZoom: false,
                doubleClickZoom: false,
                touchZoom: false,
                keyboard: false,
                attributionControl: false
            }).setView([lat, lng], 14);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
                maxZoom: 19
            }).addTo(mini);
            L.marker([lat, lng], {
                interactive: false,
                icon: L.divIcon({
                    className: '',
                    html: '<div class="feed-map-pin"></div>',
                    iconSize: [18, 18],
                    iconAnchor: [9, 9]
                })
            }).addTo(mini);
            var go = function () {
                window.location.href = '/map?spot=' + encodeURIComponent(el.dataset.spot);
            };
            mini.on('click', go);
            el.addEventListener('click', go);
        });
    }, { rootMargin: '120px' });
    maps.forEach(function (m) { observer.observe(m); });
}

/* ---------- привязка событий ---------- */
document.addEventListener('DOMContentLoaded', function () {
    // комментарии
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
    // реакции
    document.querySelectorAll('.reaction-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            toggleReaction(btn.dataset.spotId, btn.dataset.emoji);
        });
    });
    document.querySelectorAll('.reactions-row').forEach(function (row) {
        loadReactions(row.dataset.spotId);
    });
    // мини-карты
    initFeedMaps();
});
})();