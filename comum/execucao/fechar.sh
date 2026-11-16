#!/usr/bin/env bash
# Fim de uma execução de M3d: espera a verificação, registra o ciclo de metadados, confere os arquivos,
# grava só M3d (medir.py --somente-m3d) e faz o commit da medição.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
v=$1; n=$2; antes=$3; depois=$4
F="medicoes/brutos/${v}_e${n}_m3d_verificar.txt"
for i in $(seq 1 200); do grep -q '^resultado_json:' "$F" && break; sleep 5; done
grep '^resultado_json:' "$F"
T0=$(grep "^$v,$n,0," medicoes/diario.csv | cut -d, -f4)
python3 comum/execucao/ciclo.py "$PWD" "$v" "$n" "$T0"
echo "--- git diff --stat $depois (\"depois do tenant_d\") -- conectores dbt (deve ser vazio):"
git diff --stat "$depois" -- "variantes/$v/conectores" "variantes/$v/dbt"
echo "--- git status da variante (deve ser vazio):"
git status --porcelain -- "variantes/$v"
echo "--- fim da conferência"
.venv/bin/python comum/medir.py "$v" pos_tenant_d --somente-m3d --execucao "$n" --antes "$antes" --m3d-arquivo "$F"
git add medicoes
git commit -q -m "Etapa 7: M3d execução $n ($v)"
git log --oneline -1
