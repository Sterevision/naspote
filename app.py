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
    prof = sb.table("profiles").select("username").eq("id", uid).execute()
    username = prof.data[0]["username"] if prof.data else ""
    return redirect(url_for("profile_view", username=username))

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
    res = sb.table("spot_comments").select("*, user:user_id(username, display_name, avatar_url)").eq("spot_id", spot_id).order("created_at").execute()
    return jsonify(res.data or [])

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
    res = sb.table("messages").select("id", count="exact").eq("receiver_id", uid).eq("is_read", False).execute()
    incoming = sb.table("friendships").select("id", count="exact").eq("addressee_id", uid).eq("status", "pending").execute()
    return jsonify({"messages": res.count or 0, "friend_requests": incoming.count or 0})

if __name__ == "__main__":
    app.run(debug=False, port=5000)
