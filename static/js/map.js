(function () {
    'use strict';

    var map;
    var markersLayer;

    var pendingLat = 55.75;
    var pendingLng = 37.62;

    var manualMode = false;
    var allSpots = [];
    var activeCategory = '';

    var mediaRecorder = null;
    var audioChunks = [];
    var recordTimer = null;

    function $(id) {
        return document.getElementById(id);
    }

    function esc(value) {
        var div = document.createElement('div');
        div.textContent = value === null || value === undefined ? '' : String(value);
        return div.innerHTML;
    }

    function safeUrl(url) {
        if (!url) {
            return '';
        }

        var value = String(url);

        if (/^https?:\/\//i.test(value)) {
            return value;
        }

        return '';
    }

    function timeLeft(iso) {
        if (!iso) {
            return '';
        }

        var diff = new Date(iso) - new Date();

        if (diff <= 0) {
            return 'завершилась';
        }

        var hours = Math.floor(diff / 3600000);
        var minutes = Math.floor((diff % 3600000) / 60000);

        if (hours > 0) {
            return hours + 'ч ' + minutes + 'м';
        }

        if (minutes > 0) {
            return minutes + 'м';
        }

        return 'меньше минуты';
    }

    function pluralize(n, one, few, many) {
        n = Math.abs(n) % 100;
        var n1 = n % 10;

        if (n > 10 && n < 20) {
            return many;
        }

        if (n1 > 1 && n1 < 5) {
            return few;
        }

        if (n1 === 1) {
            return one;
        }

        return many;
    }

    function pinColorAndClass(spot) {
        var cls = 'spot-pin';
        var color;

        if (String(spot.owner_id) === String(window.CURRENT_USER_ID || '')) {
            color = 'var(--mine)';
        } else if (spot.visibility === 'friends') {
            color = 'var(--friends)';
        } else {
            color = 'var(--public)';
        }

        if (spot.placement_type === 'manual') {
            color = 'var(--manual)';
        }

        if (spot.wave_ends_at) {
            cls += ' is-wave';
        }

        return {
            color: color,
            cls: cls
        };
    }

    function initMap() {
        var mapElement = $('map');

        if (!mapElement) {
            return;
        }

        map = L.map('map', {
            zoomControl: false
        }).setView([55.75, 37.62], 13);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertile/voyager/{z}/{x}/{y}{r}.png', {
            maxZoom: 19
        }).addTo(map);

        L.control.zoom({
            position: 'topright'
        }).addTo(map);

        markersLayer = L.layerGroup().addTo(map);

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(function (position) {
                pendingLat = position.coords.latitude;
                pendingLng = position.coords.longitude;

                map.setView([pendingLat, pendingLng], 15);

                var icon = L.divIcon({
                    className: '',
                    html: '<div class="you-dot"></div>',
                    iconSize: [18, 18],
                    iconAnchor: [9, 9]
                });

                L.marker([pendingLat, pendingLng], {
                    icon: icon,
                    zIndexOffset: 1000
                }).addTo(map);
            });
        }

        map.on('click', function (event) {
            if (!manualMode) {
                return;
            }

            pendingLat = event.latlng.lat;
            pendingLng = event.latlng.lng;

            if ($('latInput')) {
                $('latInput').value = pendingLat;
            }

            if ($('lngInput')) {
                $('lngInput').value = pendingLng;
            }

            if ($('placementInput')) {
                $('placementInput').value = 'manual';
            }

            if ($('manualHint')) {
                $('manualHint').style.display = 'block';
            }

            if ($('addSpotOverlay')) {
                $('addSpotOverlay').classList.add('open');
            }
        });
    }

    function applyFilter() {
        if (!markersLayer) {
            return;
        }

        markersLayer.clearLayers();

        allSpots
            .filter(function (spot) {
                return !activeCategory || spot.category === activeCategory;
            })
            .forEach(function (spot) {
                var pin = pinColorAndClass(spot);

                var icon = L.divIcon({
                    className: '',
                    iconSize: [30, 30],
                    iconAnchor: [15, 15],
                    html: '<div class="' + pin.cls + '" style="background:' + pin.color + ';color:' + pin.color + '"></div>'
                });

                L.marker([spot.lat, spot.lng], {
                    icon: icon
                })
                    .addTo(markersLayer)
                    .on('click', function () {
                        openSpot(spot);
                    });
            });
    }

    async function loadSpots() {
        try {
            var response = await fetch('/api/spots', {
                credentials: 'same-origin'
            });

            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }

            if (!response.ok) {
                return;
            }

            allSpots = await response.json();
            applyFilter();
        } catch (error) {
            // silent
        }
    }

    function closeSpotSheet() {
        var overlay = $('spotSheetOverlay');

        if (overlay) {
            overlay.classList.remove('open');
        }
    }

    function openSpot(spot) {
        var html = '';

        html += '<div class="sheet-handle"></div>';
        html += '<button class="sheet-close" id="spotSheetClose" type="button">✕</button>';
        html += '<h3>' + esc(spot.title) + '</h3>';

        var metaBits = [];

        if (spot.owner && spot.owner.display_name) {
            metaBits.push(esc(spot.owner.display_name));
        }

        if (spot.organization && spot.organization.display_name) {
            metaBits.push('📍 ' + esc(spot.organization.display_name) + (spot.organization.is_verified ? ' ✅' : ''));
        }

        if (spot.category) {
            metaBits.push(esc(spot.category));
        }

        if (metaBits.length) {
            html += '<p class="hint" style="margin-bottom:10px;">' + metaBits.join(' · ') + '</p>';
        }

        if (spot.wave_ends_at) {
            html += '<p style="font-size:13px;font-weight:700;color:var(--wave);margin-bottom:8px;">';
            html += '⚡ Волна · ' + timeLeft(spot.wave_ends_at);

            if (spot.wave_max_people) {
                html += ' · до ' + esc(spot.wave_max_people) + ' человек';
            }

            html += '</p>';
        }

        if (spot.mood) {
            html += '<p style="font-size:18px;margin-bottom:8px;">' + esc(spot.mood) + '</p>';
        }

        if (spot.description) {
            html += '<p style="margin-bottom:12px;">' + esc(spot.description) + '</p>';
        }

        var photoUrl = safeUrl(spot.photo_url);

        if (photoUrl) {
            html += '<img src="' + esc(photoUrl) + '" alt="" style="width:100%;border-radius:14px;margin-bottom:12px;">';
        }

        var voiceUrl = safeUrl(spot.voice_url);

        if (voiceUrl) {
            html += '<audio controls src="' + esc(voiceUrl) + '" style="width:100%;margin-bottom:12px;"></audio>';
        }

        if (spot.organization_id) {
            html += '<div id="socialProof"></div>';
        }

        if (spot.wave_ends_at) {
            html += '<div id="collabBox"></div>';

            var waveStillActive = new Date(spot.wave_ends_at) > new Date();

            if (waveStillActive && String(spot.owner_id) !== String(window.CURRENT_USER_ID || '')) {
                html += '<button class="btn btn-soft btn-block" id="joinWaveBtn" style="margin-top:4px;">⚡ Я тоже здесь</button>';
            }
        }

        html += '<div class="section-title">Комментарии</div>';
        html += '<div id="spotComments"></div>';

        html += '<div style="display:flex;gap:8px;margin-top:10px;">';
        html += '<input type="text" id="commentInput" placeholder="Написать..." maxlength="500" style="flex:1;padding:12px 16px;border:1.5px solid var(--line);border-radius:999px;">';
        html += '<button class="btn btn-primary btn-sm" id="sendComment" type="button">➤</button>';
        html += '</div>';

        if (String(spot.owner_id) === String(window.CURRENT_USER_ID || '')) {
            html += '<button class="btn btn-soft btn-block" style="margin-top:14px;" id="deleteSpot" type="button">🗑 Убрать метку</button>';
        }

        var content = $('spotSheetContent');

        if (!content) {
            return;
        }

        content.innerHTML = html;

        var overlay = $('spotSheetOverlay');

        if (overlay) {
            overlay.classList.add('open');
        }

        var closeButton = $('spotSheetClose');

        if (closeButton) {
            closeButton.onclick = closeSpotSheet;
        }

        loadComments(spot.id);

        var sendCommentButton = $('sendComment');

        if (sendCommentButton) {
            sendCommentButton.onclick = function () {
                sendComment(spot.id);
            };
        }

        var commentInput = $('commentInput');

        if (commentInput) {
            commentInput.addEventListener('keydown', function (event) {
                if (event.key === 'Enter') {
                    sendComment(spot.id);
                }
            });
        }

        if (spot.organization_id) {
            loadSocialProof(spot.id);
        }

        if (spot.wave_ends_at) {
            loadCollaborators(spot.id);

            var joinButton = $('joinWaveBtn');

            if (joinButton) {
                joinButton.onclick = async function () {
                    joinButton.disabled = true;
                    joinButton.textContent = '✓ Вы в деле';

                    try {
                        var response = await fetch('/api/spots/' + spot.id + '/collaborate', {
                            method: 'POST',
                            credentials: 'same-origin'
                        });

                        if (!response.ok) {
                            var errorData = await response.json().catch(function () {
                                return {};
                            });

                            alert(errorData.error || 'Не удалось присоединиться');
                            joinButton.disabled = false;
                            joinButton.textContent = '⚡ Я тоже здесь';
                            return;
                        }

                        loadCollaborators(spot.id);
                    } catch (error) {
                        alert('Ошибка сети');
                        joinButton.disabled = false;
                        joinButton.textContent = '⚡ Я тоже здесь';
                    }
                };
            }
        }

        if (String(spot.owner_id) === String(window.CURRENT_USER_ID || '')) {
            var deleteButton = $('deleteSpot');

            if (deleteButton) {
                deleteButton.onclick = async function () {
                    if (!confirm('Убрать метку?')) {
                        return;
                    }

                    try {
                        var response = await fetch('/api/spots/' + spot.id, {
                            method: 'DELETE',
                            credentials: 'same-origin'
                        });

                        if (!response.ok) {
                            var errorData = await response.json().catch(function () {
                                return {};
                            });

                            alert(errorData.error || 'Не удалось удалить метку');
                            return;
                        }

                        closeSpotSheet();
                        loadSpots();
                    } catch (error) {
                        alert('Ошибка сети');
                    }
                };
            }
        }
    }

    async function loadSocialProof(spotId) {
        try {
            var response = await fetch('/api/spots/' + spotId + '/social-proof', {
                credentials: 'same-origin'
            });

            if (!response.ok) {
                return;
            }

            var data = await response.json();
            var box = $('socialProof');

            if (!box) {
                return;
            }

            if (!data.total_today) {
                return;
            }

            var text = '<b>' + esc(data.total_today) + '</b> ' + pluralize(
                data.total_today,
                'человек был',
                'человека были',
                'человек были'
            ) + ' здесь сегодня';

            if (data.friends_count > 0) {
                text += ', из них <b>' + esc(data.friends_count) + '</b> ' + pluralize(
                    data.friends_count,
                    'друг',
                    'друга',
                    'друзей'
                );
            }

            box.innerHTML = '<div class="social-proof-banner"><span style="font-size:20px;">🔥</span><span class="txt">' + text + '</span></div>';
        } catch (error) {
            // silent
        }
    }

    async function loadCollaborators(spotId) {
        try {
            var response = await fetch('/api/spots/' + spotId + '/collaborators', {
                credentials: 'same-origin'
            });

            if (!response.ok) {
                return;
            }

            var list = await response.json();
            var box = $('collabBox');

            if (!box) {
                return;
            }

            if (!list.length) {
                box.innerHTML = '';
                return;
            }

            var avatarsHtml = list.slice(0, 6).map(function (item) {
                var profile = item.profiles || {};
                var avatarUrl = safeUrl(profile.avatar_url);

                if (avatarUrl) {
                    return '<div class="avatar"><img src="' + esc(avatarUrl) + '" alt=""></div>';
                }

                var initial = esc((profile.display_name || '?')[0].toUpperCase());
                return '<div class="avatar">' + initial + '</div>';
            }).join('');

            box.innerHTML = '<div class="avatar-stack">' + avatarsHtml + '</div>' +
                '<p class="hint" style="margin-top:6px;">' +
                esc(list.length) + ' ' + pluralize(
                    list.length,
                    'человек присоединился',
                    'человека присоединились',
                    'человек присоединились'
                ) +
                '</p>';
        } catch (error) {
            // silent
        }
    }

    async function loadComments(spotId) {
        try {
            var response = await fetch('/api/spots/' + spotId + '/comments', {
                credentials: 'same-origin'
            });

            if (!response.ok) {
                return;
            }

            var list = await response.json();
            var box = $('spotComments');

            if (!box) {
                return;
            }

            if (!list.length) {
                box.innerHTML = '<p class="hint">Пока нет комментариев</p>';
                return;
            }

            box.innerHTML = list.map(function (comment) {
                var name = comment.user ? comment.user.display_name : '';
                var initial = name ? name[0].toUpperCase() : '?';

                return '<div class="row-card" style="padding:10px 14px;">' +
                    '<div class="avatar" style="width:32px;height:32px;font-size:12px;">' + esc(initial) + '</div>' +
                    '<div class="info">' +
                    '<div class="name" style="font-size:14px;">' + esc(name) + '</div>' +
                    '<div class="sub">' + esc(comment.text) + '</div>' +
                    '</div>' +
                    '</div>';
            }).join('');
        } catch (error) {
            // silent
        }
    }

    async function sendComment(spotId) {
        var input = $('commentInput');

        if (!input) {
            return;
        }

        var text = input.value.trim();

        if (!text) {
            return;
        }

        input.value = '';

        try {
            var response = await fetch('/api/spots/' + spotId + '/comments', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text
                })
            });

            if (!response.ok) {
                var errorData = await response.json().catch(function () {
                    return {};
                });

                alert(errorData.error || 'Не удалось отправить комментарий');
            }

            loadComments(spotId);
        } catch (error) {
            alert('Ошибка сети');
            loadComments(spotId);
        }
    }

    function setupVoiceRecorder() {
        var button = $('voiceBtn');
        var status = $('voiceStatus');

        if (!button || !status) {
            return;
        }

        button.addEventListener('click', async function () {
            if (button.classList.contains('recording')) {
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                }
                return;
            }

            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                status.textContent = 'Микрофон недоступен в этом браузере';
                return;
            }

            try {
                var stream = await navigator.mediaDevices.getUserMedia({
                    audio: true
                });

                audioChunks = [];

                var options = {};

                if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported('audio/webm')) {
                    options.mimeType = 'audio/webm';
                }

                mediaRecorder = new MediaRecorder(stream, options);

                mediaRecorder.ondataavailable = function (event) {
                    if (event.data && event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };

                mediaRecorder.onstop = async function () {
                    stream.getTracks().forEach(function (track) {
                        track.stop();
                    });

                    button.classList.remove('recording');
                    button.textContent = '🎙️';

                    clearTimeout(recordTimer);

                    status.textContent = 'Загружаем...';

                    var blob = new Blob(audioChunks, {
                        type: mediaRecorder.mimeType || 'audio/webm'
                    });

                    var formData = new FormData();
                    formData.append('voice', blob, 'voice.webm');

                    try {
                        var response = await fetch('/api/spots/voice', {
                            method: 'POST',
                            credentials: 'same-origin',
                            body: formData
                        });

                        if (response.ok) {
                            var data = await response.json();

                            if ($('voiceUrlInput')) {
                                $('voiceUrlInput').value = data.url;
                            }

                            status.textContent = '✓ Записано';
                            status.classList.add('ready');
                        } else {
                            var errorData = await response.json().catch(function () {
                                return {};
                            });

                            status.textContent = errorData.error || 'Не получилось записать';
                        }
                    } catch (error) {
                        status.textContent = 'Ошибка сети';
                    }
                };

                mediaRecorder.start();

                button.classList.add('recording');
                button.textContent = '⏹️';

                status.textContent = 'Идёт запись... нажмите ещё раз, чтобы остановить';

                recordTimer = setTimeout(function () {
                    if (mediaRecorder && mediaRecorder.state === 'recording') {
                        mediaRecorder.stop();
                    }
                }, 15000);
            } catch (error) {
                status.textContent = 'Доступ к микрофону не дан';
            }
        });
    }

    function setupOrgSearch() {
        var input = $('orgSearchInput');
        var results = $('orgResults');
        var chip = $('orgChip');

        if (!input || !results || !chip) {
            return;
        }

        var timer;

        input.addEventListener('input', function () {
            clearTimeout(timer);

            var query = this.value.trim();

            if (!query) {
                results.innerHTML = '';
                return;
            }

            timer = setTimeout(async function () {
                try {
                    var url = '/api/organizations/search?q=' + encodeURIComponent(query) +
                        '&lat=' + encodeURIComponent(pendingLat) +
                        '&lng=' + encodeURIComponent(pendingLng);

                    var response = await fetch(url, {
                        credentials: 'same-origin'
                    });

                    if (!response.ok) {
                        results.innerHTML = '';
                        return;
                    }

                    var organizations = await response.json();

                    results.innerHTML = '';

                    organizations.forEach(function (organization) {
                        var row = document.createElement('div');
                        row.className = 'org-result-row';
                        row.dataset.id = organization.id;
                        row.dataset.name = organization.display_name || '';

                        row.innerHTML = esc(organization.display_name || '') +
                            '<span class="hint"> · ' + esc(organization.category || '') + '</span>';

                        row.addEventListener('click', function () {
                            if ($('orgIdInput')) {
                                $('orgIdInput').value = row.dataset.id;
                            }

                            chip.innerHTML = '<span class="org-selected-chip">📍 ' +
                                esc(row.dataset.name) +
                                ' <button type="button" id="orgChipRemove">✕</button></span>';

                            var removeButton = $('orgChipRemove');

                            if (removeButton) {
                                removeButton.onclick = function () {
                                    chip.innerHTML = '';

                                    if ($('orgIdInput')) {
                                        $('orgIdInput').value = '';
                                    }
                                };
                            }

                            input.value = '';
                            results.innerHTML = '';
                        });

                        results.appendChild(row);
                    });
                } catch (error) {
                    results.innerHTML = '';
                }
            }, 300);
        });
    }

    function resetAddSpotUI() {
        var form = $('addSpotForm');

        if (form) {
            form.reset();
        }

        if ($('orgChip')) {
            $('orgChip').innerHTML = '';
        }

        if ($('waveOptions')) {
            $('waveOptions').style.display = 'none';
        }

        if ($('voiceStatus')) {
            $('voiceStatus').textContent = 'Нажмите, чтобы записать 15 секунд';
            $('voiceStatus').classList.remove('ready');
        }

        if ($('manualHint')) {
            $('manualHint').style.display = 'none';
        }

        if ($('categoryInput')) {
            $('categoryInput').value = '';
        }

        if ($('orgIdInput')) {
            $('orgIdInput').value = '';
        }

        if ($('voiceUrlInput')) {
            $('voiceUrlInput').value = '';
        }

        if ($('durationInput')) {
            $('durationInput').value = '3';
        }

        if ($('moodInput')) {
            $('moodInput').value = '';
        }

        if ($('visibilityInput')) {
            $('visibilityInput').value = 'public';
        }

        if ($('waveEnabledInput')) {
            $('waveEnabledInput').value = 'false';
        }

        document.querySelectorAll('#addCategoryPicker .cat-chip, .mood-chip').forEach(function (chip) {
            chip.classList.remove('selected');
        });

        document.querySelectorAll('.duration-option').forEach(function (option) {
            option.classList.remove('selected');
        });

        var defaultDuration = document.querySelector('.duration-option[data-h="3"]');

        if (defaultDuration) {
            defaultDuration.classList.add('selected');
        }

        document.querySelectorAll('.vis-option').forEach(function (option) {
            option.classList.remove('selected');
        });

        var defaultVisibility = document.querySelector('.vis-option[data-vis="public"]');

        if (defaultVisibility) {
            defaultVisibility.classList.add('selected');
        }
    }

    function bindUI() {
        var openAddSpotButton = $('openAddSpot');

        if (openAddSpotButton) {
            openAddSpotButton.addEventListener('click', function () {
                if ($('latInput')) {
                    $('latInput').value = pendingLat;
                }

                if ($('lngInput')) {
                    $('lngInput').value = pendingLng;
                }

                if ($('placementInput')) {
                    $('placementInput').value = 'geo';
                }

                if ($('manualHint')) {
                    $('manualHint').style.display = 'none';
                }

                if ($('addSpotOverlay')) {
                    $('addSpotOverlay').classList.add('open');
                }
            });
        }

        var closeSheetButton = $('closeSheet');

        if (closeSheetButton) {
            closeSheetButton.addEventListener('click', function () {
                if ($('addSpotOverlay')) {
                    $('addSpotOverlay').classList.remove('open');
                }
            });
        }

        var addSpotOverlay = $('addSpotOverlay');

        if (addSpotOverlay) {
            addSpotOverlay.addEventListener('click', function (event) {
                if (event.target === addSpotOverlay) {
                    addSpotOverlay.classList.remove('open');
                }
            });
        }

        var spotSheetOverlay = $('spotSheetOverlay');

        if (spotSheetOverlay) {
            spotSheetOverlay.addEventListener('click', function (event) {
                if (event.target === spotSheetOverlay) {
                    closeSpotSheet();
                }
            });
        }

        var locateButton = $('locateMe');

        if (locateButton) {
            locateButton.addEventListener('click', function () {
                if (!navigator.geolocation) {
                    return;
                }

                navigator.geolocation.getCurrentPosition(function (position) {
                    pendingLat = position.coords.latitude;
                    pendingLng = position.coords.longitude;

                    if (map) {
                        map.setView([pendingLat, pendingLng], 15);
                    }
                });
            });
        }

        var manualToggleButton = $('manualToggle');
        var manualBanner = $('manualBanner');

        if (manualToggleButton && manualBanner) {
            manualToggleButton.addEventListener('click', function () {
                manualMode = !manualMode;

                manualToggleButton.classList.toggle('active', manualMode);
                manualBanner.classList.toggle('open', manualMode);
            });
        }

        var manualBannerCloseButton = $('manualBannerClose');

        if (manualBannerCloseButton && manualBanner && manualToggleButton) {
            manualBannerCloseButton.addEventListener('click', function () {
                manualMode = false;
                manualToggleButton.classList.remove('active');
                manualBanner.classList.remove('open');
            });
        }

        var legendToggleButton = $('legendToggle');
        var legendPanel = $('legendPanel');

        if (legendToggleButton && legendPanel) {
            legendToggleButton.addEventListener('click', function () {
                legendPanel.classList.toggle('open');
            });
        }

        document.querySelectorAll('#categoryScroller .cat-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                document.querySelectorAll('#categoryScroller .cat-chip').forEach(function (item) {
                    item.classList.remove('selected');
                });

                chip.classList.add('selected');
                activeCategory = chip.dataset.cat || '';

                applyFilter();
            });
        });

        document.querySelectorAll('#addCategoryPicker .cat-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                var alreadySelected = chip.classList.contains('selected');

                document.querySelectorAll('#addCategoryPicker .cat-chip').forEach(function (item) {
                    item.classList.remove('selected');
                });

                if (!alreadySelected) {
                    chip.classList.add('selected');

                    if ($('categoryInput')) {
                        $('categoryInput').value = chip.dataset.cat || '';
                    }
                } else {
                    if ($('categoryInput')) {
                        $('categoryInput').value = '';
                    }
                }
            });
        });

        document.querySelectorAll('.duration-option').forEach(function (option) {
            option.addEventListener('click', function () {
                document.querySelectorAll('.duration-option').forEach(function (item) {
                    item.classList.remove('selected');
                });

                option.classList.add('selected');

                if ($('durationInput')) {
                    $('durationInput').value = option.dataset.h || '3';
                }
            });
        });

        document.querySelectorAll('.mood-chip').forEach(function (option) {
            option.addEventListener('click', function () {
                var alreadySelected = option.classList.contains('selected');

                document.querySelectorAll('.mood-chip').forEach(function (item) {
                    item.classList.remove('selected');
                });

                if (!alreadySelected) {
                    option.classList.add('selected');

                    if ($('moodInput')) {
                        $('moodInput').value = option.dataset.mood || '';
                    }
                } else {
                    if ($('moodInput')) {
                        $('moodInput').value = '';
                    }
                }
            });
        });

        document.querySelectorAll('.vis-option').forEach(function (option) {
            option.addEventListener('click', function () {
                document.querySelectorAll('.vis-option').forEach(function (item) {
                    item.classList.remove('selected');
                });

                option.classList.add('selected');

                if ($('visibilityInput')) {
                    $('visibilityInput').value = option.dataset.vis || 'public';
                }
            });
        });

        var waveToggle = $('waveToggle');

        if (waveToggle) {
            waveToggle.addEventListener('change', function () {
                if ($('waveOptions')) {
                    $('waveOptions').style.display = this.checked ? 'block' : 'none';
                }

                if ($('waveEnabledInput')) {
                    $('waveEnabledInput').value = this.checked ? 'true' : 'false';
                }
            });
        }

        var form = $('addSpotForm');

        if (form) {
            form.addEventListener('submit', async function (event) {
                event.preventDefault();

                var submitButton = $('submitSpotBtn');

                if (submitButton) {
                    submitButton.disabled = true;
                    submitButton.textContent = 'Ставим метку...';
                }

                var formData = new FormData(form);

                if (!formData.has('wave_enabled')) {
                    formData.append(
                        'wave_enabled',
                        waveToggle && waveToggle.checked ? 'true' : 'false'
                    );
                }

                try {
                    var response = await fetch('/api/spots', {
                        method: 'POST',
                        credentials: 'same-origin',
                        body: formData
                    });

                    if (response.status === 401) {
                        window.location.href = '/login';
                        return;
                    }

                    if (response.ok) {
                        if ($('addSpotOverlay')) {
                            $('addSpotOverlay').classList.remove('open');
                        }

                        resetAddSpotUI();
                        loadSpots();
                    } else {
                        var errorData = await response.json().catch(function () {
                            return {};
                        });

                        alert(errorData.error || 'Не получилось. Попробуйте ещё раз.');
                    }
                } catch (error) {
                    alert('Ошибка сети');
                } finally {
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.textContent = 'Поставить метку';
                    }
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!$('map')) {
            return;
        }

        initMap();
        loadSpots();

        setInterval(function () {
            if (!document.hidden) {
                loadSpots();
            }
        }, 30000);

        setupVoiceRecorder();
        setupOrgSearch();
        bindUI();
    });
})();