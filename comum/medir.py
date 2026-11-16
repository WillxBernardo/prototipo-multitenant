#!/usr/bin/env python3
"""Coleta as métricas de uma variante (seções 4 e 8 do medicao.md).

Grava uma linha por métrica em medicoes/resultados.csv
(variante, execucao, momento, metrica, valor, observacao) e as saídas brutas em
medicoes/brutos/<variante>_e<execucao>_<momento>_*.

Antes de medir, roda a verificação de correção (comum/verificar.py) com os tenants do
momento (inicial: tenant_a a tenant_c; pos_tenant_d: tenant_a a tenant_d) e não grava
nada se ela não passar. Também recusa gravar de novo um momento já medido.

M1 (estado do ambiente em execução):
  M1a  conectores com o conector e todas as tarefas em RUNNING (GET /connectors?expand=status)
  M1b  slots de replicação na origem (SELECT count(*) FROM pg_replication_slots)
  M1c  tópicos de dados no Kafka (exclui nomes iniciados por "_", o que inclui "__")
M2 (arquivos da variante; ignora README.md, arquivos ocultos e target/, logs/, dbt_packages/):
  M2a  arquivos em conectores/
  M2b  arquivos .sql em dbt/models/
  M2c  tabelas declaradas como source nos .yml de dbt/ (observação: número de blocos de source)
  M2d  arquivos .sql em dbt/macros/
  M2e  linhas não vazias e sem comentário em conectores/ e dbt/
  M2e_origem  mesma contagem em origem/ (métrica auxiliar, fora de M2e)
M3 (só em pos_tenant_d; exige --antes, --depois, --m3c, --m3c-descricao e --m3d-arquivo):
  M3a  linhas do diário da variante e execução, sem o passo 0 (tipo origem)
  M3b  arquivos alterados entre os commits --antes e --depois, restrito a conectores/ e dbt/
  M3c  sim/nao, com a descrição informada
  M3d  segundos do resultado_json da saída de verificar.py --aguardar

--somente-m3d (execuções 2 e 3; desvio registrado na seção 11): grava só M3d. M3a e M3b
(este contra --depois ou, se omitido, contra a árvore de trabalho) são calculados só para
conferência e salvos em brutos; M1, M2 e M3c não são coletados.

Uso (na raiz do repositório, com o .env exportado: set -a; . ./.env; set +a):
  python comum/medir.py v3_compartilhado inicial
  python comum/medir.py v3_compartilhado pos_tenant_d --antes <commit> --depois <commit> \\
      --m3c nao --m3c-descricao "..." --m3d-arquivo medicoes/brutos/v3_compartilhado_e1_m3d_verificar.txt
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import io
import json
import os
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

import verificar

RAIZ = Path(__file__).resolve().parent.parent
VARIANTES = ("v1_banco", "v2_esquema", "v3_compartilhado")
TENANTS = {
    "inicial": ["tenant_a", "tenant_b", "tenant_c"],
    "pos_tenant_d": ["tenant_a", "tenant_b", "tenant_c", "tenant_d"],
}
CABECALHO = ["variante", "execucao", "momento", "metrica", "valor", "observacao"]
DIRETORIOS_IGNORADOS = {"target", "logs", "dbt_packages"}
ARQUIVOS_IGNORADOS = {"README.md"}
COMENTARIO_LINHA = {".sql": ("--",), ".yml": ("#",), ".yaml": ("#",), ".sh": ("#",), ".py": ("#",)}
COMENTARIO_BLOCO = {".sql": (("/*", "*/"), ("{#", "#}"))}


# ---------------------------------------------------------------- utilitários

def executar(*comando: str) -> str:
    return subprocess.run(comando, cwd=RAIZ, check=True, capture_output=True, text=True).stdout


def psql(servico: str, sql: str, banco: str = "postgres") -> str:
    return executar("docker", "compose", "exec", "-T", servico, "psql", "-U", "postgres", "-d", banco, "-AtX", "-c", sql)


class Coleta:
    def __init__(self, variante: str, execucao: int, momento: str, dir_medicoes: Path):
        self.variante, self.execucao, self.momento = variante, execucao, momento
        self.brutos = dir_medicoes / "brutos"
        self.prefixo = f"{variante}_e{execucao}_{momento}_"
        self.linhas: list[list] = []

    def metrica(self, nome: str, valor, observacao: str = "") -> None:
        self.linhas.append([self.variante, self.execucao, self.momento, nome, valor, observacao])

    def bruto(self, nome: str, conteudo: str) -> None:
        self.brutos.mkdir(parents=True, exist_ok=True)
        (self.brutos / f"{self.prefixo}{nome}").write_text(conteudo, encoding="utf-8")


# ---------------------------------------------------------------- verificação

def verificar_correcao(c: Coleta) -> None:
    tenants = TENANTS[c.momento]
    resultado = verificar.verificar_uma_vez(
        verificar.parametros_conexao(), "analytics", verificar.calcular_esperado(tenants))
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        verificar.imprimir(resultado, 10)
        print("RESULTADO: OK" if resultado.ok else "RESULTADO: DIVERGENTE")
    if not resultado.ok:
        print(saida.getvalue())
        sys.exit(f"verificação de correção não passou com {tenants}; nada foi gravado")
    c.bruto("verificacao.txt", saida.getvalue())


# ---------------------------------------------------------------- M1

def medir_m1(c: Coleta) -> None:
    porta = os.environ.get("CONNECT_PORTA", "8083")
    url = f"http://127.0.0.1:{porta}/connectors?expand=status&expand=info"
    with urllib.request.urlopen(url, timeout=10) as resposta:
        conectores = json.load(resposta)
    c.bruto("conectores.json", json.dumps(conectores, indent=2, ensure_ascii=False) + "\n")
    ativos = sorted(
        nome for nome, dados in conectores.items()
        if dados["status"]["connector"]["state"] == "RUNNING"
        and dados["status"]["tasks"]
        and all(t["state"] == "RUNNING" for t in dados["status"]["tasks"])
    )
    c.metrica("M1a", len(ativos), f"{len(conectores)} registrados; ativos: {' '.join(ativos)}")

    slots = psql("postgres-origem", "select slot_name, plugin, slot_type, database, active "
                                    "from pg_replication_slots order by slot_name")
    n_slots = int(psql("postgres-origem", "select count(*) from pg_replication_slots").strip())
    c.bruto("slots.txt", slots)
    c.metrica("M1b", n_slots, " ".join(linha.split("|")[0] for linha in slots.splitlines() if linha))

    topicos = executar("docker", "compose", "exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh",
                       "--bootstrap-server", "localhost:9092", "--list").split()
    c.bruto("topicos.txt", "\n".join(topicos) + "\n")
    dados = [t for t in topicos if not t.startswith("_")]
    c.metrica("M1c", len(dados), f"{len(topicos) - len(dados)} internos excluídos")

    # Bruto auxiliar: linhas por tabela no destino.
    contagem = psql("postgres-destino",
                    "select table_schema || '.' || table_name, (xpath('/row/c/text()', query_to_xml("
                    "format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text "
                    "from information_schema.tables where table_schema in ('public') and table_type = 'BASE TABLE' "
                    "order by 1", banco="dw")
    c.bruto("linhas_destino.txt", contagem)


# ---------------------------------------------------------------- M2

def arquivos(diretorio: Path) -> list[Path]:
    if not diretorio.is_dir():
        return []
    encontrados = []
    for caminho in sorted(diretorio.rglob("*")):
        relativo = caminho.relative_to(diretorio)
        if (caminho.is_file()
                and caminho.name not in ARQUIVOS_IGNORADOS
                and not any(p.startswith(".") for p in relativo.parts)
                and not DIRETORIOS_IGNORADOS.intersection(relativo.parts[:-1])):
            encontrados.append(caminho)
    return encontrados


def linhas_uteis(caminho: Path) -> int:
    """Linhas não vazias e que não são só comentário."""
    sufixo = caminho.suffix.lower()
    prefixos = COMENTARIO_LINHA.get(sufixo, ())
    blocos = COMENTARIO_BLOCO.get(sufixo, ())
    fim_de_bloco = None
    total = 0
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        resto = linha.strip()
        while resto:
            if fim_de_bloco:
                posicao = resto.find(fim_de_bloco)
                if posicao < 0:
                    resto = ""
                    break
                resto = resto[posicao + len(fim_de_bloco):].strip()
                fim_de_bloco = None
                continue
            bloco = next(((a, f) for a, f in blocos if resto.startswith(a)), None)
            if bloco is None:
                break
            fim_de_bloco = bloco[1]
            resto = resto[len(bloco[0]):]
        if resto and not resto.startswith(prefixos):
            total += 1
    return total


def contar_sources(diretorio_dbt: Path) -> tuple[int, int]:
    blocos = tabelas = 0
    for caminho in arquivos(diretorio_dbt):
        if caminho.suffix.lower() not in (".yml", ".yaml"):
            continue
        documento = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
        for source in documento.get("sources") or []:
            blocos += 1
            tabelas += len(source.get("tables") or [])
    return blocos, tabelas


def medir_m2(c: Coleta) -> None:
    base = RAIZ / "variantes" / c.variante
    conectores, dbt, origem = base / "conectores", base / "dbt", base / "origem"

    c.metrica("M2a", len(arquivos(conectores)), " ".join(p.name for p in arquivos(conectores)))
    modelos = [p for p in arquivos(dbt / "models") if p.suffix == ".sql"]
    c.metrica("M2b", len(modelos), " ".join(p.stem for p in modelos))
    blocos, tabelas = contar_sources(dbt)
    c.metrica("M2c", tabelas, f"{blocos} blocos de source")
    macros = [p for p in arquivos(dbt / "macros") if p.suffix == ".sql"]
    c.metrica("M2d", len(macros), " ".join(p.stem for p in macros))

    detalhe = io.StringIO()
    escritor = csv.writer(detalhe, lineterminator="\n")
    escritor.writerow(["metrica", "arquivo", "linhas_uteis"])
    totais = Counter()
    for metrica, diretorios in (("M2e", (conectores, dbt)), ("M2e_origem", (origem,))):
        for diretorio in diretorios:
            for caminho in arquivos(diretorio):
                n = linhas_uteis(caminho)
                totais[metrica] += n
                escritor.writerow([metrica, caminho.relative_to(RAIZ).as_posix(), n])
    c.bruto("m2_linhas.csv", detalhe.getvalue())
    c.metrica("M2e", totais["M2e"], "conectores/ e dbt/")
    c.metrica("M2e_origem", totais["M2e_origem"], "origem/ (auxiliar, fora de M2e)")


# ---------------------------------------------------------------- M3

def medir_m3(c: Coleta, args: argparse.Namespace, dir_medicoes: Path) -> None:
    with (dir_medicoes / "diario.csv").open(newline="", encoding="utf-8") as f:
        diario = [r for r in csv.DictReader(f)
                  if r["variante"] == c.variante and r["execucao"] == str(c.execucao)]
    if not any(r["tipo"] == "origem" for r in diario):
        sys.exit("o diário não tem o passo 0 (tipo origem) desta variante e execução")
    passos = [r for r in diario if r["tipo"] != "origem"]
    tipos = Counter(r["tipo"] for r in passos)
    c.metrica("M3a", len(passos), ", ".join(f"{n} {t}" for t, n in sorted(tipos.items())) or "nenhum passo")

    base = f"variantes/{c.variante}"
    caminhos = [f"{base}/conectores", f"{base}/dbt", ":(exclude,glob)**/README.md"]
    # Sem --depois (só com --somente-m3d), compara --antes com a árvore de trabalho.
    refs = [executar("git", "rev-parse", "--short", r).strip() for r in (args.antes, args.depois) if r]
    rotulo = "..".join(refs) if len(refs) == 2 else f"{refs[0]}..árvore de trabalho"
    estatistica = executar("git", "diff", "--stat", *refs, "--", *caminhos)
    numstat = executar("git", "diff", "--numstat", *refs, "--", *caminhos)
    c.bruto("m3b_diff_stat.txt", f"git diff --stat {' '.join(refs)} -- {' '.join(caminhos)}\n{estatistica}")
    alterados = [linha.split("\t") for linha in numstat.splitlines() if linha]
    mais = sum(int(a) for a, _, _ in alterados if a != "-")
    menos = sum(int(r) for _, r, _ in alterados if r != "-")
    c.metrica("M3b", len(alterados),
              f"{rotulo}: +{mais} -{menos}; " + " ".join(Path(p).name for _, _, p in alterados))

    if args.m3c:
        c.metrica("M3c", args.m3c, args.m3c_descricao)

    linhas = Path(args.m3d_arquivo).read_text(encoding="utf-8").splitlines()
    json_m3d = next((l.split(":", 1)[1] for l in reversed(linhas) if l.startswith("resultado_json:")), None)
    if json_m3d is None:
        sys.exit(f"sem linha resultado_json em {args.m3d_arquivo}")
    resultado = json.loads(json_m3d)
    if not resultado["ok"]:
        sys.exit(f"a verificação de {args.m3d_arquivo} não passou; M3d não pode ser gravada")
    c.metrica("M3d", resultado["segundos"],
              f"{resultado['inicio_utc']} -> {resultado['sucesso_utc']}; "
              f"{resultado['tentativas']} tentativas a cada {resultado['intervalo_s']} s")


# ---------------------------------------------------------------- principal

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta M1, M2 (e M3 após a incorporação) de uma variante.")
    parser.add_argument("variante", choices=VARIANTES)
    parser.add_argument("momento", choices=tuple(TENANTS))
    parser.add_argument("--execucao", type=int, default=1)
    parser.add_argument("--antes", help="commit de antes da incorporação (M3b)")
    parser.add_argument("--depois", help="commit de depois da incorporação (M3b)")
    parser.add_argument("--m3c", choices=("sim", "nao"))
    parser.add_argument("--m3c-descricao", default="")
    parser.add_argument("--m3d-arquivo", help="saída de verificar.py --aguardar (M3d)")
    parser.add_argument("--dir-medicoes", type=Path, default=RAIZ / "medicoes")
    parser.add_argument("--somente-m3d", action="store_true",
                        help="execuções 2 e 3: grava só M3d; M3a e M3b ficam só como conferência em brutos")
    args = parser.parse_args(argv)

    if args.somente_m3d:
        if args.momento != "pos_tenant_d" or not (args.antes and args.m3d_arquivo):
            parser.error("--somente-m3d exige pos_tenant_d, --antes e --m3d-arquivo")
    elif args.momento == "pos_tenant_d" and not all((args.antes, args.depois, args.m3c, args.m3d_arquivo)):
        parser.error("pos_tenant_d exige --antes, --depois, --m3c e --m3d-arquivo")

    resultados = args.dir_medicoes / "resultados.csv"
    if resultados.exists():
        with resultados.open(newline="", encoding="utf-8") as f:
            if any(r["variante"] == args.variante and r["execucao"] == str(args.execucao)
                   and r["momento"] == args.momento for r in csv.DictReader(f)):
                parser.error(f"{args.variante}, execução {args.execucao}, {args.momento} já foi medido")

    c = Coleta(args.variante, args.execucao, args.momento, args.dir_medicoes)
    verificar_correcao(c)
    if args.somente_m3d:
        medir_m3(c, args, args.dir_medicoes)
        conferencia = [linha for linha in c.linhas if linha[3] in ("M3a", "M3b")]
        c.bruto("conferencia_m3a_m3b.txt", "".join(f"{l[3]} {l[4]} {l[5]}\n" for l in conferencia))
        for linha in conferencia:
            print(f"conferência (não gravada): {linha[3]} {linha[4]}  {linha[5]}")
        c.linhas = [linha for linha in c.linhas if linha[3] == "M3d"]
    else:
        medir_m1(c)
        medir_m2(c)
        if args.momento == "pos_tenant_d":
            medir_m3(c, args, args.dir_medicoes)

    commit = executar("git", "rev-parse", "--short", "HEAD").strip()
    alterado = bool(executar("git", "status", "--porcelain", "--", f"variantes/{args.variante}").strip())
    c.bruto("meta.json", json.dumps({
        "medido_em_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "commit": commit, "variante_com_alteracoes_nao_commitadas": alterado,
        "tenants_verificados": TENANTS[args.momento],
    }, indent=2, ensure_ascii=False) + "\n")

    novo = not resultados.exists()
    resultados.parent.mkdir(parents=True, exist_ok=True)
    with resultados.open("a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f, lineterminator="\n")
        if novo:
            escritor.writerow(CABECALHO)
        escritor.writerows(c.linhas)

    for linha in c.linhas:
        print(f"{linha[3]:<11} {str(linha[4]):>6}  {linha[5]}")
    print(f"gravado em {resultados.relative_to(RAIZ) if resultados.is_relative_to(RAIZ) else resultados}; "
          f"brutos em {c.brutos}/{c.prefixo}*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
