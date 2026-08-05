(function () {
    'use strict';

    var friendId = window.CHAT_FRIEND_ID;
    var canChat = window.CHAT_CAN_CHAT;
    var currentUserId = window.CURRENT_USER_ID;

    var chatBody = null;
    var chatInput = null;
    var chatSend = null;
    var attachInput = null;
    var attachPreview = null;
    var attachPreviewImg = null;
    var attachPreviewName = null;
    var attachRemove = null;
    var emojiToggle = null;
    var emojiPanel = null;

    var selectedFile = null;
    var lastCount = -1;
    var initialLoadDone = false;

    var EMOJIS = [
        '😀', '😃', '😄', '😁', '😆',
        '😂', '🤣', '😊', '😇', '🙂',
        '😉', '😍', '😘', '😜', '🤪',
        '🤔', '🤨', '😐', '😏', '😴',
        '🥱', '😷', '🤒', '🥳', '😎',
        '🤓', '😳', '🥺', '😭', '😤',
        '😡', '🤯', '😱', '🫠', '👋',
        '👍', '👎', '👏', '🙌', '🤝',
        '🙏', '💪', '❤️', '🧡', '💛',
        '💚', '💙', '💜', '🖤', '💔',
        '🔥', '⚡', '🎉', '🎊', '🎈',
        '🍕', '🍔', '🍟', '🌭', '🍿',
        '☕', '🍺', '🍻', '🥂', '🍷',
        '📍', '🗺️', '🚕', '🚇', '🌙'
    ];

    function $(id) {
        return document.getElementById(id);
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

    function isNearBottom() {
        if (!chatBody) {
            return false;
        }

        return chatBody.scrollHeight - chatBody.scrollTop - chatBody.clientHeight < 100;
    }

    function scrollToBottom() {
        if (!chatBody) {
            return;
        }

        chatBody.scrollTop = chatBody.scrollHeight;
    }

    function renderEmpty(message) {
        if (!chatBody) {
            return;
        }

        chatBody.innerHTML = '';

        var empty = document.createElement('div');
        empty.className = 'empty-state';

        var p = document.createElement('p');
        p.textContent = message;

        empty.appendChild(p);
        chatBody.appendChild(empty);
    }

    function renderMessages(messages) {
        if (!chatBody) {
            return;
        }

        chatBody.innerHTML = '';

        if (!messages.length) {
            renderEmpty('Сообщений пока нет. Напишите первое!');
            return;
        }

        messages.forEach(function (message) {
            var mine = String(message.sender_id) === String(currentUserId);

            var bubble = document.createElement('div');
            bubble.className = 'bubble ' + (mine ? 'mine' : 'theirs');

            if (message.image_url) {
                var imageUrl = safeUrl(message.image_url);

                if (imageUrl) {
                    var link = document.createElement('a');
                    link.href = imageUrl;
                    link.target = '_blank';
                    link.rel = 'noopener';

                    var img = document.createElement('img');
                    img.src = imageUrl;
                    img.alt = 'Изображение';
                    img.className = 'chat-image';

                    link.appendChild(img);
                    bubble.appendChild(link);
                }
            }

            if (message.text) {
                var text = document.createElement('div');
                text.textContent = message.text;
                bubble.appendChild(text);
            }

            if (message.created_at) {
                var date = new Date(message.created_at);

                if (!isNaN(date.getTime())) {
                    var meta = document.createElement('div');
                    meta.className = 'bubble-time';
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
                renderEmpty('Чат доступен только между друзьями.');
                return;
            }

            if (!response.ok) {
                throw new Error('load failed');
            }

            var messages = await response.json();

            if (!Array.isArray(messages)) {
                messages = [];
            }

            if (messages.length !== lastCount) {
                var stick = forceScroll || !initialLoadDone || isNearBottom();

                renderMessages(messages);

                if (stick) {
                    scrollToBottom();
                }

                lastCount = messages.length;
            }

            initialLoadDone = true;
        } catch (error) {
            if (!initialLoadDone) {
                renderEmpty('Не удалось загрузить сообщения.');
            }
        }
    }

    function clearAttachment() {
        selectedFile = null;

        if (attachInput) {
            attachInput.value = '';
        }

        if (attachPreview) {
            attachPreview.hidden = true;
        }

        if (attachPreviewImg) {
            attachPreviewImg.src = '';
        }

        if (attachPreviewName) {
            attachPreviewName.textContent = '';
        }
    }

    function selectFile(file) {
        if (!file) {
            return;
        }

        if (!file.type || file.type.indexOf('image/') !== 0) {
            alert('В чат можно отправлять только изображения.');
            return;
        }

        if (file.size > 8 * 1024 * 1024) {
            alert('Файл слишком большой. Максимум 8 МБ.');
            return;
        }

        selectedFile = file;

        if (attachPreview && attachPreviewImg && attachPreviewName) {
            attachPreviewImg.src = URL.createObjectURL(file);
            attachPreviewName.textContent = file.name || 'image';
            attachPreview.hidden = false;
        }
    }

    function insertEmoji(emoji) {
        if (!chatInput) {
            return;
        }

        chatInput.value += emoji;
        chatInput.focus();
    }

    function renderEmojiPanel() {
        if (!emojiPanel) {
            return;
        }

        emojiPanel.innerHTML = '';

        EMOJIS.forEach(function (emoji) {
            var button = document.createElement('button');
            button.className = 'emoji-btn';
            button.type = 'button';
            button.textContent = emoji;

            button.addEventListener('click', function () {
                insertEmoji(emoji);
            });

            emojiPanel.appendChild(button);
        });
    }

    async function sendMessage() {
        if (!canChat || !chatInput || !friendId) {
            return;
        }

        var text = chatInput.value.trim();

        if (!text && !selectedFile) {
            return;
        }

        if (chatSend) {
            chatSend.disabled = true;
        }

        try {
            var response;

            if (selectedFile) {
                var formData = new FormData();
                formData.append('text', text);
                formData.append('image', selectedFile);

                response = await fetch('/api/messages/' + encodeURIComponent(friendId), {
                    method: 'POST',
                    credentials: 'same-origin',
                    body: formData
                });
            } else {
                response = await fetch('/api/messages/' + encodeURIComponent(friendId), {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ text: text })
                });
            }

            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }

            if (!response.ok) {
                var data = await response.json().catch(function () {
                    return {};
                });

                alert(data.error || 'Не удалось отправить сообщение.');
                return;
            }

            chatInput.value = '';
            clearAttachment();

            await loadMessages(true);
        } catch (error) {
            alert('Ошибка сети. Попробуйте ещё раз.');
        } finally {
            if (chatSend) {
                chatSend.disabled = false;
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        chatBody = $('chatBody');
        chatInput = $('chatInput');
        chatSend = $('chatSend');
        attachInput = $('attachInput');
        attachPreview = $('attachPreview');
        attachPreviewImg = $('attachPreviewImg');
        attachPreviewName = $('attachPreviewName');
        attachRemove = $('attachRemove');
        emojiToggle = $('emojiToggle');
        emojiPanel = $('emojiPanel');

        if (!chatBody || !friendId) {
            return;
        }

        renderEmojiPanel();

        if (chatSend) {
            chatSend.addEventListener('click', sendMessage);
        }

        if (chatInput && canChat) {
            chatInput.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                }
            });
        }

        if (attachInput && canChat) {
            attachInput.addEventListener('change', function () {
                selectFile(this.files && this.files[0]);
            });
        }

        if (attachRemove) {
            attachRemove.addEventListener('click', clearAttachment);
        }

        if (emojiToggle && emojiPanel) {
            emojiToggle.addEventListener('click', function () {
                emojiPanel.classList.toggle('open');
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