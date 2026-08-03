(function () {
    var map, markersLayer, pendingLat = 55.75, pendingLng = 37.62;

    function initMap() {
        map = L.map('map', { zoomControl: false }).setView([55.75, 37.62], 13);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertile/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(map);
        L.control.zoom({ position: 'topright' }).addTo(map);
        markersLayer = L.layerGroup().addTo(map);
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(function (pos) {
                pendingLat = pos.coords.latitude; pendingLng = pos.coords.longitude;
                map.setView([pendingLat, pendingLng], 15);
                L.circleMarker([pendingLat, pendingLng], { radius: 9, color: '#E4633B', fillColor: '#E4633B', fillOpacity: .8, weight: 3 }).addTo(map);
            });
        }
    }

    async function loadSpots() {
        try {
            var res = await fetch('/api/spots');
            if (!res.ok) return;
            var spots = await res.json();
            markersLayer.clearLayers();
            spots.forEach(function (s) {
                var color = s.owner_id === window.CURRENT_USER_ID ? '#E4633B' : (s.visibility === 'friends' ? '#8B7CF6' : '#4E9B6E');
                var icon = L.divIcon({ className: '', html: '<div class="spot-pin" style="background:' + color + '"></div>', iconSize: [26, 26], iconAnchor: [13, 13] });
                L.marker([s.lat, s.lng], { icon: icon }).addTo(markersLayer).on('click', function () { openSpot(s); });
            });
        } catch (e) { }
    }

    function openSpot(s) {
        var html = '<button class="sheet-close" onclick="document.getElementById(\'spotSheetOverlay\').classList.remove(\'open\')">✕</button>';
        html += '<h3>' + esc(s.title) + '</h3>';
        if (s.owner) html += '<p class="hint" style="margin-bottom:10px;">' + esc(s.owner.display_name || '') + '</p>';
        if (s.mood) html += '<p style="font-size:18px;margin-bottom:8px;">' + esc(s.mood) + '</p>';
        if (s.description) html += '<p style="margin-bottom:12px;">' + esc(s.description) + '</p>';
        if (s.photo_url) html += '<img src="' + s.photo_url + '" style="width:100%;border-radius:14px;margin-bottom:12px;">';
        html += '<div class="section-title">Комментарии</div><div id="spotComments"></div>';
        html += '<div style="display:flex;gap:8px;margin-top:10px;"><input type="text" id="commentInput" placeholder="Написать..."><button class="btn btn-primary btn-sm" id="sendComment">➤</button></div>';
        if (s.owner_id === window.CURRENT_USER_ID) html += '<button class="btn btn-soft btn-block" style="margin-top:14px;" id="deleteSpot">🗑 Убрать метку</button>';
        document.getElementById('spotSheetContent').innerHTML = html;
        document.getElementById('spotSheetOverlay').classList.add('open');
        loadComments(s.id);
        document.getElementById('sendComment').onclick = function () { sendComment(s.id); };
        if (s.owner_id === window.CURRENT_USER_ID) {
            document.getElementById('deleteSpot').onclick = async function () {
                if (!confirm('Убрать метку?')) return;
                await fetch('/api/spots/' + s.id, { method: 'DELETE' });
                document.getElementById('spotSheetOverlay').classList.remove('open');
                loadSpots();
            };
        }
    }

    async function loadComments(id) {
        try {
            var res = await fetch('/api/spots/' + id + '/comments');
            var list = await res.json();
            var box = document.getElementById('spotComments');
            box.innerHTML = list.length ? list.map(function (c) {
                return '<div class="row-card" style="padding:10px 14px;"><div class="info"><div class="name" style="font-size:14px;">' + esc(c.user ? c.user.display_name : '') + '</div><div class="sub">' + esc(c.text) + '</div></div></div>';
            }).join('') : '<p class="hint">Пока нет комментариев</p>';
        } catch (e) { }
    }

    async function sendComment(id) {
        var input = document.getElementById('commentInput');
        var text = input.value.trim();
        if (!text) return;
        await fetch('/api/spots/' + id + '/comments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
        input.value = '';
        loadComments(id);
    }

    function esc(str) { var d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }

    document.addEventListener('DOMContentLoaded', function () {
        initMap(); loadSpots(); setInterval(loadSpots, 30000);

        document.getElementById('openAddSpot').addEventListener('click', function () {
            document.getElementById('latInput').value = pendingLat;
            document.getElementById('lngInput').value = pendingLng;
            document.getElementById('addSpotOverlay').classList.add('open');
        });
        document.getElementById('closeSheet').addEventListener('click', function () {
            document.getElementById('addSpotOverlay').classList.remove('open');
        });
        document.getElementById('spotSheetOverlay').addEventListener('click', function (e) {
            if (e.target === this) this.classList.remove('open');
        });

        document.querySelectorAll('.duration-option').forEach(function (o) {
            o.addEventListener('click', function () {
                document.querySelectorAll('.duration-option').forEach(function (x) { x.classList.remove('selected'); });
                o.classList.add('selected');
                document.getElementById('durationInput').value = o.dataset.h;
            });
        });
        document.querySelectorAll('.mood-chip').forEach(function (o) {
            o.addEventListener('click', function () {
                document.querySelectorAll('.mood-chip').forEach(function (x) { x.classList.remove('selected'); });
                o.classList.add('selected');
                document.getElementById('moodInput').value = o.dataset.mood;
            });
        });
        document.querySelectorAll('.vis-option').forEach(function (o) {
            o.addEventListener('click', function () {
                document.querySelectorAll('.vis-option').forEach(function (x) { x.classList.remove('selected'); });
                o.classList.add('selected');
                document.getElementById('visibilityInput').value = o.dataset.vis;
            });
        });

        document.getElementById('addSpotForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            var res = await fetch('/api/spots', { method: 'POST', body: new FormData(this) });
            if (res.ok) {
                document.getElementById('addSpotOverlay').classList.remove('open');
                this.reset();
                loadSpots();
            } else {
                var err = await res.json();
                alert(err.error || 'Не получилось. Попробуйте ещё раз.');
            }
        });
    });
})();