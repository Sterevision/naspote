import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

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
            <span>✋ Режим ручной расстановки — тапните по карте</span>
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
            <input type="hidden" name="voice_url" id="voiceUrlInput">
            <input type="hidden" name="duration_hours" id="durationInput" value="3">
            <input type="hidden" name="mood" id="moodInput">
            <input type="hidden" name="visibility" id="visibilityInput" value="public">
            <input type="hidden" name="wave_enabled" id="waveEnabledInput" value="false">
            <div class="field"><label>Что тут происходит?</label><input id="spotTitle" name="title" maxlength="120" required></div>
            <div class="field"><label>Пара слов</label><textarea id="spotDescription" name="description" maxlength="1000"></textarea></div>
            <div class="field"><label>Категория</label><div class="category-picker" id="addCategoryPicker">{% for c in categories %}<div class="cat-chip" data-cat="{{ c }}">{{ c }}</div>{% endfor %}</div></div>
            <div class="field"><label>Сколько метка будет на карте?</label><div class="duration-toggle"><div class="duration-option" data-h="1">1 час</div><div class="duration-option selected" data-h="3">3 часа</div><div class="duration-option" data-h="6">6 часов</div><div class="duration-option" data-h="24">сутки</div></div></div>
            <div class="field"><label>Кто увидит метку?</label><div class="visibility-toggle"><div class="vis-option selected" data-vis="public">🌍 Все</div><div class="vis-option" data-vis="friends">🤝 Только друзья</div></div></div>
            <button class="btn btn-primary btn-block" id="submitSpotBtn" type="submit">Поставить метку</button>
        </form>
    </div>
