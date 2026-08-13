(function () {
    'use strict';

    function setChip(id, text) {
        var chip = document.getElementById(id);
        if (!chip) return;

        if (text) {
            chip.hidden = false;
            chip.textContent = text;
        } else {
            chip.hidden = true;
            chip.textContent = '';
        }
    }

    window.kmSetChip = setChip;

    function initCityAutocomplete(inputId, options) {
        var input = document.getElementById(inputId);
        if (!input) return null;

        var opts = options || {};
        var latName = opts.latName || 'home_lat';
        var lngName = opts.lngName || 'home_lng';
        var chipId = opts.chipId || null;

        var box = opts.suggestId ? document.getElementById(opts.suggestId) : null;

        if (!box) {
            box = document.createElement('div');
            box.className = 'city-suggestions';
            input.parentNode.insertBefore(box, input.nextSibling);
        }

        var form = input.closest('form');
        var timer = null;
        var lastResults = [];

        function field(name) {
            if (!form) return null;
            return form.querySelector('[name="' + name + '"]');
        }

        function setCoords(lat, lng) {
            var la = field(latName);
            var ln = field(lngName);
            if (la) la.value = lat;
            if (ln) ln.value = lng;
        }

        function clearCoords() {
            setCoords('', '');
        }

        function shortName(full) {
            var parts = (full || '').split(',');
            return (parts.slice(0, 2).join(',') || full || '').trim();
        }

        function close() {
            box.classList.remove('open');
            box.innerHTML = '';
        }

        function render() {
            if (!lastResults.length) {
                close();
                return;
            }

            box.innerHTML = '';

            lastResults.forEach(function (r) {
                var row = document.createElement('div');
                row.className = 'city-suggestion';
                row.textContent = '🏙 ' + shortName(r.display_name);

                row.addEventListener('click', function () {
                    var name = shortName(r.display_name);

                    input.value = name;
                    setCoords(r.lat, r.lon);

                    if (chipId) setChip(chipId, '🏙 Выбрано: ' + name);
                    close();
                });

                box.appendChild(row);
            });

            box.classList.add('open');
        }

        input.addEventListener('input', function () {
            clearCoords();
            if (chipId) setChip(chipId, '');

            var q = input.value.trim();

            clearTimeout(timer);

            if (q.length < 3) {
                close();
                return;
            }

            timer = setTimeout(function () {
                fetch('https://nominatim.openstreetmap.org/search?format=json&limit=6&accept-language=ru&q=' + encodeURIComponent(q))
                    .then(function (r) { return r.ok ? r.json() : []; })
                    .then(function (data) {
                        lastResults = data || [];
                        render();
                    })
                    .catch(function () {
                        close();
                    });
            }, 350);
        });

        document.addEventListener('click', function (e) {
            if (!box.contains(e.target) && e.target !== input) {
                close();
            }
        });

        // При входе показываем, что точка уже сохранена
        var la = field(latName);
        var ln = field(lngName);

        if (la && ln && la.value && ln.value && chipId) {
            var current = input.value.trim();
            setChip(chipId, current ? '🏙 Сейчас: ' + current : '📍 Точка сохранена');
        }

        return { setCoords: setCoords };
    }

    window.initCityAutocomplete = initCityAutocomplete;
})();