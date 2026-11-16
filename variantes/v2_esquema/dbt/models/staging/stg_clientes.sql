select
    tenant_id,
    id as cliente_id,
    nome,
    cidade,
    criado_em
from ({{ unir_tenants('clientes') }}) as clientes
