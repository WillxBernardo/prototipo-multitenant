# v2_esquema: esquema por tenant

- **Origem:** banco `app`, com um schema por tenant (`tenant_a`, `tenant_b`, ...) e as mesmas 4 tabelas em cada um.
- **Captura:** um conector Debezium Postgres (`pgoutput`) com `schema.include.list` por expressão regular (`tenant_.*`).
  A publicação é a padrão do Debezium (`publication.autocreate.mode=all_tables`, ou seja, `CREATE PUBLICATION ... FOR ALL TABLES`).
  Ela inclui automaticamente as tabelas de schemas criados depois, sem `ALTER PUBLICATION`. Tópicos gerados: `app.<tenant>.<tabela>`.
- **Destino:** um JDBC Sink (`topics.regex`), que grava as tabelas `public.app_<tenant>_<tabela>` no `dw`.
- **dbt:**
  - uma source por tenant em `models/sources.yml`, com a lista de tenants em `vars.tenants` (`dbt_project.yml`);
  - a macro `unir_tenants` faz a união da mesma tabela de todos os tenants e acrescenta `tenant_id`;
  - 4 views de staging e 2 views finais (`fct_pedidos`, `dim_clientes`) no schema `analytics`.

## Montagem com os tenants iniciais (seção 5.2)

Comandos a partir da raiz do repositório:

```bash
docker compose down -v --remove-orphans && docker compose up -d --wait
set -a; . ./.env; set +a
V=variantes/v2_esquema

$V/origem/preparar.sh
for t in tenant_a tenant_b tenant_c; do $V/origem/criar_tenant.sh "$t"; done

curl -sS -X POST -H 'Content-Type: application/json' --data @$V/conectores/origem.json http://127.0.0.1:8083/connectors
# Espere o snapshot terminar (tópicos app.tenant_* criados) antes de registrar o sink:
curl -sS -X POST -H 'Content-Type: application/json' --data @$V/conectores/destino.json http://127.0.0.1:8083/connectors
# Espere o sink gravar as tabelas app_tenant_* no destino:
(cd $V/dbt && ../../../.venv/bin/dbt run)

.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c
```

O sink assina os tópicos por expressão regular. Um tópico criado depois que o sink já está rodando só é percebido na
próxima atualização de metadados do consumidor (`metadata.max.age.ms`, padrão de 5 min).
