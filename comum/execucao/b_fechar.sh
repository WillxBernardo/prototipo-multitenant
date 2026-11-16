#!/usr/bin/env bash
# Análise complementar B: espera a verificação com email, grava M4_app, M4a, M4b, M4c e M4d, registra quantas
# tabelas brutas de clientes ganharam email no destino e desfaz as edições do dbt (git restore para o HEAD).
# Uso: comum/execucao/b_fechar.sh <variante> <commit de referência de dbt/ e conectores/> <sim|nao> "<descrição de M4c>"
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
v=$1; ref=$2; m4c=$3; desc=$4
B=medicoes/brutos/complementar
C=".venv/bin/python comum/complementar.py"
F="$B/${v}_B_e1_m4d_verificar.txt"
for i in $(seq 1 200); do grep -q '^resultado_json:' "$F" && break; sleep 5; done
grep '^resultado_json:' "$F"
$C passos "$v" B M4_app --origem
$C passos "$v" B M4a
$C arquivos "$v" B M4b --diff "$ref:variantes/$v/conectores" --diff "$ref:variantes/$v/dbt"
$C valor "$v" B M4c "$m4c" --observacao "$desc"
$C tempo "$v" B M4d "$F"
contagem=$(docker compose exec -T postgres-destino psql -U postgres -d dw -Atc "select
    count(*) filter (where exists (select 1 from information_schema.columns c where c.table_schema = t.table_schema
        and c.table_name = t.table_name and c.column_name = 'email')) || ' de ' || count(*)
    from information_schema.tables t where t.table_schema = 'public' and t.table_name like '%clientes'")
$C valor "$v" B B_sink_coluna_todas "$contagem" --observacao "tabelas brutas de clientes no destino com a coluna email, ao fim"
git restore --source=HEAD -- "variantes/$v/dbt" "variantes/$v/conectores"
echo "--- variante x HEAD depois do restore (deve ser vazio):"
git status --porcelain -- "variantes/$v"
