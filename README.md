# prototipo-multitenant

## Sobre

Protótipos e medições do TCC *Impactos das Arquiteturas de Dados para Aplicações Multi-Tenant Baseadas em Bancos de
Dados Relacionais na Engenharia de Dados* (Universidade de Brasília). Este repositório responde à QP2: como o número
de conectores, a complexidade dos pipelines e o esforço para incorporar novos tenants se comportam em protótipos
mínimos das estratégias de isolamento e no estudo de caso do Brasil Participativo.

- **Protocolo:** [`medicao.md`](medicao.md).
- **Pré-registro:** a tag `v0-medicao`, que congela as definições antes da primeira medição.
- **Desvios:** registrados na seção 11 do protocolo.

## Resultados

**Origem dos valores:**

- `medicoes/resultados.csv`: banco por tenant, esquema por tenant e esquema compartilhado;
- `medicoes/complementar.csv`: esquema por tenant com roteamento (análise D);
- `medicoes/bp.csv`: Brasil Participativo, ambiente de homologação.

Nas células "3 → 4", o primeiro valor é com 3 tenants e o segundo, depois da incorporação do quarto tenant.

| Métrica | Banco por tenant | Esquema por tenant | Esquema por tenant com roteamento | Esquema compartilhado | Brasil Participativo |
|---|---|---|---|---|---|
| Conectores ativos (M1a) | 4 → 5 | 2 → 2 | 2 → 2 | 2 → 2 | pelo menos 2 (1 de origem e pelo menos 1 sink) |
| Slots de replicação na origem (M1b) | 3 → 4 | 1 → 1 | 1 → 1 | 1 → 1 | 1 |
| Tópicos de dados no Kafka (M1c) | 12 → 16 | 12 → 16 | 4 → 4 | 4 → 4 | até 64, mais 1 de heartbeat |
| Arquivos de configuração de conectores (M2a) | 4 → 5 | 2 → 2 | não coletado¹ | 2 → 2 | 0 (1 manifesto de origem fora do git) |
| Modelos dbt (M2b) | 6 → 6 | 6 → 6 | 6 → 6 | 6 → 6 | 114 |
| Fontes (sources) declaradas no dbt (M2c) | 12 → 16 | 12 → 16 | 4 → 4 | 4 → 4 | 64 |
| Macros dbt próprias (M2d) | 1 → 1 | 1 → 1 | 0 → 0 | 0 → 0 | 13 |
| Linhas de configuração e código do pipeline (M2e) | 179 → 205 | 148 → 159 | 123 → 123 | 116 → 116 | 9965 |
| Linhas dos artefatos da origem (M2e_origem, auxiliar) | 34 | 37 | mesma origem do esquema por tenant | 49 | não se aplica |
| Passos manuais de engenharia de dados para incorporar um tenant (M3a) | 5 | 3 | 0 | 0 | 3 |
| Arquivos alterados na incorporação (M3b) | 3 | 2 | 0 | 0 | 0 (mais 1 manifesto fora do git) |
| Reinício ou recriação de conector, slot ou publicação (M3c) | não | não | não | não | sim |
| Tempo de propagação do novo tenant, em segundos (M3d)² | 295,6 (280,3 a 300,2; 3 execuções) | 295,8 (280,8 a 301,1; 3 execuções) | 5,5 (1 execução) | 5,7 (5,3 a 6,0; 3 execuções) | não medido |

¹ O diretório `variantes/v2_esquema/roteado/conectores/` tem 2 arquivos, mas a análise D não registrou essa contagem.
A origem dessa variante é a mesma do esquema por tenant.

² Os valores são a mediana, com o mínimo e o máximo entre parênteses. No banco por tenant e no esquema por tenant, quase
todo o tempo é a espera pela atualização de metadados (5 minutos) do consumidor do sink, que assina os tópicos por
expressão regular. Os horários de cada execução estão em `medicoes/brutos/*_ciclo_metadados.txt`.

**Brasil Participativo:**
- os tópicos seriam 1344 sem roteamento, e o número não foi confirmado ao vivo;
- os conectores não são versionados;
- há 8 tenants cadastrados, 21 schemas capturados e 7 tenants cadastrados que chegam ao gold.

### Análises complementares (não pré-registradas)

Estão registradas na seção 11 do `medicao.md`, com resultados em `medicoes/complementar.csv`.

- **A. Descoberta de tenants no dbt.** Com uma macro que encontra as tabelas de cada tenant no destino, sem lista de
  tenants, a incorporação cai de 5 para 3 passos no banco por tenant e de 3 para 1 no esquema por tenant. O tempo de
  propagação não muda (cerca de 295 segundos).
- **B. Evolução de esquema** (coluna `email` em `clientes`):
  - as três estratégias exigem 3 passos de engenharia de dados e 2 arquivos;
  - a aplicação executa 6 comandos no banco por tenant e no esquema por tenant, e 4 no esquema compartilhado;
  - com a migração parcial, o `dbt run` falha no banco por tenant e no esquema por tenant e funciona no esquema compartilhado.
- **C. Fórmulas de crescimento.** Conectores, slots e tópicos medidos com 3 e 4 tenants seguem as fórmulas N+1, N e 4N
  (banco por tenant); 2, 1 e 4N (esquema por tenant); e 2, 1 e 4 (esquema compartilhado).
