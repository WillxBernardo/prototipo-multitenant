select
    tenant_id,
    id as item_id,
    pedido_id,
    produto_id,
    quantidade,
    preco_unitario
from ({{ unir_tenants('itens_pedido') }}) as itens_pedido
