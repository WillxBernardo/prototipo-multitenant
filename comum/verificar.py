#!/usr/bin/env python3
"""Verificação de correção (seção 3 do medicao.md).

Calcula, a partir de comum/gerar_dados.py, o conteúdo esperado dos modelos finais
fct_pedidos e dim_clientes para os tenants informados e compara com o que está no
postgres-destino. O destino deve conter exatamente esses tenants: linhas faltando,
linhas a mais (inclusive de outros tenants), chaves duplicadas e valores diferentes
contam como divergência.

Contrato dos modelos finais (no schema --schema, padrão "analytics"):
  fct_pedidos : tenant_id, pedido_id, cliente_id, data_pedido, status, valor_total
                (um registro por pedido; valor_total = soma de quantidade * preco_unitario)
  dim_clientes: tenant_id, cliente_id, nome, cidade, criado_em
                (um registro por cliente e tenant)
tenant_id é o nome do tenant (por exemplo, 'tenant_a'). A consulta normaliza os tipos
(text, bigint, date, timestamp em UTC) e compara valor_total com duas casas decimais.

Modo --aguardar (métrica M3d): repete a verificação a cada 5 s até passar ou até o
--timeout. Ao passar, informa os segundos desde --inicio (padrão: o início do script)
e imprime uma linha final "resultado_json: {...}".

Códigos de saída: 0 = bate; 1 = não bate (ou tempo esgotado); 2 = erro de conexão ou de uso.

Conexão por variáveis de ambiente (exporte o .env com: set -a; . ./.env; set +a):
  PG_DESTINO_SENHA (obrigatória), PG_DESTINO_HOST (padrão localhost),
  PG_DESTINO_PORTA (15433), PG_DESTINO_BANCO (dw), PG_DESTINO_USUARIO (postgres).

Exemplos:
  python comum/verificar.py tenant_a tenant_b tenant_c
  python comum/verificar.py tenant_a tenant_b tenant_c tenant_d --aguardar --timeout 900 \\
      --inicio 2026-11-20T14:03:12Z
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal
from typing import NamedTuple

import psycopg2
from psycopg2 import extensions, sql

from gerar_dados import gerar, validar_tenant

INTERVALO_S = 5  # seção 4, M3d
CENTAVO = Decimal("0.01")


class Modelo(NamedTuple):
    nome: str
    chave: tuple[str, ...]
    valores: tuple[str, ...]
    consulta: str  # {} recebe o schema


MODELOS = (
    Modelo(
        "fct_pedidos",
        ("tenant_id", "pedido_id"),
        ("cliente_id", "data_pedido", "status", "valor_total"),
        "select tenant_id::text, pedido_id::bigint, cliente_id::bigint, data_pedido::date,"
        " status::text, round(valor_total::numeric, 2) from {}.fct_pedidos",
    ),
    Modelo(
        "dim_clientes",
        ("tenant_id", "cliente_id"),
        ("nome", "cidade", "criado_em"),
        "select tenant_id::text, cliente_id::bigint, nome::text, cidade::text,"
        " criado_em::timestamp from {}.dim_clientes",
    ),
)


class Diferencas(NamedTuple):
    modelo: Modelo
    esperadas: Counter   # tenant -> número de linhas esperadas
    encontradas: Counter  # tenant -> número de linhas encontradas
    faltando: list        # [(chave, valores esperados)]
    sobrando: list        # [(chave, valores encontrados)]
    divergentes: list     # [(chave, esperados, encontrados)]
    duplicadas: list      # [chave]

    @property
    def ok(self) -> bool:
        return not (self.faltando or self.sobrando or self.divergentes or self.duplicadas)

    def resumo(self) -> str:
        return (f"{self.modelo.nome}: faltando {len(self.faltando)}, sobrando {len(self.sobrando)},"
                f" divergentes {len(self.divergentes)}, duplicadas {len(self.duplicadas)}")


class Resultado(NamedTuple):
    diferencas: list[Diferencas]
    erro: str | None = None
    erro_conexao: bool = False

    @property
    def ok(self) -> bool:
        return self.erro is None and all(d.ok for d in self.diferencas)

    def resumo(self) -> str:
        if self.erro:
            return self.erro.splitlines()[0]
        return "; ".join(d.resumo() for d in self.diferencas if not d.ok)


def calcular_esperado(tenants: list[str]) -> dict[str, dict[tuple, tuple]]:
    fct: dict[tuple, tuple] = {}
    dim: dict[tuple, tuple] = {}
    for tenant in tenants:
        dados = gerar(tenant)
        total: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for item in dados.itens_pedido:
            total[item.pedido_id] += item.quantidade * item.preco_unitario
        for p in dados.pedidos:
            fct[(tenant, p.id)] = (p.cliente_id, p.criado_em.date(), p.status, total[p.id].quantize(CENTAVO))
        for c in dados.clientes:
            dim[(tenant, c.id)] = (c.nome, c.cidade, c.criado_em)
    return {"fct_pedidos": fct, "dim_clientes": dim}


def _ordem(chave: tuple) -> tuple:
    # Ordena chaves que podem conter NULL (None) sem misturar tipos na comparação.
    return tuple((v is None, v if v is not None else 0) for v in chave)


def comparar(modelo: Modelo, esperado: dict[tuple, tuple], linhas: list[tuple]) -> Diferencas:
    n = len(modelo.chave)
    encontrado: dict[tuple, tuple] = {}
    duplicadas = []
    for linha in linhas:
        chave, valores = tuple(linha[:n]), tuple(linha[n:])
        if chave in encontrado:
            duplicadas.append(chave)
        else:
            encontrado[chave] = valores
    faltando = [(k, esperado[k]) for k in sorted(esperado.keys() - encontrado.keys(), key=_ordem)]
    sobrando = [(k, encontrado[k]) for k in sorted(encontrado.keys() - esperado.keys(), key=_ordem)]
    divergentes = [
        (k, esperado[k], encontrado[k])
        for k in sorted(esperado.keys() & encontrado.keys(), key=_ordem)
        if esperado[k] != encontrado[k]
    ]
    return Diferencas(
        modelo,
        Counter(k[0] for k in esperado),
        Counter(linha[0] for linha in linhas),
        faltando, sobrando, divergentes, sorted(duplicadas, key=_ordem),
    )


def parametros_conexao() -> dict:
    senha = os.environ.get("PG_DESTINO_SENHA")
    if not senha:
        print("erro: PG_DESTINO_SENHA não definida. Rode: set -a; . ./.env; set +a", file=sys.stderr)
        sys.exit(2)
    return {
        "host": os.environ.get("PG_DESTINO_HOST", "localhost"),
        "port": int(os.environ.get("PG_DESTINO_PORTA", "15433")),
        "dbname": os.environ.get("PG_DESTINO_BANCO", "dw"),
        "user": os.environ.get("PG_DESTINO_USUARIO", "postgres"),
        "password": senha,
        "connect_timeout": 5,
        "options": "-c TimeZone=UTC",
        "application_name": "verificar",
    }


def verificar_uma_vez(params: dict, schema: str, esperado: dict) -> Resultado:
    try:
        conexao = psycopg2.connect(**params)
    except psycopg2.Error as erro:
        return Resultado([], f"erro de conexão: {str(erro).strip()}", erro_conexao=True)
    try:
        # Um único snapshot para os dois modelos.
        conexao.set_session(isolation_level=extensions.ISOLATION_LEVEL_REPEATABLE_READ, readonly=True)
        linhas = {}
        with conexao.cursor() as cursor:
            for modelo in MODELOS:
                cursor.execute(sql.SQL(modelo.consulta).format(sql.Identifier(schema)))
                linhas[modelo.nome] = cursor.fetchall()
    except psycopg2.Error as erro:
        return Resultado([], f"erro na consulta: {str(erro).strip()}")
    finally:
        conexao.close()
    return Resultado([comparar(m, esperado[m.nome], linhas[m.nome]) for m in MODELOS])


def _fmt(valor: object) -> str:
    if valor is None:
        return "NULL"
    if isinstance(valor, str):
        return repr(valor)
    if isinstance(valor, dt.datetime):
        return valor.isoformat(sep=" ")
    if isinstance(valor, dt.date):
        return valor.isoformat()
    return str(valor)


def _fmt_linha(colunas: tuple[str, ...], valores: tuple) -> str:
    return ", ".join(f"{c}={_fmt(v)}" for c, v in zip(colunas, valores))


def imprimir(resultado: Resultado, max_exemplos: int) -> None:
    if resultado.erro:
        print(resultado.erro)
        return
    for d in resultado.diferencas:
        m = d.modelo
        print(f"{m.nome}: {'OK' if d.ok else 'DIVERGENTE'} "
              f"(esperadas {sum(d.esperadas.values())}, encontradas {sum(d.encontradas.values())})")
        for tenant in sorted(set(d.esperadas) | set(d.encontradas), key=lambda t: (t is None, t or "")):
            print(f"  {_fmt(tenant)}: esperadas {d.esperadas[tenant]}, encontradas {d.encontradas[tenant]}")
        if d.ok:
            continue
        print(f"  {d.resumo()}")
        for chave, valores in d.faltando[:max_exemplos]:
            print(f"    faltando   {_fmt_linha(m.chave, chave)} | esperado: {_fmt_linha(m.valores, valores)}")
        for chave, valores in d.sobrando[:max_exemplos]:
            print(f"    sobrando   {_fmt_linha(m.chave, chave)} | encontrado: {_fmt_linha(m.valores, valores)}")
        for chave, esp, enc in d.divergentes[:max_exemplos]:
            cols = "; ".join(f"{c}: esperado {_fmt(e)}, encontrado {_fmt(f)}"
                             for c, e, f in zip(m.valores, esp, enc) if e != f)
            print(f"    divergente {_fmt_linha(m.chave, chave)} | {cols}")
        for chave in d.duplicadas[:max_exemplos]:
            print(f"    duplicada  {_fmt_linha(m.chave, chave)}")
        omitidas = sum(max(0, len(x) - max_exemplos) for x in (d.faltando, d.sobrando, d.divergentes, d.duplicadas))
        if omitidas:
            print(f"    ... e mais {omitidas} (use --max-exemplos)")


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(momento: dt.datetime) -> str:
    return momento.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ler_instante(texto: str) -> dt.datetime:
    momento = dt.datetime.fromisoformat(texto)
    return momento.replace(tzinfo=dt.timezone.utc) if momento.tzinfo is None else momento


def aguardar(params: dict, schema: str, esperado: dict, tenants: list[str],
             timeout: float, inicio: dt.datetime, max_exemplos: int) -> int:
    t0 = time.monotonic()
    tentativa = 0
    while True:
        tentativa += 1
        momento = _agora()
        resultado = verificar_uma_vez(params, schema, esperado)
        if resultado.ok:
            segundos = (momento - inicio).total_seconds()
            imprimir(resultado, max_exemplos)
            print(f"OK na tentativa {tentativa} (consulta às {_iso(momento)}): {segundos:.1f} s desde {_iso(inicio)}")
            print("resultado_json: " + json.dumps({
                "ok": True, "tenants": tenants, "inicio_utc": _iso(inicio), "sucesso_utc": _iso(momento),
                "segundos": round(segundos, 1), "tentativas": tentativa, "intervalo_s": INTERVALO_S,
            }, ensure_ascii=False))
            return 0
        print(f"[{_iso(momento)}] tentativa {tentativa}: ainda não bate ({resultado.resumo()})", flush=True)
        proxima = t0 + tentativa * INTERVALO_S
        if proxima - t0 > timeout:
            print(f"Tempo esgotado ({timeout:.0f} s). Última verificação:")
            imprimir(resultado, max_exemplos)
            print("resultado_json: " + json.dumps({
                "ok": False, "tenants": tenants, "inicio_utc": _iso(inicio), "ultima_utc": _iso(momento),
                "tentativas": tentativa, "intervalo_s": INTERVALO_S,
            }, ensure_ascii=False))
            return 1
        time.sleep(max(0.0, proxima - time.monotonic()))


def main(argv: list[str] | None = None) -> int:
    inicio_script = _agora()
    parser = argparse.ArgumentParser(description="Verificação de correção dos modelos finais (seção 3 do medicao.md).")
    parser.add_argument("tenants", nargs="+", help="tenants esperados no destino, por exemplo tenant_a tenant_b tenant_c")
    parser.add_argument("--schema", default="analytics", help="schema dos modelos finais no destino (padrão: analytics)")
    parser.add_argument("--aguardar", action="store_true", help=f"repete a cada {INTERVALO_S} s até bater ou até o timeout")
    parser.add_argument("--timeout", type=float, default=600, help="limite do modo --aguardar, em segundos (padrão: 600)")
    parser.add_argument("--inicio", type=_ler_instante,
                        help="instante de referência para M3d, ISO 8601 (sem fuso = UTC); padrão: início do script")
    parser.add_argument("--max-exemplos", type=int, default=10, help="exemplos impressos por tipo de diferença (padrão: 10)")
    args = parser.parse_args(argv)

    try:
        tenants = [validar_tenant(t) for t in dict.fromkeys(args.tenants)]
    except ValueError as erro:
        parser.error(str(erro))

    params = parametros_conexao()
    esperado = calcular_esperado(tenants)

    if args.aguardar:
        return aguardar(params, args.schema, esperado, tenants, args.timeout,
                        args.inicio or inicio_script, args.max_exemplos)

    resultado = verificar_uma_vez(params, args.schema, esperado)
    imprimir(resultado, args.max_exemplos)
    if resultado.erro_conexao:
        return 2
    print("RESULTADO: OK" if resultado.ok else "RESULTADO: DIVERGENTE")
    return 0 if resultado.ok else 1


if __name__ == "__main__":
    sys.exit(main())
