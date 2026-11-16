#!/usr/bin/env bash
# Análise complementar B (evolução de esquema), parte da aplicação e observações:
#  1. migra o tenant_a na origem (alter + update; na v3, o alter vale para a tabela compartilhada);
#  2. espera o JDBC Sink acrescentar email à tabela bruta de clientes do tenant_a e registra se fez isso sozinho;
#  3. estado intermediário: verificar.py (3 tenants, sem email), dbt run do projeto dbt original e verificar.py de novo;
#  4. migra tenant_b e tenant_c;
#  5. inicia verificar.py --aguardar --com-email em segundo plano, com --inicio no fim da migração (M4d).
# Uso: comum/execucao/b_migrar.sh <variante>
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
v=$1
B=medicoes/brutos/complementar; mkdir -p "$B"
C=".venv/bin/python comum/complementar.py"
M=comum/execucao/migrar_email.sh
export DBT_USE_COLORS=false
bruta() { case $v in v3_compartilhado) echo app_public_clientes ;; v2_esquema) echo "app_$1_clientes" ;; v1_banco) echo "$1_public_clientes" ;; esac; }
tem_email() {
    docker compose exec -T postgres-destino psql -U postgres -d dw -Atc "select count(*) from information_schema.columns
        where table_schema = 'public' and table_name = '$1' and column_name = 'email'"
}

# 1. tenant_a
"$M" "$v" alter tenant_a
"$M" "$v" update tenant_a

# 2. o sink acrescenta a coluna sozinho?
inicio=$(date +%s)
for i in $(seq 1 120); do [ "$(tem_email "$(bruta tenant_a)")" = 1 ] && break; sleep 1; done
if [ "$(tem_email "$(bruta tenant_a)")" = 1 ]; then
    $C valor "$v" B B_sink_coluna_automatica sim \
        --observacao "o JDBC Sink acrescentou email a $(bruta tenant_a) sozinho, ~$(( $(date +%s) - inicio )) s depois do update do tenant_a"
else
    $C valor "$v" B B_sink_coluna_automatica nao --observacao "email não apareceu em $(bruta tenant_a) em 120 s"
fi

# 3. estado intermediário (só o tenant_a migrado)
.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c > "$B/${v}_B_e1_intermediario_verificar_antes_dbt.txt" 2>&1 && r1=ok || r1=falhou
$C diario "$v" B observacao "estado intermediário (só tenant_a migrado): verificar.py com 3 tenants, sem email: $r1"
(cd "variantes/$v/dbt" && ../../../.venv/bin/dbt run > "../../../$B/${v}_B_e1_intermediario_dbt_run.txt" 2>&1) && r2=ok || r2=falhou
$C diario "$v" B observacao "estado intermediário: dbt run do projeto dbt original: $r2"
.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c > "$B/${v}_B_e1_intermediario_verificar_depois_dbt.txt" 2>&1 && r3=ok || r3=falhou
$C diario "$v" B observacao "estado intermediário: verificar.py com 3 tenants depois do dbt run: $r3"
erro=$(grep -m1 -iE 'each UNION query|Database Error in' "$B/${v}_B_e1_intermediario_dbt_run.txt" | sed 's/^[0-9:]* *//' || true)
resumo=$(grep -m1 -E '^.*Done\. PASS=' "$B/${v}_B_e1_intermediario_dbt_run.txt" | sed 's/^[0-9:]* *//' || true)
$C valor "$v" B B_intermediario_modelos "$r1/$r3" --observacao "verificar.py (3 tenants, sem email) antes/depois do dbt run, com só o tenant_a migrado"
$C valor "$v" B B_intermediario_dbt_run "$r2" --observacao "$resumo ${erro:+| $erro}"

# 4. demais tenants
for t in tenant_b tenant_c; do
    [ "$v" = v3_compartilhado ] || "$M" "$v" alter "$t"
    "$M" "$v" update "$t"
done

# 5. M4d: do fim da migração até dim_clientes ter email correto para todos os tenants
T=$(grep "^$v,B,1," "$B/diario.csv" | grep ',origem,' | tail -1 | cut -d, -f5)
(nohup .venv/bin/python -u comum/verificar.py tenant_a tenant_b tenant_c --com-email --aguardar --timeout 900 \
    --inicio "$T" > "$B/${v}_B_e1_m4d_verificar.txt" 2>&1 &)
echo "fim da migração na origem: $T"
