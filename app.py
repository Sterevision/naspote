import os
import math
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

CATEGORIES = ["Бар", "Клуб", "Кофейня", "Ресторан", "Коворкинг",
              "Караоке", "Спорт", "Вечеринка", "Природа", "Выставка/галерея", "Другое"]


# ---------- helpers ----------

def get_supabase(access_token=None, refresh_token=None):
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if access_token and refresh_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            pass
    if access_token:
        try:
            client.postgrest.auth(access_token)
        except Exception:
            pass
    return client


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "access_token" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        sb = get_supabase(session["access_token"], session.get("refresh_token"))
        try:
            result = sb.table("profiles").select("id").eq("id", session["user_id"]).execute()
            if not result.data:
                raise Exception("profile not found")
        except Exception:
            try:
                refreshed = sb.auth.refresh_session()
                session["access_token"] = refreshed.session.access_token
                session["refresh_token"] = refreshed.session.refresh_token
            except Exception:
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"error": "unauthorized"}), 401
                flash("Сессия истекла. Войдите заново.")
                return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        try:
            sb = get_supabase(session["access_token"], session.get("refresh_token"))
            result = sb.table("profiles").select("is_admin").eq("id", session["user_id"]).execute()
            if not result.data or not result.data[0].get("is_admin"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "forbidden"}), 403
                flash("Доступ запрещён")
                return redirect(url_for("map_view"))
        except Exception:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def upload_to_bucket(sb, bucket, uid, file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    path = f"{uid}/{uuid.uuid4()}.{ext}"
    sb.storage.from_(bucket).upload(path, file_storage.read(),
                                    {"content-type": file_storage.mimetype})
    return sb.storage.from_(bucket).get_public_url(path)


def get_profile(sb, uid):
    res = sb.table("profiles").select("*").eq("id", uid).execute()
    return res.data[0] if res.data else {}


def haversine(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


# ---------- ДОСТИЖЕНИЯ ----------

def compute_badges(sb, uid):
    badges = []
    try:
        spots_res = sb.table("spots") \
            .select("id, category, created_at, audio_url, photo_url, organization_id") \
            .eq("owner_id", uid).execute()
        spots = spots_res.data or []
    except Exception:
        spots = []
    try:
        friends_res = sb.table("friendships").select("id").eq("status", "accepted") \
            .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
        friends_count = len(friends_res.data or [])
    except Exception:
        friends_count = 0

    night = any(parse_iso(s.get("created_at")) and parse_iso(s.get("created_at")).hour < 5 for s in spots)
    art = sum(1 for s in spots if s.get("category") == "Выставка/галерея")
    bars = sum(1 for s in spots if s.get("category") == "Бар")
    audio = any(s.get("audio_url") for s in spots)
    photo = any(s.get("photo_url") for s in spots)
    org = any(s.get("organization_id") for s in spots)

    if night:
        badges.append({"emoji": "🌙", "title": "Ночной житель", "desc": "Отметился с 00:00 до 05:00"})
    if art >= 3:
        badges.append({"emoji": "🎨", "title": "Ценитель искусства", "desc": "3 метки у выставок и галерей"})
    if bars >= 3:
        badges.append({"emoji": "🍸", "title": "Коллекционер баров", "desc": "3 метки в барах"})
    if len(spots) >= 10:
        badges.append({"emoji": "🔥", "title": "В центре событий", "desc": "10 меток на карте"})
    if friends_count >= 3:
        badges.append({"emoji": "🤝", "title": "Социальный", "desc": "3 и больше друзей"})
    if audio:
        badges.append({"emoji": "🎙️", "title": "Голос города", "desc": "Метка с аудио-атмосферой"})
    if photo:
        badges.append({"emoji": "📸", "title": "Фотограф", "desc": "Метка с фото"})
    if org:
        badges.append({"emoji": "🏢", "title": "Исследователь заведений", "desc": "Метка, привязанная к заведению"})
    return badges


# ---------- страницы ----------

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

    signup_meta = {
        "username": username,
        "display_name": display_name,
        "account_type": account_type,
    }
    if account_type == "organization":
        signup_meta["org_category"] = request.form.get("org_category", "").strip() or None
        signup_meta["org_address"] = request.form.get("org_address", "").strip() or None
        signup_meta["org_lat"] = request.form.get("org_lat", "").strip() or None
        signup_meta["org_lng"] = request.form.get("org_lng", "").strip() or None

    sb = get_supabase()
    try:
        auth_res = sb.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": signup_meta},
        })
    except Exception as e:
        flash(f"Ошибка: {e}")
        return redirect(url_for("register"))

    if not auth_res.user:
        flash("Подтвердите email по ссылке в почте")
        return redirect(url_for("login"))

    if auth_res.session:
        sb2 = get_supabase(auth_res.session.access_token, auth_res.session.refresh_token)
        profile_data = {
            "id": auth_res.user.id,
            "username": username,
            "display_name": display_name,
            "account_type": account_type,
        }
        if account_type == "organization":
            profile_data["category"] = request.form.get("org_category", "").strip() or None
            profile_data["address"] = request.form.get("org_address", "").strip() or None
            org_lat = request.form.get("org_lat", "").strip()
            org_lng = request.form.get("org_lng", "").strip()
            if org_lat and org_lng:
                try:
                    profile_data["lat"] = float(org_lat)
                    profile_data["lng"] = float(org_lng)
                except ValueError:
                    pass
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
        res = get_supabase().auth.sign_in_with_password({
            "email": request.form.get("email", "").strip(),
            "password": request.form.get("password", "")
        })
        session["access_token"] = res.session.access_token
        session["refresh_token"] = res.session.refresh_token
        session["user_id"] = res.user.id

        sb2 = get_supabase(res.session.access_token, res.session.refresh_token)
        existing = sb2.table("profiles").select("id").eq("id", res.user.id).execute()
        if not existing.data:
            meta = res.user.user_metadata or {}
            username = meta.get("username") or (res.user.email or "user").split("@")[0]
            profile_data = {
                "id": res.user.id,
                "username": username,
                "display_name": meta.get("display_name") or username,
                "account_type": meta.get("account_type", "person"),
            }
            if profile_data["account_type"] == "organization":
                if meta.get("org_category"):
                    profile_data["category"] = meta["org_category"]
                if meta.get("org_address"):
                    profile_data["address"] = meta["org_address"]
                try:
                    if meta.get("org_lat") and meta.get("org_lng"):
                        profile_data["lat"] = float(meta["org_lat"])
                        profile_data["lng"] = float(meta["org_lng"])
                except ValueError:
                    pass
            try:
                sb2.table("profiles").insert(profile_data).execute()
            except Exception as e:
                flash(f"Не удалось создать профиль: {e}")

        return redirect(url_for("map_view"))
    except Exception:
        flash("Неверный email или пароль")
        return redirect(url_for("login"))


