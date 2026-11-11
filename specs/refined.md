# Spec — camada refined

Origem: schema `raw` de `toys.duckdb` (todas as colunas VARCHAR, gerado por `ingestao.py`).
Contagens levantadas em 2026-11-10 sobre a carga atual.

## Princípios gerais

- **Conversão estrita (`CAST`, não `TRY_CAST`).** Todas as conversões testadas tiveram 0 falhas.
  Se uma carga futura trouxer um valor inválido, a transformação deve falhar em vez de gerar
  NULL silenciosamente.
- **Sem deduplicação e sem filtros de linha.** Nenhuma tabela tem chave duplicada nem linha
  inteira duplicada (0 nos dois casos, nas quatro tabelas), e não há valores fora do domínio.
  Aplicar dedup/filtro hoje não teria efeito e esconderia problemas futuros. Em vez disso, as
  chaves são declaradas `PRIMARY KEY` para que uma duplicata quebre a carga.
- **Integridade referencial declarada.** 0 órfãos em `sales` e `inventory` → as FKs podem ser
  declaradas sem descartar nenhuma linha.
- **`TRIM` só onde há espaço.** Apenas `Product_Cost` e `Product_Price` têm espaço nas bordas
  (35/35 linhas cada). Nas demais colunas texto, 0 linhas com espaço nas bordas.
- Nulos e strings vazias: **0 em todas as colunas de todas as tabelas** → todas as colunas
  `NOT NULL`.

## refined.products — 35 linhas

| Coluna | Tipo | Regra |
|---|---|---|
| product_id | INTEGER, PK | `CAST`; 0 falhas, faixa 1–35, 0 duplicatas |
| product_name | VARCHAR | sem alteração; 35 nomes distintos (também após `lower(trim())`) |
| product_category | VARCHAR | sem alteração; 5 valores: Toys, Games, Electronics, Sports & Outdoors, Art & Crafts |
| product_cost | DECIMAL(10,2) | remover `$` e `TRIM`, depois `CAST` |
| product_price | DECIMAL(10,2) | idem |

Decisões:
- **Formato de preço/custo:** 100% das linhas seguem o padrão `$N.NN ` (com `$` e um espaço
  no fim; ex.: `"$9.99 "`). 0 têm vírgula de milhar. Após remover `$` e espaços, 0 falhas na
  conversão. Faixas: custo 1.99–34.99, preço 2.99–39.99.
- **DECIMAL e não DOUBLE:** são valores monetários com 2 casas; DECIMAL evita erro de
  arredondamento nas somas de receita/margem.
- **Custo > preço:** 0 produtos → nenhuma regra de correção necessária.

## refined.stores — 50 linhas

| Coluna | Tipo | Regra |
|---|---|---|
| store_id | INTEGER, PK | `CAST`; 0 falhas, faixa 1–50, 0 duplicatas |
| store_name | VARCHAR | sem alteração; 50 nomes distintos |
| store_city | VARCHAR | ver decisão abaixo |
| store_location | VARCHAR | sem alteração; 4 valores: Residential, Downtown, Commercial, Airport |
| store_open_date | DATE | `CAST`; 100% no formato `AAAA-MM-DD`, 0 falhas; 1992-09-18 a 2016-05-18 |

Decisões:
- **`Cuidad de Mexico` → `Ciudad de Mexico`** (4 lojas). É erro de digitação: o próprio
  dataset grafa corretamente "Ciudad Victoria". Esta é a **única alteração de valor proposta**
  em toda a refined. **Aprovado e aplicado**.

## refined.sales — 829.262 linhas

| Coluna | Tipo | Regra |
|---|---|---|
| sale_id | INTEGER, PK | `CAST`; 0 falhas, 0 duplicatas, contíguo de 1 a 829.262 |
| sale_date | DATE | `CAST` de `Date`; 100% `AAAA-MM-DD`, 0 falhas |
| store_id | INTEGER, FK → stores | `CAST`; 0 falhas, 0 órfãos |
| product_id | INTEGER, FK → products | `CAST`; 0 falhas, 0 órfãos |
| units | INTEGER | `CAST`; 0 falhas, 0 valores ≤ 0, faixa 1–30 |

