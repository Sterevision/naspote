// ---------------------------------------------------------------
//  НА СПОТЕ v2.0 — логика карты + волны + голосовые + коллабы
// ---------------------------------------------------------------
// ---------------------------------------------------------------
//  TELEGRAM WEB APP — инициализация
// ---------------------------------------------------------------
let tgUser = null;

(function initTelegramWebApp() {
    if (!window.Telegram || !window.Telegram.WebApp) return;

    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    // Применяем тему Telegram к нашему приложению
    if (tg.colorScheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    // Если есть initData — пробуем бесшовный вход
    if (tg.initData && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        tgUser = tg.initDataUnsafe.user;

        // Отправляем initData на сервер для верификации и авто-входа
        fetch('/api/telegram-auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: tg.initData })
        })
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                console.log('Telegram auto-login OK, user:', data.username);
                // Перезагружаем страницу, чтобы сессия подхватилась
                // и сервер отдал map_view вместо login
                if (window.location.pathname === '/' || window.location.pathname === '/login') {
                    window.location.href = '/map';
                }
            }
        })
        .catch(err => console.warn('Telegram auth failed:', err));
    }
})();
let map;
let markersLayer;
let manualModeActive = false;
let selectedOrg = null;
let userCoords = null;
let selectedMood = null;
let waveTimerIntervals = {};

function initMap(centerLat, centerLng) {
    map = L.map('map', { zoomControl: false }).setView([centerLat, centerLng], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap',
    }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);

    map.on('click', (e) => {
        if (manualModeActive) {
            exitManualMode();
            startAddSpotFlow({ lat: e.latlng.lat, lng: e.latlng.lng, placementType: 'manual' });
        }
    });
    loadSpots();
    loadMyAchievements();
}

navigator.geolocation.getCurrentPosition(
    (pos) => {
        userCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        initMap(pos.coords.latitude, pos.coords.longitude);
    },
    () => initMap(55.751244, 37.618423),
    { enableHighAccuracy: true, timeout: 5000 }
);

function timeAgo(iso) {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'только что';
    if (mins < 60) return `${mins} мин назад`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} ч назад`;
    return `${Math.floor(hrs / 24)} дн назад`;
}

function timeLeft(iso) {
    if (!iso) return null;
    const diffMs = new Date(iso).getTime() - Date.now();
    if (diffMs <= 0) return 'исчезает...';
    const mins = Math.floor(diffMs / 60000);
    if (mins < 60) return `${mins} мин`;
    const hrs = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hrs}ч ${remMins ? remMins + 'м' : ''}`.trim();
}

// ---------- Загрузка меток ----------
async function loadSpots() {
    const res = await fetch('/api/spots');
    const spots = await res.json();
    markersLayer.clearLayers();

    // Остановить старые таймеры
    Object.values(waveTimerIntervals).forEach(clearInterval);
    waveTimerIntervals = {};

    spots.forEach((spot) => {
        const isMine = spot.owner_id === window.CURRENT_USER_ID;
        let cls = '';
        if (spot.placement_type === 'manual') cls = 'amber';
        else if (isMine) cls = 'mine';
        else if (spot.visibility === 'friends') cls = 'private';

        // Если это волна — добавляем пульсацию
        const isWave = spot.wave_ends_at && new Date(spot.wave_ends_at) > new Date();
        const waveClass = isWave ? 'wave-marker' : '';

        const icon = L.divIcon({
            className: '',
            html: `<div class="spot-pin ${cls} ${waveClass}"></div>`,
            iconSize: [32, 32],
        });
        const marker = L.marker([spot.lat, spot.lng], { icon }).addTo(markersLayer);
        marker.on('click', () => openSpotSheet(spot));
    });
}

