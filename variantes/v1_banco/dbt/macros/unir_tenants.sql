{# Une a mesma tabela de todos os tenants de var('tenants'), acrescentando a coluna tenant_id. #}
{% macro unir_tenants(tabela) %}
    {%- for tenant in var('tenants') %}
    select '{{ tenant }}'::text as tenant_id, * from {{ source(tenant, tabela) }}
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
{% endmacro %}
