#!/usr/bin/env bash
# Prepara a origem da v3_compartilhado: cria o banco app e as tabelas compartilhadas.
set -euo pipefail
cd "$(dirname "$0")/../../.."
psql() { docker compose exec -T postgres-origem psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }

psql -c "create database app"
psql -d app -f - < variantes/v3_compartilhado/origem/esquema.sql