// ---------- Открытие карточки спота ----------
async function openSpotSheet(spot) {
    const owner = spot.owner || {};
    const org = spot.organization || null;
    const isMine = spot.owner_id === window.CURRENT_USER_ID;

    const visBadge = spot.visibility === 'friends'
        ? '<span class="badge badge-private">🔒 Только друзьям</span>'
        : '<span class="badge badge-public">🌍 Открыто всем</span>';
    const liveBadge = spot.is_live ? '<span class="badge badge-live">● Сейчас тут</span>' : '';
    const manualBadge = spot.placement_type === 'manual' ? '<span class="badge badge-manual">✋ Вручную</span>' : '';
    const left = timeLeft(spot.expires_at);
    const timerBadge = left ? `<span class="badge badge-timer">⏳ ${left}</span>` : '';
    const categoryBadge = spot.category ? `<span class="badge badge-category">${spot.category}</span>` : '';
    const moodBadge = spot.mood ? `<span class="badge badge-mood">${spot.mood}</span>` : '';

    const orgBlock = org ? `
        <a href="/profile/${org.username}" class="org-tag-block">
            <span class="org-tag-icon">🏢</span>
            <div>
                <div class="org-tag-name">${org.display_name} ${org.is_verified ? '✅' : ''}</div>
                <div class="org-tag-category">${org.category || 'Заведение'}</div>
            </div>
        </a>` : '';

    const commentsBlock = `
        <div class="comments-block">
            <h4 class="comments-title">Комментарии</h4>
            <div id="commentsList_${spot.id}" class="comments-list"></div>
            <div class="comments-input-row">
                <input type="text" id="commentInput_${spot.id}" placeholder="Написать..." class="comments-input">
                <button class="btn btn-primary btn-sm" onclick="addComment(${spot.id})">➤</button>
            </div>
        </div>
    `;

    // Волна
    const waveBlock = spot.wave_ends_at ? renderWaveTimer(spot) : '';

    // Голосовое
    const voiceBlock = spot.voice_url ? `
        <div class="voice-note">
            <button class="play-btn" onclick="playVoice('${spot.voice_url}')">▶️</button>
            <div class="waveform">🎤 Голосовое сообщение</div>
            <span class="duration">0:15</span>
        </div>` : '';

    // Social proof (загружаем асинхронно)
    const socialBlock = '<div id="socialProofContainer"></div>';

    // Коллабораторы
    const collabBlock = '<div id="collabContainer"></div>';

    document.getElementById('spotSheetContent').innerHTML = `
        ${spot.photo_url ? `<img class="spot-photo" src="${spot.photo_url}">` : ''}
        <div class="spot-header">
            <div class="avatar">${(owner.display_name || '?').slice(0,1).toUpperCase()}</div>
            <div class="spot-owner">
                <span class="name">${owner.display_name || 'Кто-то'}</span>
                <span class="call">зовёт тебя сюда · ${timeAgo(spot.created_at)}</span>
            </div>
        </div>
        <h3 class="spot-title">${spot.title}</h3>
        <p class="spot-desc">${spot.description || ''}</p>
        ${orgBlock}
        ${waveBlock}
        ${voiceBlock}
        ${socialBlock}
        ${collabBlock}
        <div style="display:flex;gap:8px;margin:16px 0;flex-wrap:wrap;">
            ${liveBadge}${visBadge}${manualBadge}${timerBadge}${categoryBadge}${moodBadge}
        </div>
        ${!isMine && !spot.wave_ends_at ? `<button class="btn btn-primary btn-block" onclick="joinCollab(${spot.id})">🤝 Присоединиться</button>` : ''}
        ${isMine ? `<button class="btn btn-ghost btn-block" onclick="deleteSpot(${spot.id})">Убрать метку</button>` : ''}
        ${commentsBlock}
    `;
    document.getElementById('spotSheetOverlay').classList.add('open');

    // Загружаем комментарии, social proof и коллабораторов
    loadComments(spot.id);
    loadSocialProof(spot.id);
    loadCollaborators(spot.id);

    // Запускаем таймер волны если есть
    if (spot.wave_ends_at) {
        startWaveTimer(spot.id, spot.wave_ends_at);
    }
}

