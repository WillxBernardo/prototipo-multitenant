select
    tenant_id,
    cliente_id,
    nome,
    cidade,
    criado_em
from {{ ref('stg_clientes') }}
