#!/usr/bin/env bash
# Cria um tenant na v3_compartilhado: novas linhas, com tenant_id, nas tabelas do banco app.
# Uso: variantes/v3_compartilhado/origem/criar_tenant.sh <tenant>
set -euo pipefail
tenant=${1:?uso: $0 <tenant>}
cd "$(dirname "$0")/../../.."
psql() { docker compose exec -T postgres-origem psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }

python3 comum/gerar_dados.py "$tenant" --saida "dados/$tenant" > /dev/null

for tabela in clientes produtos pedidos itens_pedido; do
    # O CSV do gerador não tem tenant_id: tira o cabeçalho e põe o tenant no início de cada linha.
    sed "1d; s/^/$tenant,/" "dados/$tenant/$tabela.csv" |
        psql -d app -c "copy $tabela from stdin with (format csv)"
done