</div>
<div class="sheet-overlay" id="spotSheetOverlay"><div class="sheet" id="spotSheetContent"></div></div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/map.js') }}"></script>
{% endblock %}"""

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
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-prod")
CATEGORIES = ["Бар", "Клуб", "Кофейня", "Ресторан", "Коворкинг", "Караоке", "Спорт", "Вечеринка", "Природа", "Выставка/галерея", "Другое"]

def get_supabase(access_token=None, refresh_token=None):
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if access_token and refresh_token:
        try: client.auth.set_session(access_token, refresh_token)
        except Exception: client.postgrest.auth(access_token)
    elif access_token:
        client.postgrest.auth(access_token)
    return client

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "access_token" not in session:
            if request.path.startswith("/api/"): return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        try:
            sb = get_supabase(session["access_token"], session.get("refresh_token"))
            result = sb.table("profiles").select("id").eq("id", session["user_id"]).execute()
            if not result.data: raise Exception("profile not found")
        except Exception:
            session.clear()
            flash("Сессия истекла. Войдите заново.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def upload_to_bucket(sb, bucket, uid, file_storage):
    if not file_storage or not file_storage.filename: return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    path = f"{uid}/{uuid.uuid4()}.{ext}"
    sb.storage.from_(bucket).upload(path, file_storage.read(), {"content-type": file_storage.mimetype})
    return sb.storage.from_(bucket).get_public_url(path)

@app.route("/")
def index():
    if "access_token" in session: return redirect(url_for("map_view"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET": return render_template("register.html", categories=CATEGORIES)
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
            if request.form.get("org_lat") and request.form.get("org_lng"):
                profile_data["lat"] = float(request.form.get("org_lat"))
                profile_data["lng"] = float(request.form.get("org_lng"))
        try: sb2.table("profiles").insert(profile_data).execute()
        except Exception as e: flash(f"Профиль не сохранён: {e}")
        session["access_token"] = auth_res.session.access_token
        session["refresh_token"] = auth_res.session.refresh_token
        session["user_id"] = auth_res.user.id
        return redirect(url_for("map_view"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET": return render_template("login.html")
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
    if not friend_res.data: return "Пользователь не найден", 404
    return render_template("chat.html", profile=profile, friend=friend_res.data[0])

@app.route("/profile/<username>")
@login_required
def profile_view(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    prof_res = sb.table("profiles").select("*").eq("username", username).execute()
    if not prof_res.data: return "Пользователь не найден", 404
    profile = prof_res.data[0]
    spots_res = sb.table("spots").select("*").eq("owner_id", profile["id"]).order("created_at", desc=True).execute()
    tagged_spots = []
    if profile.get("account_type") == "organization":
        tagged_res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url)").eq("organization_id", profile["id"]).order("created_at", desc=True).execute()
        tagged_spots = tagged_res.data or []
    is_me = profile["id"] == session["user_id"]
    friend_status = None
    if not is_me:
        f = sb.table("friendships").select("*").or_(f"and(requester_id.eq.{session['user_id']},addressee_id.eq.{profile['id']}),and(requester_id.eq.{profile['id']},addressee_id.eq.{session['user_id']})").execute()
        if f.data: friend_status = f.data[0]
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
    return render_template("friends.html", incoming=incoming.data, accepted=accepted.data, my_id=uid, profile=profile)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "GET":
        result = sb.table("profiles").select("*").eq("id", uid).execute()
        profile = result.data[0] if result.data else {}
        return render_template("settings.html", profile=profile, categories=CATEGORIES)
    form_name = request.form.get("form_name", "profile")
    if form_name == "visibility":
        show_all = request.form.get("show_all_categories") == "on"
        update_data = {"visible_categories": None if show_all else request.form.getlist("visible_categories")}
        try: sb.table("profiles").update(update_data).eq("id", uid).execute(); flash("Фильтр обновлён")
        except Exception as e: flash(f"Ошибка: {e}")
        return redirect(url_for("settings_view"))
    update_data = {"display_name": request.form.get("display_name", "").strip(), "bio": request.form.get("bio", "").strip(), "location": request.form.get("location", "").strip()}
    account_type = request.form.get("account_type", "person")
    if account_type == "organization":
        update_data["category"] = request.form.get("category", "").strip() or None
        update_data["address"] = request.form.get("address", "").strip() or None
    else:
        age = request.form.get("age")
        update_data["age"] = int(age) if age and age.isdigit() else None
    avatar = request.files.get("avatar")
    if avatar and avatar.filename: update_data["avatar_url"] = upload_to_bucket(sb, "avatars", uid, avatar)
    cover = request.files.get("cover")
    if cover and cover.filename: update_data["cover_url"] = upload_to_bucket(sb, "avatars", uid, cover)
    try: sb.table("profiles").update(update_data).eq("id", uid).execute(); flash("Профиль обновлён")
    except Exception as e: flash(f"Ошибка: {e}")
    result = sb.table("profiles").select("username").eq("id", uid).execute()
    return redirect(url_for("profile_view", username=result.data[0]["username"]))

@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    now_iso = datetime.now(timezone.utc).isoformat()
    try: sb.table("spots").delete().eq("owner_id", session["user_id"]).lt("expires_at", now_iso).execute()
    except Exception: pass
    res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url), organization:organization_id(username, display_name, category, is_verified)").or_(f"expires_at.is.null,expires_at.gt.{now_iso}").order("created_at", desc=True).execute()
    spots = res.data or []
    profile_res = sb.table("profiles").select("visible_categories").eq("id", session["user_id"]).execute()
    preferred = (profile_res.data[0] if profile_res.data else {}).get("visible_categories")
    if preferred is not None:
        spots = [s for s in spots if s.get("owner_id") == session["user_id"] or not s.get("category") or s.get("category") in preferred]
    return jsonify(spots)

@app.route("/api/spots", methods=["POST"])
@login_required
def api_spots_create():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    title = request.form.get("title", "").strip()
    lat = request.form.get("lat")
    lng = request.form.get("lng")
    if not title or lat is None or lng is None: return jsonify({"error": "title, lat, lng обязательны"}), 400
    duration_hours = max(0.5, min(float(request.form.get("duration_hours", "6")), 48))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()
    profile_res = sb.table("profiles").select("account_type").eq("id", uid).execute()
    acc_type = (profile_res.data[0] if profile_res.data else {}).get("account_type", "person")
    if acc_type == "person": sb.table("spots").delete().eq("owner_id", uid).execute()
    data = {"owner_id": uid, "title": title, "description": request.form.get("description", "").strip(), "lat": float(lat), "lng": float(lng), "visibility": request.form.get("visibility", "public"), "placement_type": request.form.get("placement_type", "geo"), "expires_at": expires_at, "is_live": True}
    photo = request.files.get("photo")
    if photo and photo.filename: data["photo_url"] = upload_to_bucket(sb, "spot-photos", uid, photo)
    res = sb.table("spots").insert(data).execute()
    return jsonify(res.data[0]), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
"""

def write_file(rel_path, content):
    path = BASE_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    print(f"✅ Записан: {rel_path}")

write_file("templates/base.html", base_html)
write_file("templates/map.html", map_html)
write_file("app.py", app_py)
print("\n🎉 Файлы восстановлены!")
print("Теперь выполните в терминале:")
print("git add .")
print('git commit -m "fix: restore html structure and app.py"')
print("git push")