#!/usr/bin/env bash
# Prepara a origem da v2_esquema: cria o banco app (os schemas dos tenants vêm depois).
set -euo pipefail
cd "$(dirname "$0")/../../.."
psql() { docker compose exec -T postgres-origem psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }

psql -c "create database app"