@app.route("/api/auth/magic-link", methods=["POST"])
def api_magic_link():
    email = (request.json or {}).get("email", "").strip()
    if not email:
        return jsonify({"error": "Email обязателен"}), 400
    sb = get_supabase()
    try:
        site_url = os.environ.get("SITE_URL", "https://kartometr.ru")
        sb.auth.sign_in_with_otp({
            "email": email,
            "options": {"email_redirect_to": f"{site_url}/auth/callback"}
        })
        return jsonify({"ok": True, "message": "Ссылка отправлена на " + email})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/auth/session", methods=["POST"])
def api_auth_session():
    data = request.json or {}
    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    if not access_token or not refresh_token:
        return jsonify({"error": "Токены обязательны"}), 400
    try:
        sb = get_supabase(access_token, refresh_token)
        user_res = sb.auth.get_user(access_token)
        if not user_res or not user_res.user:
            return jsonify({"error": "Невалидный токен"}), 401
        session["access_token"] = access_token
        session["refresh_token"] = refresh_token
        session["user_id"] = user_res.user.id
        sb2 = get_supabase(access_token, refresh_token)
        existing = sb2.table("profiles").select("id").eq("id", user_res.user.id).execute()
        if not existing.data:
            meta = user_res.user.user_metadata or {}
            username = meta.get("username") or (user_res.user.email or "user").split("@")[0]
            existing_user = sb2.table("profiles").select("id").eq("username", username).execute()
            if existing_user.data:
                username = username + str(int(datetime.now().timestamp()))[-4:]
            profile_data = {
                "id": user_res.user.id,
                "username": username,
                "display_name": meta.get("display_name") or username,
                "account_type": meta.get("account_type", "person"),
            }
            try:
                sb2.table("profiles").insert(profile_data).execute()
            except Exception as e:
                return jsonify({"error": "Не удалось создать профиль: " + str(e)}), 500
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/auth/callback")
def auth_callback():
    return render_template("auth_callback.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/api/me")
