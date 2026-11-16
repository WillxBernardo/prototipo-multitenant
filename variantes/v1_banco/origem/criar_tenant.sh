#!/usr/bin/env bash
# Cria um tenant na v1_banco: um banco novo, com as tabelas e os dados do tenant.
# Uso: variantes/v1_banco/origem/criar_tenant.sh <tenant>
set -euo pipefail
tenant=${1:?uso: $0 <tenant>}
cd "$(dirname "$0")/../../.."
psql() { docker compose exec -T postgres-origem psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }

python3 comum/gerar_dados.py "$tenant" --saida "dados/$tenant" > /dev/null

psql -c "create database $tenant"
psql -d "$tenant" -f - < variantes/v1_banco/origem/esquema.sql

for tabela in clientes produtos pedidos itens_pedido; do
    psql -d "$tenant" -c "copy $tabela from stdin with (format csv, header)" < "dados/$tenant/$tabela.csv"
done
