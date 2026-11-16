{# Descobre no information_schema do destino as tabelas gravadas pelo sink para cada tenant
   (tenant_<x>_public_<tabela>), une todas e extrai tenant_id do nome da tabela. #}
{% macro unir_tenants(tabela) %}
    {%- set consulta -%}
        select table_name, regexp_replace(table_name, '^(.+)_public_{{ tabela }}$', '\1') as tenant_id
        from information_schema.tables
        where table_schema = 'public'
          and table_name like 'tenant\_%\_public\_{{ tabela }}'
        order by table_name
    {%- endset -%}
    {%- if execute -%}
        {%- set linhas = run_query(consulta).rows -%}
        {%- if linhas | length == 0 -%}
            {{ exceptions.raise_compiler_error("nenhuma tabela de tenant encontrada para " ~ tabela) }}
        {%- endif -%}
        {%- for linha in linhas %}
    select '{{ linha[1] }}'::text as tenant_id, *
    from {{ api.Relation.create(database=target.database, schema='public', identifier=linha[0]) }}
            {%- if not loop.last %}
    union all
            {%- endif %}
        {%- endfor %}
    {%- else -%}
    select null::text as tenant_id
    {%- endif -%}
{% endmacro %}
