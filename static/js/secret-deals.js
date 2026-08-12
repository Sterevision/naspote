(function () {
    'use strict';

    var STORAGE_KEY = 'kartometr_secret_deals_revealed';
    var SECRET_HEADING = '🤫 Секретные моменты';

    function normalize(text) {
        return (text || '').replace(/\s+/g, ' ').trim();
    }

    function getRevealedIds() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            var data = raw ? JSON.parse(raw) : [];
            return Array.isArray(data) ? data : [];
        } catch (e) {
            return [];
        }
    }

    function saveRevealedId(id) {
        if (!id) return;

        try {
            var ids = getRevealedIds();

            if (ids.indexOf(id) === -1) {
                ids.push(id);
                localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
            }
        } catch (e) {
            // silent
        }
    }

    function places(n) {
        if (n % 10 === 1 && n % 100 !== 11) {
            return 'место';
        }

        if ([2, 3, 4].indexOf(n % 10) !== -1 && [12, 13, 14].indexOf(n % 100) === -1) {
            return 'места';
        }

        return 'мест';
    }

    function transformHeading() {
        if (!document.body) return;

        var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                var value = node.nodeValue || '';

                if (value.indexOf('Flash Deals') === -1) {
                    return NodeFilter.FILTER_REJECT;
                }

                var parent = node.parentElement;
                if (!parent) {
                    return NodeFilter.FILTER_REJECT;
                }

                if (parent.closest('script, style, textarea, input, select')) {
                    return NodeFilter.FILTER_REJECT;
                }

                return NodeFilter.FILTER_ACCEPT;
            }
        });

        var nodes = [];

        while (walker.nextNode()) {
            nodes.push(walker.currentNode);
        }

        nodes.forEach(function (node) {
            node.nodeValue = node.nodeValue
                .replace(/⚡\s*Flash Deals/g, SECRET_HEADING)
                .replace(/Flash Deals/g, SECRET_HEADING);
        });
    }

    function transformButtons() {
        var buttons = document.querySelectorAll('button');

        Array.prototype.forEach.call(buttons, function (btn) {
            if (btn.childElementCount > 0) return;

            var label = normalize(btn.textContent);

            if (label.indexOf('Занять место') !== -1) {
                btn.textContent = 'Я в деле';
            }
        });
    }

    function transformCounters() {
        var elements = document.querySelectorAll('div, span, p, small, strong, b, li');

        Array.prototype.forEach.call(elements, function (el) {
            if (el.childElementCount !== 0) return;

            var text = normalize(el.textContent);
            var match = text.match(/Занято\s*(\d+)\s*из\s*(\d+)/i);

            if (!match) return;

            var claimed = parseInt(match[1], 10) || 0;
            var total = parseInt(match[2], 10) || 0;
            var left = Math.max(0, total - claimed);

            el.textContent = 'Осталось ' + left + ' ' + places(left);
        });
    }

    function getDealId(card) {
        if (!card) return '';

        if (card.getAttribute('data-deal-id')) {
            return String(card.getAttribute('data-deal-id'));
        }

        var childWithId = card.querySelector('[data-deal-id]');
        if (childWithId && childWithId.getAttribute('data-deal-id')) {
            return String(childWithId.getAttribute('data-deal-id'));
        }

        var titleEl = card.querySelector('h1, h2, h3, h4, h5, strong, b, .deal-title, [class*="title"]');
        var base = titleEl
            ? normalize(titleEl.textContent)
            : normalize(card.textContent).slice(0, 60);

        if (!base) return '';

        var hash = 0;

        for (var i = 0; i < base.length; i++) {
            hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
        }

        return 'secret-' + hash;
    }

    function findCard(btn) {
        if (!btn) return null;

        var card = btn.closest('[data-deal-id], .deal-card, .flash-deal-card, .flash-deal, article, li');
        if (card) return card;

        var el = btn.parentElement;

        for (var i = 0; i < 7 && el; i++) {
            if (el.querySelector && (el.querySelector('p') || el.querySelector('[class*="desc"]'))) {
                return el;
            }

            el = el.parentElement;
        }

        return btn.closest('.card, .inline-card, div');
    }

    function getDescriptionElements(card) {
        if (!card) return [];

        var candidates = card.querySelectorAll('p, div, span, [class*="desc"], [class*="description"]');
        var out = [];

        Array.prototype.forEach.call(candidates, function (el) {
            if (el.classList.contains('secret-deal-desc')) return;

            if (el.closest('button, a, label, form, input, textarea, select')) return;
            if (el.querySelector('button, input, textarea, select, a')) return;

            var text = normalize(el.textContent);

            if (!text || text.length < 8) return;

            var looksLikeDescription =
                el.tagName === 'P' ||
                /desc|description/i.test(String(el.className || '')) ||
                text.length > 25;

            if (!looksLikeDescription) return;

            if (/Занято|Осталось|Название акции|Описание|Сколько мест|Запустить акцию|Я в деле|Вы уже участвуете|Новых заявок|Flash Deals|Секретные моменты|Меток|Сегодня|За 7 дней|Людей|Комментариев|Реакций/i.test(text)) {
                return;
            }

            out.push(el);
        });

        return out.slice(0, 3);
    }

    function blurCard(card) {
        if (!card) return;

        var id = getDealId(card);
        var revealedIds = getRevealedIds();
        var descEls = getDescriptionElements(card);

        if (!descEls.length) return;

        descEls.forEach(function (el) {
            el.classList.add('secret-deal-desc');
            el.setAttribute('title', 'Нажми «Я в деле», чтобы открыть');

            if (id && revealedIds.indexOf(id) !== -1) {
                el.classList.add('secret-revealed');
                el.removeAttribute('title');
            }
        });

        if (id && revealedIds.indexOf(id) !== -1) {
            card.dataset.secretRevealed = '1';
        }
    }

    function revealCard(card, saveId) {
        if (!card) return;

        var id = getDealId(card);

        card.dataset.secretRevealed = '1';

        var descEls = card.querySelectorAll('.secret-deal-desc');

        Array.prototype.forEach.call(descEls, function (el) {
            el.classList.add('secret-revealed');
            el.removeAttribute('title');
        });

        if (saveId && id) {
            saveRevealedId(id);
        }
    }

    function processCards() {
        var revealedIds = getRevealedIds();
        var buttons = document.querySelectorAll('button');

        Array.prototype.forEach.call(buttons, function (btn) {
            var label = normalize(btn.textContent);

            if (/Вы уже участвуете|Участвую|Заявка принята/i.test(label)) {
                var claimedCard = findCard(btn);
                if (claimedCard) revealCard(claimedCard, true);
                return;
            }

            if (label !== 'Я в деле' && label.indexOf('Занять место') === -1) {
                return;
            }

            var card = findCard(btn);
            if (!card) return;

            var id = getDealId(card);

            if (id && revealedIds.indexOf(id) !== -1) {
                revealCard(card, false);
                return;
            }

            if (!card.dataset.secretRevealed) {
                blurCard(card);
            }
        });
    }

    function process() {
        transformHeading();
        transformButtons();
        transformCounters();
        processCards();
    }

    function init() {
        process();

        setInterval(function () {
            if (!document.hidden) {
                process();
            }
        }, 800);

        document.addEventListener('click', function (event) {
            var target = event.target;

            if (!target || !target.closest) return;

            var btn = target.closest('button');
            if (!btn) return;

            var label = normalize(btn.textContent);

            var isClaimButton =
                label === 'Я в деле' ||
                label.indexOf('Занять место') !== -1 ||
                /Вы уже участвуете|Участвую|Заявка принята/i.test(label);

            if (!isClaimButton) return;

            var card = findCard(btn);

            if (card) {
                setTimeout(function () {
                    revealCard(card, true);
                }, 700);
            }
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();