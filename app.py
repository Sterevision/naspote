import os
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
    raise RuntimeError("Не заданы SUPABASE_URL / SUPABASE_ANON_KEY")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

CATEGORIES = ["Бар", "Клуб", "Кофейня", "Ресторан", "Коворкинг", "Караоке",
              "Спорт", "Вечеринка", "Природа", "Выставка/галерея", "Другое"]


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
            sb.table("profiles").select("id").eq("id", session["user_id"]).single().execute()
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
        flash("Заполните все поля")
        return redirect(url_for("register"))
    sb = get_supabase()
    try:
        auth_res = sb.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        flash(f"Ошибка: {e}")
        return redirect(url_for("register"))
    if not auth_res.user:
        flash("Подтвердите email")
        return redirect(url_for("login"))
    if auth_res.session:
        sb2 = get_supabase(auth_res.session.access_token, auth_res.session.refresh_token)
        profile_data = {"id": auth_res.user.id, "username": username,
                        "display_name": display_name, "account_type": account_type}
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
        res = get_supabase().auth.sign_in_with_password({
            "email": request.form.get("email", "").strip(),
            "password": request.form.get("password", "")})
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
    profile = sb.table("profiles").select("*").eq("id", session["user_id"]).single().execute()
    return render_template("map.html", profile=profile.data, categories=CATEGORIES)


@app.route("/feed")
@login_required
def feed_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    profile = sb.table("profiles").select("*").eq("id", uid).single().execute().data
    friends_res = sb.table("friendships").select("requester_id, addressee_id").eq("status", "accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    friend_ids = [uid] + [f["requester_id"] if f["requester_id"] != uid else f["addressee_id"] for f in (friends_res.data or [])]
    spots_res = sb.table("spots").select("*, owner:owner_id(username, display_name, avatar_url)").in_("owner_id", friend_ids).order("created_at", desc=True).limit(50).execute()
    return render_template("feed.html", spots=spots_res.data or [], profile=profile)


@app.route("/friends")
@login_required
def friends_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    incoming = sb.table("friendships").select("*, requester:requester_id(username, display_name, avatar_url)").eq("addressee_id", uid).eq("status", "pending").execute()
    accepted = sb.table("friendships").select("*, requester:requester_id(username, display_name, avatar_url), addressee:addressee_id(username, display_name, avatar_url)").eq("status", "accepted").or_(f"requester_id.eq.{uid},addressee_id.eq.{uid}").execute()
    profile = sb.table("profiles").select("*").eq("id", uid).single().execute()
    return render_template("friends.html", incoming=incoming.data, accepted=accepted.data, my_id=uid, profile=profile.data)


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
    if not prof_res.data:
        return "Пользователь не найден", 404
    profile = prof_res.data
    spots_res = sb.table("spots").select("*").eq("owner_id", profile["id"]).order("created_at", desc=True).execute()
    is_me = profile["id"] == session["user_id"]
    friend_status = None
    if not is_me:
        f = sb.table("friendships").select("*").or_(
            f"and(requester_id.eq.{session['user_id']},addressee_id.eq.{profile['id']}),"
            f"and(requester_id.eq.{profile['id']},addressee_id.eq.{session['user_id']})").execute()
        if f.data:
            friend_status = f.data[0]
    return render_template("profile.html", profile=profile, spots=spots_res.data, is_me=is_me, friend_status=friend_status)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_view():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    uid = session["user_id"]
    if request.method == "GET":
        profile = sb.table("profiles").select("*").eq("id", uid).single().execute()
        return render_template("settings.html", profile=profile.data)
    update_data = {
        "display_name": request.form.get("display_name", "").strip(),
        "bio": request.form.get("bio", "").strip(),
        "location": request.form.get("location", "").strip(),
    }
    age = request.form.get("age")
    update_data["age"] = int(age) if age and age.isdigit() else None
    avatar = request.files.get("avatar")
    if avatar and avatar.filename:
        update_data["avatar_url"] = upload_to_bucket(sb, "avatars", uid, avatar)
    try:
        sb.table("profiles").update(update_data).eq("id", uid).execute()
        flash("Сохранено")
    except Exception as e:
        flash(f"Ошибка: {e}")
    profile = sb.table("profiles").select("*").eq("id", uid).single().execute()
    return redirect(url_for("profile_view", username=profile.data["username"]))


# ==================== API ====================

@app.route("/api/spots", methods=["GET"])
@login_required
def api_spots_list():
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    now_iso = datetime.now(timezone.utc).isoformat()
    res = sb.table("spots").select(
        "*, owner:owner_id(username, display_name, avatar_url), "
        "organization:organization_id(username, display_name, category, is_verified)"
    ).or_(f"expires_at.is.null,expires_at.gt.{now_iso}").order("created_at", desc=True).execute()
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
        return jsonify({"error": "Заполните название"}), 400
    visibility = request.form.get("visibility", "public")
    category = request.form.get("category", "").strip() or None
    if category and category not in CATEGORIES:
        category = None
    duration_hours = max(1, min(float(request.form.get("duration_hours", "6")), 24))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()
    profile_res = sb.table("profiles").select("account_type").eq("id", uid).single().execute()
    if (profile_res.data or {}).get("account_type", "person") == "person":
        sb.table("spots").delete().eq("owner_id", uid).execute()
    photo_url = None
    if request.files.get("photo") and request.files.get("photo").filename:
        photo_url = upload_to_bucket(sb, "spot-photos", uid, request.files.get("photo"))
    data = {"owner_id": uid, "title": title,
            "description": request.form.get("description", "").strip(),
            "lat": float(lat), "lng": float(lng),
            "visibility": visibility if visibility in ("public", "friends") else "public",
            "is_live": True, "placement_type": request.form.get("placement_type", "geo"),
            "expires_at": expires_at}
    if photo_url:
        data["photo_url"] = photo_url
    if category:
        data["category"] = category
    mood = request.form.get("mood", "").strip() or None
    if mood:
        data["mood"] = mood
    return jsonify(sb.table("spots").insert(data).execute().data[0]), 201


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
    if request.method == "POST":
        text = (request.json or {}).get("text", "").strip()
        if not text:
            return jsonify({"error": "Введите текст"}), 400
        res = sb.table("spot_comments").insert({"spot_id": spot_id, "user_id": session["user_id"], "text": text}).execute()
        return jsonify(res.data[0]), 201
    res = sb.table("spot_comments").select("*, user:user_id(username, display_name)").eq("spot_id", spot_id).order("created_at").execute()
    return jsonify(res.data or [])


@app.route("/api/search_users")
@login_required
def api_search_users():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    return jsonify(sb.table("profiles").select("username, display_name, avatar_url").ilike("username", f"%{q}%").limit(10).execute().data)


@app.route("/api/friends/<username>/add", methods=["POST"])
@login_required
def api_friend_add(username):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    target = sb.table("profiles").select("id").eq("username", username).single().execute()
    if not target.data:
        return jsonify({"error": "Не найдено"}), 404
    sb.table("friendships").insert({"requester_id": session["user_id"], "addressee_id": target.data["id"], "status": "pending"}).execute()
    return jsonify({"ok": True})


@app.route("/api/friends/<int:req_id>/accept", methods=["POST"])
@login_required
def api_friend_accept(req_id):
    sb = get_supabase(session["access_token"], session.get("refresh_token"))
    sb.table("friendships").update({"status": "accepted"}).eq("id", req_id).eq("addressee_id", session["user_id"]).execute()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)