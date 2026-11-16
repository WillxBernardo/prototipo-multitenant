# Protocolo de Medição: Protótipos e Estudo de Caso

**Trabalho:** Impactos das Arquiteturas de Dados para Aplicações Multi-Tenant Baseadas em Bancos de Dados Relacionais na Engenharia de Dados
**Autor:** William Bernardo da Silva (Universidade de Brasília)
**Versão:** 1.0
**Pré-registro:** as definições das seções 4 a 7 ficam congeladas pela tag `v0-medicao`, criada **depois** de a infraestrutura funcionar para os 3 tenants iniciais e **antes** da primeira medição. Qualquer mudança posterior é um desvio (seção 11).

---

## 1. Objetivo

Responder à **QP2**:

> **QP2:** Como as métricas de número de conectores, complexidade dos pipelines e esforço para incorporar novos tenants se comportam em protótipos mínimos das três estratégias de isolamento e no estudo de caso do Brasil Participativo, que adota o esquema por tenant?

Os resultados, combinados com os da revisão de literatura cinzenta (QP1), respondem à **QP principal**.

## 2. Variantes

| Código | Estratégia | Organização na origem |
|---|---|---|
| `v1_banco` | Banco por tenant | Uma instância Postgres com um banco por tenant (`tenant_a`, `tenant_b`, ...). |
| `v2_esquema` | Esquema por tenant | Um banco `app` com um schema por tenant (`tenant_a`, `tenant_b`, ...). |
| `v3_compartilhado` | Esquema compartilhado | Um banco `app`, schema `public`, com a coluna `tenant_id` em todas as tabelas. |

## 3. Ambiente comum

**Pilha** (a mesma do pipeline do Brasil Participativo, para a comparação ser direta):
- Postgres de **origem** (a aplicação), com replicação lógica habilitada (`wal_level=logical`);
- Kafka (modo KRaft) e Kafka Connect;
- Debezium (conector de origem Postgres, plugin `pgoutput`);
- Debezium JDBC Sink, gravando num Postgres de **destino** (o "data warehouse");
- dbt (`dbt-postgres`) para a transformação no destino.

**Versões:** todas as imagens e pacotes têm versão exata fixada. As versões usadas são registradas na seção 10 antes da tag `v0-medicao`.

**Esquema da aplicação** (genérico, igual nas três variantes, exceto pela coluna `tenant_id` na `v3_compartilhado`):
- `clientes` (id, nome, cidade, criado_em)
- `produtos` (id, nome, preco)
- `pedidos` (id, cliente_id, criado_em, status)
- `itens_pedido` (id, pedido_id, produto_id, quantidade, preco_unitario)

**Dados:** gerados por script (`comum/gerar_dados.py`) com semente fixa (`42`), com o mesmo volume por tenant (100 clientes, 50 produtos, 1.000 pedidos, cerca de 3 itens por pedido). A semente de cada tenant é derivada da semente fixa e do nome do tenant (SHA-256 de `"42:<tenant>"`). Assim, o conteúdo de cada tenant é idêntico entre as variantes e entre execuções, e tenants diferentes têm conteúdos diferentes, o que permite à verificação detectar dados trocados entre tenants.

**Estado final esperado (critério de correção):** em todas as variantes, o destino deve conter, no schema `analytics`, os mesmos dois modelos finais:
- `fct_pedidos` (um registro por pedido): `tenant_id`, `pedido_id`, `cliente_id`, `data_pedido`, `status`, `valor_total` (soma de `quantidade * preco_unitario` dos itens do pedido);
- `dim_clientes` (um registro por cliente e tenant): `tenant_id`, `cliente_id`, `nome`, `cidade`, `criado_em`.

Nos dois modelos, `tenant_id` é o nome do tenant em texto (por exemplo, `tenant_a`).

**Materialização no dbt:** nas três variantes, os modelos de staging e os modelos finais são materializados como **view**. Assim, o `dbt run` só é passo de incorporação quando o projeto dbt precisa mudar; se uma variante exigir alteração no dbt para o novo tenant aparecer, isso entra em M3a e M3b.

Uma consulta de verificação (`comum/verificar.py`) compara o conteúdo desses modelos com o esperado a partir dos dados gerados. Uma variante só é medida quando a verificação passa.

## 4. Métricas (definições congeladas pela tag)

### M1. Conectores e recursos de captura
| Código | Definição | Como medir |
|---|---|---|
| M1a | Número de conectores ativos no Kafka Connect (origem + destino) | `GET /connectors` da API REST do Connect |
| M1b | Número de slots de replicação na origem | `SELECT count(*) FROM pg_replication_slots` |
| M1c | Número de tópicos de dados no Kafka (excluindo tópicos internos) | listagem de tópicos |

### M2. Complexidade do pipeline
| Código | Definição | Como medir |
|---|---|---|
| M2a | Número de arquivos de configuração de conectores | contagem em `variantes/<v>/conectores/` |
| M2b | Número de modelos dbt | contagem de `.sql` em `variantes/<v>/dbt/models/` |
| M2c | Número de fontes (`sources`) declaradas no dbt | contagem nas definições `.yml` |
| M2d | Número de macros dbt próprias | contagem de `.sql` em `variantes/<v>/dbt/macros/` |
| M2e | Linhas de configuração e código | linhas não vazias e sem comentário em `variantes/<v>/` (conectores, dbt e scripts de operação), contadas por script versionado |

### M3. Esforço para incorporar um novo tenant
Medido no procedimento da seção 5.3 (incorporar o tenant `tenant_d`).

