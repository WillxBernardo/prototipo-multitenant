select
    tenant_id,
    id as produto_id,
    nome,
    preco
from {{ source('app', 'produtos') }}
