import os, uuid, hmac, hashlib, json, time, urllib.parse
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Не заданы SUPABASE_URL / SUPABASE_ANON_KEY")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
CATEGORIES = ["Бар ", "Клуб ", "Кофейня ", "Ресторан ", "Коворкинг ", "Караоке ", "Спорт ", "Вечеринка ", "Природа ", "Выставка/галерея ", "Другое "]

def get_supabase(access_token=None, refresh_token=None):
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if access_token and refresh_token:
        try: client.auth.set_session(access_token, refresh_token)
        except Exception: client.postgrest.auth(access_token)
    elif access_token: client.postgrest.auth(access_token)
    return client

def verify_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    if not bot_token: return None
    params = dict(urllib.parse.parse_qsl(init_data))
    received_hash = params.pop("hash", "")
    if not received_hash: return None
    data_check_arr = [f"{k}={v}" for k, v in sorted(params.items())]
    data_check_string = "\n".join(data_check_arr)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash): return None
    auth_date = int(params.get("auth_date", 0))
    if time.time() - auth_date > 86400: return None
    try: return json.loads(params.get("user", "{}"))
    except: return None

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # Проверка Bearer токена из Telegram
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                sb = get_supabase(access_token=token)
                sb.table("profiles").select("id").eq("id", session.get("user_id")).single().execute()
                session["access_token"] = token
                return view(*args, **kwargs)
            except: pass

        if "access_token" not in session:
            return jsonify({"error": "unauthorized"}), 401 if request.path.startswith("/api/") else redirect(url_for("login"))
        try:
            sb = get_supabase(session["access_token"], session.get("refresh_token"))
            sb.table("profiles").select("id").eq("id", session["user_id"]).single().execute()
        except Exception:
            session.clear(); flash("Сессия истекла"); return redirect(url_for("login"))
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
    email, password, username = request.form.get("email"," ").strip(), request.form.get("password"," "), request.form.get("username"," ").strip()
    display_name = request.form.get("display_name"," ").strip() or username
    account_type = request.form.get("account_type","person")
    if not email or not password or not username: flash("Заполните все поля"); return redirect(url_for("register"))
    sb = get_supabase()
    try: auth_res = sb.auth.sign_up({"email": email, "password": password})
    except Exception as e: flash(f"Ошибка: {e}"); return redirect(url_for("register"))
    if not auth_res.user: flash("Подтвердите email"); return redirect(url_for("login"))
    if auth_res.session:
        sb2 = get_supabase(auth_res.session.access_token, auth_res.session.refresh_token)
        profile_data = {"id": auth_res.user.id, "username": username, "display_name": display_name, "account_type": account_type}
        if account_type == "organization":
            profile_data["category"] = request.form.get("category","").strip() or None
            profile_data["address"] = request.form.get("address","").strip() or None
            if request.form.get("org_lat") and request.form.get("org_lng"):
                profile_data["lat"], profile_data["lng"] = float(request.form.get("org_lat")), float(request.form.get("org_lng"))
        try: sb2.table("profiles").insert(profile_data).execute()
        except Exception as e: flash(f"Профиль не сохранён: {e}")
        session["access_token"], session["refresh_token"], session["user_id"] = auth_res.session.access_token, auth_res.session.refresh_token, auth_res.user.id
        return redirect(url_for("map_view"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET": return render_template("login.html")
    try:
        res = get_supabase().auth.sign_in_with_password({"email": request.form.get("email"," ").strip(), "password": request.form.get("password"," ")})
        session["access_token"], session["refresh_token"], session["user_id"] = res.session.access_token, res.session.refresh_token, res.user.id
        return redirect(url_for("map_view"))
    except Exception: flash("Неверный email или пароль"); return redirect(url_for("login"))

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("index"))

@app.route("/map")
@login_required
def map_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    profile = sb.table("profiles").select("*").eq("id", session["user_id"]).single().execute()
    return render_template("map.html", profile=profile.data, categories=CATEGORIES)

@app.route("/feed")
@login_required
def feed_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    profile = sb.table("profiles").select("*").eq("id", uid).single().execute().data
    friends_res = sb.table("friendships").select("requester_id, addressee_id").eq("status","accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friend_ids = [uid] + [f["requester_id"] if f["requester_id"] != uid else f["addressee_id"] for f in (friends_res.data or [])]
    spots_res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url)").in_("owner_id", friend_ids).order("created_at", desc=True).limit(50).execute()
    return render_template("feed.html", spots=spots_res.data or [], profile=profile)

@app.route("/messages")
@login_required
def messages_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    profile = sb.table("profiles").select("*").eq("id", session["user_id"]).single().execute()
    return render_template("messages.html", profile=profile.data)

@app.route("/profile/<username>")
@login_required
def profile_view(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    prof_res = sb.table("profiles").select("*").eq("username", username).single().execute()
    if not prof_res.data: return "Пользователь не найден", 404
    profile = prof_res.data
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
    return render_template("profile.html", profile=profile, spots=spots_res.data, is_me=is_me, friend_status=friend_status, tagged_spots=tagged_spots)

@app.route("/friends")
@login_required
def friends_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    incoming = sb.table("friendships").select("*, requester:requester_id(username, display_name, avatar_url)").eq("addressee_id", uid).eq("status","pending").execute()
    accepted = sb.table("friendships").select("*, requester:requester_id(username, display_name, avatar_url), addressee:addressee_id(username, display_name, avatar_url)").eq("status","accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    return render_template("friends.html", incoming=incoming.data, accepted=accepted.data, my_id=uid)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "GET":
        profile = sb.table("profiles").select("*").eq("id", uid).single().execute()
        return render_template("settings.html", profile=profile.data, categories=CATEGORIES)
    form_name = request.form.get("form_name", "profile")
    if form_name == "visibility":
        show_all = request.form.get("show_all_categories") == "on"
        update_data = {"visible_categories": None if show_all else request.form.getlist("visible_categories")}
        try: sb.table("profiles").update(update_data).eq("id", uid).execute(); flash("Фильтр обновлён")
        except Exception as e: flash(f"Ошибка: {e}")
        return redirect(url_for("settings_view"))
    update_data = {"display_name": request.form.get("display_name","").strip(), "bio": request.form.get("bio","").strip(), "location": request.form.get("location","").strip()}
    account_type = request.form.get("account_type", "person")
    if account_type == "organization":
        update_data["category"] = request.form.get("category","").strip() or None
        update_data["address"] = request.form.get("address","").strip() or None
    else:
        age = request.form.get("age")
        update_data["age"] = int(age) if age and age.isdigit() else None
    avatar = request.files.get("avatar")
    if avatar and avatar.filename: update_data["avatar_url"] = upload_to_bucket(sb, "avatars", uid, avatar)
    cover = request.files.get("cover")
    if cover and cover.filename: update_data["cover_url"] = upload_to_bucket(sb, "avatars", uid, cover)
    try: sb.table("profiles").update(update_data).eq("id", uid).execute(); flash("Профиль обновлён")
    except Exception as e: flash(f"Ошибка: {e}")
    profile = sb.table("profiles").select("*").eq("id", uid).single().execute()
    return redirect(url_for("profile_view", username=profile.data["username"]))

--- API ---
@app.route("/api/check-session")
def api_check_session():
    if "access_token" in session and "user_id" in session:
        return jsonify({"logged_in": True, "user_id": session["user_id"]})
    return jsonify({"logged_in": False})

@app.route("/api/telegram-auth", methods=["POST"])
def api_telegram_auth():
    if not TELEGRAM_BOT_TOKEN: return jsonify({"ok": False, "error": "BOT_TOKEN not configured"}), 500
    init_data = (request.json or {}).get("init_data", "")
    if not init_data: return jsonify({"ok": False, "error": "no init_data"}), 400
    
    tg_user = verify_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
    if not tg_user: return jsonify({"ok": False, "error": "invalid signature"}), 403
    
    tg_id = tg_user.get("id")
    tg_username = tg_user.get("username", f"tg_{tg_id}")
    tg_first_name = tg_user.get("first_name", "User")
    tg_last_name = tg_user.get("last_name", "")
    tg_photo_url = tg_user.get("photo_url", "")
    
    # Используем service_role ключ если доступен, иначе anon
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    sb_admin = create_client(SUPABASE_URL, service_key) if service_key else get_supabase()
    
    existing = sb_admin.table("profiles").select("id, username").eq("telegram_id", tg_id).execute()
    
    if existing.data:
        uid = existing.data[0]["id"]
        uname = existing.data[0]["username"]
    else:
        fake_email = f"tg_{tg_id}@telegram.local"
        fake_password = f"tg_{tg_id}_{uuid.uuid4().hex[:16]}"
        try:
            auth_res = sb_admin.auth.admin.create_user({
                "email": fake_email, "password": fake_password, "email_confirm": True,
                "user_metadata": {"telegram_id": tg_id, "telegram_username": tg_username}
            })
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 400
        
        if not auth_res.user: return jsonify({"ok": False, "error": "creation failed"}), 400
        uid = auth_res.user.id
        uname = tg_username
        
        profile_data = {"id": uid, "username": uname, "display_name": tg_first_name + (" "+tg_last_name if tg_last_name else ""), "account_type": "person", "telegram_id": tg_id}
        if tg_photo_url: profile_data["avatar_url"] = tg_photo_url
        try: sb_admin.table("profiles").insert(profile_data).execute()
        except: pass
    
    # Создаём сессию
    try:
        sb_temp = create_client(SUPABASE_URL, service_key) if service_key else get_supabase()
        sb_temp.auth.admin.update_user_by_id(uid, {"password": fake_password})
        sb_client = get_supabase()
        sign_in_res = sb_client.auth.sign_in_with_password({"email": fake_email, "password": fake_password})
        if not sign_in_res.session: return jsonify({"ok": False, "error": "session failed"}), 400
        
        session["access_token"] = sign_in_res.session.access_token
        session["refresh_token"] = sign_in_res.session.refresh_token
        session["user_id"] = uid
        
        return jsonify({"ok": True, "username": uname, "access_token": sign_in_res.session.access_token, "refresh_token": sign_in_res.session.refresh_token, "user_id": uid})
    except Exception as e: return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    now_iso = datetime.now(timezone.utc).isoformat()
    try: sb.table("spots").delete().eq("owner_id", session["user_id"]).lt("expires_at", now_iso).execute()
    except: pass
    res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url), organization:organization_id(username, display_name, category, is_verified)").or_(f"expires_at.is.null,expires_at.gt.{now_iso}").order("created_at", desc=True).execute()
    spots = res.data or []
    profile_res = sb.table("profiles").select("visible_categories").eq("id", session["user_id"]).single().execute()
    preferred = (profile_res.data or {}).get("visible_categories")
    if preferred is not None: spots = [s for s in spots if s.get("owner_id") == session["user_id"] or not s.get("category") or s.get("category") in preferred]
    return jsonify(spots)

@app.route("/api/spots", methods=["POST"])
@login_required
def api_spots_create():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    title, description, lat, lng = request.form.get("title"," ").strip(), request.form.get("description"," ").strip(), request.form.get("lat"), request.form.get("lng")
    visibility, is_live, placement_type = request.form.get("visibility","public"), request.form.get("is_live","true")=="true", request.form.get("placement_type","geo")
    organization_id, category = request.form.get("organization_id") or None, request.form.get("category"," ").strip() or None
    if category and category not in CATEGORIES: category = None
    duration_hours = max(0.5, min(float(request.form.get("duration_hours","6")), 48))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()
    if not title or lat is None or lng is None: return jsonify({"error": "title, lat, lng обязательны"}), 400
    
    profile_res = sb.table("profiles").select("account_type").eq("id", uid).single().execute()
    if (profile_res.data or {}).get("account_type", "person") == "person":
        sb.table("spots").delete().eq("owner_id", uid).execute()
    
    photo_url = upload_to_bucket(sb, "spot-photos", uid, request.files.get("photo")) if request.files.get("photo") and request.files.get("photo").filename else None
    data = {"owner_id": uid, "title": title, "description": description, "lat": float(lat), "lng": float(lng), "visibility": visibility if visibility in ("public","friends") else "public", "is_live": is_live, "placement_type": placement_type, "expires_at": expires_at}
    if photo_url: data["photo_url"] = photo_url
    if organization_id: data["organization_id"] = organization_id
    if category: data["category"] = category
    mood = request.form.get("mood","").strip() or None
    if mood: data["mood"] = mood
    voice_url = request.form.get("voice_url","").strip() or None
    if voice_url: data["voice_url"] = voice_url
    if request.form.get("wave_enabled") == "true":
        wave_hours = max(0.25, min(float(request.form.get("wave_hours","1")), 12))
        data["wave_ends_at"] = (datetime.now(timezone.utc) + timedelta(hours=wave_hours)).isoformat()
        wave_max = request.form.get("wave_max_people")
        if wave_max and wave_max.isdigit(): data["wave_max_people"] = int(wave_max)
    return jsonify(sb.table("spots").insert(data).execute().data[0]), 201

@app.route("/api/spots/<int:spot_id>", methods=["DELETE"])
@login_required
def api_spots_delete(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("spots").delete().eq("id", spot_id).eq("owner_id", session["user_id"]).execute()
    return jsonify({"ok": True})

@app.route("/api/profile/achievements")
@login_required
def api_achievements():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    profile = sb.table("profiles").select("xp, level").eq("id", uid).single().execute().data or {}
    badges = sb.table("user_achievements").select("*").eq("user_id", uid).order("earned_at", desc=True).execute().data or []
    return jsonify({"achievements": badges, "xp": profile.get("xp", 0), "level": profile.get("level", 1)})

@app.route("/api/spots/<int:spot_id>/comments", methods=["GET", "POST"])
@login_required
def api_spot_comments(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "POST":
        text = (request.json or {}).get("text"," ").strip()
        if not text: return jsonify({"error": "Текст обязателен"}), 400
        res = sb.table("spot_comments").insert({"spot_id": spot_id, "user_id": uid, "text": text}).execute()
        return jsonify(res.data[0]), 201
    res = sb.table("spot_comments").select("*, user:user_id(username, display_name, avatar_url)").eq("spot_id", spot_id).order("created_at", desc=False).execute()
    return jsonify(res.data or [])

@app.route("/api/spots/<int:spot_id>/social-proof")
@login_required
def api_spot_social_proof(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    spot = sb.table("spots").select("organization_id").eq("id", spot_id).single().execute().data
    org_id = (spot or {}).get("organization_id")
    if not org_id: return jsonify({"friends_count": 0, "total_today": 0, "friends": []})
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    today_res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url)").eq("organization_id", org_id).gte("created_at", since).execute()
    today_spots = today_res.data or []
    friends_res = sb.table("friendships").select("requester_id, addressee_id").eq("status","accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friend_ids = {f["requester_id"] if f["requester_id"] != uid else f["addressee_id"] for f in (friends_res.data or [])}
    friend_spots = [s for s in today_spots if s.get("owner_id") in friend_ids]
    return jsonify({"friends_count": len(friend_spots), "total_today": len(today_spots), "friends": friend_spots[:6]})

@app.route("/api/spots/<int:spot_id>/collaborators")
@login_required
def api_spot_collaborators(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    res = sb.table("spot_collaborators").select("*, profiles:user_id(username, display_name, avatar_url)").eq("spot_id", spot_id).execute()
    return jsonify(res.data or [])

@app.route("/api/spots/<int:spot_id>/collaborate", methods=["POST"])
@login_required
def api_spot_collaborate(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    try: sb.table("spot_collaborators").insert({"spot_id": spot_id, "user_id": uid}).execute()
    except: pass
    return jsonify({"ok": True})

@app.route("/api/spots/voice", methods=["POST"])
@login_required
def api_spot_voice():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    voice = request.files.get("voice")
    if not voice or not voice.filename: return jsonify({"error": "Файл не передан"}), 400
    url = upload_to_bucket(sb, "voice-notes", uid, voice)
    return jsonify({"url": url})

@app.route("/api/friends_list")
@login_required
def api_friends_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    res = sb.table("friendships").select("requester_id, addressee_id").eq("status","accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friends = []
    for f in (res.data or []):
        fid = f["requester_id"] if f["requester_id"] != uid else f["addressee_id"]
        prof = sb.table("profiles").select("id, username, display_name, avatar_url").eq("id", fid).single().execute()
        if prof.data: friends.append(prof.data)
    return jsonify(friends)

@app.route("/api/messages/<friend_id>", methods=["GET", "POST"])
@login_required
def api_messages(friend_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "POST":
        text = request.json.get("text"," ").strip()
        if not text: return jsonify({"error": "Текст обязателен"}), 400
        sb.table("messages").insert({"sender_id": uid, "receiver_id": friend_id, "text": text}).execute()
        return jsonify({"ok": True}), 201
    res = sb.table("messages").select("*, sender:profiles!sender_id(username, display_name, avatar_url), receiver:profiles!receiver_id(username, display_name, avatar_url)").or_(f"and(sender_id.eq.{uid},receiver_id.eq.{friend_id}),and(sender_id.eq.{friend_id},receiver_id.eq.{uid})").order("created_at", asc=True).execute()
    sb.table("messages").update({"is_read": True}).eq("sender_id", friend_id).eq("receiver_id", uid).eq("is_read", False).execute()
    return jsonify(res.data or [])

@app.route("/api/organizations/search")
@login_required
def api_search_organizations():
    q, lat, lng = request.args.get("q"," ").strip(), request.args.get("lat", type=float), request.args.get("lng", type=float)
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    query = sb.table("profiles").select("id, username, display_name, category, address, avatar_url, is_verified, lat, lng").eq("account_type","organization")
    if q: query = query.ilike("display_name", f"%{q}%")
    orgs = query.limit(30).execute().data or []
    if lat is not None and lng is not None: orgs.sort(key=lambda o: 999999 if o.get("lat") is None else (o["lat"]-lat)**2+(o["lng"]-lng)**2)
    return jsonify(orgs[:8] if lat is not None else orgs[:15])

@app.route("/api/search_users")
@login_required
def api_search_users():
    q = request.args.get("q"," ").strip()
    if not q: return jsonify([])
    return jsonify(get_supabase(session["access_token"], session.get("refresh_token")).table("profiles").select("username, display_name, avatar_url").ilike("username", f"%{q}%").limit(10).execute().data)

if __name__ == "__main__":
    app.run(debug=True, port=5000)