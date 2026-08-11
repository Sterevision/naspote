(function () {
'use strict';
var map = null;
var markersLayer = null;
var heatmapLayer = null;
var youMarker = null;
var pendingLat = 55.75;
var pendingLng = 37.62;
var manualMode = false;
var activeCategory = '';
var allSpots = [];
var allOrganizations = [];
var orgMarkersLayer = null;
var home = window.MAP_HOME || null;
var targetSpotId = new URLSearchParams(window.location.search).get('spot');
var audioBlob = null;
var mediaRecorder = null;
var recordTimer = null;
var showOwn = false;

function $(id) { return document.getElementById(id); }
function esc(value) {
    var div = document.createElement('div');
    div.textContent = value === null || value === undefined ? '' : String(value);
    return div.innerHTML;
}
function safeUrl(url) {
    if (!url) return '';
    var value = String(url);
    return /^https?:\/\//i.test(value) ? value : '';
}
function timeLeft(iso) {
    if (!iso) return '';
    var diff = new Date(iso) - new Date();
    if (diff <= 0) return 'завершилась';
    var hours = Math.floor(diff / 3600000);
    var minutes = Math.floor((diff % 3600000) / 60000);
    if (hours > 0) return hours + ' ч ' + minutes + ' м';
    if (minutes > 0) return minutes + ' м';
    return 'меньше минуты';
}
function minutesLeft(iso) {
    if (!iso) return 999;
    var diff = new Date(iso) - new Date();
    return diff / 60000;
}
function showMapStatus(text, isError) {
    var el = $('mapStatus');
    if (!el) return;
    el.textContent = text;
    el.className = 'map-status' + (isError ? ' error' : '');
    el.style.display = 'block';
    clearTimeout(el._timer);
    el._timer = setTimeout(function () { el.style.display = 'none'; }, 5000);
}
function isWaveActive(spot) {
    return !!spot.wave_ends_at && new Date(spot.wave_ends_at) > new Date();
}
function pinColor(spot) {
    if (spot.placement_type === 'manual') return 'var(--manual)';
    if (String(spot.owner_id) === String(window.CURRENT_USER_ID || '')) return 'var(--mine)';
    if (spot.visibility === 'friends') return 'var(--friends)';
    return 'var(--public)';
}
function setYouMarker(lat, lng) {
    var icon = L.divIcon({
        className: '',
        html: '<div class="you-dot"></div>',
        iconSize: [18, 18],
        iconAnchor: [9, 9]
    });
    if (youMarker) youMarker.setLatLng([lat, lng]);
    else youMarker = L.marker([lat, lng], { icon: icon, zIndexOffset: 1200 }).addTo(map);
}
function locateUser(isAuto) {
    if (!navigator.geolocation) {
        if (!isAuto) showMapStatus('Геолокация недоступна в этом браузере', true);
        return;
    }
    if (!window.isSecureContext) {
        showMapStatus('Геолокация работает только по HTTPS или на localhost', true);
        return;
    }
    showMapStatus('Определяем местоположение...');
    navigator.geolocation.getCurrentPosition(function (position) {
        pendingLat = position.coords.latitude;
        pendingLng = position.coords.longitude;
        if (map) map.setView([pendingLat, pendingLng], 15);
        setYouMarker(pendingLat, pendingLng);
        showMapStatus('Вы здесь');
    }, function (error) {
        var message = 'Не удалось определить местоположение';
        if (error.code === 1) message = 'Доступ к геолокации запрещён. Разрешите доступ в браузере.';
        else if (error.code === 2) message = 'Геолокация недоступна на этом устройстве.';
        else if (error.code === 3) message = 'Время ожидания геолокации истекло.';
        showMapStatus(message, true);
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
}
function initMap() {
    var mapElement = $('map');
    if (!mapElement) return;
    var center = [pendingLat, pendingLng];
    var zoom = 13;
    if (home && home.lat !== null && home.lng !== null && home.lat !== undefined && home.lng !== undefined) {
        pendingLat = Number(home.lat);
        pendingLng = Number(home.lng);
        center = [pendingLat, pendingLng];
        zoom = 14;
    }
    map = L.map('map', { zoomControl: false }).setView(center, zoom);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 19, attribution: '© OpenStreetMap, © CARTO'
    }).addTo(map);
    L.control.zoom({ position: 'bottomleft' }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
    heatmapLayer = L.layerGroup().addTo(map);
    orgMarkersLayer = L.layerGroup().addTo(map);
    if (home && home.lat !== null && home.lng !== null) setYouMarker(pendingLat, pendingLng);
    else locateUser(true);
    map.on('click', function (event) {
        if (!manualMode) return;
        openAddSheet(event.latlng.lat, event.latlng.lng, 'manual');
    });
}

function renderHeatmap() {
    if (!heatmapLayer || !map) return;
    heatmapLayer.clearLayers();
    if (!allSpots.length) return;
    var gridSize = 0.003;
    var grid = {};
    allSpots.forEach(function (spot) {
        if (spot.organization_id) return;
        var key = Math.floor(spot.lat / gridSize) + ',' + Math.floor(spot.lng / gridSize);
        if (!grid[key]) grid[key] = { count: 0, lat: 0, lng: 0 };
        grid[key].count++;
        grid[key].lat += spot.lat;
        grid[key].lng += spot.lng;
    });
    Object.keys(grid).forEach(function (key) {
        var cell = grid[key];
        var avgLat = cell.lat / cell.count;
        var avgLng = cell.lng / cell.count;
        var intensity = Math.min(cell.count / 5, 1);
        if (cell.count < 2) return;
        var color = intensity < 0.3 ? '#fbbf24' : intensity < 0.6 ? '#f97316' : '#ef4444';
        var radius = 150 + intensity * 200;
        L.circle([avgLat, avgLng], {
            radius: radius,
            fillColor: color,
            fillOpacity: 0.25 + intensity * 0.15,
            stroke: false
        }).addTo(heatmapLayer);
    });
}
function checkDyingSpots() {
    if (!markersLayer) return;
    markersLayer.eachLayer(function (marker) {
        if (!marker._spot) return;
        var mins = minutesLeft(marker._spot.expires_at);
        if (mins <= 10 && mins > 0) marker._container && marker._container.classList.add('dying');
        else if (mins <= 0) markersLayer.removeLayer(marker);
    });
}

// ---------- СВОИ ЛЮДИ (НОВОЕ) ----------
function hasCommonInterests(spot) {
    if (!showOwn) return false;
    var myInt = window.MY_INTERESTS || [];
    var theirInt = (spot.owner && spot.owner.interests) || [];
    if (!myInt.length || !theirInt.length) return false;
    return myInt.some(function (i) { return theirInt.indexOf(i) !== -1; });
}

function applyFilter() {
    if (!markersLayer) return;
    markersLayer.clearLayers();
    allSpots
        .filter(function (spot) {
            if (spot.organization_id) return false;
            return !activeCategory || spot.category === activeCategory;
        })
        .forEach(function (spot) {
            var color = pinColor(spot);
            var waveClass = isWaveActive(spot) ? ' wave' : '';
            var mins = minutesLeft(spot.expires_at);
            var dyingClass = (mins <= 10 && mins > 0) ? ' dying' : '';
            var ownClass = hasCommonInterests(spot) ? ' own-highlight' : '';
            var icon = L.divIcon({
                className: '',
                html: '<div class="spot-pin' + waveClass + dyingClass + ownClass + '" style="background:' + color + '; color:' + color + '"></div>',
                iconSize: [30, 30],
                iconAnchor: [15, 26]
            });
            var marker = L.marker([spot.lat, spot.lng], { icon: icon })
                .addTo(markersLayer)
                .on('click', function () { openSpot(spot); });
            marker._spot = spot;
        });
    renderHeatmap();
    loadOrganizations();
}
function renderOrganizations() {
    if (!orgMarkersLayer) return;
    orgMarkersLayer.clearLayers();
    allOrganizations
        .filter(function (org) { return !activeCategory || org.category === activeCategory; })
        .forEach(function (org) {
            var letter = esc((org.display_name || '?').charAt(0).toUpperCase());
            var colors = org.is_verified
                ? 'background:var(--primary); color:#fff;'
                : 'background:#0f172a; color:#fff;';
            var icon = L.divIcon({
                className: '',
                iconSize: [30, 30],
                iconAnchor: [15, 15],
                html: '<div class="org-pin' + (org.is_verified ? ' verified' : '') + '" style="' + colors + 'font-family:var(--font-display); font-weight:700; font-size:13px; line-height:1; text-align:center;">' + letter + '</div>'
            });
            L.marker([org.lat, org.lng], { icon: icon, zIndexOffset: 1500 })
                .addTo(orgMarkersLayer)
                .on('click', function () {
                    window.location.href = '/profile/' + encodeURIComponent(org.username);
                });
        });
}
async function loadOrganizations() {
    try {
        var res = await fetch('/api/organizations', { credentials: 'same-origin' });
        if (!res.ok) return;
        allOrganizations = await res.json();
        renderOrganizations();
    } catch (e) { /* silent */ }
}
async function loadSpots() {
    try {
        var response = await fetch('/api/spots', { credentials: 'same-origin' });
        if (response.status === 401) { window.location.href = '/login'; return; }
        if (!response.ok) return;
        allSpots = await response.json();
        applyFilter();
        if (targetSpotId) {
            var target = allSpots.find(function (s) { return String(s.id) === String(targetSpotId); });
            if (target && map) { map.setView([target.lat, target.lng], 16); openSpot(target); }
            targetSpotId = null;
        }
    } catch (error) { /* silent */ }
}

function initAudioRecorder() {
    var recordBtn = $('recordAudioBtn');
    var statusEl = $('audioRecordStatus');
    var audioInput = $('audioInputHidden');
    if (!recordBtn || !statusEl) return;

    recordBtn.addEventListener('click', async function () {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            return;
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            statusEl.textContent = '❌ Микрофон не поддерживается';
            return;
        }
        try {
            var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            var chunks = [];
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.ondataavailable = function (e) { if (e.data.size > 0) chunks.push(e.data); };
            mediaRecorder.onstop = function () {
                audioBlob = new Blob(chunks, { type: 'audio/webm' });
                var file = new File([audioBlob], 'vibe.webm', { type: 'audio/webm' });
                var dt = new DataTransfer();
                dt.items.add(file);
                audioInput.files = dt.files;
                statusEl.textContent = '✅ Записано ' + (audioBlob.size / 1024).toFixed(1) + ' КБ';
                stream.getTracks().forEach(function (t) { t.stop(); });
                recordBtn.textContent = '🎙️ Записать заново';
                recordBtn.classList.remove('recording');
            };
            mediaRecorder.start();
            recordBtn.textContent = '⏹ Остановить';
            recordBtn.classList.add('recording');
            statusEl.textContent = '🔴 Идёт запись...';
            var elapsed = 0;
            var maxSec = 10;
            clearInterval(recordTimer);
            recordTimer = setInterval(function () {
                elapsed++;
                statusEl.textContent = '🔴 Запись: ' + elapsed + ' / ' + maxSec + ' сек';
                if (elapsed >= maxSec) {
                    clearInterval(recordTimer);
                    if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
                }
            }, 1000);
        } catch (err) {
            statusEl.textContent = '❌ Нет доступа к микрофону';
        }
    });
}

function openAddSheet(lat, lng, placement) {
    if ($('latInput')) $('latInput').value = lat;
    if ($('lngInput')) $('lngInput').value = lng;
    if ($('placementInput')) $('placementInput').value = placement || 'geo';
    if ($('addSpotOverlay')) $('addSpotOverlay').classList.add('open');
    initAudioRecorder();
}
function closeAddSheet() {
    if ($('addSpotOverlay')) $('addSpotOverlay').classList.remove('open');
}
function closeSpotSheet() {
    if ($('spotSheetOverlay')) $('spotSheetOverlay').classList.remove('open');
}
function resetAddForm() {
    var form = $('addSpotForm');
    if (form) form.reset();
    if ($('categoryInput')) $('categoryInput').value = '';
    if ($('durationInput')) $('durationInput').value = '3';
    if ($('visibilityInput')) $('visibilityInput').value = 'public';
    if ($('placementInput')) $('placementInput').value = 'geo';
    document.querySelectorAll('#addCategoryPicker .chip').forEach(function (chip) { chip.classList.remove('selected'); });
    document.querySelectorAll('.duration-option').forEach(function (option) { option.classList.remove('selected'); });
    var defaultDuration = document.querySelector('.duration-option[data-h="3"]');
    if (defaultDuration) defaultDuration.classList.add('selected');
    document.querySelectorAll('.segmented-item[data-vis]').forEach(function (option) { option.classList.remove('selected'); });
    var defaultVisibility = document.querySelector('.segmented-item[data-vis="public"]');
    if (defaultVisibility) defaultVisibility.classList.add('selected');
    var preview = $('photoPreview');
    var dropText = $('photoDropText');
    if (preview) { preview.src = ''; preview.hidden = true; }
    if (dropText) dropText.style.display = 'flex';
    audioBlob = null;
    var audioStatus = $('audioRecordStatus');
    if (audioStatus) audioStatus.textContent = '';
    var recBtn = $('recordAudioBtn');
    if (recBtn) { recBtn.textContent = '🎙️ Записать атмосферу (10 сек)'; recBtn.classList.remove('recording'); }
    if ($('audioInputHidden')) $('audioInputHidden').value = '';
}
async function loadComments(spotId) {
    var box = $('spotComments');
    if (!box) return;
    try {
        var response = await fetch('/api/spots/' + spotId + '/comments', { credentials: 'same-origin' });
        if (!response.ok) { box.innerHTML = '<p class="hint">Не удалось загрузить комментарии</p>'; return; }
        var comments = await response.json();
        if (!comments.length) { box.innerHTML = '<p class="hint">Пока нет комментариев</p>'; return; }
        box.innerHTML = comments.map(function (comment) {
            var name = comment.user ? (comment.user.display_name || comment.user.username || 'Пользователь') : 'Пользователь';
            var initial = name.charAt(0).toUpperCase();
            var date = '';
            if (comment.created_at) {
                var d = new Date(comment.created_at);
                if (!isNaN(d.getTime())) {
                    date = d.toLocaleDateString([], { day: '2-digit', month: '2-digit' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                }
            }
            return '<div class="comment-row">' +
                '<div class="avatar avatar-sm">' +
                (comment.user && comment.user.avatar_url ? '<img src="' + esc(safeUrl(comment.user.avatar_url)) + '" alt="">' : esc(initial)) +
                '</div>' +
                '<div class="info">' +
                '<div class="name">' + esc(name) + '</div>' +
                '<div class="sub">' + esc(comment.text || '') + '</div>' +
                '<div class="hint">' + esc(date) + '</div>' +
                '</div></div>';
        }).join('');
    } catch (error) { box.innerHTML = '<p class="hint">Ошибка загрузки комментариев</p>'; }
}
async function sendComment(spotId) {
    var input = $('commentInput');
    if (!input) return;
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    try {
        var response = await fetch('/api/spots/' + spotId + '/comments', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        if (response.status === 401) { window.location.href = '/login'; return; }
        if (!response.ok) {
            var data = await response.json().catch(function () { return {}; });
            alert(data.error || 'Не удалось отправить комментарий');
        }
        await loadComments(spotId);
    } catch (error) { alert('Ошибка сети'); }
}
function openSpot(spot) {
    var content = $('spotSheetContent');
    if (!content) return;
    var isMine = String(spot.owner_id) === String(window.CURRENT_USER_ID || '');
    var photoUrl = safeUrl(spot.photo_url);
    var audioUrl = safeUrl(spot.audio_url);
    var html = '';
    html += '<div class="sheet-handle"></div>';
    html += '<button class="sheet-close" id="spotSheetClose" type="button">✕</button>';
    html += '<h3>' + esc(spot.title) + '</h3>';
    var meta = [];
    if (spot.owner && spot.owner.display_name) meta.push(esc(spot.owner.display_name));
    if (spot.category) meta.push(esc(spot.category));
    if (spot.visibility === 'friends') meta.push('🤝 только друзья');
    else meta.push('🌍 видят все');
    if (spot.expires_at) meta.push('⏳ ' + timeLeft(spot.expires_at));
    if (meta.length) html += '<p class="hint" style="margin-bottom:14px;">' + meta.join(' · ') + '</p>';
    if (photoUrl) html += '<img src="' + esc(photoUrl) + '" alt="" style="width:100%; border-radius:22px; object-fit:cover; max-height:320px; margin-bottom:14px;">';
    if (audioUrl) {
        html += '<div class="audio-player">' +
            '<div class="audio-head">' +
            '<span class="audio-ico">🎧</span>' +
            '<div><div class="audio-title">Атмосфера места</div>' +
            '<div class="audio-hint">Нажмите ▶, чтобы послушать</div></div>' +
            '</div>' +
            '<audio controls preload="none" src="' + esc(audioUrl) + '" style="width:100%; margin-top:8px;"></audio>' +
            '</div>';
    }
    if (spot.description) html += '<p style="margin-bottom:14px;">' + esc(spot.description) + '</p>';
    html += '<div class="section-title">💬 Комментарии</div>';
    html += '<div id="spotComments"></div>';
    html += '<div class="comment-input-row">' +
        '<input class="input" type="text" id="commentInput" maxlength="500" placeholder="Написать комментарий...">' +
        '<button class="btn btn-primary btn-sm" id="sendComment" type="button">➤</button>' +
        '</div>';
    if (isMine) html += '<button class="btn btn-ghost btn-block" id="deleteSpotBtn" type="button" style="margin-top:14px;">🗑 Убрать метку</button>';
    content.innerHTML = html;
    if ($('spotSheetOverlay')) $('spotSheetOverlay').classList.add('open');
    var closeButton = $('spotSheetClose');
    if (closeButton) closeButton.onclick = closeSpotSheet;
    loadComments(spot.id);
    var sendCommentButton = $('sendComment');
    if (sendCommentButton) sendCommentButton.onclick = function () { sendComment(spot.id); };
    var commentInput = $('commentInput');
    if (commentInput) {
        commentInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') { event.preventDefault(); sendComment(spot.id); }
        });
    }
    var deleteButton = $('deleteSpotBtn');
    if (deleteButton) {
        deleteButton.onclick = async function () {
            if (!confirm('Убрать метку?')) return;
            try {
                var response = await fetch('/api/spots/' + spot.id, { method: 'DELETE', credentials: 'same-origin' });
                if (!response.ok) {
                    var data = await response.json().catch(function () { return {}; });
                    alert(data.error || 'Не удалось удалить метку');
                    return;
                }
                closeSpotSheet();
                loadSpots();
            } catch (error) { alert('Ошибка сети'); }
        };
    }
}
function bindUI() {
    var openAddSpot = $('openAddSpot');
    if (openAddSpot) openAddSpot.addEventListener('click', function () { openAddSheet(pendingLat, pendingLng, 'geo'); });
    var closeSheet = $('closeSheet');
    if (closeSheet) closeSheet.addEventListener('click', closeAddSheet);
    var addSpotOverlay = $('addSpotOverlay');
    if (addSpotOverlay) addSpotOverlay.addEventListener('click', function (event) { if (event.target === addSpotOverlay) closeAddSheet(); });
    var spotSheetOverlay = $('spotSheetOverlay');
    if (spotSheetOverlay) spotSheetOverlay.addEventListener('click', function (event) { if (event.target === spotSheetOverlay) closeSpotSheet(); });
    var locateMe = $('locateMe');
    if (locateMe) locateMe.addEventListener('click', function () { locateUser(false); });
    var manualToggle = $('manualToggle');
    var manualBanner = $('manualBanner');
    var manualBannerClose = $('manualBannerClose');
    if (manualToggle && manualBanner) {
        manualToggle.addEventListener('click', function () {
            manualMode = !manualMode;
            manualToggle.classList.toggle('active', manualMode);
            manualBanner.classList.toggle('open', manualMode);
        });
    }
    if (manualBannerClose && manualBanner && manualToggle) {
        manualBannerClose.addEventListener('click', function () {
            manualMode = false;
            manualToggle.classList.remove('active');
            manualBanner.classList.remove('open');
        });
    }
    var legendToggle = $('legendToggle');
    var legendPanel = $('legendPanel');
    if (legendToggle && legendPanel) legendToggle.addEventListener('click', function () { legendPanel.classList.toggle('open'); });
    
    // ---- ЧИП "СВОИ" (НОВОЕ) ----
    var ownToggle = $('ownToggle');
    if (ownToggle) {
        ownToggle.addEventListener('click', function () {
            showOwn = !showOwn;
            ownToggle.classList.toggle('active', showOwn);
            ownToggle.style.background = showOwn ? 'var(--primary)' : '';
            ownToggle.style.color = showOwn ? '#fff' : '';
            applyFilter();
        });
    }
    
    document.querySelectorAll('#categoryScroller .chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            document.querySelectorAll('#categoryScroller .chip').forEach(function (item) { item.classList.remove('selected'); });
            chip.classList.add('selected');
            activeCategory = chip.dataset.cat || '';
            applyFilter();
        });
    });
    document.querySelectorAll('#addCategoryPicker .chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            var alreadySelected = chip.classList.contains('selected');
            document.querySelectorAll('#addCategoryPicker .chip').forEach(function (item) { item.classList.remove('selected'); });
            if (!alreadySelected) {
                chip.classList.add('selected');
                if ($('categoryInput')) $('categoryInput').value = chip.dataset.cat || '';
            } else {
                if ($('categoryInput')) $('categoryInput').value = '';
            }
        });
    });
    document.querySelectorAll('.duration-option').forEach(function (option) {
        option.addEventListener('click', function () {
            document.querySelectorAll('.duration-option').forEach(function (item) { item.classList.remove('selected'); });
            option.classList.add('selected');
            if ($('durationInput')) $('durationInput').value = option.dataset.h || '3';
        });
    });
    document.querySelectorAll('.segmented-item[data-vis]').forEach(function (option) {
        option.addEventListener('click', function () {
            document.querySelectorAll('.segmented-item[data-vis]').forEach(function (item) { item.classList.remove('selected'); });
            option.classList.add('selected');
            if ($('visibilityInput')) $('visibilityInput').value = option.dataset.vis || 'public';
        });
    });
    var photoInput = $('spotPhoto');
    var photoPreview = $('photoPreview');
    var photoDropText = $('photoDropText');
    if (photoInput && photoPreview && photoDropText) {
        photoInput.addEventListener('change', function () {
            var file = this.files && this.files[0];
            if (!file) { photoPreview.src = ''; photoPreview.hidden = true; photoDropText.style.display = 'flex'; return; }
            var url = URL.createObjectURL(file);
            photoPreview.src = url;
            photoPreview.hidden = false;
            photoDropText.style.display = 'none';
        });
    }
    var form = $('addSpotForm');
    if (form) {
        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            var submitButton = $('submitSpotBtn');
            if (submitButton) { submitButton.disabled = true; submitButton.textContent = 'Ставим метку...'; }
            try {
                var formData = new FormData(form);
                var response = await fetch('/api/spots', { method: 'POST', credentials: 'same-origin', body: formData });
                if (response.status === 401) { window.location.href = '/login'; return; }
                if (response.ok) { closeAddSheet(); resetAddForm(); loadSpots(); }
                else {
                    var data = await response.json().catch(function () { return {}; });
                    alert(data.error || 'Не получилось создать метку.');
                }
            } catch (error) { alert('Ошибка сети'); }
            finally { if (submitButton) { submitButton.disabled = false; submitButton.textContent = 'Поставить метку'; } }
        });
    }
}
document.addEventListener('DOMContentLoaded', function () {
    if (!$('map')) return;
    initMap();
    bindUI();
    loadSpots();
    setInterval(function () {
        if (!document.hidden) { loadSpots(); loadOrganizations(); checkDyingSpots(); }
    }, 30000);
    setInterval(function () {
        if (!document.hidden) { checkDyingSpots(); }
    }, 10000);
});
})();