@login_required
def api_me():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    prof = get_profile(sb, session["user_id"])
    return jsonify({
        "id": session["user_id"],
        "username": prof.get("username"),
        "interests": prof.get("interests") or [],
    })


@app.route("/api/own-spots")
@login_required
def api_own_spots():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    profile = get_profile(sb, uid)
    my_interests = profile.get("interests") or []
    if not my_interests:
        return jsonify([])
    friends_res = sb.table("friendships").select("requester_id, addressee_id") \
        .eq("status", "accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friend_ids = [uid] + [f["requester_id"] if f["requester_id"] != uid else f["addressee_id"]
                          for f in (friends_res.data or [])]
    ppl_res = sb.table("profiles").select("id").neq("id", uid) \
        .overlaps("interests", my_interests).limit(100).execute()
    ppl_ids = [p["id"] for p in (ppl_res.data or []) if p["id"] not in friend_ids]
    if not ppl_ids:
        return jsonify([])
    res = sb.table("spots") \
        .select("*, owner:owner_id(username, display_name, avatar_url)") \
        .in_("owner_id", ppl_ids).eq("visibility", "public") \
        .order("created_at", desc=True).limit(20).execute()
    return jsonify(res.data or [])


@app.route("/map")
@login_required
def map_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    result = sb.table("profiles").select("*").eq("id", session["user_id"]).execute()
    if not result.data:
        session.clear()
        return redirect(url_for("login"))
    profile = result.data[0]
    map_home = {
        "lat": profile.get("home_lat"),
        "lng": profile.get("home_lng"),
        "name": profile.get("home_location_name"),
    }
    return render_template("map.html", profile=profile, categories=CATEGORIES, map_home=map_home)


@app.route("/feed")
@login_required
def feed_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    profile = get_profile(sb, uid)
    friends_res = sb.table("friendships").select("requester_id, addressee_id") \
        .eq("status", "accepted") \
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friend_ids = [uid] + [f["requester_id"] if f["requester_id"] != uid else f["addressee_id"]
                          for f in (friends_res.data or [])]
    spots_res = sb.table("spots") \
        .select("*, owner:owner_id(username, display_name, avatar_url)") \
        .in_("owner_id", friend_ids) \
        .order("created_at", desc=True).limit(50).execute()

    return render_template("feed.html", spots=spots_res.data or [], profile=profile)


@app.route("/messages")
@login_required
def messages_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    profile = get_profile(sb, session["user_id"])
    return render_template("messages.html", profile=profile)


