#!/usr/bin/env bash
# Passo 0 da incorporação (criação do tenant_d na origem) e início imediato do verificar.py --aguardar (M3d).
# Uso: comum/execucao/passo0.sh <variante> <execucao> [análise complementar, ex.: A]
# Com a análise, a saída vai para medicoes/brutos/complementar/ e o diário para o das análises complementares.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
v=$1; n=$2; analise=${3:-}
case $v in
    v3_compartilhado) d="variantes/$v/origem/criar_tenant.sh tenant_d (novas linhas com tenant_id nas tabelas do banco app)" ;;
    v2_esquema) d="variantes/$v/origem/criar_tenant.sh tenant_d (novo schema tenant_d no banco app, com tabelas e dados)" ;;
    v1_banco) d="variantes/$v/origem/criar_tenant.sh tenant_d (novo banco tenant_d, com tabelas e dados)" ;;
esac
"variantes/$v/origem/criar_tenant.sh" tenant_d
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ -n "$analise" ]; then
    saida="medicoes/brutos/complementar/${v}_${analise}_e${n}_m3d_verificar.txt"
    mkdir -p medicoes/brutos/complementar
else
    saida="medicoes/brutos/${v}_e${n}_m3d_verificar.txt"
fi
(nohup .venv/bin/python -u comum/verificar.py tenant_a tenant_b tenant_c tenant_d --aguardar --timeout 900 \
    --inicio "$T0" > "$saida" 2>&1 &)
if [ -n "$analise" ]; then
    .venv/bin/python comum/complementar.py diario "$v" "$analise" origem "$d" --execucao "$n" --timestamp "$T0"
else
    .venv/bin/python comum/diario.py "$v" origem "$d" --execucao "$n" --timestamp "$T0"
fi
