(function () {
    const CURRENT_USER_ID = window.CURRENT_USER_ID;
    let map, userMarker, markersLayer;
    let manualMode = false;
    let pendingLat = null, pendingLng = null;

    // ========== ИНИЦИАЛИЗАЦИЯ КАРТЫ ==========
    function initMap() {
        map = L.map('map', { zoomControl: false, attributionControl: false }).setView([55.751244, 37.618423], 13);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19
        }).addTo(map);
        markersLayer = L.layerGroup().addTo(map);
        L.control.zoom({ position: 'topright' }).addTo(map);

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(function (pos) {
                const lat = pos.coords.latitude, lng = pos.coords.longitude;
                map.setView([lat, lng], 15);
                userMarker = L.circleMarker([lat, lng], {
                    radius: 8, color: '#00f5b5', fillColor: '#00f5b5', fillOpacity: 0.9, weight: 2
                }).addTo(map).bindPopup('Вы здесь');
                pendingLat = lat;
                pendingLng = lng;
            }, function () {
                pendingLat = 55.751244;
                pendingLng = 37.618423;
            });
        }

        map.on('click', function (e) {
            if (manualMode) {
                pendingLat = e.latlng.lat;
                pendingLng = e.latlng.lng;
                manualMode = false;
                document.getElementById('manualModeBanner').classList.remove('open');
                openAddSheet(pendingLat, pendingLng, 'manual');
            }
        });
    }

    // ========== ЗАГРУЗКА СПОТОВ ==========
    async function loadSpots() {
        try {
            const res = await fetch('/api/spots');
            if (!res.ok) return;
            const spots = await res.json();
            markersLayer.clearLayers();
            spots.forEach(function (spot) {
                let color = '#00f5b5';
                let cls = 'spot-pin';
                if (spot.owner_id === CURRENT_USER_ID) { color = '#ff3d81'; cls += ' mine'; }
                else if (spot.visibility === 'friends') { color = '#a78bfa'; cls += ' private'; }
                if (spot.placement_type === 'manual') { color = '#ffb020'; cls += ' amber'; }

                const icon = L.divIcon({
                    className: '',
                    html: '<div class="' + cls + '" style="background:' + color + ';box-shadow:0 0 12px ' + color + ';"></div>',
                    iconSize: [22, 22], iconAnchor: [11, 11]
                });
                const marker = L.marker([spot.lat, spot.lng], { icon: icon }).addTo(markersLayer);
                marker.on('click', function () { openSpotSheet(spot); });
            });
        } catch (e) { console.error('loadSpots error:', e); }
    }

    // ========== ПРОСМОТР СПОТА ==========
    function openSpotSheet(spot) {
        const overlay = document.getElementById('spotSheetOverlay');
        const content = document.getElementById('spotSheetContent');
        const isMine = spot.owner_id === CURRENT_USER_ID;
        let html = '<div class="sheet-handle"></div>';
        html += '<button class="sheet-close" onclick="document.getElementById(\'spotSheetOverlay\').classList.remove(\'open\')">✕</button>';
        html += '<h3 class="display" style="font-size:20px;margin-bottom:4px;">' + escHtml(spot.title) + '</h3>';
        if (spot.owner) {
            html += '<p class="hint" style="margin-bottom:12px;">' + escHtml(spot.owner.display_name || '') + ' · @' + escHtml(spot.owner.username || '') + '</p>';
        }
        if (spot.description) {
            html += '<p style="color:var(--text-secondary);font-size:14px;margin-bottom:12px;">' + escHtml(spot.description) + '</p>';
        }
        if (spot.mood) {
            html += '<p style="font-size:13px;color:var(--text-muted);margin-bottom:8px;">Настроение: ' + escHtml(spot.mood) + '</p>';
        }
        if (spot.category) {
            html += '<span class="chip" style="margin-bottom:12px;">' + escHtml(spot.category) + '</span>';
        }
        if (spot.photo_url) {
            html += '<img src="' + spot.photo_url + '" style="width:100%;border-radius:12px;margin:12px 0;">';
        }
        if (spot.voice_url) {
            html += '<audio controls src="' + spot.voice_url + '" style="width:100%;margin:8px 0;"></audio>';
        }
        html += '<div style="margin-top:16px;">';
        html += '<h4 style="font-size:14px;margin-bottom:8px;">Комментарии</h4>';
        html += '<div id="spotComments" style="max-height:200px;overflow-y:auto;margin-bottom:8px;"></div>';
        html += '<div style="display:flex;gap:8px;">';
        html += '<input type="text" id="commentInput" placeholder="Написать..." style="flex:1;">';
        html += '<button class="btn btn-primary btn-sm" id="sendComment">➤</button>';
        html += '</div></div>';
        if (isMine) {
            html += '<button class="btn btn-ghost btn-block" style="color:var(--pink);margin-top:16px;" id="deleteSpotBtn">🗑 Удалить метку</button>';
        }
        content.innerHTML = html;
        overlay.classList.add('open');

        loadComments(spot.id);

        document.getElementById('sendComment').addEventListener('click', function () {
            sendComment(spot.id);
        });
        if (isMine) {
            document.getElementById('deleteSpotBtn').addEventListener('click', function () {
                deleteSpot(spot.id);
            });
        }
    }

    async function loadComments(spotId) {
        try {
            const res = await fetch('/api/spots/' + spotId + '/comments');
            const comments = await res.json();
            const container = document.getElementById('spotComments');
            if (!container) return;
            if (!comments.length) {
                container.innerHTML = '<p style="color:var(--text-faint);font-size:13px;">Пока нет комментариев</p>';
                return;
            }
            container.innerHTML = comments.map(function (c) {
                const name = c.user ? c.user.display_name : 'Аноним';
                return '<div style="margin-bottom:8px;"><strong style="font-size:13px;">' + escHtml(name) + '</strong><p style="font-size:13px;color:var(--text-secondary);">' + escHtml(c.text) + '</p></div>';
            }).join('');
        } catch (e) { }
    }

    async function sendComment(spotId) {
        const input = document.getElementById('commentInput');
        const text = input.value.trim();
        if (!text) return;
        try {
            await fetch('/api/spots/' + spotId + '/comments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            input.value = '';
            loadComments(spotId);
        } catch (e) { }
    }

    async function deleteSpot(spotId) {
        if (!confirm('Удалить метку?')) return;
        try {
            await fetch('/api/spots/' + spotId, { method: 'DELETE' });
            document.getElementById('spotSheetOverlay').classList.remove('open');
            loadSpots();
        } catch (e) { }
    }

    // ========== ДОБАВЛЕНИЕ СПОТА ==========
    function openAddSheet(lat, lng, placementType) {
        document.getElementById('latInput').value = lat;
        document.getElementById('lngInput').value = lng;
        document.getElementById('placementTypeInput').value = placementType || 'geo';
        document.getElementById('addSpotOverlay').classList.add('open');
    }

    function initAddForm() {
        // Кнопки открытия
        document.getElementById('openAddSpot').addEventListener('click', function () {
            openAddSheet(pendingLat || 55.751244, pendingLng || 37.618423, 'geo');
        });
        document.getElementById('openManualAdd').addEventListener('click', function () {
            manualMode = true;
            document.getElementById('manualModeBanner').classList.add('open');
        });
        document.getElementById('cancelManualMode').addEventListener('click', function () {
            manualMode = false;
            document.getElementById('manualModeBanner').classList.remove('open');
        });

        // Закрытие
        document.getElementById('closeSheet').addEventListener('click', closeAddSheet);
        document.getElementById('cancelAddSpot').addEventListener('click', closeAddSheet);
        document.getElementById('addSpotOverlay').addEventListener('click', function (e) {
            if (e.target === this) closeAddSheet();
        });
        document.getElementById('spotSheetOverlay').addEventListener('click', function (e) {
            if (e.target === this) this.classList.remove('open');
        });

        // Длительность
        document.querySelectorAll('.duration-option').forEach(function (opt) {
            opt.addEventListener('click', function () {
                document.querySelectorAll('.duration-option').forEach(function (o) { o.classList.remove('selected'); });
                opt.classList.add('selected');
                document.getElementById('durationInput').value = opt.dataset.h;
            });
        });

        // Настроение
        document.querySelectorAll('.mood-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                document.querySelectorAll('.mood-chip').forEach(function (c) { c.classList.remove('selected'); });
                chip.classList.add('selected');
                document.getElementById('moodInput').value = chip.dataset.mood;
                var cats = (chip.dataset.categories || '').split(',');
                var sel = document.getElementById('categorySelect');
                if (cats.length && cats[0]) {
                    for (var i = 0; i < sel.options.length; i++) {
                        if (cats.indexOf(sel.options[i].value) !== -1) { sel.selectedIndex = i; break; }
                    }
                }
            });
        });

        // Видимость
        document.querySelectorAll('.vis-option').forEach(function (opt) {
            opt.addEventListener('click', function () {
                document.querySelectorAll('.vis-option').forEach(function (o) { o.classList.remove('selected'); });
                opt.classList.add('selected');
                document.getElementById('visibilityInput').value = opt.dataset.vis;
            });
        });

        // Волна
        document.getElementById('waveToggle').addEventListener('change', function () {
            document.getElementById('waveOptions').style.display = this.checked ? 'block' : 'none';
            document.getElementById('waveEnabledInput').value = this.checked ? 'true' : 'false';
        });

        // Фото
        document.getElementById('photoDrop').addEventListener('click', function () {
            document.getElementById('photoInput').click();
        });
        document.getElementById('photoInput').addEventListener('change', function () {
            if (this.files.length) {
                document.getElementById('photoLabel').textContent = '📎 ' + this.files[0].name;
            }
        });

        // Поиск организаций
        var orgTimeout;
        document.getElementById('orgSearchInput').addEventListener('input', function () {
            clearTimeout(orgTimeout);
            var q = this.value.trim();
            var results = document.getElementById('orgSearchResults');
            if (!q) { results.innerHTML = ''; return; }
            orgTimeout = setTimeout(async function () {
                try {
                    var res = await fetch('/api/organizations/search?q=' + encodeURIComponent(q));
                    var orgs = await res.json();
                    results.innerHTML = orgs.map(function (o) {
                        return '<div class="org-result" data-id="' + o.id + '" data-name="' + escHtml(o.display_name) + '">' +
                            '<strong>' + escHtml(o.display_name) + '</strong>' +
                            (o.category ? ' · ' + escHtml(o.category) : '') +
                            (o.address ? '<br><small>' + escHtml(o.address) + '</small>' : '') +
                            '</div>';
                    }).join('');
                    results.querySelectorAll('.org-result').forEach(function (el) {
                        el.addEventListener('click', function () {
                            document.getElementById('organizationIdInput').value = el.dataset.id;
                            document.getElementById('orgSelectedChip').textContent = '🏢 ' + el.dataset.name;
                            document.getElementById('orgSelectedChip').style.display = 'block';
                            document.getElementById('orgSearchInput').value = '';
                            results.innerHTML = '';
                        });
                    });
                } catch (e) { }
            }, 300);
        });

        // Отправка формы
        document.getElementById('addSpotForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            var formData = new FormData(this);
            try {
                var res = await fetch('/api/spots', { method: 'POST', body: formData });
                if (res.ok) {
                    closeAddSheet();
                    this.reset();
                    loadSpots();
                } else {
                    var err = await res.json();
                    alert(err.error || 'Ошибка');
                }
            } catch (e) { alert('Ошибка сети'); }
        });
    }

    function closeAddSheet() {
        document.getElementById('addSpotOverlay').classList.remove('open');
    }

    // ========== ЛЕГЕНДА ==========
    function initLegend() {
        var btn = document.getElementById('legendBtn');
        var panel = document.getElementById('legendPanel');
        if (btn && panel) {
            btn.addEventListener('click', function () {
                panel.classList.toggle('open');
            });
        }
    }

    // ========== УТИЛИТЫ ==========
    function escHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ========== ЗАПУСК ==========
    document.addEventListener('DOMContentLoaded', function () {
        initMap();
        loadSpots();
        initAddForm();
        initLegend();
        setInterval(loadSpots, 30000);
    });
})();