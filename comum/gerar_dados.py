#!/usr/bin/env python3
"""Gera os dados de um tenant conforme a seção 3 do medicao.md.

Os dados dependem apenas do nome do tenant. A semente de cada tenant é derivada da
semente fixa 42 e do nome do tenant (SHA-256), de modo que:
  - a saída é idêntica para o mesmo tenant em qualquer execução e em qualquer variante;
  - tenants diferentes recebem dados diferentes, o que permite à verificação de
    correção detectar dados trocados ou misturados entre tenants.

O gerador usa apenas a biblioteca padrão (random.Random com semente inteira), sem
bibliotecas de dados falsos cuja saída mude entre versões. Versão de referência do
Python: 3.12.

Como biblioteca (a forma de carregar fica com cada variante):
    from gerar_dados import gerar, TABELAS, COLUNAS
    dados = gerar("tenant_a")          # DadosTenant: quatro listas de tuplas nomeadas
    for tabela in TABELAS:             # ordem compatível com as chaves estrangeiras
        linhas = getattr(dados, tabela)

Pela linha de comando:
    python comum/gerar_dados.py tenant_a               # imprime contagens e hashes
    python comum/gerar_dados.py tenant_a --saida DIR   # grava DIR/<tabela>.csv (com cabeçalho)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import random
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

SEMENTE = 42

N_CLIENTES = 100
N_PRODUTOS = 50
N_PEDIDOS = 1000
ITENS_POR_PEDIDO = (1, 5)        # uniforme em [1, 5]: média de 3 itens por pedido
QUANTIDADE = (1, 5)              # unidades de cada item
PRECO_CENTAVOS = (500, 50_000)   # R$ 5,00 a R$ 500,00

INICIO_CLIENTES = dt.datetime(2024, 1, 1)   # clientes cadastrados ao longo de 2024
INICIO_PEDIDOS = dt.datetime(2025, 1, 1)    # pedidos feitos ao longo de 2025
SEGUNDOS_NO_ANO = 365 * 24 * 60 * 60

NOMES = (
    "Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Felipe", "Gabriela", "Heitor",
    "Isabela", "João", "Larissa", "Marcos", "Natália", "Otávio", "Paula", "Rafael",
    "Sofia", "Thiago", "Valéria", "Yuri",
)
SOBRENOMES = (
    "Almeida", "Barbosa", "Cardoso", "Costa", "Ferreira", "Gomes", "Lima", "Martins",
    "Oliveira", "Pereira", "Ribeiro", "Rocha", "Santos", "Silva", "Souza",
)
CIDADES = (
    "Brasília", "São Paulo", "Rio de Janeiro", "Belo Horizonte", "Salvador", "Fortaleza",
    "Recife", "Porto Alegre", "Curitiba", "Goiânia", "Manaus", "Belém",
)
# 10 tipos x 5 linhas = 50 nomes de produto distintos (um por id).
TIPOS_PRODUTO = (
    "Caderno", "Caneta", "Mochila", "Garrafa", "Fone de ouvido",
    "Teclado", "Mouse", "Luminária", "Cadeira", "Mesa",
)
LINHAS_PRODUTO = ("Básico", "Compacto", "Plus", "Pro", "Premium")

STATUS = ("pendente", "pago", "enviado", "entregue", "cancelado")
PESOS_STATUS = (10, 15, 15, 50, 10)

# O nome do tenant vira nome de banco ou de schema em algumas variantes.
PADRAO_TENANT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

assert len(TIPOS_PRODUTO) * len(LINHAS_PRODUTO) == N_PRODUTOS


class Cliente(NamedTuple):
    id: int
    nome: str
    cidade: str
    criado_em: dt.datetime


class Produto(NamedTuple):
    id: int
    nome: str
    preco: Decimal


class Pedido(NamedTuple):
    id: int
    cliente_id: int
    criado_em: dt.datetime
    status: str


class ItemPedido(NamedTuple):
    id: int
    pedido_id: int
    produto_id: int
    quantidade: int
    preco_unitario: Decimal


class DadosTenant(NamedTuple):
    tenant: str
    clientes: list[Cliente]
    produtos: list[Produto]
    pedidos: list[Pedido]
    itens_pedido: list[ItemPedido]


# Ordem de carga compatível com as chaves estrangeiras.
TABELAS = ("clientes", "produtos", "pedidos", "itens_pedido")
COLUNAS = {
    "clientes": Cliente._fields,
    "produtos": Produto._fields,
    "pedidos": Pedido._fields,
    "itens_pedido": ItemPedido._fields,
}


def validar_tenant(tenant: str) -> str:
    if not PADRAO_TENANT.fullmatch(tenant):
        raise ValueError(
            f"nome de tenant inválido: {tenant!r} (use minúsculas, dígitos e _, começando por letra)"
        )
    return tenant


def semente_do_tenant(tenant: str) -> int:
    """Semente inteira derivada de SEMENTE e do nome do tenant."""
    resumo = hashlib.sha256(f"{SEMENTE}:{tenant}".encode("utf-8")).digest()
    return int.from_bytes(resumo[:8], "big")


def _instante(rng: random.Random, inicio: dt.datetime) -> dt.datetime:
    """Instante com precisão de segundos dentro do ano que começa em `inicio`."""
    return inicio + dt.timedelta(seconds=rng.randrange(SEGUNDOS_NO_ANO))


def gerar(tenant: str) -> DadosTenant:
    """Gera os dados do tenant. Mesma entrada, mesma saída."""
    validar_tenant(tenant)
    rng = random.Random(semente_do_tenant(tenant))

    clientes = []
    for i in range(1, N_CLIENTES + 1):
        nome = f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}"
        cidade = rng.choice(CIDADES)
        criado_em = _instante(rng, INICIO_CLIENTES)
        clientes.append(Cliente(i, nome, cidade, criado_em))

    produtos = []
    for i in range(1, N_PRODUTOS + 1):
        tipo = TIPOS_PRODUTO[(i - 1) % len(TIPOS_PRODUTO)]
        linha = LINHAS_PRODUTO[(i - 1) // len(TIPOS_PRODUTO)]
        preco = Decimal(rng.randint(*PRECO_CENTAVOS)).scaleb(-2)  # sempre com 2 casas
        produtos.append(Produto(i, f"{tipo} {linha}", preco))

    # Ids crescem com o tempo, como numa aplicação real.
    instantes = sorted(_instante(rng, INICIO_PEDIDOS) for _ in range(N_PEDIDOS))
    pedidos = []
    for i, criado_em in enumerate(instantes, start=1):
        cliente_id = rng.randint(1, N_CLIENTES)
        status = rng.choices(STATUS, weights=PESOS_STATUS)[0]
        pedidos.append(Pedido(i, cliente_id, criado_em, status))

    itens: list[ItemPedido] = []
    for pedido in pedidos:
        n_itens = rng.randint(*ITENS_POR_PEDIDO)
        # Sem produto repetido dentro do mesmo pedido.
        for produto_id in rng.sample(range(1, N_PRODUTOS + 1), n_itens):
            quantidade = rng.randint(*QUANTIDADE)
            preco_unitario = produtos[produto_id - 1].preco
            itens.append(ItemPedido(len(itens) + 1, pedido.id, produto_id, quantidade, preco_unitario))

    return DadosTenant(tenant, clientes, produtos, pedidos, itens)


def _formatar(valor: object) -> str:
    if isinstance(valor, dt.datetime):
        return valor.isoformat(sep=" ")  # AAAA-MM-DD HH:MM:SS, aceito pelo COPY do Postgres
    return str(valor)


def para_csv(dados: DadosTenant) -> dict[str, bytes]:
    """Serialização canônica: um CSV UTF-8 por tabela, com cabeçalho e fim de linha \\n."""
    arquivos = {}
    for tabela in TABELAS:
        buffer = io.StringIO()
        escritor = csv.writer(buffer, lineterminator="\n")
        escritor.writerow(COLUNAS[tabela])
        for linha in getattr(dados, tabela):
            escritor.writerow([_formatar(v) for v in linha])
        arquivos[tabela] = buffer.getvalue().encode("utf-8")
    return arquivos


def hash_total(arquivos: dict[str, bytes]) -> str:
    """SHA-256 do conjunto das quatro tabelas, na ordem de TABELAS."""
    h = hashlib.sha256()
    for tabela in TABELAS:
        h.update(tabela.encode("utf-8") + b"\0" + arquivos[tabela])
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera os dados de um tenant (seção 3 do medicao.md).")
    parser.add_argument("tenant", help="nome do tenant, por exemplo tenant_a")
    parser.add_argument("--saida", type=Path, help="diretório onde gravar <tabela>.csv (criado se não existir)")
    args = parser.parse_args(argv)

    try:
        dados = gerar(args.tenant)
    except ValueError as erro:
        parser.error(str(erro))
    arquivos = para_csv(dados)

    if args.saida:
        args.saida.mkdir(parents=True, exist_ok=True)
        for tabela in TABELAS:
            (args.saida / f"{tabela}.csv").write_bytes(arquivos[tabela])

    for tabela in TABELAS:
        n = len(getattr(dados, tabela))
        print(f"{tabela:<13} {n:>5} linhas  sha256={hashlib.sha256(arquivos[tabela]).hexdigest()}")
    print(f"tenant={dados.tenant} semente={semente_do_tenant(dados.tenant)} sha256_total={hash_total(arquivos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
