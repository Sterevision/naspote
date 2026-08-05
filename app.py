import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
    g,
)
from dotenv import load_dotenv
from supabase import create_client
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Не заданы SUPABASE_URL / SUPABASE_ANON_KEY в .env")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

if os.environ.get("BEHIND_PROXY", "1") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

secure_cookie = os.environ.get("SESSION_COOKIE_SECURE", "auto")
if secure_cookie == "1":
    app.config["SESSION_COOKIE_SECURE"] = True
elif secure_cookie == "auto" and os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CATEGORIES = [
    "Бар",
    "Клуб",
    "Кофейня",
    "Ресторан",
    "Коворкинг",
    "Караоке",
    "Спорт",
    "Вечеринка",
    "Природа",
    "Выставка/галерея",
    "Другое",
]

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_IMAGE_MB = 8


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, max_length=None):
    value = (value or "").strip()
    if max_length:
        value = value[:max_length]
    return value


def parse_float_or_none(value):
    value = clean_text(value, 100)

    if not value:
        return None

    value = value.replace(",", ".")

    try:
        return float(value)
    except Exception:
        return None


def clean_telegram_username(value):
    value = clean_text(value, 32).lstrip("@")

    if not value:
        return None

    if re.fullmatch(r"[A-Za-z0-9_]{3,32}", value):
        return value

    return None


def clean_phone(value):
    value = clean_text(value, 30)

    if not value:
        return None

    if re.fullmatch(r"[0-9+\-() ]{5,30}", value):
        return value

    return None


def clean_email(value):
    value = clean_text(value, 255).lower()

    if not value:
        return None

    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return value

    return None


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
        access_token = session.get("access_token")
        refresh_token = session.get("refresh_token")
        user_id = session.get("user_id")

        if not access_token or not user_id:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))

        try:
            sb = get_supabase(access_token, refresh_token)
            result = (
                sb.table("profiles")
                .select("*")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )

            if not result.data:
                raise Exception("profile not found")

            g.sb = sb
            g.profile = result.data[0]

        except Exception:
            session.clear()
            flash("Сессия истекла. Войдите заново.")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def read_and_validate_file(file_storage, allowed_extensions, max_mb=8):
    if not file_storage or not file_storage.filename:
        return None

    filename = file_storage.filename
    if "." not in filename:
        raise ValueError("Недопустимый файл")

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_extensions:
        raise ValueError("Можно загружать только изображения")

    data = file_storage.read()
    if len(data) > max_mb * 1024 * 1024:
        raise ValueError("Файл слишком большой. Максимум 8 МБ.")

    return ext, data


def upload_to_bucket(sb, bucket, uid, file_storage, max_mb=8):
    prepared = read_and_validate_file(file_storage, ALLOWED_IMAGE_EXTENSIONS, max_mb)
    if not prepared:
        return None

    ext, data = prepared
    path = f"{uid}/{uuid.uuid4()}.{ext}"

    sb.storage.from_(bucket).upload(
        path,
        data,
        {
            "content-type": file_storage.mimetype or "application/octet-stream",
        },
    )

    return sb.storage.from_(bucket).get_public_url(path)


def get_friendship(sb, user_a, user_b):
    res = (
        sb.table("friendships")
        .select("*")
        .or_(
            f"and(requester_id.eq.{user_a},addressee_id.eq.{user_b}),"
            f"and(requester_id.eq.{user_b},addressee_id.eq.{user_a})"
        )
        .limit(1)
        .execute()
    )

    return res.data[0] if res.data else None


def are_friends_db(sb, user_a, user_b):
    row = get_friendship(sb, user_a, user_b)
    return bool(row and row.get("status") == "accepted")