Decisões:
- **Renomear `Date` → `sale_date`:** `date` é nome de tipo SQL; evita aspas e ambiguidade.
- **Intervalo de datas:** 2017-01-01 a 2018-09-30, 638 dias distintos = 638 dias do
  intervalo → sem dias faltando. Nenhum filtro de período.
- **Units:** nenhum valor ≤ 0 ou não inteiro → sem filtro. Não há devoluções representadas.
- **Venda antes da abertura da loja:** 0 casos → nenhuma regra necessária.
- Não há preço na venda; a receita será calculada com o `product_price` atual (o dataset
  não tem histórico de preço). Fica registrado como limitação, não como limpeza.

## refined.inventory — 1.593 linhas

| Coluna | Tipo | Regra |
|---|---|---|
| store_id | INTEGER, PK (com product_id), FK → stores | `CAST`; 0 falhas, 0 órfãos |
| product_id | INTEGER, PK (com store_id), FK → products | `CAST`; 0 falhas, 0 órfãos |
| stock_on_hand | INTEGER | `CAST`; 0 falhas, 0 negativos, faixa 0–139 |

Decisões:
- **Par (store_id, product_id):** 0 duplicatas → PK composta sem dedup.
- **Estoque zero (77 linhas):** mantido. É um estado válido (produto em ruptura), não um
  dado faltante.
- **Cobertura:** 1.593 de 50 × 35 = 1.750 pares possíveis; 157 pares ausentes. Os pares
  ausentes **não são preenchidos com 0 nem com nenhum outro valor**. A hipótese inicial,
  "ausência = produto não comercializado na loja", **não se sustenta para todos**:
  contagem cruzando `refined.sales` (1.631 pares com venda) e `refined.inventory`:

  | Grupo | Pares | Leitura |
  |---|---:|---|
  | Ausentes do estoque e sem nenhuma venda | 116 | Consistente com "não comercializado na loja" |
  | Ausentes do estoque, com venda que parou entre 02/2017 e 03/2018 | 17 | Consistente com produto descontinuado na loja (7 produtos, ex.: Mini Basketball Hoop, Classic Dominoes) |
  | Ausentes do estoque, Jenga, com venda até 05–09/2018 | 24 | **Não** é "não comercializado": 23 venderam a partir de 07/2018 e as vendas vão até 13/09/2018. Jenga está no estoque de só 26 das 50 lojas |
  | No estoque e sem nenhuma venda | 3 | Estoque de 3 a 6 unidades (15 no total); produto em loja que não vendeu no período |

  Os 41 pares vendidos e ausentes do estoque somam 6.232 linhas de venda (6.674 unidades).
  Como a ausência tem pelo menos dois significados, ela não pode ser lida como "estoque
  zerado" (o arquivo registra zero explicitamente em 77 linhas) nem como "não comercializado".
  **Para a camada analítica:** tratar par ausente como "sem registro de estoque". Em
  qualquer métrica de estoque ou ruptura, sinalizar Jenga à parte: a falta dele em 24 lojas
  com venda recente é provável falha de registro no arquivo de origem, não ausência do
  produto.

## Resumo das transformações

| Tabela | Linhas raw | Linhas refined | Alterações de valor |
|---|---|---|---|
| products | 35 | 35 | `$` e espaço removidos de cost/price |
| stores | 50 | 50 | `Cuidad` → `Ciudad` (4 linhas, aprovado e aplicado) |
| sales | 829.262 | 829.262 | nenhuma (só tipagem e `Date` → `sale_date`) |
| inventory | 1.593 | 1.593 | nenhuma (só tipagem) |
