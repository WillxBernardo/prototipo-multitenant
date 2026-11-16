select
    tenant_id,
    id as pedido_id,
    cliente_id,
    criado_em,
    status
from {{ source('raw', 'pedidos') }}
