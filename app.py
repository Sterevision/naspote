import os
import re
import uuid
import logging
import logging.handlers
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
)
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from supabase import create_client
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()


# =========================================================
# LOGGING SETUP
# =========================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.environ.get("LOG_FILE", "").strip()

logger = logging.getLogger("kartometr")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# Консольный вывод
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s: %(message)s"
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Файловый вывод (если указан LOG_FILE)
if LOG_FILE:
    try:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(module)s:%(lineno)d] %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        logger.info("File logging enabled: %s", LOG_FILE)
    except Exception as e:
        logger.warning("Could not set up file logging: %s", e)


# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Не заданы SUPABASE_URL / SUPABASE_ANON_KEY в .env")

if not FLASK_SECRET_KEY:
    raise RuntimeError("Не задан FLASK_SECRET_KEY в .env")


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
)

secure_mode = os.environ.get("SESSION_COOKIE_SECURE", "auto").strip().lower()

if secure_mode == "auto":
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("FLASK_ENV", "development").strip().lower() == "production"
    )
else:
    app.config["SESSION_COOKIE_SECURE"] = secure_mode in ("1", "true", "yes", "on")


# Reverse proxy support
behind_proxy = os.environ.get("BEHIND_PROXY", "1").strip().lower() in ("1", "true", "yes", "on")

if behind_proxy:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
    )


# =========================================================
# RATE LIMITING
# =========================================================

rate_limits_enabled = os.environ.get("RATE_LIMITS_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")

default_limits = []

if rate_limits_enabled:
    default_limits = [
        "600 per hour",
        "180 per minute",
    ]

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=default_limits,
    storage_uri="memory://",
)

if rate_limits_enabled:
    @limiter.request_filter
    def exempt_static_files():
        return request.endpoint == "static"


def rate_limit(limit_value: str):
    if rate_limits_enabled:
        return limiter.limit(limit_value)

    def decorator(func):
        return func

    return decorator


# =========================================================
# CSRF PROTECTION
# =========================================================

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def same_origin(left: str, right: str) -> bool:
    try:
        left_parts = urlsplit(left)
        right_parts = urlsplit(right)

        return (
            left_parts.scheme == right_parts.scheme
            and left_parts.netloc == right_parts.netloc
        )
    except Exception:
        return False


@app.before_request
def csrf_protect():
    if request.method in CSRF_SAFE_METHODS:
        return

    origin = (request.headers.get("Origin") or "").strip()
    referer = (request.headers.get("Referer") or "").strip()
    base_url = request.host_url.rstrip("/")

    if origin and same_origin(origin, base_url):
        return

    if referer and same_origin(referer, base_url):
        return

    csrf_mode = os.environ.get("CSRF_STRICT", "auto").strip().lower()

    if csrf_mode == "auto":
        strict = os.environ.get("FLASK_ENV", "development").strip().lower() == "production"
    else:
        strict = csrf_mode in ("1", "true", "yes", "on")

    if origin or referer or strict:
        logger.warning(
            "CSRF blocked: method=%s path=%s origin=%s referer=%s",
            request.method,
            request.path,
            origin,
            referer,
        )

        if request.path.startswith("/api/"):
            return jsonify({"error": "CSRF check failed"}), 403

        return "CSRF check failed", 403


# =========================================================
# REQUEST LOGGING
# =========================================================

@app.before_request
def log_request_info():
    logger.info(
        "Request: %s %s from %s",
        request.method,
        request.path,
        request.remote_addr or "unknown",
    )


@app.after_request
def log_response_info(response):
    logger.info(
        "Response: %s %s -> %s",
        request.method,
        request.path,
        response.status_code,
    )
    return response


# =========================================================
# APP CONSTANTS
# =========================================================

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

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


# =========================================================
# EXCEPTIONS
# =========================================================

class ValidationError(Exception):
    pass


class UploadError(Exception):
    pass


# =========================================================
# UPLOAD RULES
# =========================================================

UPLOAD_RULES = {
    "avatars": (
        {"jpg", "jpeg", "png", "webp"},
        5 * 1024 * 1024,
    ),
    "spot-photos": (
        {"jpg", "jpeg", "png", "webp"},
        10 * 1024 * 1024,
    ),
    "voice-notes": (
        {"webm", "mp3", "m4a", "ogg"},
        15 * 1024 * 1024,
    ),
}

MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "webm": "audio/webm",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
}


# =========================================================
# HELPERS
# =========================================================

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.isoformat()


def parse_iso_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_text(value, max_length=None, field_name="Значение") -> str:
    text = "" if value is None else str(value).strip()

    if max_length is not None and len(text) > max_length:
        raise ValidationError(f"{field_name}: слишком длинное значение")

    return text


def parse_float(value, field_name="Число", default=None) -> float:
    raw = "" if value is None else str(value).strip()

    if not raw:
        if default is None:
            raise ValidationError(f"{field_name}: обязательно")

        return float(default)

    try:
        return float(raw)
    except ValueError:
        raise ValidationError(f"{field_name}: должно быть числом")


