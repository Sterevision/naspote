(function () {
    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.bottom-nav')) return;
        fetch('/api/messages/unread_count', {credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                if (!d) return;
                var links = document.querySelectorAll('.bottom-nav a.nav-item');
                var friendsLink = null, msgLink = null;
                links.forEach(function (a) {
                    if (a.href.indexOf('/friends') > -1) friendsLink = a;
                    if (a.href.indexOf('/messages') > -1) msgLink = a;
                });
                if (friendsLink && d.friend_requests > 0 && !friendsLink.querySelector('.nav-badge')) {
                    var ic = friendsLink.querySelector('.ic');
                    if (ic) ic.insertAdjacentHTML('afterend', '<span class="nav-badge"></span>');
                }
                if (msgLink && d.messages > 0 && !msgLink.querySelector('.nav-badge')) {
                    var ic = msgLink.querySelector('.ic');
                    if (ic) ic.insertAdjacentHTML('afterend', '<span class="nav-badge"></span>');
                }
            }).catch(function () {});
    });
})();