@app.route("/messages/<username>")
@login_required
def chat_view(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    profile = get_profile(sb, session["user_id"])
    friend_res = sb.table("profiles").select("id, username, display_name, avatar_url") \
        .eq("username", username).execute()
    if not friend_res.data:
        return "Пользователь не найден", 404
    friend = friend_res.data[0]
    fs = sb.table("friendships").select("id").eq("status", "accepted").or_(
        f"and(requester_id.eq.{session['user_id']},addressee_id.eq.{friend['id']}),"
        f"and(requester_id.eq.{friend['id']},addressee_id.eq.{session['user_id']})"
    ).execute()
    is_friend = bool(fs.data)
    return render_template("chat.html", profile=profile, friend=friend, is_friend=is_friend)


@app.route("/profile/<username>")
@login_required
def profile_view(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    prof_res = sb.table("profiles").select("*").eq("username", username).execute()
    if not prof_res.data:
        return "Пользователь не найден", 404
    profile = prof_res.data[0]
    spots_res = sb.table("spots").select("*").eq("owner_id", profile["id"]) \
        .order("created_at", desc=True).execute()
    tagged_spots = []
    if profile.get("account_type") == "organization":
        tagged_res = sb.table("spots") \
            .select("*, owner:owner_id(username, display_name, avatar_url)") \
            .eq("organization_id", profile["id"]) \
            .order("created_at", desc=True).execute()
        tagged_spots = tagged_res.data or []
    is_me = profile["id"] == session["user_id"]
    friend_status = None
    if not is_me:
        f = sb.table("friendships").select("*").or_(
            f"and(requester_id.eq.{session['user_id']},addressee_id.eq.{profile['id']}),"
            f"and(requester_id.eq.{profile['id']},addressee_id.eq.{session['user_id']})").execute()
        if f.data:
            friend_status = f.data[0]
    my_profile = get_profile(sb, session["user_id"])
    is_admin = bool(my_profile.get("is_admin"))

    badges = compute_badges(sb, profile["id"])

    new_claims = 0
    if is_me and profile.get("account_type") == "organization":
        try:
            my_deals = sb.table("flash_deals").select("id").eq("org_id", profile["id"]).execute()
            deal_ids = [d["id"] for d in (my_deals.data or [])]
            if deal_ids:
                qc = sb.table("flash_deal_claims").select("id", count="exact").in_("deal_id", deal_ids)
                if profile.get("deals_seen_at"):
                    qc = qc.gt("created_at", profile["deals_seen_at"])
                new_claims = qc.execute().count or 0
            sb.table("profiles").update({"deals_seen_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", profile["id"]).execute()
        except Exception:
            new_claims = 0

    org_stats = None
    if profile.get("account_type") == "organization":
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        spot_ids = [s["id"] for s in tagged_spots]
        unique_people = set(s.get("owner_id") for s in tagged_spots if s.get("owner_id"))
        comments_count = 0
        reactions_count = 0
        if spot_ids:
            try:
                c_res = sb.table("spot_comments").select("id", count="exact") \
                    .in_("spot_id", spot_ids).execute()
                comments_count = c_res.count or 0
            except Exception:
                comments_count = 0
            try:
                r_res = sb.table("spot_reactions").select("id", count="exact") \
                    .in_("spot_id", spot_ids).execute()
                reactions_count = r_res.count or 0
            except Exception:
                reactions_count = 0
        org_stats = {
            "total": len(tagged_spots),
            "today": sum(1 for s in tagged_spots
                         if parse_iso(s.get("created_at")) and parse_iso(s.get("created_at")) >= today_start),
            "week": sum(1 for s in tagged_spots
                        if parse_iso(s.get("created_at")) and parse_iso(s.get("created_at")) >= week_start),
            "people": len(unique_people),
            "comments": comments_count,
            "reactions": reactions_count,
        }

    return render_template("profile.html", profile=profile, spots=spots_res.data,
                           is_me=is_me, friend_status=friend_status,
                           tagged_spots=tagged_spots, my_id=session["user_id"],
                           org_stats=org_stats, is_admin=is_admin, badges=badges,
                           new_claims=new_claims)


@app.route("/friends")
@login_required
def friends_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    try:
        sb.table("profiles").update({
            "friends_seen_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", uid).execute()
    except Exception:
        pass
    incoming = sb.table("friendships") \
        .select("*, requester:requester_id(username, display_name, avatar_url)") \
        .eq("addressee_id", uid).eq("status", "pending").execute()
    outgoing = sb.table("friendships") \
        .select("*, addressee:addressee_id(username, display_name, avatar_url)") \
        .eq("requester_id", uid).eq("status", "pending").execute()
    accepted = sb.table("friendships") \
        .select("*, requester:requester_id(username, display_name, avatar_url), "
                "addressee:addressee_id(username, display_name, avatar_url)") \
        .eq("status", "accepted") \
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    profile = get_profile(sb, uid)
    return render_template("friends.html", incoming=incoming.data or [],
                           outgoing=outgoing.data or [],
                           accepted=accepted.data or [], my_id=uid, profile=profile)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]

    if request.method == "GET":
        profile = get_profile(sb, uid)
        return render_template("settings.html", profile=profile, categories=CATEGORIES)

    profile = get_profile(sb, uid)
    update_data = {
        "display_name": request.form.get("display_name", "").strip(),
        "bio": request.form.get("bio", "").strip(),
        "location": request.form.get("location", "").strip(),
    }
    update_data["telegram_username"] = request.form.get("telegram_username", "").strip() or None
    update_data["contact_phone"] = request.form.get("contact_phone", "").strip() or None
    update_data["contact_email"] = request.form.get("contact_email", "").strip() or None
    update_data["home_location_name"] = request.form.get("home_location_name", "").strip() or None

    update_data["interests"] = request.form.getlist("interests")

    hlat = request.form.get("home_lat", "").strip()
    hlng = request.form.get("home_lng", "").strip()
    if hlat and hlng:
        try:
            update_data["home_lat"] = float(hlat)
            update_data["home_lng"] = float(hlng)
        except ValueError:
            pass

    account_type = profile.get("account_type", "person")
    if account_type == "organization":
        update_data["category"] = request.form.get("org_category", "").strip() or None
        update_data["address"] = request.form.get("org_address", "").strip() or None
        olat = request.form.get("org_lat", "").strip()
        olng = request.form.get("org_lng", "").strip()
        if olat and olng:
            try:
                update_data["lat"] = float(olat)
                update_data["lng"] = float(olng)
            except ValueError:
                pass
    else:
        age = request.form.get("age")
        update_data["age"] = int(age) if age and age.isdigit() else None

    avatar = request.files.get("avatar")
    if avatar and avatar.filename:
        update_data["avatar_url"] = upload_to_bucket(sb, "avatars", uid, avatar)

    try:
        sb.table("profiles").update(update_data).eq("id", uid).execute()
        flash("Профиль обновлён")
    except Exception as e:
        flash(f"Ошибка: {e}")

    return redirect(url_for("profile_view", username=profile.get("username", "")))


# ---------- АДМИН-ПАНЕЛЬ ----------

@app.route("/admin")
@admin_required
def admin_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    profile = get_profile(sb, session["user_id"])
    return render_template("admin.html", profile=profile)


@app.route("/api/admin/users")
@admin_required
def api_admin_users():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    q = request.args.get("q", "").strip().lower()
    try:
        res = sb.table("profiles") \
            .select("id, username, display_name, avatar_url, account_type, category, "
                    "is_verified, is_admin, created_at") \
            .order("created_at", desc=True).limit(200).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    users = res.data or []
    if q:
        users = [u for u in users
                 if q in (u.get("username") or "").lower()
                 or q in (u.get("display_name") or "").lower()]
    return jsonify(users)


@app.route("/api/admin/orgs/<user_id>/verify", methods=["POST"])
@admin_required
def api_admin_verify_org(user_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    value = (request.json or {}).get("value", True)
    try:
        sb.table("profiles").update({"is_verified": bool(value)}) \
            .eq("id", user_id).eq("account_type", "organization").execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "is_verified": bool(value)})


@app.route("/api/admin/users/<user_id>/admin", methods=["POST"])
@admin_required
def api_admin_toggle_admin(user_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    value = (request.json or {}).get("value", True)
    if user_id == session["user_id"] and not value:
        return jsonify({"error": "Нельзя снять админку с самого себя"}), 400
    try:
        sb.table("profiles").update({"is_admin": bool(value)}) \
            .eq("id", user_id).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "is_admin": bool(value)})


@app.route("/api/admin/spots")
@admin_required
def api_admin_spots():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    try:
        res = sb.table("spots") \
            .select("*, owner:owner_id(username, display_name)") \
            .order("created_at", desc=True).limit(200).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(res.data or [])


@app.route("/api/admin/spots/<int:spot_id>", methods=["DELETE"])
@admin_required
def api_admin_delete_spot(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    try:
        sb.table("spots").delete().eq("id", spot_id).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


# ---------- API: метки ----------

@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        sb.table("spots").delete().eq("owner_id", session["user_id"]) \
            .lt("expires_at", now_iso).execute()
    except Exception:
        pass
    res = sb.table("spots") \
        .select("*, owner:owner_id(username, display_name, avatar_url, interests), "
                "organization:organization_id(username, display_name, category, is_verified)") \
        .or_(f"expires_at.is.null,expires_at.gt.{now_iso}") \
        .order("created_at", desc=True).execute()
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

    profile = get_profile(sb, uid)
    acc_type = profile.get("account_type", "person")
    if acc_type == "person":
        sb.table("spots").delete().eq("owner_id", uid).execute()

    data = {
        "owner_id": uid,
        "title": title,
        "description": request.form.get("description", "").strip(),
        "lat": float(lat),
        "lng": float(lng),
        "visibility": request.form.get("visibility", "public"),
        "placement_type": request.form.get("placement_type", "geo"),
        "expires_at": expires_at,
        "is_live": True,
        "category": request.form.get("category", "").strip() or None,
    }

    organization_id = request.form.get("organization_id", "").strip()
    if organization_id:
        data["organization_id"] = organization_id

    photo = request.files.get("photo")
    if photo and photo.filename:
        data["photo_url"] = upload_to_bucket(sb, "spot-photos", uid, photo)

    audio = request.files.get("audio")
    if audio and audio.filename:
        data["audio_url"] = upload_to_bucket(sb, "spot-audio", uid, audio)

    try:
        res = sb.table("spots").insert(data).execute()
        return jsonify(res.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/spots/<int:spot_id>", methods=["DELETE"])
@login_required
def api_spots_delete(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("spots").delete().eq("id", spot_id).eq("owner_id", session["user_id"]).execute()
    return jsonify({"ok": True})


@app.route("/api/spots/<int:spot_id>/comments", methods=["GET", "POST"])
@login_required
def api_spot_comments(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]

    if request.method == "POST":
        text = (request.json or {}).get("text", "").strip()
        if not text:
            return jsonify({"error": "Текст обязателен"}), 400
        try:
            sb.table("spot_comments").insert({"spot_id": spot_id, "user_id": uid, "text": text}).execute()
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True}), 201

    res = sb.table("spot_comments") \
        .select("*, user:user_id(username, display_name, avatar_url)") \
        .eq("spot_id", spot_id).order("created_at").execute()
    return jsonify(res.data or [])


# ---------- API: организации ----------

@app.route("/api/organizations")
@login_required
def api_organizations_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    res = sb.table("profiles") \
        .select("id, username, display_name, avatar_url, category, address, lat, lng, is_verified") \
        .eq("account_type", "organization") \
        .not_.is_("lat", "null") \
        .not_.is_("lng", "null") \
        .execute()
    orgs = res.data or []
    cat = request.args.get("category", "").strip()
    if cat:
        orgs = [o for o in orgs if o.get("category") == cat]
    return jsonify(orgs)


@app.route("/api/organizations/search")
@login_required
def api_organizations_search():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    q = request.args.get("q", "").strip().lower()
    try:
        lat = float(request.args.get("lat", 0))
        lng = float(request.args.get("lng", 0))
    except ValueError:
        lat, lng = 0, 0

    res = sb.table("profiles") \
        .select("id, username, display_name, category, address, lat, lng") \
        .eq("account_type", "organization") \
        .not_.is_("lat", "null") \
        .not_.is_("lng", "null") \
        .execute()
    orgs = res.data or []
    out = []
    for o in orgs:
        name = (o.get("display_name") or "").lower()
        uname = (o.get("username") or "").lower()
        cat = (o.get("category") or "").lower()
        if q and not (q in name or q in uname or q in cat):
            continue
        try:
            dist = haversine(lat, lng, float(o["lat"]), float(o["lng"]))
        except Exception:
            dist = 99999
        o["distance_km"] = round(dist, 2)
        out.append(o)
    out.sort(key=lambda x: x["distance_km"])
    return jsonify(out[:10])


# ---------- API: друзья / сообщения ----------

@app.route("/api/friends_list")
@login_required
def api_friends_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    res = sb.table("friendships").select("requester_id, addressee_id") \
        .eq("status", "accepted") \
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friends = []
    for f in (res.data or []):
        fid = f["requester_id"] if f["requester_id"] != uid else f["addressee_id"]
        prof = sb.table("profiles").select("id, username, display_name, avatar_url") \
            .eq("id", fid).execute()
        if prof.data:
            friends.append(prof.data[0])
    return jsonify(friends)


@app.route("/api/users/search")
@login_required
def api_users_search():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    q = request.args.get("q", "").strip()
    if q.startswith("@"):
        q = q[1:]
    if len(q) < 2:
        return jsonify([])
    fields = "id, username, display_name, avatar_url, account_type"
    try:
        res1 = sb.table("profiles").select(fields).ilike("username", f"%{q}%").limit(10).execute()
        res2 = sb.table("profiles").select(fields).ilike("display_name", f"%{q}%").limit(10).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    merged = {}
    for row in (res1.data or []) + (res2.data or []):
        merged[row["id"]] = row
    people = [p for p in merged.values() if p["id"] != uid]
    people.sort(key=lambda p: (p.get("username") or "").lower())
    return jsonify(people[:10])


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

    existing = sb.table("friendships").select("*").or_(
        f"and(requester_id.eq.{uid},addressee_id.eq.{target_id}),"
        f"and(requester_id.eq.{target_id},addressee_id.eq.{uid})"
    ).execute()
    if existing.data:
        row = existing.data[0]
        if row["status"] == "accepted":
            return jsonify({"ok": True, "status": "accepted"})
        if row["requester_id"] == target_id:
            sb.table("friendships").update({"status": "accepted"}) \
                .eq("id", row["id"]).execute()
            return jsonify({"ok": True, "status": "accepted"})
        return jsonify({"ok": True, "status": "pending"})

    try:
        res = sb.table("friendships").insert({"requester_id": uid, "addressee_id": target_id}).execute()
    except Exception:
        return jsonify({"error": "Не удалось отправить заявку"}), 400
    return jsonify({"ok": True, "status": "pending", "friendship": res.data[0]}), 201


@app.route("/api/friends/<int:friendship_id>/accept", methods=["POST"])
@login_required
def api_friend_accept(friendship_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").update({"status": "accepted"}) \
        .eq("id", friendship_id).eq("addressee_id", session["user_id"]).execute()
    return jsonify({"ok": True})


@app.route("/api/friends/<int:friendship_id>/decline", methods=["POST"])
@login_required
def api_friend_decline(friendship_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").delete().eq("id", friendship_id) \
        .eq("addressee_id", session["user_id"]).execute()
    return jsonify({"ok": True})


@app.route("/api/friends/<int:friendship_id>", methods=["DELETE"])
@login_required
def api_friend_remove(friendship_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").delete().eq("id", friendship_id) \
        .or_(f"requester_id.eq.{session['user_id']},addressee_id.eq.{session['user_id']}").execute()
    return jsonify({"ok": True})


@app.route("/api/messages/<friend_id>", methods=["GET", "POST"])
@login_required
def api_messages(friend_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]

    if request.method == "POST":
        image = request.files.get("image")
        if image or request.form:
            text = request.form.get("text", "").strip()
        else:
            text = (request.get_json(silent=True) or {}).get("text", "").strip()

        if not text and not (image and image.filename):
            return jsonify({"error": "Сообщение не может быть пустым"}), 400

        insert_data = {"sender_id": uid, "receiver_id": friend_id}
        if text:
            insert_data["text"] = text
        if image and image.filename:
            insert_data["image_url"] = upload_to_bucket(sb, "chat-images", uid, image)

        try:
            sb.table("messages").insert(insert_data).execute()
        except Exception:
            return jsonify({"error": "Не удалось отправить. Возможно, вы ещё не друзья."}), 400
        return jsonify({"ok": True}), 201

    res = sb.table("messages").select("*") \
        .or_(f"and(sender_id.eq.{uid},receiver_id.eq.{friend_id}),"
             f"and(sender_id.eq.{friend_id},receiver_id.eq.{uid})") \
        .order("created_at").execute()
    sb.table("messages").update({"is_read": True}) \
        .eq("sender_id", friend_id).eq("receiver_id", uid).eq("is_read", False).execute()
    return jsonify(res.data or [])


@app.route("/api/conversations")
@login_required
def api_conversations():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    try:
        res = sb.rpc("get_conversations", {}).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(res.data or [])


@app.route("/api/messages/unread_count")
@login_required
def api_unread_count():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    res = sb.table("messages").select("id", count="exact") \
        .eq("receiver_id", uid).eq("is_read", False).execute()
    profile = get_profile(sb, uid)
    seen_at = profile.get("friends_seen_at")
    q = sb.table("friendships").select("id", count="exact") \
        .eq("addressee_id", uid).eq("status", "pending")
    if seen_at:
        q = q.gt("created_at", seen_at)
    incoming = q.execute()
    return jsonify({"messages": res.count or 0, "friend_requests": incoming.count or 0})


# ---------- API: реакции на метки ----------

@app.route("/api/spots/<int:spot_id>/reactions", methods=["GET"])
@login_required
def api_spot_reactions_get(spot_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    try:
        res = sb.rpc("get_spot_reactions", {"p_spot_id": spot_id}).execute()
        return jsonify(res.data or [])
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/spots/<int:spot_id>/reactions/<emoji>", methods=["POST", "DELETE"])
@login_required
def api_spot_reaction_toggle(spot_id, emoji):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]

    valid_emojis = ['\U0001F525', '❤️', '\U0001F602', '\U0001F389']
    if emoji not in valid_emojis:
        return jsonify({"error": "Недопустимая реакция"}), 400

    if request.method == "POST":
        try:
            sb.table("spot_reactions").insert({
                "spot_id": spot_id,
                "user_id": uid,
                "emoji": emoji
            }).execute()
            return jsonify({"ok": True, "action": "added"}), 201
        except Exception:
            return jsonify({"ok": True, "action": "already_exists"})

    else:
        try:
            sb.table("spot_reactions").delete() \
                .eq("spot_id", spot_id) \
                .eq("user_id", uid) \
                .eq("emoji", emoji).execute()
            return jsonify({"ok": True, "action": "removed"})
        except Exception as e:
            return jsonify({"error": str(e)}), 400


# ---------- FLASH DEALS (B2B) ----------

@app.route("/api/flash-deals", methods=["GET"])
@login_required
def api_flash_deals_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    org_id = request.args.get("org_id")
    q = sb.table("flash_deals").select("*").order("created_at", desc=True)
    if org_id:
        q = q.eq("org_id", org_id)
    else:
        q = q.eq("active", True)
    res = q.execute()
    deals = res.data or []
    if deals:
        ids = [d["id"] for d in deals]
        claims = sb.table("flash_deal_claims").select("deal_id").in_("deal_id", ids).execute()
        counts = {}
        for c in (claims.data or []):
            counts[c["deal_id"]] = counts.get(c["deal_id"], 0) + 1
        for d in deals:
            d["claimed"] = counts.get(d["id"], 0)
    return jsonify(deals)


@app.route("/api/flash-deals", methods=["POST"])
@login_required
def api_flash_deals_create():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    prof = get_profile(sb, uid)
    if prof.get("account_type") != "organization":
        return jsonify({"error": "Только заведения могут создавать флеш-дилы"}), 403
    data = request.json or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Нужен заголовок"}), 400
    insert = {
        "org_id": uid,
        "title": title,
        "description": (data.get("description") or "").strip(),
        "total_slots": int(data.get("total_slots") or 10),
        "claimed": 0,
        "active": True,
    }
    if data.get("ends_at"):
        insert["ends_at"] = data["ends_at"]
    res = sb.table("flash_deals").insert(insert).execute()
    return jsonify(res.data[0]), 201


@app.route("/api/flash-deals/<int:deal_id>", methods=["DELETE"])
@login_required
def api_flash_deals_delete(deal_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("flash_deals").delete().eq("id", deal_id).eq("org_id", session["user_id"]).execute()
    return jsonify({"ok": True})


@app.route("/api/flash-deals/<int:deal_id>/claim", methods=["POST"])
@login_required
def api_flash_deals_claim(deal_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    deal = sb.table("flash_deals").select("*").eq("id", deal_id).execute()
    if not deal.data:
        return jsonify({"error": "Дил не найден"}), 404
    d = deal.data[0]
    if not d.get("active"):
        return jsonify({"error": "Дил завершён"}), 400
    if d.get("ends_at") and parse_iso(d["ends_at"]) and parse_iso(d["ends_at"]) < datetime.now(timezone.utc):
        return jsonify({"error": "Время вышло"}), 400
    cur = sb.table("flash_deal_claims").select("id", count="exact").eq("deal_id", deal_id).execute()
    claimed = cur.count or 0
    if claimed >= (d.get("total_slots") or 0):
        return jsonify({"error": "Места закончились"}), 400
    already = sb.table("flash_deal_claims").select("id").eq("deal_id", deal_id).eq("user_id", uid).execute()
    if already.data:
        return jsonify({"error": "Вы уже участвуете"}), 400
    try:
        sb.table("flash_deal_claims").insert({"deal_id": deal_id, "user_id": uid}).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "claimed": claimed + 1})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)