def clamp_number(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def sanitize_like(value: str) -> str:
    value = value or ""
    value = re.sub(r"[%_\\,()]", " ", value)
    return value.strip()


def is_safe_voice_url(url: str, user_id: str) -> bool:
    if not url:
        return False

    base = SUPABASE_URL.rstrip("/")
    prefix = f"{base}/storage/v1/object/public/voice-notes/{user_id}/"
    return url.startswith(prefix)


# =========================================================
# SUPABASE CLIENT
# =========================================================

def create_supabase_client():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def set_client_tokens(client, access_token=None, refresh_token=None):
    if access_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            logger.debug("Не удалось вызвать auth.set_session", exc_info=True)

        try:
            client.postgrest.auth(access_token)
        except Exception:
            logger.debug("Не удалось вызвать postgrest.auth", exc_info=True)

    return client


def get_sb():
    client = create_supabase_client()
    return set_client_tokens(
        client,
        session.get("access_token"),
        session.get("refresh_token"),
    )


def refresh_sb():
    refresh_token = session.get("refresh_token")

    if not refresh_token:
        raise ValidationError("Нет refresh token")

    client = create_supabase_client()
    refreshed = client.auth.refresh_session(refresh_token)

    new_session = getattr(refreshed, "session", None) or refreshed
    access_token = getattr(new_session, "access_token", None)
    new_refresh_token = getattr(new_session, "refresh_token", None) or refresh_token

    if not access_token:
        raise ValidationError("Не удалось обновить сессию")

    session.permanent = True
    session["access_token"] = access_token
    session["refresh_token"] = new_refresh_token

    user = getattr(refreshed, "user", None)
    if user and getattr(user, "id", None):
        session["user_id"] = user.id

    return set_client_tokens(client, access_token, new_refresh_token)


def persist_tokens(access_token: str, refresh_token: str, user_id=None):
    session.permanent = True
    session["access_token"] = access_token
    session["refresh_token"] = refresh_token

    if user_id:
        session["user_id"] = user_id


# =========================================================
# AUTH DECORATOR
# =========================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        is_api = request.path.startswith("/api/")

        if "access_token" not in session or "user_id" not in session:
            if is_api:
                return jsonify({"error": "unauthorized"}), 401

            return redirect(url_for("login"))

        def load_profile(sb):
            return (
                sb.table("profiles")
                .select("*")
                .eq("id", session.get("user_id"))
                .limit(1)
                .execute()
            )

        try:
            sb = get_sb()
            profile_res = load_profile(sb)

            if not profile_res.data:
                raise Exception("Profile not found")

        except Exception:
            try:
                sb = refresh_sb()
                profile_res = load_profile(sb)

                if not profile_res.data:
                    raise Exception("Profile not found after refresh")

            except Exception:
                logger.exception("Auth failed")
                session.clear()

                if is_api:
                    return jsonify({"error": "unauthorized"}), 401

                flash("Сессия истекла. Войдите заново.")
                return redirect(url_for("login"))

        return view(sb, profile_res.data[0], *args, **kwargs)

    return wrapped


# =========================================================
# STORAGE
# =========================================================

def upload_to_bucket(sb, bucket: str, user_id: str, file_storage):
    if not file_storage or not getattr(file_storage, "filename", None):
        return None

    if bucket not in UPLOAD_RULES:
        raise UploadError("Неизвестный bucket")

    allowed_extensions, max_size = UPLOAD_RULES[bucket]

    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in allowed_extensions:
        raise UploadError("Недопустимый тип файла")

    data = file_storage.read(max_size + 1)

    if len(data) > max_size:
        raise UploadError("Файл слишком большой")

    path = f"{user_id}/{uuid.uuid4()}.{ext}"
    content_type = file_storage.mimetype or MIME_TYPES.get(ext, "application/octet-stream")

    sb.storage.from_(bucket).upload(
        path,
        data,
        {
            "content-type": content_type,
        },
    )

    return sb.storage.from_(bucket).get_public_url(path)


# =========================================================
# FRIENDSHIP HELPERS
# =========================================================

def get_accepted_friendship(sb, uid: str, other_id: str):
    query = (
        f"and(requester_id.eq.{uid},addressee_id.eq.{other_id}),"
        f"and(requester_id.eq.{other_id},addressee_id.eq.{uid})"
    )

    res = (
        sb.table("friendships")
        .select("id,status")
        .eq("status", "accepted")
        .or_(query)
        .limit(1)
        .execute()
    )

    return res.data[0] if res.data else None


def fallback_conversations(sb, uid: str):
    friendships_res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .limit(500)
        .execute()
    )

    friend_ids = []

    for friendship in friendships_res.data or []:
        friend_id = (
            friendship["addressee_id"]
            if friendship["requester_id"] == uid
            else friendship["requester_id"]
        )

        if friend_id not in friend_ids:
            friend_ids.append(friend_id)

    if not friend_ids:
        return []

    profiles_res = (
        sb.table("profiles")
        .select("id, username, display_name, avatar_url")
        .in_("id", friend_ids)
        .limit(500)
        .execute()
    )

    profiles_by_id = {
        profile["id"]: profile
        for profile in profiles_res.data or []
    }

    result = []

    for friend_id in friend_ids:
        profile = profiles_by_id.get(friend_id, {})

        result.append(
            {
                "friend_id": friend_id,
                "username": profile.get("username"),
                "display_name": profile.get("display_name"),
                "avatar_url": profile.get("avatar_url"),
                "last_message_text": None,
                "last_message_at": None,
                "last_message_mine": False,
                "unread_count": 0,
            }
        )

    result.sort(key=lambda item: (item.get("display_name") or "").lower())

    return result


