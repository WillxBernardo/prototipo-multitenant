-- Esquema compartilhado: todas as tabelas têm tenant_id, que faz parte da chave primária.
create table clientes (
    tenant_id  text      not null,
    id         integer   not null,
    nome       text      not null,
    cidade     text      not null,
    criado_em  timestamp not null,
    primary key (tenant_id, id)
);

create table produtos (
    tenant_id  text          not null,
    id         integer       not null,
    nome       text          not null,
    preco      numeric(10,2) not null,
    primary key (tenant_id, id)
);

create table pedidos (
    tenant_id   text      not null,
    id          integer   not null,
    cliente_id  integer   not null,
    criado_em   timestamp not null,
    status      text      not null,
    primary key (tenant_id, id),
    foreign key (tenant_id, cliente_id) references clientes (tenant_id, id)
);

create table itens_pedido (
    tenant_id       text          not null,
    id              integer       not null,
    pedido_id       integer       not null,
    produto_id      integer       not null,
    quantidade      integer       not null,
    preco_unitario  numeric(10,2) not null,
    primary key (tenant_id, id),
    foreign key (tenant_id, pedido_id) references pedidos (tenant_id, id),
    foreign key (tenant_id, produto_id) references produtos (tenant_id, id)
);
