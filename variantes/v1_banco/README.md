# v1_banco: banco por tenant

- **Origem:** um banco por tenant (`tenant_a`, `tenant_b`, ...) na mesma instância, com as mesmas 4 tabelas no schema `public` de cada banco.
- **Captura:** um conector Debezium Postgres (`pgoutput`) **por banco**, porque cada conector captura um único banco.
  - Cada conector tem seu `topic.prefix` (o nome do tenant) e seu `slot.name`, já que os slots são globais na instância.
  - A publicação padrão (`FOR ALL TABLES`) é criada em cada banco.
  - Tópicos gerados: `<tenant>.public.<tabela>`.
- **Destino:** um JDBC Sink (`topics.regex`), que grava as tabelas `public.<tenant>_public_<tabela>` no `dw`.
- **dbt:**
  - uma source por tenant em `models/sources.yml`, com a lista de tenants em `vars.tenants` (`dbt_project.yml`);
  - a macro `unir_tenants` faz a união da mesma tabela de todos os tenants e acrescenta `tenant_id`;
  - 4 views de staging e 2 views finais (`fct_pedidos`, `dim_clientes`) no schema `analytics`.

## Montagem com os tenants iniciais (seção 5.2)

Comandos a partir da raiz do repositório:

```bash
docker compose down -v --remove-orphans && docker compose up -d --wait
set -a; . ./.env; set +a
V=variantes/v1_banco

for t in tenant_a tenant_b tenant_c; do $V/origem/criar_tenant.sh "$t"; done

for t in tenant_a tenant_b tenant_c; do
    curl -sS -X POST -H 'Content-Type: application/json' --data @$V/conectores/origem_$t.json http://127.0.0.1:8083/connectors
done
# Espere os snapshots terminarem (tópicos tenant_*.public.* criados) antes de registrar o sink:
curl -sS -X POST -H 'Content-Type: application/json' --data @$V/conectores/destino.json http://127.0.0.1:8083/connectors
# Espere o sink gravar as tabelas tenant_*_public_* no destino:
(cd $V/dbt && ../../../.venv/bin/dbt run)

.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c
```

O sink assina os tópicos por expressão regular. Um tópico criado depois que o sink já está rodando só é percebido na
próxima atualização de metadados do consumidor (`metadata.max.age.ms`, padrão de 5 min).
