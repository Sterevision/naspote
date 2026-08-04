# deploy/gunicorn.conf.py
# Запуск: gunicorn --config deploy/gunicorn.conf.py app:app

import multiprocessing

# Адрес и порт
bind = "127.0.0.1:8000"

# Количество воркеров
# Формула: (2 * CPU) + 1, но для начала хватит 2
workers = 2

# Тип воркеров
worker_class = "sync"

# Таймауты
timeout = 120
keepalive = 5
graceful_timeout = 30

# Максимум запросов до перезапуска воркера (защита от утечек памяти)
max_requests = 1000
max_requests_jitter = 100

# Логирование
accesslog = "/var/www/kartometr/logs/access.log"
errorlog = "/var/www/kartometr/logs/error.log"
loglevel = "warning"

# Заголовок для прокси
# (proxy_allow_from ниже был удалён — такой настройки в Gunicorn не существует,
#  она ничего не делала и создавала ложное чувство защиты)
forwarded_allow_ips = "127.0.0.1"

# Безопасность
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Префикс пути (если приложение не в корне)
# prefix = "/"