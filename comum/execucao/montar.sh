#!/usr/bin/env bash
# Montagem com os 3 tenants iniciais, conforme o README da variante (seção 5.2), a partir de ambiente limpo.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
v=$1; V=variantes/$v
docker compose down -v --remove-orphans > /dev/null 2>&1
docker compose up -d --wait --wait-timeout 300 > /dev/null 2>&1
echo "ambiente no ar: $(date -u +%H:%M:%SZ)"
if [ -x "$V/origem/preparar.sh" ]; then "$V/origem/preparar.sh"; fi
for t in tenant_a tenant_b tenant_c; do "$V/origem/criar_tenant.sh" "$t"; done
n=0
for f in "$V"/conectores/origem*.json; do
    curl -sS -o /dev/null -w "$(basename "$f"): HTTP %{http_code}\n" -X POST -H 'Content-Type: application/json' --data @"$f" http://127.0.0.1:8083/connectors
    n=$((n + 1))
done
for i in $(seq 1 60); do
    [ "$(docker compose logs kafka-connect 2>&1 | grep -c 'Snapshot ended with SnapshotResult \[status=COMPLETED')" -ge "$n" ] && break
    sleep 3
done
echo "snapshots concluídos ($n): $(date -u +%H:%M:%SZ)"
curl -sS -o /dev/null -w "destino.json: HTTP %{http_code} às $(date -u +%H:%M:%SZ)\n" -X POST -H 'Content-Type: application/json' --data @"$V/conectores/destino.json" http://127.0.0.1:8083/connectors
q="select coalesce(sum((xpath('/row/c/text()', query_to_xml(format('select count(*) as c from public.%I', table_name), false, true, '')))[1]::text::int),0) from information_schema.tables where table_schema='public'"
for i in $(seq 1 60); do
    r=$(docker compose exec -T postgres-destino psql -U postgres -d dw -Atc "$q")
    [ "$r" = "12437" ] && break
    sleep 3
done
echo "linhas no destino: $r"
(cd "$V/dbt" && ../../../.venv/bin/dbt run 2>&1 | grep -E 'Done\.|ERROR')
.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c | tail -1
echo "montagem concluída: $(date -u +%H:%M:%SZ)"
