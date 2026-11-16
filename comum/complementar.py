#!/usr/bin/env python3
"""Registro das análises complementares, posteriores à tag v0-medicao (seção 11 do medicao.md).

Grava os resultados em medicoes/complementar.csv
(variante, analise, execucao, metrica, valor, observacao) e o diário das análises em
medicoes/brutos/complementar/diario.csv
(variante, analise, execucao, passo, timestamp_utc, tipo, descricao).

Subcomandos (na raiz do repositório; todos aceitam --execucao, padrão 1):
  diario   <variante> <analise> <tipo> "<descrição>" [--timestamp T]
           tipos: origem e observacao (não contam como passo de engenharia de dados),
           comando, edicao, chamada_api, reinicio. Os passos são numerados a partir de 0.
  valor    <variante> <analise> <metrica> <valor> [--observacao "..."]
  passos   <variante> <analise> <metrica> [--origem]
           conta as linhas do diário sem origem e observacao (com --origem, só as de origem)
  arquivos <variante> <analise> <metrica> --diff REF:CAMINHO [--diff REF:CAMINHO ...]
           arquivos alterados entre REF e a árvore de trabalho em cada CAMINHO (sem README.md),
           incluindo arquivos novos ainda não versionados
  tempo    <variante> <analise> <metrica> <saída do verificar.py --aguardar>
  m2       <variante> <analise> --dbt <diretório dbt> [--conectores <diretório>] [--sufixo _inicial]
           M2b, M2c, M2d e M2e (conectores + o diretório dbt indicado, relativos a variantes/<variante>/),
           como no medir.py
  m1       <variante> <analise> <inicial|pos_tenant_d>
           roda a verificação de correção do momento e coleta M1a, M1b e M1c do ambiente em execução,
           com as mesmas funções do medir.py (métricas gravadas como M1x_<momento>)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import medir

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ / "medicoes" / "complementar.csv"
BRUTOS = RAIZ / "medicoes" / "brutos" / "complementar"
DIARIO = BRUTOS / "diario.csv"
CAB_RESULTADOS = ["variante", "analise", "execucao", "metrica", "valor", "observacao"]
CAB_DIARIO = ["variante", "analise", "execucao", "passo", "timestamp_utc", "tipo", "descricao"]
TIPOS = ("origem", "observacao", "comando", "edicao", "chamada_api", "reinicio")
NAO_CONTAM = ("origem", "observacao")


def anexar(caminho: Path, cabecalho: list[str], linha: list) -> None:
    novo = not caminho.exists() or caminho.stat().st_size == 0
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f, lineterminator="\n")
        if novo:
            escritor.writerow(cabecalho)
        escritor.writerow(linha)


def ler(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    with caminho.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gravar(args, metrica: str, valor, observacao: str = "") -> None:
    anexar(RESULTADOS, CAB_RESULTADOS, [args.variante, args.analise, args.execucao, metrica, valor, observacao])
    print(f"{args.variante} {args.analise} e{args.execucao} {metrica} = {valor}  {observacao}")


def bruto(args, nome: str, conteudo: str) -> None:
    BRUTOS.mkdir(parents=True, exist_ok=True)
    (BRUTOS / f"{args.variante}_{args.analise}_e{args.execucao}_{nome}").write_text(conteudo, encoding="utf-8")


def cmd_diario(args) -> None:
    timestamp = args.timestamp or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    timestamp = timestamp.replace("+00:00", "Z")
    anteriores = [r for r in ler(DIARIO) if (r["variante"], r["analise"], r["execucao"])
                  == (args.variante, args.analise, str(args.execucao))]
    linha = [args.variante, args.analise, args.execucao, len(anteriores), timestamp, args.tipo, args.descricao]
    anexar(DIARIO, CAB_DIARIO, linha)
    print(",".join(str(v) for v in linha))


def cmd_valor(args) -> None:
    gravar(args, args.metrica, args.valor_metrica, args.observacao)


def cmd_passos(args) -> None:
    linhas = [r for r in ler(DIARIO) if (r["variante"], r["analise"], r["execucao"])
              == (args.variante, args.analise, str(args.execucao))]
    escolhidas = [r for r in linhas if (r["tipo"] == "origem") == args.origem and r["tipo"] != "observacao"]
    tipos = Counter(r["tipo"] for r in escolhidas)
    gravar(args, args.metrica, len(escolhidas), ", ".join(f"{n} {t}" for t, n in sorted(tipos.items())) or "nenhum passo")


def git(*comando: str) -> str:
    return subprocess.run(("git", *comando), cwd=RAIZ, check=True, capture_output=True, text=True).stdout


def cmd_arquivos(args) -> None:
    alterados, texto = [], []
    for item in args.diff:
        ref, caminho = item.split(":", 1)
        pathspec = [caminho, ":(exclude,glob)**/README.md"]
        texto.append(f"$ git diff --stat {ref} -- {caminho}\n" + git("diff", "--stat", ref, "--", *pathspec))
        texto.append(git("diff", ref, "--", *pathspec))
        for linha in git("diff", "--numstat", ref, "--", *pathspec).splitlines():
            alterados.append(linha.split("\t")[2])
        novos = [p for p in git("ls-files", "--others", "--exclude-standard", "--", *pathspec).splitlines()
                 if Path(p).name != "README.md"]
        texto.append("arquivos novos não versionados: " + (" ".join(novos) or "nenhum") + "\n")
        alterados += novos
    bruto(args, f"{args.metrica}_diff.txt", "\n".join(texto))
    gravar(args, args.metrica, len(alterados), " ".join(Path(p).name for p in alterados) or "nenhum arquivo")


def cmd_tempo(args) -> None:
    linhas = Path(args.arquivo).read_text(encoding="utf-8").splitlines()
    bruto_json = next((l.split(":", 1)[1] for l in reversed(linhas) if l.startswith("resultado_json:")), None)
    if bruto_json is None:
        sys.exit(f"sem linha resultado_json em {args.arquivo}")
    r = json.loads(bruto_json)
    if not r["ok"]:
        sys.exit(f"a verificação de {args.arquivo} não passou")
    gravar(args, args.metrica, r["segundos"],
           f"{r['inicio_utc']} -> {r['sucesso_utc']}; {r['tentativas']} tentativas a cada {r['intervalo_s']} s")


def cmd_m1(args) -> None:
    c = medir.Coleta(args.variante, args.execucao, args.momento, RAIZ / "medicoes")
    c.brutos = BRUTOS
    c.prefixo = f"{args.variante}_{args.analise}_e{args.execucao}_{args.momento}_"
    medir.verificar_correcao(c)
    medir.medir_m1(c)
    for linha in c.linhas:
        gravar(args, f"{linha[3]}_{args.momento}", linha[4], linha[5])


def cmd_m2(args) -> None:
    base = RAIZ / "variantes" / args.variante
    conectores, dbt = base / args.conectores, base / args.dbt
    modelos = [p for p in medir.arquivos(dbt / "models") if p.suffix == ".sql"]
    macros = [p for p in medir.arquivos(dbt / "macros") if p.suffix == ".sql"]
    blocos, tabelas = medir.contar_sources(dbt)
    detalhe = io.StringIO()
    escritor = csv.writer(detalhe, lineterminator="\n")
    escritor.writerow(["arquivo", "linhas_uteis"])
    total = 0
    for diretorio in (conectores, dbt):
        for caminho in medir.arquivos(diretorio):
            n = medir.linhas_uteis(caminho)
            total += n
            escritor.writerow([caminho.relative_to(RAIZ).as_posix(), n])
    bruto(args, f"m2{args.sufixo}_linhas.csv", detalhe.getvalue())
    s = args.sufixo
    gravar(args, f"M2b{s}", len(modelos), f"{args.dbt}/models")
    gravar(args, f"M2c{s}", tabelas, f"{blocos} blocos de source")
    gravar(args, f"M2d{s}", len(macros), " ".join(p.stem for p in macros))
    gravar(args, f"M2e{s}", total, f"{args.conectores}/ e {args.dbt}/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Registro das análises complementares (seção 11).")
    sub = parser.add_subparsers(dest="comando", required=True)

    def novo(nome, funcao):
        p = sub.add_parser(nome)
        p.add_argument("variante", choices=medir.VARIANTES)
        p.add_argument("analise")
        p.add_argument("--execucao", type=int, default=1)
        p.set_defaults(funcao=funcao)
        return p

    p = novo("diario", cmd_diario)
    p.add_argument("tipo", choices=TIPOS)
    p.add_argument("descricao")
    p.add_argument("--timestamp")
    p = novo("valor", cmd_valor)
    p.add_argument("metrica")
    p.add_argument("valor_metrica")
    p.add_argument("--observacao", default="")
    p = novo("passos", cmd_passos)
    p.add_argument("metrica")
    p.add_argument("--origem", action="store_true")
    p = novo("arquivos", cmd_arquivos)
    p.add_argument("metrica")
    p.add_argument("--diff", action="append", required=True, metavar="REF:CAMINHO")
    p = novo("tempo", cmd_tempo)
    p.add_argument("metrica")
    p.add_argument("arquivo")
    p = novo("m2", cmd_m2)
    p.add_argument("--dbt", required=True)
    p.add_argument("--conectores", default="conectores")
    p.add_argument("--sufixo", default="")
    p = novo("m1", cmd_m1)
    p.add_argument("momento", choices=tuple(medir.TENANTS))

    args = parser.parse_args(argv)
    args.funcao(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
