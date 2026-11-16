#!/usr/bin/env python3
"""Registra uma ação do operador em medicoes/diario.csv (seção 6 do medicao.md).

Colunas: variante, execucao, passo, timestamp_utc, tipo, descricao.
O passo é numerado automaticamente: 0 para o tipo "origem" (criação do tenant na
origem, ato da aplicação que não conta em M3a) e o próximo número para os demais.
O timestamp padrão é o instante do registro, em UTC.

Uso (na raiz do repositório):
  python comum/diario.py v2_esquema origem "criar_tenant.sh tenant_d" --timestamp 2026-11-16T13:00:00Z
  python comum/diario.py v2_esquema edicao "sources.yml: source tenant_d"
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VARIANTES = ("v1_banco", "v2_esquema", "v3_compartilhado")
TIPOS = ("origem", "comando", "edicao", "chamada_api", "reinicio")
CABECALHO = ["variante", "execucao", "passo", "timestamp_utc", "tipo", "descricao"]


def _instante(texto: str) -> str:
    momento = dt.datetime.fromisoformat(texto)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=dt.timezone.utc)
    return momento.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Registra uma ação do operador no diário (seção 6).")
    parser.add_argument("variante", choices=VARIANTES)
    parser.add_argument("tipo", choices=TIPOS)
    parser.add_argument("descricao")
    parser.add_argument("--execucao", type=int, default=1)
    parser.add_argument("--timestamp", type=_instante, help="instante da ação, ISO 8601 (padrão: agora, UTC)")
    parser.add_argument("--arquivo", type=Path, default=RAIZ / "medicoes" / "diario.csv")
    args = parser.parse_args(argv)

    timestamp = args.timestamp or _instante(dt.datetime.now(dt.timezone.utc).isoformat())
    linhas = []
    if args.arquivo.exists():
        with args.arquivo.open(newline="", encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
    da_execucao = [r for r in linhas if r["variante"] == args.variante and r["execucao"] == str(args.execucao)]

    if args.tipo == "origem":
        if any(r["passo"] == "0" for r in da_execucao):
            parser.error("o passo 0 já foi registrado para esta variante e execução")
        passo = 0
    else:
        passo = max([int(r["passo"]) for r in da_execucao] + [0]) + 1

    novo = not args.arquivo.exists() or args.arquivo.stat().st_size == 0
    args.arquivo.parent.mkdir(parents=True, exist_ok=True)
    with args.arquivo.open("a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f, lineterminator="\n")
        if novo:
            escritor.writerow(CABECALHO)
        linha = [args.variante, args.execucao, passo, timestamp, args.tipo, args.descricao]
        escritor.writerow(linha)
    print(",".join(str(v) for v in linha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
