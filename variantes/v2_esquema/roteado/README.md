# v2_esquema/roteado: esquema por tenant com roteamento (análise complementar D)

Reproduz o desenho do Brasil Participativo sobre a origem da v2 (`variantes/v2_esquema/origem/`). Não é uma
variante pré-registrada: ver a seção 11 do `medicao.md`.

- **Captura:** um conector Debezium Postgres com `schema.include.list` `tenant_.*` e o SMT nativo
  `io.debezium.transforms.ByLogicalTableRouter`. O SMT roteia `app.<schema>.<tabela>` para `raw.<tabela>` e põe o
  schema na chave como `tenant_id`. São 4 tópicos, independentemente do número de tenants.
- **Destino:** um JDBC Sink com `topics.regex` `raw\..*`, que grava as tabelas `public.raw_<tabela>` com chave
  primária `(id, tenant_id)`.
- **dbt:** como na v3, uma source `raw` sem lista de tenants, com `tenant_id` vindo da coluna.

## Montagem com 3 tenants

```bash
comum/execucao/montar.sh v2_esquema roteado/dbt roteado/conectores
```