| Código | Definição | Como medir |
|---|---|---|
| M3a | Passos manuais | número de ações do operador registradas no diário (seção 6) |
| M3b | Arquivos alterados | `git diff --stat` entre os commits de antes e depois da incorporação, restrito a `variantes/<v>/` |
| M3c | Exigiu reiniciar ou recriar algum conector, slot ou publicação? | sim/não, com descrição |
| M3d | Tempo de propagação | segundos entre o fim do último passo manual e o momento em que os dados do `tenant_d` aparecem corretos nos modelos finais, medido por script de verificação periódica (a cada 5 s) |

## 5. Procedimento

### 5.1 Regras de equidade
1. **Configuração idiomática mínima:** cada variante usa a configuração mais simples documentada pelas próprias ferramentas para aquela estratégia. Recursos nativos (listas de inclusão por expressão regular, macros e variáveis do dbt) são permitidos. Scripts próprios que geram configuração automaticamente **não** são permitidos, porque mediriam a automação, e não a estratégia.
2. **Mesmo esforço de engenharia:** nenhuma variante recebe otimizações que as outras não recebem.
3. **Mesmos dados e mesmas versões** em todas as variantes.
4. **Ambiente limpo:** cada medição parte de um ambiente recriado do zero (volumes removidos).

### 5.2 Medição do estado inicial (3 tenants)
Para cada variante:
1. subir o ambiente limpo;
2. criar os tenants `tenant_a`, `tenant_b` e `tenant_c` e carregar os dados;
3. registrar os conectores e executar o dbt;
4. rodar a verificação de correção;
5. medir M1 e M2 e gravar em `medicoes/resultados.csv`.

### 5.3 Incorporação de um novo tenant
Partindo do estado da seção 5.2, já correto:
1. fazer um commit marcando o estado antes da incorporação;
2. criar o `tenant_d` na origem, da forma natural na estratégia (novo banco, novo schema ou novas linhas com `tenant_id`), e carregar seus dados;
3. executar os passos necessários para os dados do `tenant_d` chegarem aos modelos finais, registrando cada um no diário;
4. rodar a verificação de correção, agora com 4 tenants;
5. fazer um commit marcando o estado depois da incorporação;
6. medir M1, M2 (de novo) e M3 e gravar.

### 5.4 Repetições
- M1, M2, M3a, M3b e M3c são determinísticas: medidas uma vez por variante.
- M3d (tempo) é medida em **uma execução** por variante, em ambiente limpo. Por ser uma única execução, o valor é indicativo e não permite comparação estatística entre variantes (seção 9).

## 6. Diário de operação

Cada ação do operador durante a incorporação vira uma linha em `medicoes/diario.csv`:

`variante, execucao, passo, timestamp_utc, tipo, descricao`

- `tipo`: `comando` (um comando executado), `edicao` (alteração de um arquivo), `chamada_api` (registro ou alteração de conector) ou `reinicio` (reinício de um componente).
- Um passo é **uma** ação atômica. Uma edição que altera vários trechos do mesmo arquivo conta como um passo; alterar dois arquivos conta como dois.
- Verificações que apenas leem o estado (consultar, listar) **não** contam como passo.

## 7. Estudo de caso: Brasil Participativo

O pipeline real é medido com as mesmas métricas, sobre uma **versão fixa** (commit identificado na seção 10).
- **M1:** contagem de conectores, slots e tópicos em produção ou homologação.
- **M2:** contagem dos artefatos do pipeline (conectores, modelos e macros dbt, definições de orquestração, se houver).
- **M3:** passos, arquivos e reinícios necessários para incorporar um tenant, obtidos do procedimento real (runbook, histórico de commits ou acompanhamento de uma incorporação). M3d só é reportada se puder ser medida. No BP, cada novo tenant cria na origem um schema com nome no formato UUID, e a captura o descobre automaticamente por uma regra de inclusão por expressão regular restrita a nomes nesse formato; a medição verifica se alguma etapa posterior (sink, dbt) ainda exige ação manual.
- Apenas números agregados são publicados. Nenhum dado de participantes ou da plataforma é copiado para este repositório.

## 8. Registro e rastreabilidade

| Arquivo | Conteúdo |
|---|---|
| `medicoes/resultados.csv` | `variante, execucao, momento (inicial|pos_tenant_d), metrica, valor, observacao` |
| `medicoes/diario.csv` | ações do operador (seção 6) |
| `medicoes/brutos/` | saídas brutas: estado dos conectores, slots, tópicos, contagem de linhas, saída da verificação |
| `medicoes/bp.csv` | métricas do estudo de caso (seção 7) |

Um commit ao fim de cada medição. Nenhuma credencial é versionada.

## 9. Limitações conhecidas

- Os protótipos são mínimos, com 4 tenants e um esquema pequeno. Eles mostram como as métricas **crescem** com o número de tenants e o que muda estruturalmente, mas não reproduzem a escala de produção.
- Desempenho e carga estão fora do escopo.
- A regra de configuração idiomática mínima mede cada estratégia sem automação própria. Em produção, equipes costumam automatizar parte da incorporação, o que reduziria M3 em algumas variantes.
- O estudo de caso cobre apenas o esquema por tenant.
- M3d foi medida uma única vez por variante; diferenças de poucos segundos não devem ser interpretadas.

## 10. Versões e referências de execução

*(Preenchido antes da tag `v0-medicao`.)*

| Item | Valor |
|---|---|
| Postgres (origem e destino) | |
| Kafka | |
| Kafka Connect / Debezium | |
| Debezium JDBC Sink | |
| dbt-core / dbt-postgres | |
| Commit do pipeline do Brasil Participativo | |

## 11. Desvios do protocolo

| Data | Seção | Descrição | Justificativa |
|---|---|---|---|
| | | | |