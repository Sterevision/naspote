(function () {
'use strict';
var searchInput = document.getElementById('orgSearch');
var resultsBox = document.getElementById('orgSearchResults');
var selectedBox = document.getElementById('orgSelected');
var orgIdInput = document.getElementById('orgIdInput');
if (!searchInput || !resultsBox || !orgIdInput) return;
var timer = null;
function esc(v) {
    var d = document.createElement('div');
    d.textContent = v === null || v === undefined ? '' : String(v);
    return d.innerHTML;
}
function clearSelection() {
    orgIdInput.value = '';
    selectedBox.innerHTML = '';
    resultsBox.innerHTML = '';
    searchInput.disabled = false;
    searchInput.value = '';
}
function selectOrg(org) {
    orgIdInput.value = org.id;
    resultsBox.innerHTML = '';
    searchInput.disabled = true;
    selectedBox.innerHTML = '<div class="org-selected-chip">\ud83c\udfe2 ' + esc(org.display_name) +
        ' <button type="button" id="orgClearBtn">\u2715</button></div>';
    var clearBtn = document.getElementById('orgClearBtn');
    if (clearBtn) clearBtn.addEventListener('click', clearSelection);
}
searchInput.addEventListener('input', function () {
    clearTimeout(timer);
    var q = searchInput.value.trim();
    if (q.length < 2) { resultsBox.innerHTML = ''; return; }
    timer = setTimeout(async function () {
        try {
            var lat = (document.getElementById('latInput') || {}).value || 0;
            var lng = (document.getElementById('lngInput') || {}).value || 0;
            var url = '/api/organizations/search?q=' + encodeURIComponent(q)
                + '&lat=' + encodeURIComponent(lat)
                + '&lng=' + encodeURIComponent(lng);
            var res = await fetch(url, { credentials: 'same-origin' });
            if (!res.ok) return;
            var orgs = await res.json();
            if (!orgs.length) {
                resultsBox.innerHTML = '<div class="org-result-row" style="color:var(--muted);">Ничего не найдено</div>';
                return;
            }
            resultsBox.innerHTML = orgs.map(function (o) {
                return '<div class="org-result-row" data-id="' + esc(o.id) + '">' + esc(o.display_name) +
                    ' <span style="color:var(--muted);font-size:12px;">' +
                    (o.category ? esc(o.category) : '') +
                    (o.distance_km !== null && o.distance_km !== undefined ? ' \u00b7 ' + o.distance_km + ' км' : '') +
                    '</span></div>';
            }).join('');
            resultsBox.querySelectorAll('.org-result-row[data-id]').forEach(function (row) {
                row.addEventListener('click', function () {
                    var org = null;
                    for (var i = 0; i < orgs.length; i++) {
                        if (String(orgs[i].id) === String(row.dataset.id)) { org = orgs[i]; break; }
                    }
                    if (org) selectOrg(org);
                });
            });
        } catch (e) { /* silent */ }
    }, 300);
});
var overlay = document.getElementById('addSpotOverlay');
if (overlay && typeof MutationObserver !== 'undefined') {
    var mo = new MutationObserver(function () {
        if (!overlay.classList.contains('open')) clearSelection();
    });
    mo.observe(overlay, { attributes: true, attributeFilter: ['class'] });
}
})();