// ---------- Комментарии ----------
async function loadComments(spotId) {
    const box = document.getElementById(`commentsList_${spotId}`);
    if (!box) return;
    try {
        const res = await fetch(`/api/spots/${spotId}/comments`);
        const comments = await res.json();
        if (!comments.length) {
            box.innerHTML = '<div class="comments-empty">Пока нет комментариев</div>';
            return;
        }
        box.innerHTML = comments.map(c => `
            <div class="comment-row">
                <span class="comment-author">${(c.user && c.user.display_name) || 'Кто-то'}</span>: ${c.text}
            </div>
        `).join('');
    } catch (e) {
        box.innerHTML = '<div class="comments-empty">Не удалось загрузить комментарии</div>';
    }
}

async function addComment(spotId) {
    const input = document.getElementById(`commentInput_${spotId}`);
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    try {
        await fetch(`/api/spots/${spotId}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        input.value = '';
        loadComments(spotId);
    } catch (e) {
        alert('Не получилось отправить комментарий');
    }
}

function renderWaveTimer(spot) {
    return `
        <div class="wave-timer" id="waveTimer_${spot.id}">
            <div class="wave-icon">🌊</div>
            <div class="wave-countdown" id="waveCountdown_${spot.id}">—</div>
            <div class="wave-progress">
                <div class="wave-bar" id="waveBar_${spot.id}" style="width: 100%"></div>
            </div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:8px;">
                ${spot.wave_max_people ? `Лимит: ${spot.wave_max_people} человек` : 'Волна идёт!'}
            </div>
        </div>
    `;
}

function startWaveTimer(spotId, endsAtIso) {
    const endsAt = new Date(endsAtIso).getTime();
    const startedAt = Date.now();
    const totalDuration = endsAt - startedAt;

    function update() {
        const now = Date.now();
        const remaining = endsAt - now;
        if (remaining <= 0) {
            document.getElementById(`waveCountdown_${spotId}`).textContent = 'Завершено';
            clearInterval(waveTimerIntervals[spotId]);
            return;
        }
        const mins = Math.floor(remaining / 60000);
        const secs = Math.floor((remaining % 60000) / 1000);
        document.getElementById(`waveCountdown_${spotId}`).textContent =
            `${mins}:${secs.toString().padStart(2, '0')}`;
        const pct = (remaining / totalDuration) * 100;
        document.getElementById(`waveBar_${spotId}`).style.width = `${pct}%`;
    }
    update();
    waveTimerIntervals[spotId] = setInterval(update, 1000);
}

async function loadSocialProof(spotId) {
    try {
        const res = await fetch(`/api/spots/${spotId}/social-proof`);
        const data = await res.json();
        const container = document.getElementById('socialProofContainer');
        if (!container) return;

        if (data.friends_count === 0 && data.total_today === 0) {
            container.innerHTML = '';
            return;
        }

        const avatars = (data.friends || []).map(f => {
            const name = f.owner?.display_name || '?';
            const initial = name.slice(0, 1).toUpperCase();
            const img = f.owner?.avatar_url
                ? `<img src="${f.owner.avatar_url}" class="avatar-mini">`
                : `<div class="avatar-mini">${initial}</div>`;
            return img;
        }).join('');

        container.innerHTML = `
            <div class="social-proof">
                <div class="avatars-stack">${avatars}</div>
                <div class="social-text">
                    ${data.friends_count > 0
                        ? `<strong>${data.friends_count} друзей</strong> были здесь сегодня`
                        : `<strong>${data.total_today}</strong> человек отметились`}
                    <span class="muted"> · за 24ч</span>
                </div>
            </div>
        `;
    } catch (e) {
        console.error('social proof error', e);
    }
}

async function loadCollaborators(spotId) {
    try {
        const res = await fetch(`/api/spots/${spotId}/collaborators`);
        const collabs = await res.json();
        const container = document.getElementById('collabContainer');
        if (!container || collabs.length === 0) {
            if (container) container.innerHTML = '';
            return;
        }
        const avatars = collabs.map(c => {
            const name = c.profiles?.display_name || '?';
            const initial = name.slice(0, 1).toUpperCase();
            const img = c.profiles?.avatar_url
                ? `<img src="${c.profiles.avatar_url}" class="collab-avatar">`
                : `<div class="collab-avatar">${initial}</div>`;
            return img;
        }).join('');
        container.innerHTML = `
            <div class="collaborators">
                <div class="collab-avatars">${avatars}</div>
                <div class="collab-text">${collabs.length} человек сейчас тут</div>
            </div>
        `;
    } catch (e) {
        console.error('collabs error', e);
    }
}

async function joinCollab(spotId) {
    try {
        await fetch(`/api/spots/${spotId}/collaborate`, { method: 'POST' });
        loadCollaborators(spotId);
        alert('Ты присоединился к метке! 🎉');
    } catch (e) {
        alert('Не получилось присоединиться');
    }
}

async function deleteSpot(id) {
    if (!confirm('Убрать эту метку с карты?')) return;
    await fetch(`/api/spots/${id}`, { method: 'DELETE' });
    document.getElementById('spotSheetOverlay').classList.remove('open');
    loadSpots();
}

document.getElementById('closeSheet').addEventListener('click', () => {
    document.getElementById('spotSheetOverlay').classList.remove('open');
});
document.getElementById('spotSheetOverlay').addEventListener('click', (e) => {
    if (e.target.id === 'spotSheetOverlay') e.currentTarget.classList.remove('open');
});

// ---------- Голосовые ----------
let mediaRecorder;
let voiceChunks = [];

async function startVoiceRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        voiceChunks = [];
        mediaRecorder.ondataavailable = e => voiceChunks.push(e.data);
        mediaRecorder.onstop = async () => {
            const blob = new Blob(voiceChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('voice', blob, 'voice.webm');
            try {
                const res = await fetch('/api/spots/voice', { method: 'POST', body: formData });
                const { url } = await res.json();
                document.getElementById('voiceUrlInput').value = url;
                document.getElementById('voiceRecordingStatus').textContent = '✅ Голосовое записано';
                document.getElementById('voiceRecordBtn').textContent = '🎤 Записать заново';
            } catch (e) {
                document.getElementById('voiceRecordingStatus').textContent = '❌ Ошибка загрузки';
            }
            stream.getTracks().forEach(t => t.stop());
        };
        mediaRecorder.start();
        document.getElementById('voiceRecordBtn').textContent = '⏹️ Остановить';
        document.getElementById('voiceRecordingStatus').textContent = '🔴 Записываем... (макс 15 сек)';
        setTimeout(() => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }
        }, 15000);
    } catch (e) {
        alert('Нет доступа к микрофону');
    }
}

function stopVoiceRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }
}

document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'voiceRecordBtn') {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            stopVoiceRecording();
        } else {
            startVoiceRecording();
        }
    }
});

function playVoice(url) {
    const audio = new Audio(url);
    audio.play();
}

// ---------- Достижения ----------
async function loadMyAchievements() {
    try {
        const res = await fetch('/api/profile/achievements');
        const data = await res.json();
        // Можно отобразить в topbar, если нужно
        const badge = document.getElementById('levelBadge');
        if (badge && data.level > 1) {
            badge.textContent = `⚡ Lvl ${data.level}`;
            badge.style.display = 'inline-flex';
        }
    } catch (e) {}
}

// ---------- Легенда ----------
document.getElementById('legendBtn').addEventListener('click', () => {
    document.getElementById('legendPanel').classList.toggle('open');
});

// ---------- Ручная расстановка ----------
function enterManualMode() {
    manualModeActive = true;
    document.getElementById('manualModeBanner').classList.add('open');
    document.getElementById('map').style.cursor = 'crosshair';
}
function exitManualMode() {
    manualModeActive = false;
    document.getElementById('manualModeBanner').classList.remove('open');
    document.getElementById('map').style.cursor = '';
}
document.getElementById('openManualAdd').addEventListener('click', enterManualMode);
document.getElementById('cancelManualMode').addEventListener('click', exitManualMode);

// ---------- Добавление метки ----------
document.getElementById('openAddSpot').addEventListener('click', () => {
    navigator.geolocation.getCurrentPosition(
        (pos) => startAddSpotFlow({ lat: pos.coords.latitude, lng: pos.coords.longitude, placementType: 'geo' }),
        () => {
            const c = map.getCenter();
            startAddSpotFlow({ lat: c.lat, lng: c.lng, placementType: 'geo' });
        }
    );
});

function startAddSpotFlow({ lat, lng, placementType }) {
    document.getElementById('latInput').value = lat;
    document.getElementById('lngInput').value = lng;
    document.getElementById('placementTypeInput').value = placementType;

    const title = document.getElementById('addSpotTitle');
    const hint = document.getElementById('addSpotHint');
    if (placementType === 'manual') {
        title.textContent = 'Отметить точку вручную';
        hint.textContent = 'Точка поставлена по клику — выделена жёлтым.';
    } else {
        title.textContent = 'Позови сюда людей';
        hint.textContent = 'Метка появится там, где ты сейчас находишься.';
    }
    searchOrganizations('', lat, lng);
    document.getElementById('addSpotOverlay').classList.add('open');
}

document.getElementById('cancelAddSpot').addEventListener('click', () => {
    document.getElementById('addSpotOverlay').classList.remove('open');
});

document.querySelectorAll('.vis-option').forEach((el) => {
    el.addEventListener('click', () => {
        document.querySelectorAll('.vis-option').forEach((o) => o.classList.remove('selected'));
        el.classList.add('selected');
        document.getElementById('visibilityInput').value = el.dataset.vis;
    });
});

document.querySelectorAll('.duration-option').forEach((el) => {
    el.addEventListener('click', () => {
        document.querySelectorAll('.duration-option').forEach((o) => o.classList.remove('selected'));
        el.classList.add('selected');
        document.getElementById('durationInput').value = el.dataset.h;
    });
});

// ---------- Mood-селектор ----------
document.querySelectorAll('.mood-chip').forEach((el) => {
    el.addEventListener('click', () => {
        document.querySelectorAll('.mood-chip').forEach((o) => o.classList.remove('selected'));
        el.classList.add('selected');
        selectedMood = el.dataset.mood;
        document.getElementById('moodInput').value = selectedMood;

        // Авто-выбор категории на основе mood
        const categories = el.dataset.categories?.split(',') || [];
        if (categories.length > 0) {
            const categorySelect = document.getElementById('categorySelect');
            for (const cat of categories) {
                for (const opt of categorySelect.options) {
                    if (opt.value === cat.trim()) {
                        categorySelect.value = cat.trim();
                        return;
                    }
                }
            }
        }
    });
});

// ---------- Wave toggle ----------
document.getElementById('waveToggle')?.addEventListener('change', (e) => {
    const waveOptions = document.getElementById('waveOptions');
    if (waveOptions) waveOptions.style.display = e.target.checked ? 'block' : 'none';
    const waveEnabledInput = document.getElementById('waveEnabledInput');
    if (waveEnabledInput) waveEnabledInput.value = e.target.checked ? 'true' : 'false';
});

// ---------- Photo ----------
document.getElementById('photoDrop').addEventListener('click', () => {
    document.getElementById('photoInput').click();
});
document.getElementById('photoInput').addEventListener('change', (e) => {
    const file = e.target.files[0];
    document.getElementById('photoLabel').textContent = file ? `✅ ${file.name}` : '📷 Прикрепить фото места';
});

// ---------- Поиск организаций ----------
let orgSearchTimeout;
document.getElementById('orgSearchInput').addEventListener('input', (e) => {
    clearTimeout(orgSearchTimeout);
    const q = e.target.value.trim();
    orgSearchTimeout = setTimeout(() => {
        const lat = document.getElementById('latInput').value;
        const lng = document.getElementById('lngInput').value;
        searchOrganizations(q, lat, lng);
    }, 250);
});

async function searchOrganizations(q, lat, lng) {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (lat) params.set('lat', lat);
    if (lng) params.set('lng', lng);
    const res = await fetch(`/api/organizations/search?${params.toString()}`);
    const orgs = await res.json();
    const box = document.getElementById('orgSearchResults');
    if (!orgs.length) {
        box.innerHTML = q ? '<p class="org-empty">Ничего не найдено</p>' : '';
        return;
    }
    box.innerHTML = orgs.map(o => `
        <div class="org-result-row" onclick='selectOrg(${JSON.stringify(o).replace(/'/g, "&#39;")})'>
            <span class="org-tag-icon">🏢</span>
            <div>
                <div class="org-tag-name">${o.display_name} ${o.is_verified ? '✅' : ''}</div>
                <div class="org-tag-category">${o.category || ''} ${o.address ? '· ' + o.address : ''}</div>
            </div>
        </div>
    `).join('');
}

function selectOrg(org) {
    selectedOrg = org;
    document.getElementById('organizationIdInput').value = org.id;
    document.getElementById('orgSearchInput').style.display = 'none';
    document.getElementById('orgSearchResults').innerHTML = '';
    const chip = document.getElementById('orgSelectedChip');
    chip.style.display = 'flex';
    chip.innerHTML = `<span>🏢 ${org.display_name}</span> <button type="button" onclick="clearOrgSelection()">✕</button>`;
    const categorySelect = document.getElementById('categorySelect');
    if (org.category && !categorySelect.value) {
        categorySelect.value = org.category;
    }
}

function clearOrgSelection() {
    selectedOrg = null;
    document.getElementById('organizationIdInput').value = '';
    document.getElementById('orgSearchInput').style.display = 'block';
    document.getElementById('orgSearchInput').value = '';
    document.getElementById('orgSelectedChip').style.display = 'none';
}

// ---------- Submit формы ----------
document.getElementById('addSpotForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    formData.set('is_live', 'true');

    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Публикуем...';

    try {
        const res = await fetch('/api/spots', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('failed');
        document.getElementById('addSpotOverlay').classList.remove('open');
        form.reset();
        const photoLabel = document.getElementById('photoLabel');
        if (photoLabel) photoLabel.textContent = '📷 Прикрепить фото места';
        document.querySelectorAll('.duration-option').forEach((o) => o.classList.remove('selected'));
        document.querySelector('.duration-option[data-h="6"]')?.classList.add('selected');
        document.querySelectorAll('.mood-chip').forEach((o) => o.classList.remove('selected'));
        const moodInput = document.getElementById('moodInput');
        if (moodInput) moodInput.value = '';
        const voiceUrlInput = document.getElementById('voiceUrlInput');
        if (voiceUrlInput) voiceUrlInput.value = '';
        const voiceStatus = document.getElementById('voiceRecordingStatus');
        if (voiceStatus) voiceStatus.textContent = '';
        const voiceBtn = document.getElementById('voiceRecordBtn');
        if (voiceBtn) voiceBtn.textContent = '🎤 Записать голосовое';
        const waveToggle = document.getElementById('waveToggle');
        if (waveToggle) waveToggle.checked = false;
        const waveOptions = document.getElementById('waveOptions');
        if (waveOptions) waveOptions.style.display = 'none';
        const waveEnabledInput = document.getElementById('waveEnabledInput');
        if (waveEnabledInput) waveEnabledInput.value = 'false';
        clearOrgSelection();
        loadSpots();
        loadMyAchievements();
    } catch (err) {
        alert('Не получилось оставить метку. Попробуй ещё раз.');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Оставить метку';
    }
});