# =========================================================
# PAGES
# =========================================================

@app.route("/")
def index():
    if session.get("access_token"):
        return redirect(url_for("map_view"))

    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
@rate_limit("20 per minute")
def register():
    if request.method == "GET":
        return render_template("register.html", categories=CATEGORIES)

    try:
        email = clean_text(request.form.get("email"), 254, "Email")
        password = request.form.get("password", "")
        username = clean_text(request.form.get("username"), 30, "Имя пользователя")
        display_name = clean_text(request.form.get("display_name"), 80, "Имя") or username
        account_type = request.form.get("account_type", "person")

        if account_type not in ("person", "organization"):
            account_type = "person"

        if not email or not password or not username:
            flash("Заполните email, имя пользователя и пароль")
            return redirect(url_for("register"))

        if not USERNAME_RE.match(username):
            flash("Имя пользователя: 3–30 символов, латиница, цифры и _")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Пароль должен быть не короче 8 символов")
            return redirect(url_for("register"))

    except ValidationError as e:
        flash(str(e))
        return redirect(url_for("register"))

    sb = create_supabase_client()

    try:
        auth_res = sb.auth.sign_up(
            {
                "email": email,
                "password": password,
            }
        )
    except Exception:
        logger.exception("Supabase sign_up failed")
        flash("Не удалось зарегистрироваться. Попробуйте позже.")
        return redirect(url_for("register"))

    if not auth_res.user or not auth_res.session:
        flash("Подтвердите email по ссылке в почте")
        return redirect(url_for("login"))

    profile_data = {
        "id": auth_res.user.id,
        "username": username,
        "display_name": display_name,
        "account_type": account_type,
    }

    if account_type == "organization":
        try:
            category = clean_text(request.form.get("category"), 50, "Категория") or None
            address = clean_text(request.form.get("address"), 200, "Адрес") or None

            if category and category not in CATEGORIES:
                category = None

            profile_data["category"] = category
            profile_data["address"] = address

            if request.form.get("org_lat") and request.form.get("org_lng"):
                profile_data["lat"] = parse_float(request.form.get("org_lat"), "Широта")
                profile_data["lng"] = parse_float(request.form.get("org_lng"), "Долгота")

        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("register"))

    sb2 = create_supabase_client()

    try:
        sb2.postgrest.auth(auth_res.session.access_token)
    except Exception:
        logger.debug("Не удалось установить postgrest.auth после регистрации", exc_info=True)

    try:
        sb2.table("profiles").insert(profile_data).execute()
    except Exception:
        logger.exception("Profile insert failed")
        flash("Аккаунт создан, но профиль не сохранён. Попробуйте войти позже.")
        return redirect(url_for("login"))

    persist_tokens(
        auth_res.session.access_token,
        auth_res.session.refresh_token,
        auth_res.user.id,
    )

    return redirect(url_for("map_view"))