- **D. Esquema por tenant com roteamento.** Reproduz o desenho do Brasil Participativo (coluna própria na tabela acima).
  A variante com lista fechada de tabelas no conector, como no Brasil Participativo, foi avaliada só de forma analítica:
  3 passos, com reinício do conector.

## Como reproduzir

### Pré-requisitos

- Docker com Compose v2 (testado com Docker 29.1.3 e Compose v5.0.0).
- Python 3.12.
- As versões fixadas estão na seção 10 do `medicao.md` e em `comum/requirements.txt`.

### Preparação

```bash
cp .env.exemplo .env            # troque as senhas; o .env não é versionado
python3.12 -m venv .venv
.venv/bin/pip install -r comum/requirements.txt
set -a; . ./.env; set +a        # os scripts e o dbt leem as senhas do ambiente
```

Serviços (`docker-compose.yml`):

| Serviço | Endereço |
|---|---|
| Postgres de origem | `127.0.0.1:15432` |
| Kafka | só na rede interna |
| Kafka Connect | `http://127.0.0.1:8083` |
| Postgres de destino (banco `dw`) | `127.0.0.1:15433` |

### Montagem com 3 tenants

O `montar.sh` derruba o ambiente com os volumes e o sobe do zero. Depois, seguindo o README da variante, cria
`tenant_a` a `tenant_c`, registra os conectores, roda o dbt e verifica a correção.

```bash
comum/execucao/montar.sh v3_compartilhado                            # esquema compartilhado
comum/execucao/montar.sh v2_esquema                                  # esquema por tenant
comum/execucao/montar.sh v1_banco                                    # banco por tenant
comum/execucao/montar.sh v2_esquema roteado/dbt roteado/conectores   # esquema por tenant com roteamento
.venv/bin/python comum/medir.py v3_compartilhado inicial             # M1 e M2 (verifica a correção antes de gravar)
```

**Estado de partida no banco por tenant e no esquema por tenant.** Nessas variantes, `conectores/` e `dbt/` estão
versionados no estado com 4 tenants. Para partir do estado com 3 tenants:

```bash
git restore --source=v0-medicao -- variantes/v1_banco/conectores variantes/v1_banco/dbt       # banco por tenant
git restore --source=v0-medicao -- variantes/v2_esquema/conectores variantes/v2_esquema/dbt   # esquema por tenant
```

**Não sobrescrever os resultados do artigo.** O `medir.py` não grava duas vezes o mesmo momento. Para reproduzir sem
tocar nos resultados, trabalhe numa cópia do repositório ou use `--dir-medicoes` (`medir.py`) e `--arquivo` (`diario.py`).

### Incorporação do tenant_d

1. Faça o commit do estado "antes".
2. Rode o passo 0, que cria o `tenant_d` na origem e inicia a verificação periódica (M3d):

   ```bash
   comum/execucao/passo0.sh v2_esquema 1
   ```
3. Faça os passos de engenharia de dados da variante, cada um registrado no diário:
   - **Esquema compartilhado e esquema por tenant com roteamento:** nenhum.
   - **Esquema por tenant:**
     1. acrescentar a source `tenant_d` em `dbt/models/sources.yml`;
     2. acrescentar `tenant_d` em `vars.tenants` (`dbt/dbt_project.yml`);
     3. rodar `dbt run` quando as tabelas `app_tenant_d_*` aparecerem no destino.
   - **Banco por tenant:** os mesmos passos do esquema por tenant (com as tabelas `tenant_d_public_*`), e antes deles:
     1. criar `conectores/origem_tenant_d.json`;
     2. registrá-lo com `POST /connectors`.

   ```bash
   .venv/bin/python comum/diario.py v2_esquema edicao "variantes/v2_esquema/dbt/models/sources.yml: nova source tenant_d"
   (cd variantes/v2_esquema/dbt && ../../../.venv/bin/dbt run)
   .venv/bin/python comum/diario.py v2_esquema comando "dbt run em variantes/v2_esquema/dbt"
   ```
4. Quando a verificação passar, faça o commit "depois" e meça:

   ```bash
   .venv/bin/python comum/medir.py v2_esquema pos_tenant_d --antes <commit antes> --depois <commit depois> \
       --m3c nao --m3c-descricao "..." --m3d-arquivo medicoes/brutos/v2_esquema_e1_m3d_verificar.txt
   ```

**Execuções 2 e 3 de M3d** (desvio da seção 11): use `montar.sh` e `passo0.sh <variante> <execucao>`. Depois de
refazer os passos, rode `comum/execucao/fechar.sh <variante> <execucao> <commit antes> <commit depois>`. Ele grava só
M3d e faz o commit.

### Derrubar o ambiente

```bash
docker compose down -v --remove-orphans
```

### Onde ficam os resultados

- `medicoes/resultados.csv`: métricas pré-registradas (M1, M2 e M3; M3d em 3 execuções).
- `medicoes/diario.csv`: ações do operador na incorporação.
- `medicoes/complementar.csv`: análises complementares A a D; o diário e os brutos delas ficam em `medicoes/brutos/complementar/`.
- `medicoes/bp.csv`: Brasil Participativo.
- `medicoes/brutos/`: saídas brutas (conectores, slots, tópicos, verificação de correção e ciclo de metadados do sink).
