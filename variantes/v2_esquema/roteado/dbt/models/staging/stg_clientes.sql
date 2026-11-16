select
    tenant_id,
    id as cliente_id,
    nome,
    cidade,
    criado_em
from {{ source('raw', 'clientes') }}
