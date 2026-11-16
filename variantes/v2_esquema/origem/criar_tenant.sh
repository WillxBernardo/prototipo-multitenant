#!/usr/bin/env bash
# Cria um tenant na v2_esquema: um schema novo no banco app, com as tabelas e os dados do tenant.
# Uso: variantes/v2_esquema/origem/criar_tenant.sh <tenant>
set -euo pipefail
tenant=${1:?uso: $0 <tenant>}
cd "$(dirname "$0")/../../.."
psql() { docker compose exec -T postgres-origem psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }

python3 comum/gerar_dados.py "$tenant" --saida "dados/$tenant" > /dev/null

psql -d app -c "create schema $tenant" -c "set search_path to $tenant" -f - < variantes/v2_esquema/origem/esquema.sql

for tabela in clientes produtos pedidos itens_pedido; do
    psql -d app -c "copy $tenant.$tabela from stdin with (format csv, header)" < "dados/$tenant/$tabela.csv"
done
