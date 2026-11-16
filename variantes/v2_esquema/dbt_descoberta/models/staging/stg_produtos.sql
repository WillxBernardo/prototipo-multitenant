select
    tenant_id,
    id as produto_id,
    nome,
    preco
from ({{ unir_tenants('produtos') }}) as produtos