@app.route("/login", methods=["GET", "POST"])
@rate_limit("20 per minute")
def login():
    if request.method == "GET":
        return render_template("login.html")

    try:
        email = clean_text(request.form.get("email"), 254, "Email")
        password = request.form.get("password", "")
    except ValidationError as e:
        flash(str(e))
        return redirect(url_for("login"))

    if not email or not password:
        flash("Заполните email и пароль")
        return redirect(url_for("login"))

    sb = create_supabase_client()

    try:
        res = sb.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )
    except Exception:
        flash("Неверный email или пароль")
        return redirect(url_for("login"))

    if not res.session or not res.user:
        flash("Подтвердите email по ссылке в почте")
        return redirect(url_for("login"))

    persist_tokens(
        res.session.access_token,
        res.session.refresh_token,
        res.user.id,
    )

    return redirect(url_for("map_view"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/map")
@login_required
def map_view(sb, profile):
    return render_template(
        "map.html",
        profile=profile,
        categories=CATEGORIES,
    )


@app.route("/feed")
@login_required
def feed_view(sb, profile):
    uid = profile["id"]
    now_iso = to_iso(utcnow())

    friends_res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    friend_ids = [uid]

    for friendship in friends_res.data or []:
        if friendship["requester_id"] == uid:
            friend_ids.append(friendship["addressee_id"])
        else:
            friend_ids.append(friendship["requester_id"])

    friend_ids = list(dict.fromkeys(friend_ids))

    spots_res = (
        sb.table("spots")
        .select("*, owner:owner_id(username, display_name, avatar_url)")
        .in_("owner_id", friend_ids)
        .or_(f"expires_at.is.null,expires_at.gt.{now_iso}")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )

    return render_template(
        "feed.html",
        spots=spots_res.data or [],
        profile=profile,
    )


@app.route("/messages")
@login_required
def messages_view(sb, profile):
    return render_template(
        "messages.html",
        profile=profile,
    )


@app.route("/messages/<username>")
@login_required
def chat_view(sb, profile, username):
    friend_res = (
        sb.table("profiles")
        .select("id, username, display_name, avatar_url")
        .eq("username", username)
        .limit(1)
        .execute()
    )

    if not friend_res.data:
        return "Пользователь не найден", 404

    return render_template(
        "chat.html",
        profile=profile,
        friend=friend_res.data[0],
    )


@app.route("/profile/<username>")
@login_required
def profile_view(sb, me, username):
    prof_res = (
        sb.table("profiles")
        .select("*")
        .eq("username", username)
        .limit(1)
        .execute()
    )

    if not prof_res.data:
        return "Пользователь не найден", 404

    viewed = prof_res.data[0]
    is_me = viewed["id"] == me["id"]
    now_iso = to_iso(utcnow())

    spots_query = (
        sb.table("spots")
        .select("*")
        .eq("owner_id", viewed["id"])
        .order("created_at", desc=True)
        .limit(100)
    )

    if not is_me:
        spots_query = spots_query.or_(f"expires_at.is.null,expires_at.gt.{now_iso}")

    spots_res = spots_query.execute()

    tagged_spots = []

    if viewed.get("account_type") == "organization":
        tagged_query = (
            sb.table("spots")
            .select("*, owner:owner_id(username, display_name, avatar_url)")
            .eq("organization_id", viewed["id"])
            .order("created_at", desc=True)
            .limit(100)
        )

        if not is_me:
            tagged_query = tagged_query.or_(f"expires_at.is.null,expires_at.gt.{now_iso}")

        tagged_spots = tagged_query.execute().data or []

    friend_status = None

    if not is_me:
        friendship_query = (
            f"and(requester_id.eq.{me['id']},addressee_id.eq.{viewed['id']}),"
            f"and(requester_id.eq.{viewed['id']},addressee_id.eq.{me['id']})"
        )

        friendship_res = (
            sb.table("friendships")
            .select("*")
            .or_(friendship_query)
            .limit(1)
            .execute()
        )

        if friendship_res.data:
            friend_status = friendship_res.data[0]

    return render_template(
        "profile.html",
        profile=viewed,
        spots=spots_res.data or [],
        is_me=is_me,
        friend_status=friend_status,
        tagged_spots=tagged_spots,
        my_id=me["id"],
    )


@app.route("/friends")
@login_required
def friends_view(sb, profile):
    uid = profile["id"]

    incoming = (
        sb.table("friendships")
        .select("*, requester:requester_id(username, display_name, avatar_url)")
        .eq("addressee_id", uid)
        .eq("status", "pending")
        .limit(100)
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
        .limit(300)
        .execute()
    )

    return render_template(
        "friends.html",
        incoming=incoming.data or [],
        accepted=accepted.data or [],
        my_id=uid,
        profile=profile,
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view(sb, profile):
    uid = profile["id"]

    if request.method == "GET":
        full = (
            sb.table("profiles")
            .select("*")
            .eq("id", uid)
            .limit(1)
            .execute()
        )

        current_profile = full.data[0] if full.data else profile

        return render_template(
            "settings.html",
            profile=current_profile,
            categories=CATEGORIES,
        )

    form_name = request.form.get("form_name", "profile")

    if form_name == "visibility":
        show_all = request.form.get("show_all_categories") in ("on", "true", "1", "yes")

        if show_all:
            visible_categories = None
        else:
            visible_categories = [
                category
                for category in request.form.getlist("visible_categories")
                if category in CATEGORIES
            ]

        try:
            (
                sb.table("profiles")
                .update({"visible_categories": visible_categories})
                .eq("id", uid)
                .execute()
            )
            flash("Фильтр обновлён")
        except Exception:
            logger.exception("Failed to update visible_categories")
            flash("Не удалось сохранить фильтр")

        return redirect(url_for("settings_view"))

    try:
        display_name = (
            clean_text(request.form.get("display_name"), 80, "Имя")
            or profile.get("display_name")
            or profile.get("username")
        )

        bio = clean_text(request.form.get("bio"), 500, "О себе") or None
        location = clean_text(request.form.get("location"), 100, "Местоположение") or None

    except ValidationError as e:
        flash(str(e))
        return redirect(url_for("settings_view"))

    update_data = {
        "display_name": display_name,
        "bio": bio,
        "location": location,
    }

    full = (
        sb.table("profiles")
        .select("*")
        .eq("id", uid)
        .limit(1)
        .execute()
    )

    current_profile = full.data[0] if full.data else profile

    if current_profile.get("account_type") == "organization":
        try:
            category = clean_text(request.form.get("category"), 50, "Категория") or None
            address = clean_text(request.form.get("address"), 200, "Адрес") or None
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("settings_view"))

        if category and category not in CATEGORIES:
            category = current_profile.get("category")

        update_data["category"] = category
        update_data["address"] = address

    else:
        age_raw = clean_text(request.form.get("age"), 5, "Возраст")

        if age_raw:
            if not age_raw.isdigit() or not (13 <= int(age_raw) <= 120):
                flash("Некорректный возраст")
                return redirect(url_for("settings_view"))

            update_data["age"] = int(age_raw)
        else:
            update_data["age"] = None

    try:
        avatar = request.files.get("avatar")

        if avatar and avatar.filename:
            update_data["avatar_url"] = upload_to_bucket(
                sb,
                "avatars",
                uid,
                avatar,
            )

        cover = request.files.get("cover")

        if cover and cover.filename:
            update_data["cover_url"] = upload_to_bucket(
                sb,
                "avatars",
                uid,
                cover,
            )

    except UploadError as e:
        flash(str(e))
        return redirect(url_for("settings_view"))

    try:
        (
            sb.table("profiles")
            .update(update_data)
            .eq("id", uid)
            .execute()
        )
        flash("Профиль обновлён")
    except Exception:
        logger.exception("Profile update failed")
        flash("Не удалось обновить профиль")

    latest = (
        sb.table("profiles")
        .select("username")
        .eq("id", uid)
        .limit(1)
        .execute()
    )

    if latest.data:
        return redirect(url_for("profile_view", username=latest.data[0]["username"]))

    return redirect(url_for("settings_view"))


# =========================================================
# API: SPOTS
# =========================================================

@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list(sb, profile):
    uid = profile["id"]
    now_iso = to_iso(utcnow())

    try:
        (
            sb.table("spots")
            .delete()
            .eq("owner_id", uid)
            .lt("expires_at", now_iso)
            .execute()
        )
    except Exception:
        logger.exception("Failed to cleanup expired spots")

    res = (
        sb.table("spots")
        .select(
            "*, "
            "owner:owner_id(username, display_name, avatar_url), "
            "organization:organization_id(username, display_name, category, is_verified)"
        )
        .or_(f"expires_at.is.null,expires_at.gt.{now_iso}")
        .order("created_at", desc=True)
        .limit(300)
        .execute()
    )

    spots = res.data or []

    pref_res = (
        sb.table("profiles")
        .select("visible_categories")
        .eq("id", uid)
        .limit(1)
        .execute()
    )

    preferred = (pref_res.data[0] if pref_res.data else {}).get("visible_categories")

    if preferred is not None:
        spots = [
            spot
            for spot in spots
            if spot.get("owner_id") == uid
            or not spot.get("category")
            or spot.get("category") in preferred
        ]

    return jsonify(spots)


@app.route("/api/spots", methods=["POST"])
@rate_limit("10 per minute")
@login_required
def api_spots_create(sb, profile):
    uid = profile["id"]

    try:
        title = clean_text(request.form.get("title"), 120, "Название")
        description = clean_text(request.form.get("description"), 1000, "Описание") or None
        lat = parse_float(request.form.get("lat"), "Широта")
        lng = parse_float(request.form.get("lng"), "Долгота")
        duration_hours = clamp_number(
            parse_float(request.form.get("duration_hours"), "Длительность", 6),
            0.5,
            48,
        )
        category = clean_text(request.form.get("category"), 50, "Категория") or None
        mood = clean_text(request.form.get("mood"), 50, "Настроение") or None
        voice_url = clean_text(request.form.get("voice_url"), 500, "Голосовая заметка") or None
        organization_id = clean_text(request.form.get("organization_id"), 100, "Заведение") or None

    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if not title:
        return jsonify({"error": "Название обязательно"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "Некорректные координаты"}), 400

    visibility = request.form.get("visibility", "public")

    if visibility not in ("public", "friends"):
        visibility = "public"

    placement_type = request.form.get("placement_type", "geo")

    if placement_type not in ("geo", "manual"):
        placement_type = "geo"

    if category and category not in CATEGORIES:
        category = None

    if organization_id:
        try:
            uuid.UUID(organization_id)
        except ValueError:
            return jsonify({"error": "Некорректное заведение"}), 400

        org_res = (
            sb.table("profiles")
            .select("id, account_type")
            .eq("id", organization_id)
            .limit(1)
            .execute()
        )

        if not org_res.data or org_res.data[0].get("account_type") != "organization":
            return jsonify({"error": "Заведение не найдено"}), 400

    if voice_url and not is_safe_voice_url(voice_url, uid):
        return jsonify({"error": "Некорректная ссылка на голосовую заметку"}), 400

    try:
        photo_url = upload_to_bucket(
            sb,
            "spot-photos",
            uid,
            request.files.get("photo"),
        )
    except UploadError as e:
        return jsonify({"error": str(e)}), 400

    account_type = profile.get("account_type", "person")

    if account_type == "person":
        try:
            (
                sb.table("spots")
                .delete()
                .eq("owner_id", uid)
                .execute()
            )
        except Exception:
            logger.exception("Failed to delete old spots")

    expires_at = to_iso(utcnow() + timedelta(hours=duration_hours))

    data = {
        "owner_id": uid,
        "title": title,
        "description": description,
        "lat": lat,
        "lng": lng,
        "visibility": visibility,
        "is_live": request.form.get("is_live", "true") in ("true", "on", "1", "yes"),
        "placement_type": placement_type,
        "expires_at": expires_at,
    }

    if photo_url:
        data["photo_url"] = photo_url

    if organization_id:
        data["organization_id"] = organization_id

    if category:
        data["category"] = category

    if mood:
        data["mood"] = mood

    if voice_url:
        data["voice_url"] = voice_url

    if request.form.get("wave_enabled") in ("true", "on", "1", "yes"):
        try:
            wave_hours = clamp_number(
                parse_float(request.form.get("wave_hours"), "Длительность волны", 1),
                0.25,
                12,
            )
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400

        data["wave_ends_at"] = to_iso(utcnow() + timedelta(hours=wave_hours))

        wave_max_raw = (request.form.get("wave_max_people") or "").strip()

        if wave_max_raw:
            if not wave_max_raw.isdigit():
                return jsonify({"error": "Лимит людей должен быть числом"}), 400

            wave_max = int(wave_max_raw)

            if not (1 <= wave_max <= 500):
                return jsonify({"error": "Лимит людей должен быть от 1 до 500"}), 400

            data["wave_max_people"] = wave_max

    try:
        res = sb.table("spots").insert(data).execute()
        return jsonify(res.data[0]), 201
    except Exception:
        logger.exception("Spot create failed")
        return jsonify({"error": "Не удалось создать метку"}), 500


@app.route("/api/spots/<int:spot_id>", methods=["DELETE"])
@rate_limit("20 per minute")
@login_required
def api_spots_delete(sb, profile, spot_id):
    try:
        (
            sb.table("spots")
            .delete()
            .eq("id", spot_id)
            .eq("owner_id", profile["id"])
            .execute()
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception("Spot delete failed")
        return jsonify({"error": "Не удалось удалить метку"}), 500


@app.route("/api/profile/achievements")
@login_required
def api_achievements(sb, profile):
    uid = profile["id"]

    badges = (
        sb.table("user_achievements")
        .select("*")
        .eq("user_id", uid)
        .order("earned_at", desc=True)
        .limit(100)
        .execute()
    )

    return jsonify(
        {
            "achievements": badges.data or [],
            "xp": profile.get("xp", 0),
            "level": profile.get("level", 1),
        }
    )


@app.route("/api/spots/<int:spot_id>/comments", methods=["GET", "POST"])
@rate_limit("30 per minute")
@login_required
def api_spot_comments(sb, profile, spot_id):
    uid = profile["id"]

    spot_res = (
        sb.table("spots")
        .select("id")
        .eq("id", spot_id)
        .limit(1)
        .execute()
    )

    if not spot_res.data:
        return jsonify({"error": "Метка не найдена"}), 404

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}

        if not isinstance(payload, dict):
            payload = {}

        try:
            text = clean_text(payload.get("text"), 500, "Комментарий")
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400

        if not text:
            return jsonify({"error": "Текст обязателен"}), 400

        try:
            res = (
                sb.table("spot_comments")
                .insert(
                    {
                        "spot_id": spot_id,
                        "user_id": uid,
                        "text": text,
                    }
                )
                .execute()
            )
            return jsonify(res.data[0]), 201
        except Exception:
            logger.exception("Comment create failed")
            return jsonify({"error": "Не удалось добавить комментарий"}), 500

    res = (
        sb.table("spot_comments")
        .select("*, user:user_id(username, display_name, avatar_url)")
        .eq("spot_id", spot_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    comments = res.data or []
    comments.reverse()

    return jsonify(comments)


@app.route("/api/spots/<int:spot_id>/social-proof")
@login_required
def api_spot_social_proof(sb, profile, spot_id):
    uid = profile["id"]

    spot_res = (
        sb.table("spots")
        .select("id, organization_id")
        .eq("id", spot_id)
        .limit(1)
        .execute()
    )

    if not spot_res.data:
        return jsonify({"error": "Метка не найдена"}), 404

    org_id = spot_res.data[0].get("organization_id")

    if not org_id:
        return jsonify(
            {
                "friends_count": 0,
                "total_today": 0,
                "friends": [],
            }
        )

    since = to_iso(utcnow() - timedelta(hours=24))

    today_res = (
        sb.table("spots")
        .select("*, owner:owner_id(username, display_name, avatar_url)")
        .eq("organization_id", org_id)
        .gte("created_at", since)
        .limit(300)
        .execute()
    )

    today_spots = today_res.data or []

    friends_res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    friend_ids = set()

    for friendship in friends_res.data or []:
        if friendship["requester_id"] == uid:
            friend_ids.add(friendship["addressee_id"])
        else:
            friend_ids.add(friendship["requester_id"])

    friend_spots = [
        spot
        for spot in today_spots
        if spot.get("owner_id") in friend_ids
    ]

    return jsonify(
        {
            "friends_count": len(friend_spots),
            "total_today": len(today_spots),
            "friends": friend_spots[:6],
        }
    )


@app.route("/api/spots/<int:spot_id>/collaborators")
@login_required
def api_spot_collaborators(sb, profile, spot_id):
    spot_res = (
        sb.table("spots")
        .select("id")
        .eq("id", spot_id)
        .limit(1)
        .execute()
    )

    if not spot_res.data:
        return jsonify({"error": "Метка не найдена"}), 404

    res = (
        sb.table("spot_collaborators")
        .select("*, profiles:user_id(username, display_name, avatar_url)")
        .eq("spot_id", spot_id)
        .limit(100)
        .execute()
    )

    return jsonify(res.data or [])


@app.route("/api/spots/<int:spot_id>/collaborate", methods=["POST"])
@rate_limit("20 per minute")
@login_required
def api_spot_collaborate(sb, profile, spot_id):
    uid = profile["id"]

    spot_res = (
        sb.table("spots")
        .select("id, owner_id, wave_ends_at, wave_max_people")
        .eq("id", spot_id)
        .limit(1)
        .execute()
    )

    if not spot_res.data:
        return jsonify({"error": "Метка не найдена"}), 404

    spot = spot_res.data[0]

    if spot.get("owner_id") == uid:
        return jsonify({"error": "Вы автор этой метки"}), 400

    wave_ends_at = parse_iso_datetime(spot.get("wave_ends_at"))

    if not wave_ends_at:
        return jsonify({"error": "Это не волна"}), 400

    if wave_ends_at <= utcnow():
        return jsonify({"error": "Волна закончилась"}), 400

    max_people = spot.get("wave_max_people")

    if max_people:
        count_res = (
            sb.table("spot_collaborators")
            .select("spot_id", count="exact")
            .eq("spot_id", spot_id)
            .execute()
        )

        count = count_res.count or 0

        if count >= max_people:
            return jsonify({"error": "Волна заполнена"}), 400

    try:
        (
            sb.table("spot_collaborators")
            .upsert(
                {
                    "spot_id": spot_id,
                    "user_id": uid,
                },
                {
                    "on_conflict": "spot_id,user_id",
                },
            )
            .execute()
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception("Collaborate failed")
        return jsonify({"error": "Не удалось присоединиться"}), 500


@app.route("/api/spots/voice", methods=["POST"])
@rate_limit("20 per hour")
@login_required
def api_spot_voice(sb, profile):
    try:
        url = upload_to_bucket(
            sb,
            "voice-notes",
            profile["id"],
            request.files.get("voice"),
        )
    except UploadError as e:
        return jsonify({"error": str(e)}), 400

    if not url:
        return jsonify({"error": "Файл не передан"}), 400

    return jsonify({"url": url})


# =========================================================
# API: FRIENDS
# =========================================================

@app.route("/api/friends_list")
@login_required
def api_friends_list(sb, profile):
    uid = profile["id"]

    res = (
        sb.table("friendships")
        .select("requester_id, addressee_id")
        .eq("status", "accepted")
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    friend_ids = []

    for friendship in res.data or []:
        friend_id = (
            friendship["addressee_id"]
            if friendship["requester_id"] == uid
            else friendship["requester_id"]
        )

        if friend_id not in friend_ids:
            friend_ids.append(friend_id)

    if not friend_ids:
        return jsonify([])

    profiles_res = (
        sb.table("profiles")
        .select("id, username, display_name, avatar_url")
        .in_("id", friend_ids)
        .limit(300)
        .execute()
    )

    return jsonify(profiles_res.data or [])


@app.route("/api/friends/<username>/add", methods=["POST"])
@rate_limit("20 per minute")
@login_required
def api_friend_add(sb, profile, username):
    uid = profile["id"]

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

    existing_query = (
        f"and(requester_id.eq.{uid},addressee_id.eq.{target_id}),"
        f"and(requester_id.eq.{target_id},addressee_id.eq.{uid})"
    )

    existing_res = (
        sb.table("friendships")
        .select("id,status")
        .or_(existing_query)
        .limit(1)
        .execute()
    )

    if existing_res.data:
        return jsonify(
            {
                "ok": True,
                "status": existing_res.data[0]["status"],
            }
        )

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
    except Exception:
        logger.exception("Friend add failed")
        return jsonify({"error": "Не удалось отправить заявку"}), 500

    return jsonify(
        {
            "ok": True,
            "status": "pending",
            "friendship": res.data[0],
        }
    ), 201


@app.route("/api/friends/<int:friendship_id>/accept", methods=["POST"])
@rate_limit("30 per minute")
@login_required
def api_friend_accept(sb, profile, friendship_id):
    res = (
        sb.table("friendships")
        .update({"status": "accepted"})
        .eq("id", friendship_id)
        .eq("addressee_id", profile["id"])
        .execute()
    )

    if not res.data:
        return jsonify({"error": "Заявка не найдена"}), 404

    return jsonify({"ok": True})


@app.route("/api/friends/<int:friendship_id>/decline", methods=["POST"])
@rate_limit("30 per minute")
@login_required
def api_friend_decline(sb, profile, friendship_id):
    res = (
        sb.table("friendships")
        .delete()
        .eq("id", friendship_id)
        .eq("addressee_id", profile["id"])
        .execute()
    )

    if not res.data:
        return jsonify({"error": "Заявка не найдена"}), 404

    return jsonify({"ok": True})


@app.route("/api/friends/<int:friendship_id>", methods=["DELETE"])
@rate_limit("30 per minute")
@login_required
def api_friend_remove(sb, profile, friendship_id):
    uid = profile["id"]

    res = (
        sb.table("friendships")
        .delete()
        .eq("id", friendship_id)
        .or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}")
        .execute()
    )

    if not res.data:
        return jsonify({"error": "Дружба не найдена"}), 404

    return jsonify({"ok": True})


# =========================================================
# API: MESSAGES
# =========================================================

@app.route("/api/conversations")
@login_required
def api_conversations(sb, profile):
    uid = profile["id"]

    try:
        res = sb.rpc("get_conversations").execute()

        if isinstance(res.data, list):
            return jsonify(res.data)

    except Exception:
        logger.exception("RPC get_conversations failed, using fallback")

    return jsonify(fallback_conversations(sb, uid))


@app.route("/api/messages/<friend_id>", methods=["GET", "POST"])
@rate_limit("120 per minute")
@login_required
def api_messages(sb, profile, friend_id):
    uid = profile["id"]

    try:
        uuid.UUID(friend_id)
    except ValueError:
        return jsonify({"error": "Некорректный пользователь"}), 404

    friend_res = (
        sb.table("profiles")
        .select("id")
        .eq("id", friend_id)
        .limit(1)
        .execute()
    )

    if not friend_res.data:
        return jsonify({"error": "Пользователь не найден"}), 404

    if not get_accepted_friendship(sb, uid, friend_id):
        return jsonify({"error": "Чат доступен только с друзьями"}), 403

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}

        if not isinstance(payload, dict):
            payload = {}

        try:
            text = clean_text(payload.get("text"), 2000, "Сообщение")
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400

        if not text:
            return jsonify({"error": "Текст обязателен"}), 400

        try:
            (
                sb.table("messages")
                .insert(
                    {
                        "sender_id": uid,
                        "receiver_id": friend_id,
                        "text": text,
                    }
                )
                .execute()
            )
            return jsonify({"ok": True}), 201
        except Exception:
            logger.exception("Message send failed")
            return jsonify({"error": "Не удалось отправить сообщение"}), 500

    conversation_query = (
        f"and(sender_id.eq.{uid},receiver_id.eq.{friend_id}),"
        f"and(sender_id.eq.{friend_id},receiver_id.eq.{uid})"
    )

    res = (
        sb.table("messages")
        .select(
            "*, "
            "sender:profiles!sender_id(username, display_name, avatar_url), "
            "receiver:profiles!receiver_id(username, display_name, avatar_url)"
        )
        .or_(conversation_query)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    messages = res.data or []
    messages.reverse()

    try:
        (
            sb.table("messages")
            .update({"is_read": True})
            .eq("sender_id", friend_id)
            .eq("receiver_id", uid)
            .eq("is_read", False)
            .execute()
        )
    except Exception:
        logger.exception("Failed to mark messages as read")

    return jsonify(messages)


@app.route("/api/messages/unread_count")
@login_required
def api_unread_count(sb, profile):
    uid = profile["id"]

    messages_res = (
        sb.table("messages")
        .select("id", count="exact")
        .eq("receiver_id", uid)
        .eq("is_read", False)
        .execute()
    )

    incoming_res = (
        sb.table("friendships")
        .select("id", count="exact")
        .eq("addressee_id", uid)
        .eq("status", "pending")
        .execute()
    )

    return jsonify(
        {
            "messages": messages_res.count or 0,
            "friend_requests": incoming_res.count or 0,
        }
    )


# =========================================================
# API: SEARCH
# =========================================================

@app.route("/api/organizations/search")
@rate_limit("30 per minute")
@login_required
def api_search_organizations(sb, profile):
    q_raw = request.args.get("q", "")

    try:
        q = clean_text(q_raw, 100, "Поиск")
    except ValidationError:
        return jsonify([])

    q = sanitize_like(q)

    if not q:
        return jsonify([])

    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    query = (
        sb.table("profiles")
        .select(
            "id, username, display_name, category, address, avatar_url, is_verified, lat, lng"
        )
        .eq("account_type", "organization")
        .ilike("display_name", f"%{q}%")
        .limit(30)
    )

    orgs = query.execute().data or []

    if lat is not None and lng is not None:
        def distance(item):
            if item.get("lat") is None or item.get("lng") is None:
                return float("inf")

            return (item["lat"] - lat) ** 2 + (item["lng"] - lng) ** 2

        orgs.sort(key=distance)
        return jsonify(orgs[:8])

    return jsonify(orgs[:15])


@app.route("/api/search_users")
@rate_limit("30 per minute")
@login_required
def api_search_users(sb, profile):
    q_raw = request.args.get("q", "")

    try:
        q = clean_text(q_raw, 50, "Поиск")
    except ValidationError:
        return jsonify([])

    q = sanitize_like(q)

    if not q:
        return jsonify([])

    pattern = f"%{q}%"

    res = (
        sb.table("profiles")
        .select("username, display_name, avatar_url")
        .eq("account_type", "person")
        .or_(f"username.ilike.{pattern},display_name.ilike.{pattern}")
        .limit(10)
        .execute()
    )

    return jsonify(res.data or [])


# =========================================================
# SECURITY HEADERS + ERROR HANDLERS
# =========================================================

@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404

    return "Страница не найдена", 404


@app.errorhandler(405)
def handle_405(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "method not allowed"}), 405

    return "Метод не поддерживается", 405


@app.errorhandler(413)
def handle_413(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "file too large"}), 413

    return "Файл слишком большой", 413


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"error": e.name}), e.code

        return e

    logger.exception("Unhandled server error")

    if request.path.startswith("/api/"):
        return jsonify({"error": "server_error"}), 500

    return "Внутренняя ошибка сервера", 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")
    port = int(os.environ.get("PORT", "5000"))

    if debug:
        logger.warning("Debug mode enabled. Do not use debug mode in production.")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
    )