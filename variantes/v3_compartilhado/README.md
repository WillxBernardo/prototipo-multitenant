# v3_compartilhado: esquema compartilhado

- **Origem:** banco `app`, schema `public`, com a coluna `tenant_id` em todas as tabelas (chave primária `(tenant_id, id)`). Um tenant novo são linhas novas.
- **Captura:** um conector Debezium Postgres (`pgoutput`, publicação padrão `FOR ALL TABLES`), que gera os tópicos `app.public.<tabela>`.
- **Destino:** um JDBC Sink (`topics.regex`), que grava as tabelas `public.app_public_<tabela>` no `dw`.
- **dbt:** 4 views de staging com seleção direta das fontes e 2 views finais (`fct_pedidos`, `dim_clientes`) no schema `analytics`.

## Montagem com os tenants iniciais (seção 5.2)

Comandos a partir da raiz do repositório:

```bash
docker compose down -v --remove-orphans && docker compose up -d --wait
set -a; . ./.env; set +a
V=variantes/v3_compartilhado

$V/origem/preparar.sh
for t in tenant_a tenant_b tenant_c; do $V/origem/criar_tenant.sh "$t"; done

curl -sS -X POST -H 'Content-Type: application/json' --data @$V/conectores/origem.json http://127.0.0.1:8083/connectors
# Espere o snapshot terminar (tópicos app.public.* criados) antes de registrar o sink:
curl -sS -X POST -H 'Content-Type: application/json' --data @$V/conectores/destino.json http://127.0.0.1:8083/connectors
# Espere o sink gravar as tabelas app_public_* no destino:
(cd $V/dbt && ../../../.venv/bin/dbt run)

.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c
```

O sink assina os tópicos por expressão regular. Um tópico criado depois que o sink já está rodando só é percebido na
próxima atualização de metadados do consumidor (`metadata.max.age.ms`, padrão de 5 min). Por isso, na montagem, o sink é
registrado depois do snapshot.
