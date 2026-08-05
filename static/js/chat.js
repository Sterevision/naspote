(function () {
    'use strict';

    var friendId = window.CHAT_FRIEND_ID;
    var currentUserId = window.CURRENT_USER_ID;

    var chatBody = null;
    var chatInput = null;
    var chatSend = null;

    var lastCount = -1;
    var initialLoadDone = false;

    function isNearBottom() {
        if (!chatBody) {
            return false;
        }

        var threshold = 90;

        return (
            chatBody.scrollHeight -
            chatBody.scrollTop -
            chatBody.clientHeight < threshold
        );
    }

    function scrollToBottom() {
        if (!chatBody) {
            return;
        }

        chatBody.scrollTop = chatBody.scrollHeight;
    }

    var ICONS = {
        chat: '<svg viewBox="0 0 20 20"><path d="M3 10a7 7 0 1 1 3.1 5.8L3 17l1.3-3.4A6.96 6.96 0 0 1 3 10z"/></svg>',
        lock: '<svg viewBox="0 0 20 20"><rect x="4.8" y="9" width="10.4" height="7.2" rx="1.4"/><path d="M6.8 9V6.7a3.2 3.2 0 0 1 6.4 0V9"/></svg>',
        alert: '<svg viewBox="0 0 20 20"><path d="M10 3.6l7.8 13.4H2.2L10 3.6z"/><path d="M10 8.6v3.2"/><circle cx="10" cy="14.4" r=".2"/></svg>'
    };

    function renderEmptyState(iconKey, text) {
        if (!chatBody) {
            return;
        }

        chatBody.innerHTML = '';

        var empty = document.createElement('div');
        empty.className = 'empty-state';

        var em = document.createElement('span');
        em.className = 'em';
        em.innerHTML = ICONS[iconKey] || '';

        var p = document.createElement('p');
        p.textContent = text;

        empty.appendChild(em);
        empty.appendChild(p);

        chatBody.appendChild(empty);
    }

    function renderMessages(messages) {
        if (!chatBody) {
            return;
        }

        chatBody.innerHTML = '';

        if (!messages.length) {
            renderEmptyState('chat', 'Сообщений пока нет. Напишите первое!');
            return;
        }

        messages.forEach(function (message) {
            var mine = String(message.sender_id) === String(currentUserId);

            var bubble = document.createElement('div');
            bubble.className = 'bubble ' + (mine ? 'mine' : 'theirs');

            var text = document.createElement('div');
            text.textContent = message.text || '';

            bubble.appendChild(text);

            if (message.created_at) {
                var date = new Date(message.created_at);

                if (!isNaN(date.getTime())) {
                    var meta = document.createElement('div');
                    meta.style.fontSize = '11px';
                    meta.style.opacity = '.72';
                    meta.style.marginTop = '4px';

                    meta.textContent = date.toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                    });

                    bubble.appendChild(meta);
                }
            }

            chatBody.appendChild(bubble);
        });
    }

    async function loadMessages(forceScroll) {
        if (!friendId || !chatBody) {
            return;
        }

        try {
            var response = await fetch('/api/messages/' + encodeURIComponent(friendId), {
                credentials: 'same-origin'
            });

            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }

            if (response.status === 403) {
                renderEmptyState('lock', 'Чат доступен только с друзьями.');
                return;
            }

            if (!response.ok) {
                throw new Error('messages load failed');
            }

            var messages = await response.json();

            if (!Array.isArray(messages)) {
                messages = [];
            }

            if (messages.length !== lastCount) {
                var shouldStick = forceScroll || !initialLoadDone || isNearBottom();

                renderMessages(messages);

                if (shouldStick) {
                    scrollToBottom();
                }

                lastCount = messages.length;
            }

            initialLoadDone = true;
        } catch (error) {
            if (!initialLoadDone) {
                renderEmptyState('alert', 'Не удалось загрузить сообщения.');
            }
        }
    }

    async function sendMessage() {
        if (!chatInput || !friendId) {
            return;
        }

        var text = chatInput.value.trim();

        if (!text) {
            return;
        }

        chatInput.value = '';

        try {
            var response = await fetch('/api/messages/' + encodeURIComponent(friendId), {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text
                })
            });

            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }

            if (!response.ok) {
                var errorData = await response.json().catch(function () {
                    return {};
                });

                chatInput.value = text;

                alert(errorData.error || 'Не удалось отправить сообщение.');
                return;
            }

            await loadMessages(true);
        } catch (error) {
            chatInput.value = text;
            alert('Ошибка сети. Попробуйте ещё раз.');
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        chatBody = document.getElementById('chatBody');
        chatInput = document.getElementById('chatInput');
        chatSend = document.getElementById('chatSend');

        if (!chatBody || !friendId) {
            return;
        }

        if (chatSend) {
            chatSend.addEventListener('click', function () {
                sendMessage();
            });
        }

        if (chatInput) {
            chatInput.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                }
            });
        }

        loadMessages(true);

        setInterval(function () {
            if (!document.hidden) {
                loadMessages(false);
            }
        }, 5000);
    });
})();