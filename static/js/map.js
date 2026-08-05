(function () {
    'use strict';

    var map = null;
    var markersLayer = null;
    var youMarker = null;

    var pendingLat = 55.75;
    var pendingLng = 37.62;
    var manualMode = false;
    var activeCategory = '';
    var allSpots = [];

    function $(id) {
        return document.getElementById(id);
    }

    function esc(value) {
        var div = document.createElement('div');
        div.textContent = value === null || value === undefined ? '' : String(value);
        return div.innerHTML;
    }

    function safeUrl(url) {
        if (!url) return '';

        var value = String(url);

        if (/^https?:\/\//i.test(value)) {
            return value;
        }

        return '';
    }

    function timeLeft(iso) {
        if (!iso) return '';

        var diff = new Date(iso) - new Date();

        if (diff <= 0) {
            return 'завершилась';
        }

        var hours = Math.floor(diff / 3600000);
        var minutes = Math.floor((diff % 3600000) / 60000);

        if (hours > 0) {
            return hours + ' ч ' + minutes + ' м';
        }

        if (minutes > 0) {
            return minutes + ' м';
        }

        return 'меньше минуты';
    }

    function pinColor(spot) {
        if (String(spot.owner_id) === String(window.CURRENT_USER_ID || '')) {
            return 'var(--mine)';
        }

        if (spot.placement_type === 'manual') {
            return 'var(--manual)';
        }

        if (spot.visibility === 'friends') {
            return 'var(--friends)';
        }

        return 'var(--public)';
    }

    function initMap() {
        var mapElement = $('map');

        if (!mapElement) {
            return;
        }

        map = L.map('map', {
            zoomControl: false
        }).setView([pendingLat, pendingLng], 13);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap, © CARTO'
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
                setYouMarker(pendingLat, pendingLng);
            });
        }

        map.on('click', function (event) {
            if (!manualMode) {
                return;
            }

            openAddSheet(event.latlng.lat, event.latlng.lng, 'manual');
        });
    }

    function setYouMarker(lat, lng) {
        var icon = L.divIcon({
            className: '',
            html: '<div class="you-dot"></div>',
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });

        if (youMarker) {
            youMarker.setLatLng([lat, lng]);
        } else {
            youMarker = L.marker([lat, lng], {
                icon: icon,
                zIndexOffset: 1200
            }).addTo(map);
        }
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
                var color = pinColor(spot);

                var icon = L.divIcon({
                    className: '',
                    html: '<div class="spot-pin" style="background:' + color + '; color:' + color + '"></div>',
                    iconSize: [30, 30],
                    iconAnchor: [15, 26]
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

    function openAddSheet(lat, lng, placement) {
        if ($('latInput')) {
            $('latInput').value = lat;
        }

        if ($('lngInput')) {
            $('lngInput').value = lng;
        }

        if ($('placementInput')) {
            $('placementInput').value = placement || 'geo';
        }

        if ($('addSpotOverlay')) {
            $('addSpotOverlay').classList.add('open');
        }
    }

    function closeAddSheet() {
        if ($('addSpotOverlay')) {
            $('addSpotOverlay').classList.remove('open');
        }
    }

    function closeSpotSheet() {
        if ($('spotSheetOverlay')) {
            $('spotSheetOverlay').classList.remove('open');
        }
    }

    function resetAddForm() {
        var form = $('addSpotForm');

        if (form) {
            form.reset();
        }

        if ($('categoryInput')) {
            $('categoryInput').value = '';
        }

        if ($('durationInput')) {
            $('durationInput').value = '3';
        }

        if ($('visibilityInput')) {
            $('visibilityInput').value = 'public';
        }

        if ($('placementInput')) {
            $('placementInput').value = 'geo';
        }

        document.querySelectorAll('#addCategoryPicker .chip').forEach(function (chip) {
            chip.classList.remove('selected');
        });

        document.querySelectorAll('.duration-option').forEach(function (option) {
            option.classList.remove('selected');
        });

        var defaultDuration = document.querySelector('.duration-option[data-h="3"]');

        if (defaultDuration) {
            defaultDuration.classList.add('selected');
        }

        document.querySelectorAll('.segmented-item[data-vis]').forEach(function (option) {
            option.classList.remove('selected');
        });

        var defaultVisibility = document.querySelector('.segmented-item[data-vis="public"]');

        if (defaultVisibility) {
            defaultVisibility.classList.add('selected');
        }

        var preview = $('photoPreview');
        var dropText = $('photoDropText');

        if (preview) {
            preview.src = '';
            preview.hidden = true;
        }

        if (dropText) {
            dropText.style.display = 'flex';
        }
    }

    function openSpot(spot) {
        var content = $('spotSheetContent');

        if (!content) {
            return;
        }

        var isMine = String(spot.owner_id) === String(window.CURRENT_USER_ID || '');
        var photoUrl = safeUrl(spot.photo_url);

        var html = '';

        html += '<div class="sheet-handle"></div>';
        html += '<button class="sheet-close" id="spotSheetClose" type="button">✕</button>';
        html += '<h3>' + esc(spot.title) + '</h3>';

        var meta = [];

        if (spot.owner && spot.owner.display_name) {
            meta.push(esc(spot.owner.display_name));
        }

        if (spot.category) {
            meta.push(esc(spot.category));
        }

        if (spot.visibility === 'friends') {
            meta.push('🤝 только друзья');
        } else {
            meta.push('🌍 видят все');
        }

        if (spot.expires_at) {
            meta.push('⏳ ' + timeLeft(spot.expires_at));
        }

        if (meta.length) {
            html += '<p class="hint" style="margin-bottom:14px;">' + meta.join(' · ') + '</p>';
        }

        if (photoUrl) {
            html += '<img src="' + esc(photoUrl) + '" alt="" style="width:100%; border-radius:22px; object-fit:cover; max-height:320px; margin-bottom:14px;">';
        }

        if (spot.description) {
            html += '<p style="margin-bottom:14px;">' + esc(spot.description) + '</p>';
        }

        if (isMine) {
            html += '<button class="btn btn-ghost btn-block" id="deleteSpotBtn" type="button">🗑 Убрать метку</button>';
        }

        content.innerHTML = html;

        if ($('spotSheetOverlay')) {
            $('spotSheetOverlay').classList.add('open');
        }

        var closeButton = $('spotSheetClose');

        if (closeButton) {
            closeButton.onclick = closeSpotSheet;
        }

        var deleteButton = $('deleteSpotBtn');

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
                        var data = await response.json().catch(function () {
                            return {};
                        });

                        alert(data.error || 'Не удалось удалить метку');
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

    function bindUI() {
        var openAddSpot = $('openAddSpot');

        if (openAddSpot) {
            openAddSpot.addEventListener('click', function () {
                openAddSheet(pendingLat, pendingLng, 'geo');
            });
        }

        var closeSheet = $('closeSheet');

        if (closeSheet) {
            closeSheet.addEventListener('click', closeAddSheet);
        }

        var addSpotOverlay = $('addSpotOverlay');

        if (addSpotOverlay) {
            addSpotOverlay.addEventListener('click', function (event) {
                if (event.target === addSpotOverlay) {
                    closeAddSheet();
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

        var locateMe = $('locateMe');

        if (locateMe && navigator.geolocation) {
            locateMe.addEventListener('click', function () {
                navigator.geolocation.getCurrentPosition(function (position) {
                    pendingLat = position.coords.latitude;
                    pendingLng = position.coords.longitude;

                    if (map) {
                        map.setView([pendingLat, pendingLng], 15);
                    }

                    setYouMarker(pendingLat, pendingLng);
                });
            });
        }

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

        if (legendToggle && legendPanel) {
            legendToggle.addEventListener('click', function () {
                legendPanel.classList.toggle('open');
            });
        }

        document.querySelectorAll('#categoryScroller .chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                document.querySelectorAll('#categoryScroller .chip').forEach(function (item) {
                    item.classList.remove('selected');
                });

                chip.classList.add('selected');
                activeCategory = chip.dataset.cat || '';
                applyFilter();
            });
        });

        document.querySelectorAll('#addCategoryPicker .chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                var alreadySelected = chip.classList.contains('selected');

                document.querySelectorAll('#addCategoryPicker .chip').forEach(function (item) {
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

        document.querySelectorAll('.segmented-item[data-vis]').forEach(function (option) {
            option.addEventListener('click', function () {
                document.querySelectorAll('.segmented-item[data-vis]').forEach(function (item) {
                    item.classList.remove('selected');
                });

                option.classList.add('selected');

                if ($('visibilityInput')) {
                    $('visibilityInput').value = option.dataset.vis || 'public';
                }
            });
        });

        var photoInput = $('spotPhoto');
        var photoPreview = $('photoPreview');
        var photoDropText = $('photoDropText');

        if (photoInput && photoPreview && photoDropText) {
            photoInput.addEventListener('change', function () {
                var file = this.files && this.files[0];

                if (!file) {
                    photoPreview.src = '';
                    photoPreview.hidden = true;
                    photoDropText.style.display = 'flex';
                    return;
                }

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

                if (submitButton) {
                    submitButton.disabled = true;
                    submitButton.textContent = 'Ставим метку...';
                }

                try {
                    var formData = new FormData(form);

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
                        closeAddSheet();
                        resetAddForm();
                        loadSpots();
                    } else {
                        var data = await response.json().catch(function () {
                            return {};
                        });

                        alert(data.error || 'Не получилось создать метку.');
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
        bindUI();
        loadSpots();

        setInterval(function () {
            if (!document.hidden) {
                loadSpots();
            }
        }, 30000);
    });
})();