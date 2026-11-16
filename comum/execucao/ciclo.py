"""Extrai dos logs do Kafka Connect o ciclo de metadados do consumidor do sink (grupo connect-destino).

Uso: python3 comum/execucao/ciclo.py <raiz do repo> <variante> <execucao> <passo0_utc ISO>
Grava medicoes/brutos/<variante>_e<execucao>_ciclo_metadados.txt.
"""
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

raiz, variante, execucao, t0_texto = sys.argv[1:5]
log = subprocess.run(["docker", "compose", "logs", "--no-log-prefix", "kafka-connect"],
                     cwd=raiz, capture_output=True, text=True, check=True).stdout
padrao = re.compile(r"groupId=connect-destino\].*(Subscribed to pattern|Finished assignment for group at generation"
                    r"|Adding newly assigned partitions|Notifying assignor about the new Assignment)")
linhas = [l for l in log.splitlines() if padrao.search(l)]


def instante(linha):
    return dt.datetime.strptime(linha[:23], "%Y-%m-%dT%H:%M:%S,%f").replace(tzinfo=dt.timezone.utc)


def iso(m):
    return m.isoformat(timespec="milliseconds").replace("+00:00", "Z") if m else "não encontrado"


t0 = dt.datetime.fromisoformat(t0_texto)
assinatura = next((instante(l) for l in linhas if "Subscribed to pattern" in l), None)
rebalanceamento = next((instante(l) for l in linhas if "tenant_d" in l and instante(l) >= t0), None)

def delta(a, b):
    return f"{(a - b).total_seconds():.1f}" if a and b else "n/a"

resumo = [
    f"# Ciclo de metadados do consumidor do sink (grupo connect-destino): {variante}, execução {execucao}",
    "# Fonte: docker compose logs --no-log-prefix kafka-connect, linhas do grupo connect-destino com",
    "#   'Subscribed to pattern', 'Finished assignment', 'Notifying assignor' ou 'Adding newly assigned partitions'.",
    f"assinatura_do_sink_utc: {iso(assinatura)}",
    f"passo0_utc: {iso(t0)}",
    "rebalanceamento_com_tenant_d_utc: " + (iso(rebalanceamento) if rebalanceamento
                                            else "não houve (nenhum tópico novo a assinar)"),
    f"passo0_menos_assinatura_s: {delta(t0, assinatura)}",
    f"rebalanceamento_menos_assinatura_s: {delta(rebalanceamento, assinatura)}",
    f"rebalanceamento_menos_passo0_s: {delta(rebalanceamento, t0)}",
    "# Linhas do log (cortadas em 300 caracteres):",
]
saida = Path(raiz) / "medicoes" / "brutos" / f"{variante}_e{execucao}_ciclo_metadados.txt"
saida.write_text("\n".join(resumo + [l[:300] for l in linhas]) + "\n", encoding="utf-8")
print("\n".join(resumo[3:9]))