@app.route("/")
def index():
    if session.get("access_token"):
        return redirect(url_for("map_view"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", categories=CATEGORIES)

    email = clean_text(request.form.get("email"), 255).lower()
    password = request.form.get("password", "")
    username = clean_text(request.form.get("username"), 30)
    display_name = clean_text(request.form.get("display_name"), 80) or username
    account_type = request.form.get("account_type", "person")

    if account_type not in ("person", "organization"):
        account_type = "person"

    if not email or not password or not username:
        flash("Заполните email, username и пароль")
        return redirect(url_for("register"))

    sb = get_supabase()

    try:
        auth_res = sb.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        flash(f"Ошибка регистрации: {e}")
        return redirect(url_for("register"))

    if not auth_res.user:
        flash("Подтвердите email по ссылке в почте")
        return redirect(url_for("login"))

    if not auth_res.session:
        flash("Подтвердите email по ссылке в почте")
        return redirect(url_for("login"))

    sb2 = get_supabase(auth_res.session.access_token, auth_res.session.refresh_token)

    profile_data = {
        "id": auth_res.user.id,
        "username": username,
        "display_name": display_name,
        "account_type": account_type,
    }

    if account_type == "organization":
        profile_data["category"] = clean_text(request.form.get("category"), 50) or None
        profile_data["address"] = clean_text(request.form.get("address"), 200) or None

    try:
        sb2.table("profiles").insert(profile_data).execute()
    except Exception as e:
        flash(f"Профиль не сохранён: {e}")
        return redirect(url_for("login"))

    session["access_token"] = auth_res.session.access_token
    session["refresh_token"] = auth_res.session.refresh_token
    session["user_id"] = auth_res.user.id

    return redirect(url_for("map_view"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = clean_text(request.form.get("email"), 255).lower()
    password = request.form.get("password", "")

    try:
        res = get_supabase().auth.sign_in_with_password(
            {"email": email, "password": password}
        )

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
    map_home = {
        "lat": g.profile.get("home_lat"),
        "lng": g.profile.get("home_lng"),
        "name": g.profile.get("home_location_name"),
    }

    return render_template(
        "map.html",
        profile=g.profile,
        categories=CATEGORIES,
        map_home=map_home,
    )


@app.route("/feed")
@login_required
def feed_view():
    sb = g.sb
    uid = session["user_id"]
    now_iso = utc_now_iso()

    friends_res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    friend_ids = [uid]
    for row in friends_res.data or []:
        friend_id = row["addressee_id"] if row["requester_id"] == uid else row["requester_id"]
        if friend_id not in friend_ids:
            friend_ids.append(friend_id)

    spots_res = (
        sb.table("spots")
        .select("*, owner:owner_id(username, display_name, avatar_url)")
        .in_("owner_id", friend_ids)
        .or_(f"expires_at.is.null,expires_at.gt.{now_iso}")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    return render_template(
        "feed.html",
        profile=g.profile,
        spots=spots_res.data or [],
    )


@app.route("/messages")
@login_required
def messages_view():
    return render_template("messages.html", profile=g.profile)


@app.route("/messages/<username>")
@login_required
def chat_view(username):
    sb = g.sb
    uid = session["user_id"]

    friend_res = (
        sb.table("profiles")
        .select("id, username, display_name, avatar_url")
        .eq("username", username)
        .limit(1)
        .execute()
    )

    if not friend_res.data:
        return "Пользователь не найден", 404

    friend = friend_res.data[0]

    if friend["id"] == uid:
        return redirect(url_for("profile_view", username=username))

    is_friend = are_friends_db(sb, uid, friend["id"])

    return render_template(
        "chat.html",
        profile=g.profile,
        friend=friend,
        is_friend=is_friend,
    )


@app.route("/profile/<username>")
@login_required
def profile_view(username):
    sb = g.sb
    uid = session["user_id"]

    prof_res = (
        sb.table("profiles")
        .select("*")
        .eq("username", username)
        .limit(1)
        .execute()
    )

    if not prof_res.data:
        return "Пользователь не найден", 404

    profile = prof_res.data[0]

    spots_res = (
        sb.table("spots")
        .select("*")
        .eq("owner_id", profile["id"])
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    is_me = profile["id"] == uid
    friend_status = None

    if not is_me:
        row = get_friendship(sb, uid, profile["id"])
        if row and row.get("status") != "declined":
            friend_status = row

    return render_template(
        "profile.html",
        profile=profile,
        spots=spots_res.data or [],
        is_me=is_me,
        friend_status=friend_status,
        my_id=uid,
    )


@app.route("/friends")
@login_required
def friends_view():
    sb = g.sb
    uid = session["user_id"]

    incoming = (
        sb.table("friendships")
        .select("*, requester:requester_id(username, display_name, avatar_url)")
        .eq("addressee_id", uid)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )

    outgoing = (
        sb.table("friendships")
        .select("*, addressee:addressee_id(username, display_name, avatar_url)")
        .eq("requester_id", uid)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )

    accepted = (
        sb.table("friendships")
        .select(
            "*, "
            "requester:requester_id(username, display_name, avatar_url), "
            "addressee:addressee_id(username, display_name, avatar_url)"
        )
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .order("created_at", desc=True)
        .execute()
    )

    return render_template(
        "friends.html",
        profile=g.profile,
        incoming=incoming.data or [],
        outgoing=outgoing.data or [],
        accepted=accepted.data or [],
        my_id=uid,
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    sb = g.sb
    uid = session["user_id"]

    if request.method == "GET":
        return render_template(
            "settings.html",
            profile=g.profile,
            categories=CATEGORIES,
        )

    home_lat = parse_float_or_none(request.form.get("home_lat"))
    home_lng = parse_float_or_none(request.form.get("home_lng"))

    if home_lat is not None and not (-90 <= home_lat <= 90):
        home_lat = None

    if home_lng is not None and not (-180 <= home_lng <= 180):
        home_lng = None

    update_data = {
        "display_name": clean_text(request.form.get("display_name"), 80),
        "bio": clean_text(request.form.get("bio"), 500),
        "location": clean_text(request.form.get("location"), 100),
        "home_lat": home_lat,
        "home_lng": home_lng,
        "home_location_name": clean_text(request.form.get("home_location_name"), 120) or None,
        "telegram_username": clean_telegram_username(request.form.get("telegram_username")),
        "contact_phone": clean_phone(request.form.get("contact_phone")),
        "contact_email": clean_email(request.form.get("contact_email")),
    }

    if g.profile.get("account_type") == "organization":
        update_data["category"] = clean_text(request.form.get("category"), 50) or None
        update_data["address"] = clean_text(request.form.get("address"), 200) or None
    else:
        age = clean_text(request.form.get("age"), 3)
        update_data["age"] = int(age) if age.isdigit() else None

    avatar = request.files.get("avatar")

    try:
        if avatar and avatar.filename:
            avatar_url = upload_to_bucket(
                sb,
                "avatars",
                uid,
                avatar,
                MAX_IMAGE_MB,
            )
            if avatar_url:
                update_data["avatar_url"] = avatar_url

        sb.table("profiles").update(update_data).eq("id", uid).execute()
        flash("Профиль обновлён")

    except ValueError as e:
        flash(str(e))
    except Exception as e:
        flash(f"Ошибка: {e}")

    return redirect(url_for("profile_view", username=g.profile.get("username", "")))


@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list():
    sb = g.sb
    uid = session["user_id"]
    now_iso = utc_now_iso()
    category = clean_text(request.args.get("category"), 50)

    try:
        sb.table("spots").delete().eq("owner_id", uid).lt("expires_at", now_iso).execute()
    except Exception:
        pass

    query = (
        sb.table("spots")
        .select(
            "*, "
            "owner:owner_id(username, display_name, avatar_url), "
            "organization:organization_id(username, display_name, category, is_verified)"
        )
        .or_(f"expires_at.is.null,expires_at.gt.{now_iso}")
        .order("created_at", desc=True)
        .limit(200)
    )

    if category:
        query = query.eq("category", category)

    res = query.execute()
    return jsonify(res.data or [])


@app.route("/api/spots", methods=["POST"])
@login_required
def api_spots_create():
    sb = g.sb
    uid = session["user_id"]

    title = clean_text(request.form.get("title"), 120)
    description = clean_text(request.form.get("description"), 1000)
    category = clean_text(request.form.get("category"), 50)
    visibility = request.form.get("visibility", "public")
    placement_type = request.form.get("placement_type", "geo")

    if not title:
        return jsonify({"error": "Нужно указать заголовок метки"}), 400

    try:
        lat = float(request.form.get("lat"))
        lng = float(request.form.get("lng"))
    except Exception:
        return jsonify({"error": "Некорректные координаты"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "Некорректные координаты"}), 400

    if visibility not in ("public", "friends"):
        visibility = "public"

    if placement_type not in ("geo", "manual"):
        placement_type = "geo"

    if category not in CATEGORIES:
        category = None

    try:
        duration_hours = float(request.form.get("duration_hours", "3"))
    except Exception:
        duration_hours = 3.0

    duration_hours = max(1.0, min(24.0, duration_hours))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()

    try:
        profile_res = (
            sb.table("profiles")
            .select("account_type")
            .eq("id", uid)
            .limit(1)
            .execute()
        )
        acc_type = (profile_res.data[0] if profile_res.data else {}).get("account_type", "person")
    except Exception:
        acc_type = "person"

    try:
        photo_url = None
        photo = request.files.get("photo")

        if photo and photo.filename:
            photo_url = upload_to_bucket(
                sb,
                "spot-photos",
                uid,
                photo,
                MAX_IMAGE_MB,
            )

        if acc_type == "person":
            sb.table("spots").delete().eq("owner_id", uid).execute()

        data = {
            "owner_id": uid,
            "title": title,
            "description": description,
            "lat": lat,
            "lng": lng,
            "visibility": visibility,
            "placement_type": placement_type,
            "expires_at": expires_at,
            "is_live": True,
        }

        if category:
            data["category"] = category

        if photo_url:
            data["photo_url"] = photo_url

        res = sb.table("spots").insert(data).execute()
        return jsonify(res.data[0] if res.data else {}), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Не удалось создать метку: {e}"}), 400


@app.route("/api/spots/<int:spot_id>", methods=["DELETE"])
@login_required
def api_spots_delete(spot_id):
    sb = g.sb
    uid = session["user_id"]

    try:
        sb.table("spots").delete().eq("id", spot_id).eq("owner_id", uid).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/spots/<int:spot_id>/comments", methods=["GET", "POST"])
@login_required
def api_spot_comments(spot_id):
    sb = g.sb
    uid = session["user_id"]

    if request.method == "POST":
        text = clean_text((request.json or {}).get("text"), 500)

        if not text:
            return jsonify({"error": "Текст комментария обязателен"}), 400

        try:
            sb.table("spot_comments").insert(
                {
                    "spot_id": spot_id,
                    "user_id": uid,
                    "text": text,
                }
            ).execute()

            return jsonify({"ok": True}), 201

        except Exception as e:
            return jsonify({"error": str(e)}), 400

    try:
        res = (
            sb.table("spot_comments")
            .select("*, user:user_id(username, display_name, avatar_url)")
            .eq("spot_id", spot_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        return jsonify(res.data or [])

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/friends_list")
@login_required
def api_friends_list():
    sb = g.sb
    uid = session["user_id"]

    res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    friends = []

    for row in res.data or []:
        friend_id = row["addressee_id"] if row["requester_id"] == uid else row["requester_id"]

        prof = (
            sb.table("profiles")
            .select("id, username, display_name, avatar_url")
            .eq("id", friend_id)
            .limit(1)
            .execute()
        )

        if prof.data:
            friends.append(prof.data[0])

    return jsonify(friends)


@app.route("/api/search_users")
@login_required
def api_search_users():
    sb = g.sb
    uid = session["user_id"]
    q = clean_text(request.args.get("q"), 60)

    if not q:
        return jsonify([])

    def search_by_field(field):
        return (
            sb.table("profiles")
            .select("id, username, display_name, avatar_url, account_type")
            .ilike(field, f"%{q}%")
            .neq("id", uid)
            .limit(10)
            .execute()
            .data
            or []
        )

    results = []
    seen = set()

    for item in search_by_field("username") + search_by_field("display_name"):
        if item["id"] not in seen:
            seen.add(item["id"])
            results.append(item)

    return jsonify(results[:20])


@app.route("/api/friends/<username>/add", methods=["POST"])
@login_required
def api_friend_add(username):
    sb = g.sb
    uid = session["user_id"]

    target_res = (
        sb.table("profiles")
        .select("id")
        .eq("username", username)
        .limit(1)
        .execute()
    )

    if not target_res.data:
        return jsonify({"error": "Пользователь не найден"}), 404

    target_id = target_res.data[0]["id"]

    if target_id == uid:
        return jsonify({"error": "Нельзя добавить самого себя"}), 400

    existing = get_friendship(sb, uid, target_id)

    if existing:
        if existing.get("status") == "accepted":
            return jsonify({"ok": True, "status": "accepted"})

        if existing.get("status") == "pending":
            return jsonify(
                {
                    "ok": True,
                    "status": "pending",
                    "friendship_id": existing.get("id"),
                    "incoming_for_me": existing.get("addressee_id") == uid,
                }
            )

        if existing.get("status") == "declined":
            try:
                sb.table("friendships").delete().eq("id", existing["id"]).execute()
            except Exception:
                pass

    try:
        res = (
            sb.table("friendships")
            .insert(
                {
                    "requester_id": uid,
                    "addressee_id": target_id,
                }
            )
            .execute()
        )

        row = res.data[0] if res.data else {}

        return jsonify(
            {
                "ok": True,
                "status": "pending",
                "friendship_id": row.get("id"),
                "incoming_for_me": False,
            }
        ), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/friends/<int:friendship_id>/accept", methods=["POST"])
@login_required
def api_friend_accept(friendship_id):
    sb = g.sb
    uid = session["user_id"]

    try:
        sb.table("friendships").update({"status": "accepted"}).eq(
            "id", friendship_id
        ).eq("addressee_id", uid).execute()

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/friends/<int:friendship_id>/decline", methods=["POST"])
@login_required
def api_friend_decline(friendship_id):
    sb = g.sb
    uid = session["user_id"]

    try:
        sb.table("friendships").delete().eq("id", friendship_id).eq(
            "addressee_id", uid
        ).execute()

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/friends/<int:friendship_id>", methods=["DELETE"])
@login_required
def api_friend_remove(friendship_id):
    sb = g.sb
    uid = session["user_id"]

    try:
        sb.table("friendships").delete().eq("id", friendship_id).or_(
            f"requester_id.eq.{uid},addressee_id.eq.{uid}"
        ).execute()

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/messages/<friend_id>", methods=["GET", "POST"])
@login_required
def api_messages(friend_id):
    sb = g.sb
    uid = session["user_id"]

    try:
        if request.method == "POST":
            if not are_friends_db(sb, uid, friend_id):
                return jsonify({"error": "Писать можно только друзьям"}), 403

            text = ""
            image = None

            if request.mimetype == "multipart/form-data":
                text = clean_text(request.form.get("text"), 2000)
                image = request.files.get("image")
            else:
                payload = request.get_json(silent=True) or {}
                text = clean_text(payload.get("text"), 2000)

            image_url = None

            if image and image.filename:
                try:
                    image_url = upload_to_bucket(
                        sb,
                        "chat-images",
                        uid,
                        image,
                        MAX_IMAGE_MB,
                    )
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            if not text and not image_url:
                return jsonify({"error": "Пустое сообщение"}), 400

            sb.table("messages").insert(
                {
                    "sender_id": uid,
                    "receiver_id": friend_id,
                    "text": text or "",
                    "image_url": image_url,
                }
            ).execute()

            return jsonify({"ok": True}), 201

        res = (
            sb.table("messages")
            .select("id, sender_id, receiver_id, text, image_url, created_at, is_read")
            .or_(
                f"and(sender_id.eq.{uid},receiver_id.eq.{friend_id}),"
                f"and(sender_id.eq.{friend_id},receiver_id.eq.{uid})"
            )
            .order("created_at")
            .limit(500)
            .execute()
        )

        try:
            sb.table("messages").update({"is_read": True}).eq(
                "sender_id", friend_id
            ).eq("receiver_id", uid).eq("is_read", False).execute()
        except Exception:
            pass

        return jsonify(res.data or [])

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/conversations")
@login_required
def api_conversations():
    sb = g.sb
    uid = session["user_id"]

    try:
        res = sb.rpc("get_conversations", {}).execute()
        if isinstance(res.data, list):
            return jsonify(res.data)
    except Exception:
        pass

    friends_res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    conversations = []

    for row in friends_res.data or []:
        friend_id = row["addressee_id"] if row["requester_id"] == uid else row["requester_id"]

        prof_res = (
            sb.table("profiles")
            .select("id, username, display_name, avatar_url")
            .eq("id", friend_id)
            .limit(1)
            .execute()
        )

        if not prof_res.data:
            continue

        item = prof_res.data[0]

        last_res = (
            sb.table("messages")
            .select("text, image_url, created_at, sender_id")
            .or_(
                f"and(sender_id.eq.{uid},receiver_id.eq.{friend_id}),"
                f"and(sender_id.eq.{friend_id},receiver_id.eq.{uid})"
            )
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        unread_res = (
            sb.table("messages")
            .select("id", count="exact")
            .eq("sender_id", friend_id)
            .eq("receiver_id", uid)
            .eq("is_read", False)
            .execute()
        )

        last_message_text = None
        last_message_at = None
        last_message_mine = False

        if last_res.data:
            last = last_res.data[0]
            last_message_text = last.get("text")

            if last.get("image_url") and not last_message_text:
                last_message_text = "🖼️ Фото"

            last_message_at = last.get("created_at")
            last_message_mine = last.get("sender_id") == uid

        item.update(
            {
                "friend_id": friend_id,
                "last_message_text": last_message_text,
                "last_message_at": last_message_at,
                "last_message_mine": last_message_mine,
                "unread_count": unread_res.count or 0,
            }
        )

        conversations.append(item)

    conversations.sort(key=lambda x: x.get("last_message_at") or "", reverse=True)
    return jsonify(conversations)


@app.route("/api/messages/unread_count")
@login_required
def api_unread_count():
    sb = g.sb
    uid = session["user_id"]

    messages_res = (
        sb.table("messages")
        .select("id", count="exact")
        .eq("receiver_id", uid)
        .eq("is_read", False)
        .execute()
    )

    requests_res = (
        sb.table("friendships")
        .select("id", count="exact")
        .eq("addressee_id", uid)
        .eq("status", "pending")
        .execute()
    )

    return jsonify(
        {
            "messages": messages_res.count or 0,
            "friend_requests": requests_res.count or 0,
        }
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )