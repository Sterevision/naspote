(function () {
'use strict';
var LS_KEY = 'kartometr_geo_notify';
var POLL_MS = 45000;
var settings = loadSettings();
var myLat = null;
var myLng = null;
var friendNames = {};
var notified = {};
var started = false;

function loadSettings() {
    try {
        var raw = localStorage.getItem(LS_KEY);
        if (raw) {
            var s = JSON.parse(raw);
            return { enabled: !!s.enabled, radius: Number(s.radius) || 500 };
        }
    } catch (e) { /* silent */ }
    return { enabled: false, radius: 500 };
}
function saveSettings() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(settings)); } catch (e) { /* silent */ }
}
function haversineMeters(lat1, lng1, lat2, lng2) {
    var r = 6371000;
    var p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
    var dp = (lat2 - lat1) * Math.PI / 180;
    var dl = (lng2 - lng1) * Math.PI / 180;
    var a = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * r * Math.asin(Math.sqrt(a));
}

function buildUI() {
    var fab = document.querySelector('.fab-column');
    var wrap = document.querySelector('.map-wrap');
    if (!fab || !wrap) return;
    fab.insertAdjacentHTML('afterbegin',
        '<button class="fab-mini" id="geoNotifyToggle" type="button" title="Геозоны и уведомления">🔔</button>');
    var btn = document.getElementById('geoNotifyToggle');
    var panel = document.createElement('div');
    panel.id = 'geoNotifyPanel';
    panel.style.cssText = 'position:absolute; right:16px; bottom:170px; z-index:40; background:rgba(255,255,255,.97); border:1px solid var(--line); border-radius:20px; box-shadow:var(--shadow-md); padding:16px; width:236px; display:none; backdrop-filter:blur(16px);';
    panel.innerHTML =
        '<div style="font-weight:900; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:10px;">🔔 Друг рядом</div>' +
        '<label style="display:flex; align-items:center; gap:10px; font-size:14px; font-weight:700; margin-bottom:12px; cursor:pointer;"><input type="checkbox" id="geoEnabled" style="width:20px; height:20px;"> Уведомлять, когда друг рядом</label>' +
        '<div style="font-size:11px; font-weight:900; color:var(--muted); margin-bottom:6px;">РАДИУС</div>' +
        '<div style="display:flex; gap:6px; margin-bottom:12px;">' +
        ['300', '500', '1000'].map(function (m) {
            return '<div class="geo-radius-opt" data-m="' + m + '" style="flex:1; text-align:center; padding:8px 0; border-radius:12px; background:var(--surface-2); font-size:12px; font-weight:800; color:var(--muted); cursor:pointer;">' + (m === '1000' ? '1 км' : m + ' м') + '</div>';
        }).join('') + '</div>' +
        '<button class="btn btn-soft btn-block" id="geoPermBtn" type="button" style="padding:10px; font-size:12px;">Разрешить уведомления браузера</button>';
    wrap.appendChild(panel);

    function paint() {
        btn.style.background = settings.enabled ? 'var(--manual)' : '';
        btn.style.color = settings.enabled ? '#fff' : '';
        var cb = document.getElementById('geoEnabled');
        if (cb) cb.checked = settings.enabled;
        panel.querySelectorAll('.geo-radius-opt').forEach(function (o) {
            var active = Number(o.dataset.m) === settings.radius;
            o.style.background = active ? 'var(--primary)' : 'var(--surface-2)';
            o.style.color = active ? '#fff' : 'var(--muted)';
        });
    }
    btn.addEventListener('click', function () {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        paint();
    });
    document.getElementById('geoEnabled').addEventListener('change', function () {
        settings.enabled = this.checked;
        saveSettings();
        paint();
        if (settings.enabled) start();
    });
    panel.querySelectorAll('.geo-radius-opt').forEach(function (o) {
        o.addEventListener('click', function () {
            settings.radius = Number(o.dataset.m);
            saveSettings();
            paint();
        });
    });
    document.getElementById('geoPermBtn').addEventListener('click', function () {
        if (!('Notification' in window)) { alert('Этот браузер не поддерживает уведомления.'); return; }
        Notification.requestPermission().then(function (p) {
            alert(p === 'granted' ? 'Уведомления браузера разрешены!' : 'Разрешение не выдано.');
        });
    });
    paint();
}

function locate() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (pos) {
        myLat = pos.coords.latitude;
        myLng = pos.coords.longitude;
    }, function () { /* silent */ }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
}

async function check() {
    if (!settings.enabled || myLat === null) return;
    try {
        var fr = await fetch('/api/friends_list', { credentials: 'same-origin' });
        if (!fr.ok) return;
        var friends = await fr.json();
        friendNames = {};
        (friends || []).forEach(function (f) { friendNames[f.id] = f.display_name || f.username; });
        var sr = await fetch('/api/spots', { credentials: 'same-origin' });
        if (!sr.ok) return;
        var spots = await sr.json();
        (spots || []).forEach(function (s) {
            if (notified[s.id]) return;
            if (String(s.owner_id) === String(window.CURRENT_USER_ID || '')) return;
            if (!friendNames[s.owner_id]) return;
            var d = haversineMeters(myLat, myLng, s.lat, s.lng);
            if (d <= settings.radius) {
                notified[s.id] = true;
                var name = friendNames[s.owner_id];
                var meters = Math.round(d);
                toast('🔔 ' + name + ' рядом (' + meters + ' м): «' + (s.title || 'метка') + '»');
                browserNotify('Картометр: ' + name + ' рядом', name + ' в ' + meters + ' м от вас — «' + (s.title || '') + '»');
            }
        });
    } catch (e) { /* silent */ }
}

function toast(text) {
    var wrap = document.querySelector('.map-wrap');
    if (!wrap) return;
    var el = document.createElement('div');
    el.textContent = text;
    el.style.cssText = 'position:absolute; top:66px; left:50%; transform:translateX(-50%); z-index:60; background:rgba(15,23,42,.92); color:#fff; font-size:13px; font-weight:700; padding:11px 16px; border-radius:999px; box-shadow:var(--shadow-md); max-width:calc(100% - 28px); text-align:center;';
    wrap.appendChild(el);
    setTimeout(function () { el.remove(); }, 7000);
}
function browserNotify(title, body) {
    if ('Notification' in window && Notification.permission === 'granted') {
        try { new Notification(title, { body: body }); } catch (e) { /* silent */ }
    }
}

function start() {
    if (started) return;
    started = true;
    locate();
    setInterval(function () { if (!document.hidden) locate(); }, 60000);
    check();
    setInterval(function () { if (!document.hidden) check(); }, POLL_MS);
}

document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('map')) return;
    buildUI();
    if (settings.enabled) start();
});
})();