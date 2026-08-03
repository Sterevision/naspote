(function () {
    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.bottom-nav')) return;
        fetch('/api/messages/unread_count').then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
            if (!d) return;
            var friendsNav = document.getElementById('navFriends');
            var msgNav = document.getElementById('navMessages');
            if (friendsNav && d.friend_requests > 0 && !friendsNav.querySelector('.nav-badge')) {
                friendsNav.querySelector('.ic').insertAdjacentHTML('afterend', '<span class="nav-badge"></span>');
            }
            if (msgNav && d.messages > 0 && !msgNav.querySelector('.nav-badge')) {
                msgNav.querySelector('.ic').insertAdjacentHTML('afterend', '<span class="nav-badge"></span>');
            }
        }).catch(function () {});
    });
})();
