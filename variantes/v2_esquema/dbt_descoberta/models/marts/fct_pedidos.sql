with totais as (
    select
        tenant_id,
        pedido_id,
        sum(quantidade * preco_unitario) as valor_total
    from {{ ref('stg_itens_pedido') }}
    group by tenant_id, pedido_id
)

select
    p.tenant_id,
    p.pedido_id,
    p.cliente_id,
    p.criado_em::date as data_pedido,
    p.status,
    coalesce(t.valor_total, 0) as valor_total
from {{ ref('stg_pedidos') }} as p
left join totais as t
    on t.tenant_id = p.tenant_id
    and t.pedido_id = p.pedido_id
