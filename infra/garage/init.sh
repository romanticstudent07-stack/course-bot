# infra/garage/garage.toml — конфиг Garage S3 (dev-контур).
# Официальная документация: https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/
#
# Правила dev:
#   - Один узел (single-node), replication_factor=1.
#   - Данные и метаданные — в volumes course-bot_garage-{data,meta}.
#   - S3 API слушает на 0.0.0.0:3900 внутри контейнера, снаружи → 127.0.0.1:9000.
#   - Web-UI (object browser) на 0.0.0.0:3902 → снаружи 127.0.0.1:9001.
#
# ВНИМАНИЕ: rpc_secret и admin_token — DEV-дефолты для локали.
# В prod генерируй свои через `openssl rand -hex 32` и подставляй через переменные.

metadata_dir = "/var/lib/garage/meta"
data_dir     = "/var/lib/garage/data"

db_engine = "lmdb"

replication_factor = 1

# RPC — 32-байтный hex. DEV-дефолт, для локали безопасно.
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "0000000000000000000000000000000000000000000000000000000000000001"

[s3_api]
s3_region     = "garage"
api_bind_addr = "[::]:3900"
root_domain   = ".s3.garage.localhost"

[s3_web]
bind_addr   = "[::]:3902"
root_domain = ".web.garage.localhost"
index       = "index.html"

[admin]
api_bind_addr = "[::]:3903"
# admin_token — DEV-дефолт. В prod — свой рандом.
admin_token = "0000000000000000000000000000000000000000000000000000000000000002"
metrics_token = "0000000000000000000000000000000000000000000000000000000000000003"
