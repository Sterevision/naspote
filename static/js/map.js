(function () {
    var map, markersLayer, pendingLat = 55.75, pendingLng = 37.62;
    var manualMode = false, allSpots = [], activeCategory = '';
    var mediaRecorder, audioChunks = [], voiceBlobUrl = null, recordTimer = null;

    function esc(str) { var d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }

    function initMap() {
        map = L.map('map', { zoomControl: false }).setView([55.75, 37.62], 13);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertile/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(map);
        L.control.zoom({ position: 'topright' }).addTo(map);
        markersLayer = L.layerGroup().addTo(map);

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(function (pos) {
                pendingLat = pos.coords.latitude; pendingLng = pos.coords.longitude;
                map.setView([pendingLat, pendingLng], 15);
                var icon = L.divIcon({ className: '', html: '<div class="you-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
                L.marker([pendingLat, pendingLng], { icon: icon, zIndexOffset: 1000 }).addTo(map);
            });
        }

        map.on('click', function (e) {
            if (!manualMode) return;
            pendingLat = e.latlng.lat; pendingLng = e.latlng.lng;
            document.getElementById('latInput').value = pendingLat;
            document.getElementById('lngInput').value = pendingLng;
            document.getElementById('placementInput').value = 'manual';
            document.getElementById('manualHint').style.display = 'block';
            document.getElementById('addSpotOverlay').classList.add('open');
        });
    }

    function timeLeft(iso) {
        if (!iso) return null;
        var diff = new Date(iso) - new Date();
        if (diff <= 0) return 'истекает';
        var h = Math.floor(diff / 3600000), m = Math.floor((diff % 3600000) / 60000);
        return h > 0 ? h + 'ч ' + m + 'м' : m + 'м';
    }

    function pinColorAndClass(s) {
        var cls = 'spot-pin';
        var color;
        if (s.owner_id === window.CURRENT_USER_ID) color = 'var(--mine)';
        else if (s.visibility === 'friends') color = 'var(--friends)';
        else color = 'var(--public)';
        if (s.placement_type === 'manual') color = 'var(--manual)';
        if (s.wave_ends_at) cls += ' is-wave';
        return { color: color, cls: cls };
    }

    function applyFilter() {
        markersLayer.clearLayers();
        allSpots.filter(function (s) { return !activeCategory || s.category === activeCategory; }).forEach(function (s) {
            var pc = pinColorAndClass(s);
            var icon = L.divIcon({
                className: '', iconSize: [30, 30], iconAnchor: [15, 15],
                html: '<div class="' + pc.cls + '" style="background:' + pc.color + ';color:' + pc.color + '"></div>'
            });
            L.marker([s.lat, s.lng], { icon: icon }).addTo(markersLayer).on('click', function () { openSpot(s); });
        });
    }

    async function loadSpots() {
        try {
            var res = await fetch('/api/spots');
            if (!res.ok) return;
            allSpots = await res.json();
            applyFilter();
        } catch (e) { }
    }

    function closeSpotSheet() { document.getElementById('spotSheetOverlay').classList.remove('open'); }

    function openSpot(s) {
        var html = '<div class="sheet-handle"></div>';
        html += '<button class="sheet-close" onclick="document.getElementById(\'spotSheetOverlay\').classList.remove(\'open\')">✕</button>';
        html += '<h3>' + esc(s.title) + '</h3>';
        var metaBits = [];
        if (s.owner) metaBits.push(esc(s.owner.display_name || ''));
        if (s.organization) metaBits.push('📍 ' + esc(s.organization.display_name) + (s.organization.is_verified ? ' ✅' : ''));
        if (s.category) metaBits.push(esc(s.category));
        if (metaBits.length) html += '<p class="hint" style="margin-bottom:10px;">' + metaBits.join(' · ') + '</p>';
        if (s.wave_ends_at) html += '<p style="font-size:13px;font-weight:700;color:var(--wave);margin-bottom:8px;">⚡ Волна · осталось ' + timeLeft(s.wave_ends_at) + (s.wave_max_people ? ' · до ' + s.wave_max_people + ' человек' : '') + '</p>';
        if (s.mood) html += '<p style="font-size:18px;margin-bottom:8px;">' + esc(s.mood) + '</p>';
        if (s.description) html += '<p style="margin-bottom:12px;">' + esc(s.description) + '</p>';
        if (s.photo_url) html += '<img src="' + s.photo_url + '" style="width:100%;border-radius:14px;margin-bottom:12px;">';
        if (s.voice_url) html += '<audio controls src="' + s.voice_url + '" style="width:100%;margin-bottom:12px;"></audio>';

        if (s.organization_id) html += '<div id="socialProof"></div>';
        if (s.wave_ends_at) {
            html += '<div id="collabBox"></div>';
            if (s.owner_id !== window.CURRENT_USER_ID) html += '<button class="btn btn-soft btn-block" id="joinWaveBtn" style="margin-top:4px;">⚡ Я тоже здесь</button>';
        }

        html += '<div class="section-title">Комментарии</div><div id="spotComments"></div>';
        html += '<div style="display:flex;gap:8px;margin-top:10px;"><input type="text" id="commentInput" placeholder="Написать..." style="flex:1;padding:12px 16px;border:1.5px solid var(--line);border-radius:999px;"><button class="btn btn-primary btn-sm" id="sendComment">➤</button></div>';
        if (s.owner_id === window.CURRENT_USER_ID) html += '<button class="btn btn-soft btn-block" style="margin-top:14px;" id="deleteSpot">🗑 Убрать метку</button>';

        document.getElementById('spotSheetContent').innerHTML = html;
        document.getElementById('spotSheetOverlay').classList.add('open');

        loadComments(s.id);
        document.getElementById('sendComment').onclick = function () { sendComment(s.id); };
        document.getElementById('commentInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') sendComment(s.id); });

        if (s.organization_id) loadSocialProof(s.id);
        if (s.wave_ends_at) {
            loadCollaborators(s.id);
            var joinBtn = document.getElementById('joinWaveBtn');
            if (joinBtn) joinBtn.onclick = async function () {
                joinBtn.disabled = true; joinBtn.textContent = '✓ Вы в деле';
                await fetch('/api/spots/' + s.id + '/collaborate', { method: 'POST' });
                loadCollaborators(s.id);
            };
        }
        if (s.owner_id === window.CURRENT_USER_ID) {
            document.getElementById('deleteSpot').onclick = async function () {
                if (!confirm('Убрать метку?')) return;
                await fetch('/api/spots/' + s.id, { method: 'DELETE' });
                closeSpotSheet();
                loadSpots();
            };
        }
    }

    async function loadSocialProof(id) {
        try {
            var res = await fetch('/api/spots/' + id + '/social-proof');
            var d = await res.json();
            var box = document.getElementById('socialProof');
            if (!box) return;
            if (d.total_today === 0) return;
            var txt = '<b>' + d.total_today + '</b> ' + pluralize(d.total_today, 'человек был', 'человека были', 'человек были') + ' здесь сегодня';
            if (d.friends_count > 0) txt += ', из них <b>' + d.friends_count + '</b> ' + pluralize(d.friends_count, 'друг', 'друга', 'друзей');
            box.innerHTML = '<div class="social-proof-banner"><span style="font-size:20px;">🔥</span><span class="txt">' + txt + '</span></div>';
        } catch (e) {}
    }

    function pluralize(n, one, few, many) {
        n = Math.abs(n) % 100; var n1 = n % 10;
        if (n > 10 && n < 20) return many;
        if (n1 > 1 && n1 < 5) return few;
        if (n1 === 1) return one;
        return many;
    }

    async function loadCollaborators(id) {
        try {
            var res = await fetch('/api/spots/' + id + '/collaborators');
            var list = await res.json();
            var box = document.getElementById('collabBox');
            if (!box) return;
            if (!list.length) { box.innerHTML = ''; return; }
            box.innerHTML = '<div class="avatar-stack">' + list.slice(0, 6).map(function (c) {
                var p = c.profiles || {};
                return '<div class="avatar">' + (p.avatar_url ? '<img src="' + p.avatar_url + '">' : (p.display_name || '?')[0].toUpperCase()) + '</div>';
            }).join('') + '</div><p class="hint" style="margin-top:6px;">' + list.length + ' ' + pluralize(list.length, 'человек присоединился', 'человека присоединились', 'человек присоединились') + '</p>';
        } catch (e) {}
    }

    async function loadComments(id) {
        try {
            var res = await fetch('/api/spots/' + id + '/comments');
            var list = await res.json();
            var box = document.getElementById('spotComments');
            box.innerHTML = list.length ? list.map(function (c) {
                return '<div class="row-card" style="padding:10px 14px;"><div class="avatar" style="width:32px;height:32px;font-size:12px;">' + (c.user ? (c.user.display_name || '?')[0].toUpperCase() : '?') + '</div><div class="info"><div class="name" style="font-size:14px;">' + esc(c.user ? c.user.display_name : '') + '</div><div class="sub">' + esc(c.text) + '</div></div></div>';
            }).join('') : '<p class="hint">Пока нет комментариев</p>';
        } catch (e) { }
    }

    async function sendComment(id) {
        var input = document.getElementById('commentInput');
        var text = input.value.trim();
        if (!text) return;
        input.value = '';
        await fetch('/api/spots/' + id + '/comments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
        loadComments(id);
    }

    /* ---------- запись голосовой заметки ---------- */
    function setupVoiceRecorder() {
        var btn = document.getElementById('voiceBtn');
        var status = document.getElementById('voiceStatus');
        btn.addEventListener('click', async function () {
            if (btn.classList.contains('recording')) {
                mediaRecorder.stop();
                return;
            }
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                status.textContent = 'Микрофон недоступен в этом браузере'; return;
            }
            try {
                var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                audioChunks = [];
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = function (e) { audioChunks.push(e.data); };
                mediaRecorder.onstop = async function () {
                    stream.getTracks().forEach(function (t) { t.stop(); });
                    btn.classList.remove('recording'); btn.textContent = '🎙️';
                    clearTimeout(recordTimer);
                    status.textContent = 'Загружаем...';
                    var blob = new Blob(audioChunks, { type: 'audio/webm' });
                    var fd = new FormData();
                    fd.append('voice', blob, 'voice.webm');
                    var res = await fetch('/api/spots/voice', { method: 'POST', body: fd });
                    if (res.ok) {
                        var data = await res.json();
                        document.getElementById('voiceUrlInput').value = data.url;
                        status.textContent = '✓ Записано'; status.classList.add('ready');
                    } else {
                        status.textContent = 'Не получилось записать';
                    }
                };
                mediaRecorder.start();
                btn.classList.add('recording'); btn.textContent = '⏹️';
                status.textContent = 'Идёт запись... нажмите ещё раз, чтобы остановить';
                recordTimer = setTimeout(function () { if (mediaRecorder.state === 'recording') mediaRecorder.stop(); }, 15000);
            } catch (e) {
                status.textContent = 'Доступ к микрофону не дан';
            }
        });
    }

    /* ---------- поиск заведения для привязки ---------- */
    function setupOrgSearch() {
        var input = document.getElementById('orgSearchInput');
        var results = document.getElementById('orgResults');
        var chip = document.getElementById('orgChip');
        var t;
        input.addEventListener('input', function () {
            clearTimeout(t);
            var q = this.value.trim();
            if (!q) { results.innerHTML = ''; return; }
            t = setTimeout(async function () {
                var url = '/api/organizations/search?q=' + encodeURIComponent(q) + '&lat=' + pendingLat + '&lng=' + pendingLng;
                var res = await fetch(url);
                var orgs = await res.json();
                results.innerHTML = orgs.map(function (o) {
                    return '<div class="org-result-row" data-id="' + o.id + '" data-name="' + esc(o.display_name) + '">' + esc(o.display_name) + '<span class="hint"> · ' + esc(o.category || '') + '</span></div>';
                }).join('');
                results.querySelectorAll('.org-result-row').forEach(function (row) {
                    row.addEventListener('click', function () {
                        document.getElementById('orgIdInput').value = row.dataset.id;
                        chip.innerHTML = '<span class="org-selected-chip">📍 ' + esc(row.dataset.name) + ' <button type="button" id="orgChipRemove">✕</button></span>';
                        document.getElementById('orgChipRemove').onclick = function () { chip.innerHTML = ''; document.getElementById('orgIdInput').value = ''; };
                        input.value = ''; results.innerHTML = '';
                    });
                });
            }, 300);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initMap(); loadSpots(); setInterval(loadSpots, 30000);
        setupVoiceRecorder(); setupOrgSearch();

        document.getElementById('openAddSpot').addEventListener('click', function () {
            document.getElementById('latInput').value = pendingLat;
            document.getElementById('lngInput').value = pendingLng;
            document.getElementById('placementInput').value = 'geo';
            document.getElementById('manualHint').style.display = 'none';
            document.getElementById('addSpotOverlay').classList.add('open');
        });
        document.getElementById('closeSheet').addEventListener('click', function () {
            document.getElementById('addSpotOverlay').classList.remove('open');
        });
        document.getElementById('spotSheetOverlay').addEventListener('click', function (e) {
            if (e.target === this) closeSpotSheet();
        });
        document.getElementById('addSpotOverlay').addEventListener('click', function (e) {
            if (e.target === this) this.classList.remove('open');
        });

        document.getElementById('locateMe').addEventListener('click', function () {
            if (!navigator.geolocation) return;
            navigator.geolocation.getCurrentPosition(function (pos) {
                pendingLat = pos.coords.latitude; pendingLng = pos.coords.longitude;
                map.setView([pendingLat, pendingLng], 15);
            });
        });

        var manualToggle = document.getElementById('manualToggle');
        var manualBanner = document.getElementById('manualBanner');
        manualToggle.addEventListener('click', function () {
            manualMode = !manualMode;
            manualToggle.classList.toggle('active', manualMode);
            manualBanner.classList.toggle('open', manualMode);
        });
        document.getElementById('manualBannerClose').addEventListener('click', function () {
            manualMode = false; manualToggle.classList.remove('active'); manualBanner.classList.remove('open');
        });

        document.getElementById('legendToggle').addEventListener('click', function () {
            document.getElementById('legendPanel').classList.toggle('open');
        });

        document.querySelectorAll('#categoryScroller .cat-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                document.querySelectorAll('#categoryScroller .cat-chip').forEach(function (c) { c.classList.remove('selected'); });
                chip.classList.add('selected');
                activeCategory = chip.dataset.cat;
                applyFilter();
            });
        });
        document.querySelectorAll('#addCategoryPicker .cat-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                var already = chip.classList.contains('selected');
                document.querySelectorAll('#addCategoryPicker .cat-chip').forEach(function (c) { c.classList.remove('selected'); });
                if (!already) { chip.classList.add('selected'); document.getElementById('categoryInput').value = chip.dataset.cat; }
                else { document.getElementById('categoryInput').value = ''; }
            });
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
                var already = o.classList.contains('selected');
                document.querySelectorAll('.mood-chip').forEach(function (x) { x.classList.remove('selected'); });
                if (!already) { o.classList.add('selected'); document.getElementById('moodInput').value = o.dataset.mood; }
                else { document.getElementById('moodInput').value = ''; }
            });
        });
        document.querySelectorAll('.vis-option').forEach(function (o) {
            o.addEventListener('click', function () {
                document.querySelectorAll('.vis-option').forEach(function (x) { x.classList.remove('selected'); });
                o.classList.add('selected');
                document.getElementById('visibilityInput').value = o.dataset.vis;
            });
        });

        document.getElementById('waveToggle').addEventListener('change', function () {
            document.getElementById('waveOptions').style.display = this.checked ? 'block' : 'none';
        });

        document.getElementById('addSpotForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            var btn = document.getElementById('submitSpotBtn');
            btn.disabled = true; btn.textContent = 'Ставим метку...';
            var res = await fetch('/api/spots', { method: 'POST', body: new FormData(this) });
            btn.disabled = false; btn.textContent = 'Поставить метку';
            if (res.ok) {
                document.getElementById('addSpotOverlay').classList.remove('open');
                this.reset();
                document.getElementById('orgChip').innerHTML = '';
                document.getElementById('waveOptions').style.display = 'none';
                document.querySelectorAll('#addCategoryPicker .cat-chip, .mood-chip').forEach(function (c) { c.classList.remove('selected'); });
                document.querySelectorAll('.duration-option').forEach(function (x) { x.classList.remove('selected'); });
                document.querySelector('.duration-option[data-h="3"]').classList.add('selected');
                document.querySelectorAll('.vis-option').forEach(function (x) { x.classList.remove('selected'); });
                document.querySelector('.vis-option[data-vis="public"]').classList.add('selected');
                document.getElementById('voiceStatus').textContent = 'Нажмите, чтобы записать 15 секунд';
                document.getElementById('voiceStatus').classList.remove('ready');
                loadSpots();
            } else {
                var err = await res.json();
                alert(err.error || 'Не получилось. Попробуйте ещё раз.');
            }
        });
    });
})();
