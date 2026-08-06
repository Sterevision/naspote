function initLocationPicker(mapId, latInputId, lngInputId, locateBtnId, coordsId, initialLat, initialLng) {
    var latInput = document.getElementById(latInputId);
    var lngInput = document.getElementById(lngInputId);
    var coordsOut = coordsId ? document.getElementById(coordsId) : null;
    if (!latInput || !lngInput) return null;

    var startLat = initialLat || 55.75;
    var startLng = initialLng || 37.62;
    var map = L.map(mapId).setView([startLat, startLng], initialLat ? 15 : 12);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap, © CARTO'
    }).addTo(map);

    var marker = null;

    function updateReadout(lat, lng) {
        if (coordsOut) coordsOut.textContent = lat.toFixed(5) + ', ' + lng.toFixed(5);
    }

    function setMarker(lat, lng) {
        if (marker) {
            marker.setLatLng([lat, lng]);
        } else {
            marker = L.marker([lat, lng], { draggable: true }).addTo(map);
            marker.on('dragend', function () {
                var p = marker.getLatLng();
                latInput.value = p.lat;
                lngInput.value = p.lng;
                updateReadout(p.lat, p.lng);
            });
        }
        latInput.value = lat;
        lngInput.value = lng;
        updateReadout(lat, lng);
    }

    if (initialLat && initialLng) setMarker(initialLat, initialLng);

    map.on('click', function (e) {
        setMarker(e.latlng.lat, e.latlng.lng);
    });

    var locateBtn = locateBtnId ? document.getElementById(locateBtnId) : null;
    if (locateBtn && navigator.geolocation) {
        locateBtn.addEventListener('click', function () {
            navigator.geolocation.getCurrentPosition(function (pos) {
                map.setView([pos.coords.latitude, pos.coords.longitude], 16);
                setMarker(pos.coords.latitude, pos.coords.longitude);
            });
        });
    }

    setTimeout(function () { map.invalidateSize(); }, 150);
    return map;
}