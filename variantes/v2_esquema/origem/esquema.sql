-- Tabelas de um tenant. Sem tenant_id: o tenant é o schema (aplicado com search_path).
create table clientes (
    id         integer   primary key,
    nome       text      not null,
    cidade     text      not null,
    criado_em  timestamp not null
);

create table produtos (
    id     integer       primary key,
    nome   text          not null,
    preco  numeric(10,2) not null
);

create table pedidos (
    id          integer   primary key,
    cliente_id  integer   not null references clientes (id),
    criado_em   timestamp not null,
    status      text      not null
);

create table itens_pedido (
    id              integer       primary key,
    pedido_id       integer       not null references pedidos (id),
    produto_id      integer       not null references produtos (id),
    quantidade      integer       not null,
    preco_unitario  numeric(10,2) not null
);
