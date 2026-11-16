select
    tenant_id,
    id as item_id,
    pedido_id,
    produto_id,
    quantidade,
    preco_unitario
from {{ source('raw', 'itens_pedido') }}
