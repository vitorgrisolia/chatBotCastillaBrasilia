#!/bin/sh
# Prepara a pasta do banco para o usuário sem privilégios e troca de usuário.
# Volumes montados costumam chegar como root, por isso o ajuste é feito aqui.
set -eu

if [ "$(id -u)" = "0" ]; then
    db_dir="$(dirname "${CASTILLA_DB_PATH:-data/private/castilla.sqlite3}")"
    mkdir -p "$db_dir"
    if chown -R castilla:castilla "$db_dir"; then
        exec setpriv --reuid=castilla --regid=castilla --init-groups "$@"
    fi
    echo "Aviso: não foi possível ajustar o dono de $db_dir; executando como root." >&2
fi
exec "$@"
