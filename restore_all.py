#!/usr/bin/env python3
"""
Полное восстановление проекта Картометр.
Запуск: python restore_all.py
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
print(f"📁 Рабочая папка: {BASE_DIR}\n")

# ========================================
# 1. BASE.HTML - базовый шаблон
# ========================================
base_html = """<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>{% block title %}Картометр{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Unbounded:wght@500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    {% block head %}{% endblock %}
</head>
<body>
    {% with messages = get_flashed_messages() %}
        {% if messages %}
            {% for message in messages %}
                <div class="flash">{{ message }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
    <script>
        window.CURRENT_USER_ID = {{ session.get('user_id')|tojson if session.get('user_id') else 'null' }};
    </script>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="{{ url_for('static', filename='js/nav.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>"""

# ========================================
# 2. MAP.HTML - главный экран карты
# ========================================
map_html = """{% extends "base.html" %}
{% block title %}Карта — Картометр{% endblock %}
{% block content %}
<div class="app-shell">
    <div class="map-wrap">
        <div id="map"></div>
        <div class="category-scroller" id="categoryScroller">
            <div class="cat-chip selected" data-cat="">Все</div>
            {% for c in categories %}
                <div class="cat-chip" data-cat="{{ c }}">{{ c }}</div>
            {% endfor %}
        </div>
        <button class="icon-btn legend-btn" id="legendToggle" type="button">🎨</button>
        <div class="legend-panel" id="legendPanel">
            <div class="legend-row"><span class="legend-dot mine"></span> Ваши метки</div>
            <div class="legend-row"><span class="legend-dot friends"></span> Только для друзей</div>
            <div class="legend-row"><span class="legend-dot public"></span> Видят все</div>
            <div class="legend-row"><span class="legend-dot manual"></span> Расставлено вручную</div>
            <div class="legend-row">⚡ Волна — пульсирует</div>
        </div>
        <div class="fab-column">
            <button class="fab-mini" id="manualToggle" type="button">✋</button>
            <button class="fab-mini" id="locateMe" type="button">📍</button>
            <button class="big-add" id="openAddSpot" type="button">+</button>
        </div>
        <div class="manual-mode-banner" id="manualBanner">
            <span>✋ Режим ручной расстановки</span>
            <button type="button" id="manualBannerClose">✕</button>
        </div>
    </div>
    <nav class="bottom-nav">
        <a class="nav-item active" href="{{ url_for('map_view') }}"><span class="ic">🗺️</span>Карта</a>
        <a class="nav-item" href="{{ url_for('feed_view') }}"><span class="ic">📰</span>Лента</a>
        <a class="nav-item" href="{{ url_for('friends_view') }}"><span class="ic">🤝</span>Друзья</a>
        <a class="nav-item" href="{{ url_for('messages_view') }}"><span class="ic">💬</span>Чаты</a>
        <a class="nav-item" href="{{ url_for('profile_view', username=profile.username) }}"><span class="ic">👤</span>Профиль</a>
    </nav>
</div>
<div class="sheet-overlay" id="addSpotOverlay">
    <div class="sheet">
        <div class="sheet-handle"></div>
        <button class="sheet-close" id="closeSheet" type="button">✕</button>
        <h3>📍 Новая метка</h3>
        <form id="addSpotForm">
            <input type="hidden" name="lat" id="latInput">
            <input type="hidden" name="lng" id="lngInput">
            <input type="hidden" name="placement_type" id="placementInput" value="geo">
            <input type="hidden" name="category" id="categoryInput">
            <input type="hidden" name="organization_id" id="orgIdInput">
            <input type="hidden" name="duration_hours" id="durationInput" value="3">
            <input type="hidden" name="visibility" id="visibilityInput" value="public">
            <div class="field"><label>Что тут происходит?</label><input id="spotTitle" name="title" maxlength="120" required></div>
            <div class="field"><label>Пара слов</label><textarea id="spotDescription" name="description" maxlength="1000"></textarea></div>
            <div class="field"><label>Категория</label><div class="category-picker" id="addCategoryPicker">{% for c in categories %}<div class="cat-chip" data-cat="{{ c }}">{{ c }}</div>{% endfor %}</div></div>
            <div class="field"><label>Сколько на карте?</label><div class="duration-toggle"><div class="duration-option" data-h="1">1 ч</div><div class="duration-option selected" data-h="3">3 ч</div><div class="duration-option" data-h="6">6 ч</div><div class="duration-option" data-h="24">сутки</div></div></div>
            <div class="field"><label>Кто увидит?</label><div class="visibility-toggle"><div class="vis-option selected" data-vis="public">🌍 Все</div><div class="vis-option" data-vis="friends">🤝 Друзья</div></div></div>
            <button class="btn btn-primary btn-block" id="submitSpotBtn" type="submit">Поставить метку</button>
        </form>
    </div>
</div>
<div class="sheet-overlay" id="spotSheetOverlay"><div class="sheet" id="spotSheetContent"></div></div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/map.js') }}"></script>
{% endblock %}"""

# ========================================
# 3. INDEX.HTML - лендинг
# ========================================
index_html = """{% extends "base.html" %}
{% block title %}Картометр — карта живого города{% endblock %}
{% block content %}
<div class="center-page">
    <div class="auth-box card">
        <div class="logo-circle">📍</div>
        <h1 class="display" style="text-align:center">Картометр</h1>
        <p class="subtitle" style="text-align:center">Не лента, а карта. Оставь метку — где ты и что тут происходит — и друзья увидят это сразу.</p>
        <div class="cta-row">
            <a class="btn btn-primary btn-block" href="{{ url_for('register') }}">Создать профиль</a>
            <a class="btn btn-ghost btn-block" href="{{ url_for('login') }}">Войти</a>
        </div>
        <div class="feature-list">
            <div class="feature-item"><span class="em">📍</span><div><b>Метки на карте</b><span>Покажи, где ты</span></div></div>
            <div class="feature-item"><span class="em">🤝</span><div><b>Гибкая приватность</b><span>Все или только близкие</span></div></div>
            <div class="feature-item"><span class="em">⏳</span><div><b>Своё время жизни</b><span>1–24 часа</span></div></div>
            <div class="feature-item"><span class="em">⚡</span><div><b>Волны</b><span>События в реальном времени</span></div></div>
        </div>
    </div>
</div>
{% endblock %}"""

# ========================================
# 4. LOGIN.HTML
# ========================================
login_html = """{% extends "base.html" %}
{% block title %}Вход — Картометр{% endblock %}
{% block content %}
<div class="center-page">
    <div class="auth-box card">
        <div class="logo-circle">👋</div>
        <h1 class="display" style="text-align:center">С возвращением</h1>
        <p class="subtitle" style="text-align:center">Войдите, чтобы увидеть карту живого города</p>
        <form method="post" action="{{ url_for('login') }}">
            <div class="field"><label for="email">Email</label><input type="email" id="email" name="email" autocomplete="email" required></div>
            <div class="field"><label for="password">Пароль</label><input type="password" id="password" name="password" autocomplete="current-password" required></div>
            <button class="btn btn-primary btn-block" type="submit">Войти</button>
        </form>
        <div class="switch-link">Ещё нет аккаунта? <a href="{{ url_for('register') }}">Создать</a></div>
    </div>
</div>
{% endblock %}"""

# ========================================
# 5. REGISTER.HTML
# ========================================
register_html = """{% extends "base.html" %}
{% block title %}Регистрация — Картометр{% endblock %}
{% block content %}
<div class="center-page">
    <div class="auth-box card">
        <div class="logo-circle">🌱</div>
        <h1 class="display" style="text-align:center">Создать профиль</h1>
        <form method="post" action="{{ url_for('register') }}">
            <div class="field"><label>Кто вы?</label><div class="visibility-toggle" id="accountTypePicker"><div class="vis-option selected" data-type="person">🙋 Человек</div><div class="vis-option" data-type="organization">🏢 Заведение</div></div><input type="hidden" name="account_type" id="accountTypeInput" value="person"></div>
            <div class="field"><label>Имя</label><input type="text" name="display_name" maxlength="80" required></div>
            <div class="field"><label>Username (латиницей)</label><input type="text" name="username" maxlength="30" required></div>
            <div class="field"><label>Email</label><input type="email" name="email" autocomplete="email" required></div>
            <div class="field"><label>Пароль</label><input type="password" name="password" minlength="8" required></div>
            <button class="btn btn-primary btn-block" type="submit">Зарегистрироваться</button>
        </form>
        <div class="switch-link">Уже есть аккаунт? <a href="{{ url_for('login') }}">Войти</a></div>
    </div>
</div>
{% endblock %}"""

# ========================================
# 6. FEED.HTML - лента
# ========================================
feed_html = """{% extends "base.html" %}
{% block title %}Лента — Картометр{% endblock %}
{% block content %}
<div class="app-shell">
    <div class="list-page" style="flex:1; overflow-y:auto;">
        <div class="page-head">
            <div><h1 class="display" style="font-size:24px">📰 Лента</h1><p class="subtitle">Что происходит у друзей</p></div>
        </div>
        {% if spots %}
            {% for spot in spots %}
            <div class="card" style="margin-bottom:12px;">
                <div class="spot-thumb-row">
                    <div class="spot-thumb">{% if spot.photo_url %}<img src="{{ spot.photo_url }}">{% else %}📍{% endif %}</div>
                    <div class="info">
                        <div class="name">{{ spot.owner.display_name if spot.owner else 'Кто-то' }}{% if spot.wave_ends_at %} ⚡{% endif %}</div>
                        <div class="sub">{{ spot.title }}</div>
                    </div>
                </div>
                {% if spot.description %}<p style="margin-top:10px;">{{ spot.description }}</p>{% endif %}
                <div class="hint" style="margin-top:8px;">
                    {% if spot.category %}{{ spot.category }} · {% endif %}
                    {% if spot.visibility == 'friends' %}🤝 Только друзья{% else %}🌍 Видят все{% endif %}
                </div>
            </div>
            {% endfor %}
        {% else %}
            <div class="empty-state"><span class="em">🌤️</span><p>Пока тихо. Добавьте друзей!</p></div>
        {% endif %}
    </div>
    <nav class="bottom-nav">
        <a class="nav-item" href="{{ url_for('map_view') }}"><span class="ic">🗺️</span>Карта</a>
        <a class="nav-item active" href="{{ url_for('feed_view') }}"><span class="ic">📰</span>Лента</a>
        <a class="nav-item" href="{{ url_for('friends_view') }}"><span class="ic">🤝</span>Друзья</a>
        <a class="nav-item" href="{{ url_for('messages_view') }}"><span class="ic">💬</span>Чаты</a>
        <a class="nav-item" href="{{ url_for('profile_view', username=profile.username) }}"><span class="ic">👤</span>Профиль</a>
    </nav>
</div>
{% endblock %}"""

# ========================================
# 7. FRIENDS.HTML
# ========================================
friends_html = """{% extends "base.html" %}
{% block title %}Друзья — Картометр{% endblock %}
{% block content %}
<div class="app-shell">
    <div class="list-page" style="flex:1; overflow-y:auto;">
        <div class="page-head"><div><h1 class="display" style="font-size:24px">🤝 Друзья</h1><p class="subtitle">Заявки и ваши друзья</p></div></div>
        {% if incoming %}
        <div class="section-title">Хотят добавить · {{ incoming|length }}</div>
        {% for req in incoming %}
        <div class="row-card">
            <div class="avatar">{{ req.requester.display_name[:1]|upper }}</div>
            <div class="info"><div class="name">{{ req.requester.display_name }}</div><div class="sub">@{{ req.requester.username }}</div></div>
            <button class="btn btn-green btn-sm accept-friend-btn" data-id="{{ req.id }}">✓</button>
            <button class="btn btn-soft btn-sm decline-friend-btn" data-id="{{ req.id }}">✕</button>
        </div>
        {% endfor %}
        {% endif %}
        <div class="section-title">Ваши друзья · {{ accepted|length }}</div>
        {% if accepted %}
            {% for f in accepted %}
            {% set friend = f.requester if f.requester_id != my_id else f.addressee %}
            <div class="row-card">
                <div class="avatar">{{ friend.display_name[:1]|upper }}</div>
                <div class="info"><div class="name">{{ friend.display_name }}</div><div class="sub">@{{ friend.username }}</div></div>
                <a class="btn btn-soft btn-sm" href="{{ url_for('chat_view', username=friend.username) }}">💬</a>
                <a class="btn btn-soft btn-sm" href="{{ url_for('profile_view', username=friend.username) }}">👤</a>
                <button class="btn btn-ghost btn-sm remove-friend-btn" data-id="{{ f.id }}">✕</button>
            </div>
            {% endfor %}
        {% else %}
            <div class="empty-state"><span class="em">🤝</span><p>Пока нет друзей.</p></div>
        {% endif %}
    </div>
    <nav class="bottom-nav">
        <a class="nav-item" href="{{ url_for('map_view') }}"><span class="ic">🗺️</span>Карта</a>
        <a class="nav-item" href="{{ url_for('feed_view') }}"><span class="ic">📰</span>Лента</a>
        <a class="nav-item active" href="{{ url_for('friends_view') }}"><span class="ic">🤝</span>Друзья</a>
        <a class="nav-item" href="{{ url_for('messages_view') }}"><span class="ic">💬</span>Чаты</a>
        <a class="nav-item" href="{{ url_for('profile_view', username=profile.username) }}"><span class="ic">👤</span>Профиль</a>
    </nav>
</div>
{% endblock %}
{% block scripts %}
<script>
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.accept-friend-btn').forEach(function (btn) {
        btn.onclick = async function () { await fetch('/api/friends/' + btn.dataset.id + '/accept', {method: 'POST'}); location.reload(); };
    });
    document.querySelectorAll('.decline-friend-btn').forEach(function (btn) {
        btn.onclick = async function () { await fetch('/api/friends/' + btn.dataset.id + '/decline', {method: 'POST'}); location.reload(); };
    });
    document.querySelectorAll('.remove-friend-btn').forEach(function (btn) {
        btn.onclick = async function () { if (confirm('Удалить?')) { await fetch('/api/friends/' + btn.dataset.id, {method: 'DELETE'}); location.reload(); } };
    });
});
</script>
{% endblock %}"""

# ========================================
# 8. MESSAGES.HTML - список чатов
# ========================================
messages_html = """{% extends "base.html" %}
{% block title %}Чаты — Картометр{% endblock %}
{% block content %}
<div class="app-shell">
    <div class="list-page" style="flex:1; overflow-y:auto;">
        <div class="page-head"><div><h1 class="display" style="font-size:24px">💬 Чаты</h1><p class="subtitle">Личные сообщения</p></div></div>
        <div id="conversationsList"><div class="empty-state"><span class="em">⏳</span><p>Загрузка...</p></div></div>
    </div>
    <nav class="bottom-nav">
        <a class="nav-item" href="{{ url_for('map_view') }}"><span class="ic">🗺️</span>Карта</a>
        <a class="nav-item" href="{{ url_for('feed_view') }}"><span class="ic">📰</span>Лента</a>
        <a class="nav-item" href="{{ url_for('friends_view') }}"><span class="ic">🤝</span>Друзья</a>
        <a class="nav-item active" href="{{ url_for('messages_view') }}"><span class="ic">💬</span>Чаты</a>
        <a class="nav-item" href="{{ url_for('profile_view', username=profile.username) }}"><span class="ic">👤</span>Профиль</a>
    </nav>
</div>
{% endblock %}
{% block scripts %}
<script>
document.addEventListener('DOMContentLoaded', async function () {
    var list = document.getElementById('conversationsList');
    try {
        var res = await fetch('/api/friends_list');
        var friends = await res.json();
        if (!friends.length) { list.innerHTML = '<div class="empty-state"><span class="em">🤝</span><p>Пока нет чатов. Добавьте друзей!</p></div>'; return; }
        list.innerHTML = '';
        friends.forEach(function (f) {
            var link = document.createElement('a');
            link.className = 'row-card';
            link.href = '/messages/' + f.username;
            link.innerHTML = '<div class="avatar">' + (f.display_name||'?')[0].toUpperCase() + '</div><div class="info"><div class="name">' + (f.display_name||f.username) + '</div><div class="sub">@' + f.username + '</div></div>';
            list.appendChild(link);
        });
    } catch (e) { list.innerHTML = '<div class="empty-state"><span class="em">⚠️</span><p>Ошибка загрузки</p></div>'; }
});
</script>
{% endblock %}"""

# ========================================
# 9. CHAT.HTML - отдельный чат
# ========================================
chat_html = """{% extends "base.html" %}
{% block title %}{{ friend.display_name }} — Картометр{% endblock %}
{% block content %}
<div class="chat-shell">
    <div class="chat-head">
        <a class="icon-btn" href="{{ url_for('messages_view') }}">←</a>
        <div class="avatar">{% if friend.avatar_url %}<img src="{{ friend.avatar_url }}">{% else %}{{ friend.display_name[:1]|upper }}{% endif %}</div>
        <div><div class="name">{{ friend.display_name }}</div><div class="hint">@{{ friend.username }}</div></div>
    </div>
    <div class="chat-body" id="chatBody"><div class="empty-state"><p>Загрузка...</p></div></div>
    <div class="chat-input-row">
        <input type="text" id="chatInput" placeholder="Написать..." maxlength="2000">
        <button class="chat-send" id="chatSend" type="button">➤</button>
    </div>
</div>
{% endblock %}
{% block scripts %}
<script>
window.CHAT_FRIEND_ID = {{ friend.id|tojson }};
</script>
<script>
(function () {
    var friendId = window.CHAT_FRIEND_ID;
    var userId = window.CURRENT_USER_ID;
    var chatBody = document.getElementById('chatBody');
    var chatInput = document.getElementById('chatInput');
    var chatSend = document.getElementById('chatSend');
    async function loadMessages() {
        var res = await fetch('/api/messages/' + friendId);
        var msgs = await res.json();
        chatBody.innerHTML = msgs.length ? msgs.map(function (m) {
            var mine = m.sender_id === userId;
            return '<div class="bubble ' + (mine ? 'mine' : 'theirs') + '">' + (m.text||'') + '</div>';
        }).join('') : '<div class="empty-state"><p>Нет сообщений</p></div>';
        chatBody.scrollTop = chatBody.scrollHeight;
    }
    async function send() {
        var text = chatInput.value.trim();
        if (!text) return;
        chatInput.value = '';
        await fetch('/api/messages/' + friendId, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: text})});
        loadMessages();
    }
    chatSend.onclick = send;
    chatInput.onkeydown = function (e) { if (e.key === 'Enter') send(); };
    loadMessages();
    setInterval(loadMessages, 5000);
})();
</script>
{% endblock %}"""

# ========================================
# 10. PROFILE.HTML
# ========================================
profile_html = """{% extends "base.html" %}
{% block title %}{{ profile.display_name }} — Картометр{% endblock %}
{% block content %}
<div class="app-shell">
    <div class="list-page" style="flex:1; overflow-y:auto;">
        <div class="card profile-card">
            <div class="avatar profile-avatar-lg">{% if profile.avatar_url %}<img src="{{ profile.avatar_url }}">{% else %}{{ profile.display_name[:1]|upper }}{% endif %}</div>
            <div class="profile-name-row"><h1 class="display" style="font-size:22px;">{{ profile.display_name }}</h1>{% if profile.is_verified %}<span class="verified-tick">✅</span>{% endif %}</div>
            <div class="hint">@{{ profile.username }}{% if profile.age %} · {{ profile.age }}{% endif %}{% if profile.location %} · {{ profile.location }}{% endif %}</div>
            {% if profile.bio %}<p style="margin-top:12px;">{{ profile.bio }}</p>{% endif %}
            {% if profile.account_type != 'organization' %}<div class="level-badge"><span class="lv-num">{{ profile.level or 1 }}</span>Уровень · {{ profile.xp or 0 }} XP</div>{% endif %}
            <div style="display:flex; gap:8px; justify-content:center; margin-top:16px;">
                {% if is_me %}<a class="btn btn-soft" href="{{ url_for('settings_view') }}">⚙️ Настройки</a>
                {% elif friend_status is none %}<button class="btn btn-primary" id="addFriendBtn">🤝 Добавить</button>
                {% elif friend_status.status == 'accepted' %}<a class="btn btn-primary" href="{{ url_for('chat_view', username=profile.username) }}">💬 Написать</a>
                {% elif friend_status.addressee_id == my_id %}<button class="btn btn-green" id="acceptFriendBtn">✓ Принять</button>
                {% else %}<button class="btn btn-ghost" disabled>Заявка отправлена</button>{% endif %}
            </div>
        </div>
        <div class="section-title">Метки · {{ spots|length }}</div>
        {% if spots %}{% for spot in spots %}
        <div class="row-card"><div class="spot-thumb">{% if spot.photo_url %}<img src="{{ spot.photo_url }}">{% else %}📍{% endif %}</div>
            <div class="info"><div class="name">{{ spot.title }}</div><div class="sub">{% if spot.visibility == 'friends' %}🤝 Только друзья{% else %}🌍 Видят все{% endif %}</div></div></div>
        {% endfor %}{% else %}<div class="empty-state"><span class="em">🗺️</span><p>Меток пока нет</p></div>{% endif %}
    </div>
    <nav class="bottom-nav">
        <a class="nav-item" href="{{ url_for('map_view') }}"><span class="ic">🗺️</span>Карта</a>
        <a class="nav-item" href="{{ url_for('feed_view') }}"><span class="ic">📰</span>Лента</a>
        <a class="nav-item" href="{{ url_for('friends_view') }}"><span class="ic">🤝</span>Друзья</a>
        <a class="nav-item" href="{{ url_for('messages_view') }}"><span class="ic">💬</span>Чаты</a>
        <a class="nav-item active" href="{{ url_for('profile_view', username=profile.username) }}"><span class="ic">👤</span>Профиль</a>
    </nav>
</div>
{% endblock %}
{% block scripts %}
<script>
var addBtn = document.getElementById('addFriendBtn');
if (addBtn) addBtn.onclick = async function () { await fetch('/api/friends/{{ profile.username }}/add', {method:'POST'}); location.reload(); };
var acceptBtn = document.getElementById('acceptFriendBtn');
if (acceptBtn) acceptBtn.onclick = async function () { await fetch('/api/friends/{{ friend_status.id }}/accept', {method:'POST'}); location.reload(); };
</script>
{% endblock %}"""

# ========================================
# 11. SETTINGS.HTML
# ========================================
settings_html = """{% extends "base.html" %}
{% block title %}Настройки — Картометр{% endblock %}
{% block content %}
<div class="app-shell">
    <div class="list-page" style="flex:1; overflow-y:auto;">
        <div class="page-head"><div><h1 class="display" style="font-size:24px">⚙️ Настройки</h1></div></div>
        <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="form_name" value="profile">
            <div class="field"><label>Имя</label><input type="text" name="display_name" value="{{ profile.display_name or '' }}"></div>
            <div class="field"><label>Локация</label><input type="text" name="location" value="{{ profile.location or '' }}"></div>
            <div class="field"><label>О себе</label><textarea name="bio">{{ profile.bio or '' }}</textarea></div>
            <div class="field"><label>Аватар</label><input type="file" name="avatar" accept="image/*"></div>
            <button class="btn btn-primary btn-block" type="submit">Сохранить</button>
        </form>
        <div class="section-divider"></div>
        <a class="btn btn-ghost btn-block" href="{{ url_for('logout') }}" style="margin-top:10px;">Выйти</a>
    </div>
    <nav class="bottom-nav">
        <a class="nav-item" href="{{ url_for('map_view') }}"><span class="ic">🗺️</span>Карта</a>
        <a class="nav-item" href="{{ url_for('feed_view') }}"><span class="ic">📰</span>Лента</a>
        <a class="nav-item" href="{{ url_for('friends_view') }}"><span class="ic">🤝</span>Друзья</a>
        <a class="nav-item" href="{{ url_for('messages_view') }}"><span class="ic">💬</span>Чаты</a>
        <a class="nav-item" href="{{ url_for('profile_view', username=profile.username) }}"><span class="ic">👤</span>Профиль</a>
    </nav>
</div>
{% endblock %}"""

# ========================================
# 12. NAV.JS - исправленный (& & → &&)
# ========================================
nav_js = """(function () {
    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.bottom-nav')) return;
        fetch('/api/messages/unread_count', {credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                if (!d) return;
                var links = document.querySelectorAll('.bottom-nav a.nav-item');
                var friendsLink = null, msgLink = null;
                links.forEach(function (a) {
                    if (a.href.indexOf('/friends') > -1) friendsLink = a;
                    if (a.href.indexOf('/messages') > -1) msgLink = a;
                });
                if (friendsLink && d.friend_requests > 0 && !friendsLink.querySelector('.nav-badge')) {
                    var ic = friendsLink.querySelector('.ic');
                    if (ic) ic.insertAdjacentHTML('afterend', '<span class="nav-badge"></span>');
                }
                if (msgLink && d.messages > 0 && !msgLink.querySelector('.nav-badge')) {
                    var ic = msgLink.querySelector('.ic');
                    if (ic) ic.insertAdjacentHTML('afterend', '<span class="nav-badge"></span>');
                }
            }).catch(function () {});
    });
})();
"""

# ========================================
# 13. APP.PY - исправленный
# ========================================
app_py = """import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Не заданы SUPABASE_URL / SUPABASE_ANON_KEY в .env")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
CATEGORIES = ["Бар", "Клуб", "Кофейня", "Ресторан", "Коворкинг", "Караоке", "Спорт", "Вечеринка", "Природа", "Выставка/галерея", "Другое"]

def get_supabase(access_token=None, refresh_token=None):
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if access_token and refresh_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            client.postgrest.auth(access_token)
    elif access_token:
        client.postgrest.auth(access_token)
    return client

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "access_token" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        try:
            sb = get_supabase(session["access_token"], session.get("refresh_token"))
            result = sb.table("profiles").select("id").eq("id", session["user_id"]).execute()
            if not result.data:
                raise Exception("profile not found")
        except Exception:
            session.clear()
            flash("Сессия истекла. Войдите заново.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def upload_to_bucket(sb, bucket, uid, file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    path = f"{uid}/{uuid.uuid4()}.{ext}"
    sb.storage.from_(bucket).upload(path, file_storage.read(), {"content-type": file_storage.mimetype})
    return sb.storage.from_(bucket).get_public_url(path)

@app.route("/")
def index():
    if "access_token" in session:
        return redirect(url_for("map_view"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", categories=CATEGORIES)
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip() or username
    account_type = request.form.get("account_type", "person")
    if not email or not password or not username:
        flash("Заполните email, имя пользователя и пароль")
        return redirect(url_for("register"))
    sb = get_supabase()
    try:
        auth_res = sb.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        flash(f"Ошибка: {e}")
        return redirect(url_for("register"))
    if not auth_res.user:
        flash("Подтвердите email по ссылке в почте")
        return redirect(url_for("login"))
    if auth_res.session:
        sb2 = get_supabase(auth_res.session.access_token, auth_res.session.refresh_token)
        profile_data = {"id": auth_res.user.id, "username": username, "display_name": display_name, "account_type": account_type}
        if account_type == "organization":
            profile_data["category"] = request.form.get("category", "").strip() or None
            profile_data["address"] = request.form.get("address", "").strip() or None
        try:
            sb2.table("profiles").insert(profile_data).execute()
        except Exception as e:
            flash(f"Профиль не сохранён: {e}")
        session["access_token"] = auth_res.session.access_token
        session["refresh_token"] = auth_res.session.refresh_token
        session["user_id"] = auth_res.user.id
        return redirect(url_for("map_view"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    try:
        res = get_supabase().auth.sign_in_with_password({"email": request.form.get("email", "").strip(), "password": request.form.get("password", "")})
        session["access_token"] = res.session.access_token
        session["refresh_token"] = res.session.refresh_token
        session["user_id"] = res.user.id
        return redirect(url_for("map_view"))
    except Exception:
        flash("Неверный email или пароль")
        return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/map")
@login_required
def map_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    result = sb.table("profiles").select("*").eq("id", session["user_id"]).execute()
    if not result.data:
        session.clear()
        return redirect(url_for("login"))
    return render_template("map.html", profile=result.data[0], categories=CATEGORIES)

@app.route("/feed")
@login_required
def feed_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    prof = sb.table("profiles").select("*").eq("id", uid).execute()
    profile = prof.data[0] if prof.data else {}
    friends_res = sb.table("friendships").select("requester_id, addressee_id").eq("status", "accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friend_ids = [uid] + [f["requester_id"] if f["requester_id"] != uid else f["addressee_id"] for f in (friends_res.data or [])]
    spots_res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url)").in_("owner_id", friend_ids).order("created_at", desc=True).limit(50).execute()
    return render_template("feed.html", spots=spots_res.data or [], profile=profile)

@app.route("/messages")
@login_required
def messages_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    result = sb.table("profiles").select("*").eq("id", session["user_id"]).execute()
    profile = result.data[0] if result.data else {}
    return render_template("messages.html", profile=profile)

@app.route("/messages/<username>")
@login_required
def chat_view(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    result = sb.table("profiles").select("*").eq("id", session["user_id"]).execute()
    profile = result.data[0] if result.data else {}
    friend_res = sb.table("profiles").select("id, username, display_name, avatar_url").eq("username", username).execute()
    if not friend_res.data:
        return "Пользователь не найден", 404
    return render_template("chat.html", profile=profile, friend=friend_res.data[0])

@app.route("/profile/<username>")
@login_required
def profile_view(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    prof_res = sb.table("profiles").select("*").eq("username", username).execute()
    if not prof_res.data:
        return "Пользователь не найден", 404
    profile = prof_res.data[0]
    spots_res = sb.table("spots").select("*").eq("owner_id", profile["id"]).order("created_at", desc=True).execute()
    tagged_spots = []
    if profile.get("account_type") == "organization":
        tagged_res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url)").eq("organization_id", profile["id"]).order("created_at", desc=True).execute()
        tagged_spots = tagged_res.data or []
    is_me = profile["id"] == session["user_id"]
    friend_status = None
    if not is_me:
        f = sb.table("friendships").select("*").or_(
            f"and(requester_id.eq.{session['user_id']},addressee_id.eq.{profile['id']}),"
            f"and(requester_id.eq.{profile['id']},addressee_id.eq.{session['user_id']})").execute()
        if f.data:
            friend_status = f.data[0]
    return render_template("profile.html", profile=profile, spots=spots_res.data, is_me=is_me, friend_status=friend_status, tagged_spots=tagged_spots, my_id=session["user_id"])

@app.route("/friends")
@login_required
def friends_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    incoming = sb.table("friendships").select("*, requester:requester_id(username, display_name, avatar_url)").eq("addressee_id", uid).eq("status", "pending").execute()
    accepted = sb.table("friendships").select("*, requester:requester_id(username, display_name, avatar_url), addressee:addressee_id(username, display_name, avatar_url)").eq("status", "accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    result = sb.table("profiles").select("*").eq("id", uid).execute()
    profile = result.data[0] if result.data else {}
    return render_template("friends.html", incoming=incoming.data or [], accepted=accepted.data or [], my_id=uid, profile=profile)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "GET":
        result = sb.table("profiles").select("*").eq("id", uid).execute()
        profile = result.data[0] if result.data else {}
        return render_template("settings.html", profile=profile, categories=CATEGORIES)
    update_data = {
        "display_name": request.form.get("display_name", "").strip(),
        "bio": request.form.get("bio", "").strip(),
        "location": request.form.get("location", "").strip(),
    }
    avatar = request.files.get("avatar")
    if avatar and avatar.filename:
        update_data["avatar_url"] = upload_to_bucket(sb, "avatars", uid, avatar)
    try:
        sb.table("profiles").update(update_data).eq("id", uid).execute()
        flash("Профиль обновлён")
    except Exception as e:
        flash(f"Ошибка: {e}")
    return redirect(url_for("profile_view", username=session.get("username", "")))

@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        sb.table("spots").delete().eq("owner_id", session["user_id"]).lt("expires_at", now_iso).execute()
    except Exception:
        pass
    res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url), organization:organization_id(username, display_name, category, is_verified)").or_(f"expires_at.is.null,expires_at.gt.{now_iso}").order("created_at", desc=True).execute()
    return jsonify(res.data or [])

@app.route("/api/spots", methods=["POST"])
@login_required
def api_spots_create():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    title = request.form.get("title", "").strip()
    lat = request.form.get("lat")
    lng = request.form.get("lng")
    if not title or lat is None or lng is None:
        return jsonify({"error": "title, lat, lng обязательны"}), 400
    duration_hours = max(0.5, min(float(request.form.get("duration_hours", "6")), 48))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()
    profile_res = sb.table("profiles").select("account_type").eq("id", uid).execute()
    acc_type = (profile_res.data[0] if profile_res.data else {}).get("account_type", "person")
    if acc_type == "person":
        sb.table("spots").delete().eq("owner_id", uid).execute()
    data = {"owner_id": uid, "title": title, "description": request.form.get("description", "").strip(), "lat": float(lat), "lng": float(lng), "visibility": request.form.get("visibility", "public"), "placement_type": request.form.get("placement_type", "geo"), "expires_at": expires_at, "is_live": True}
    photo = request.files.get("photo")
    if photo and photo.filename:
        data["photo_url"] = upload_to_bucket(sb, "spot-photos", uid, photo)
    res = sb.table("spots").insert(data).execute()
    return jsonify(res.data[0]), 201

@app.route("/api/spots/<int:spot_id>", methods=["DELETE"])
@login_required
def api_spots_delete(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("spots").delete().eq("id", spot_id).eq("owner_id", session["user_id"]).execute()
    return jsonify({"ok": True})

@app.route("/api/friends_list")
@login_required
def api_friends_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    res = sb.table("friendships").select("requester_id, addressee_id").eq("status", "accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friends = []
    for f in (res.data or []):
        fid = f["requester_id"] if f["requester_id"] != uid else f["addressee_id"]
        prof = sb.table("profiles").select("id, username, display_name, avatar_url").eq("id", fid).execute()
        if prof.data:
            friends.append(prof.data[0])
    return jsonify(friends)

@app.route("/api/friends/<username>/add", methods=["POST"])
@login_required
def api_friend_add(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    target = sb.table("profiles").select("id").eq("username", username).execute()
    if not target.data:
        return jsonify({"error": "Пользователь не найден"}), 404
    target_id = target.data[0]["id"]
    if target_id == uid:
        return jsonify({"error": "Нельзя добавить самого себя"}), 400
    res = sb.table("friendships").insert({"requester_id": uid, "addressee_id": target_id}).execute()
    return jsonify({"ok": True, "status": "pending", "friendship": res.data[0]}), 201

@app.route("/api/friends/<int:friendship_id>/accept", methods=["POST"])
@login_required
def api_friend_accept(friendship_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").update({"status": "accepted"}).eq("id", friendship_id).eq("addressee_id", session["user_id"]).execute()
    return jsonify({"ok": True})

@app.route("/api/friends/<int:friendship_id>/decline", methods=["POST"])
@login_required
def api_friend_decline(friendship_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").delete().eq("id", friendship_id).eq("addressee_id", session["user_id"]).execute()
    return jsonify({"ok": True})

@app.route("/api/friends/<int:friendship_id>", methods=["DELETE"])
@login_required
def api_friend_remove(friendship_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").delete().eq("id", friendship_id).or_(f"requester_id.eq.{session['user_id']},addressee_id.eq.{session['user_id']}").execute()
    return jsonify({"ok": True})

@app.route("/api/messages/<friend_id>", methods=["GET", "POST"])
@login_required
def api_messages(friend_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "POST":
        text = (request.json or {}).get("text", "").strip()
        if not text:
            return jsonify({"error": "Текст обязателен"}), 400
        sb.table("messages").insert({"sender_id": uid, "receiver_id": friend_id, "text": text}).execute()
        return jsonify({"ok": True}), 201
    res = sb.table("messages").select("*, sender:profiles!sender_id(username, display_name, avatar_url), receiver:profiles!receiver_id(username, display_name, avatar_url)").or_(f"and(sender_id.eq.{uid},receiver_id.eq.{friend_id}),and(sender_id.eq.{friend_id},receiver_id.eq.{uid})").order("created_at").execute()
    sb.table("messages").update({"is_read": True}).eq("sender_id", friend_id).eq("receiver_id", uid).eq("is_read", False).execute()
    return jsonify(res.data or [])

@app.route("/api/messages/unread_count")
@login_required
def api_unread_count():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    res = sb.table("messages").select("id", count="exact").eq("receiver_id", uid).eq("is_read", False).execute()
    incoming = sb.table("friendships").select("id", count="exact").eq("addressee_id", uid).eq("status", "pending").execute()
    return jsonify({"messages": res.count or 0, "friend_requests": incoming.count or 0})

if __name__ == "__main__":
    app.run(debug=False, port=5000)
"""

# ========================================
# 14. REQUIREMENTS.TXT
# ========================================
requirements_txt = """flask==3.0.3
supabase==2.7.4
python-dotenv==1.0.1
gunicorn==22.0.0
"""

# ========================================
# Функция записи файлов
# ========================================
def write_file(rel_path, content):
    path = BASE_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    print(f"✅ {rel_path}")

# ========================================
# Запуск восстановления
# ========================================
print("🚀 Восстанавливаю файлы...\n")

write_file("templates/base.html", base_html)
write_file("templates/map.html", map_html)
write_file("templates/index.html", index_html)
write_file("templates/login.html", login_html)
write_file("templates/register.html", register_html)
write_file("templates/feed.html", feed_html)
write_file("templates/friends.html", friends_html)
write_file("templates/messages.html", messages_html)
write_file("templates/chat.html", chat_html)
write_file("templates/profile.html", profile_html)
write_file("templates/settings.html", settings_html)
write_file("static/js/nav.js", nav_js)
write_file("app.py", app_py)
write_file("requirements.txt", requirements_txt)

print("\n" + "="*50)
print("🎉 ВСЕ ФАЙЛЫ ВОССТАНОВЛЕНЫ!")
print("="*50)
print("\nТеперь выполните в PowerShell:")
print("  git add .")
print('  git commit -m "fix: restore all html structure"')
print("  git push")
print("\nНа сервере (SSH):")
print("  cd /opt/app")
print("  git pull")
print("  systemctl restart kartometr")