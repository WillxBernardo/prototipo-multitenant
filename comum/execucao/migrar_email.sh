#!/usr/bin/env bash
# Análise complementar B: um comando da migração de esquema na origem (ato da aplicação), registrado no
# diário das análises complementares com tipo origem e o timestamp UTC do fim do comando.
# Uso: comum/execucao/migrar_email.sh <variante> <alter|update> <tenant>
# Na v3_compartilhado, o alter é feito uma vez na tabela compartilhada; o update é feito tenant por tenant.
set -euo pipefail
cd "$(dirname "$0")/../.."
v=$1; acao=$2; t=$3
[[ $t =~ ^tenant_[a-z]$ ]] || { echo "tenant inválido: $t" >&2; exit 2; }
case "$v:$acao" in
    v3_compartilhado:alter)  banco=app; sql="alter table clientes add column email text" ;;
    v3_compartilhado:update) banco=app; sql="update clientes set email = 'cliente' || id || '@' || tenant_id || '.exemplo' where tenant_id = '$t'" ;;
    v2_esquema:alter)        banco=app; sql="alter table $t.clientes add column email text" ;;
    v2_esquema:update)       banco=app; sql="update $t.clientes set email = 'cliente' || id || '@$t.exemplo'" ;;
    v1_banco:alter)          banco=$t;  sql="alter table clientes add column email text" ;;
    v1_banco:update)         banco=$t;  sql="update clientes set email = 'cliente' || id || '@$t.exemplo'" ;;
    *) echo "uso: $0 <variante> <alter|update> <tenant>" >&2; exit 2 ;;
esac
docker compose exec -T postgres-origem psql -U postgres -d "$banco" -v ON_ERROR_STOP=1 -q -c "$sql"
fim=$(date -u +%Y-%m-%dT%H:%M:%SZ)
.venv/bin/python comum/complementar.py diario "$v" B origem "banco $banco: $sql" --timestamp "$fim"
