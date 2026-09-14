#!/bin/sh
# Резервное копирование базы ИС «Электронный архив» по расписанию
# (ТС-176 разд. 14 п. 1.1: «автоматическое резервное копирование данных»).
#
# Работает в контейнере postgres:16-alpine (там есть pg_dump). Дамп пишется во
# временный файл и переименовывается только после успешного завершения:
# оборванная копия не должна выглядеть последней удачной. Старые копии
# удаляются только после появления новой удачной.
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
DEST=/backups/db
mkdir -p "$DEST"

while true; do
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    target="$DEST/earchive-$stamp.dump"
    if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "${POSTGRES_HOST:-postgres}" \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$target.part"; then
        mv "$target.part" "$target"
        date -u +%s > "$DEST/last_success"
        find "$DEST" -name 'earchive-*.dump' -mtime +"$KEEP_DAYS" -delete
        echo "backup-db: $target"
    else
        rm -f "$target.part"
        echo "backup-db: pg_dump завершился с ошибкой" >&2
    fi
    sleep $((INTERVAL_HOURS * 3600))
done
