# prototipo-multitenant

Protótipos e medições da QP2 do TCC. O protocolo, que é a fonte de verdade, está em [`medicao.md`](medicao.md).

## Pré-requisitos

- Docker com Compose v2 (testado com Docker 29.1.3 e Compose v5.0.0)
- Python 3.12

## Preparação (uma vez)

```bash
cp .env.exemplo .env            # troque as senhas; o .env não é versionado
python3.12 -m venv .venv
.venv/bin/pip install -r comum/requirements.txt
```

## Subir o ambiente do zero

```bash
docker compose down -v --remove-orphans   # remove contêineres e volumes de uma execução anterior
docker compose up -d --wait               # sobe e espera todos os healthchecks
docker compose ps
```

| Serviço | Imagem | No host |
|---|---|---|
| `postgres-origem` | `postgres:17.12` | `127.0.0.1:15432` |
| `kafka` | `apache/kafka:4.3.2` | (só na rede interna, `kafka:9092`) |
| `kafka-connect` | `quay.io/debezium/connect:3.6.3.Final` | `http://127.0.0.1:8083` |
| `postgres-destino` | `postgres:17.12` (banco `dw`) | `127.0.0.1:15433` |

As portas podem ser trocadas no `.env`. O usuário dos dois Postgres é `postgres`.

## Derrubar e limpar

```bash
docker compose down -v --remove-orphans
```

O `-v` remove os volumes (`pg-origem-dados`, `kafka-dados`, `pg-destino-dados`). Sem ele, origem, Kafka
(com o estado do Connect) e destino sobrevivem, e o próximo `up` não parte do zero. Cada medição deve partir de um
ambiente derrubado com `-v` (seção 5.1, "ambiente limpo").

## Scripts comuns

Os scripts e o dbt leem as senhas do ambiente:

```bash
set -a; . ./.env; set +a

# Gera os dados de um tenant (determinístico: mesma saída em qualquer execução e variante)
.venv/bin/python comum/gerar_dados.py tenant_a                    # contagens e hashes
.venv/bin/python comum/gerar_dados.py tenant_a --saida dados/tenant_a   # grava os CSV

# Compara fct_pedidos e dim_clientes do destino com o esperado (0 = bate, 1 = não bate, 2 = erro)
.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c

# M3d: repete a cada 5 s até bater
.venv/bin/python comum/verificar.py tenant_a tenant_b tenant_c tenant_d --aguardar --timeout 900
```
