# pipeline-toys

Pipeline local em DuckDB sobre os dados de vendas da Maven Toys (lojas de brinquedos
no México, jan/2017 a set/2018), em três camadas: `raw` → `refined` → `marts`,
com testes em pytest e um painel em Streamlit.

## Como rodar

Requer [uv](https://docs.astral.sh/uv/) (Python 3.14). Todos os comandos na raiz do projeto.

```bash
uv sync                              # instala as dependências
uv run python ingestao.py            # raw/*.csv.gz  -> schema raw
uv run python transformacao.py       # raw           -> schema refined
uv run python marts.py               # refined       -> schema marts
uv run pytest                        # contagens, chaves únicas e receita
uv run streamlit run app.py          # painel em http://localhost:8501
```

Cada script recria o próprio schema do zero, numa transação, e pode ser rodado de novo
a qualquer momento. O banco gerado é `toys.duckdb` (fora do git). Os arquivos de `raw/`
nunca são alterados.

O painel abre o banco só em leitura e só durante cada consulta, então o pipeline pode
ser rodado com o painel aberto. Os resultados ficam em cache por 5 minutos; para ver
dados novos antes disso, use *Clear cache* no menu do Streamlit.

## Camadas

| Etapa | Arquivo | O que faz |
|---|---|---|
| raw | `ingestao.py` | Lê os 4 CSVs com todas as colunas como texto |
| refined | `transformacao.py` | Tipagem estrita, PK/FK e limpeza, conforme [`specs/refined.md`](specs/refined.md) |
| marts | `marts.py` + `sql/marts/*.sql` | Cada arquivo SQL vira `marts.<nome sem o número>` |
| testes unitários | `tests/unit/` | Ingestão, transformação e marts 01 e 07 com dado inventado em banco temporário |
| testes de qualidade | `tests/quality/` | Qualidade dos dados em `toys.duckdb`: contagens, unicidade das chaves, receita total entre refined e marts e fumaça do painel |
| painel | `app.py` | Painel interativo, só com SELECT em `marts.vendas_mes_loja_produto` |

## Contagens

| Tabela | Linhas |
|---|---:|
| raw.sales / refined.sales | 829.262 |
| raw.inventory / refined.inventory | 1.593 |
| raw.stores / refined.stores | 50 |
| raw.products / refined.products | 35 |
| marts.receita_por_mes | 21 |
| marts.receita_margem_por_categoria | 5 |
| marts.ranking_lojas | 50 |
| marts.pareto_produtos | 35 |
| marts.receita_por_tipo_localizacao | 4 |
| marts.vendas_mes_loja_produto | 22.931 |
| marts.cobertura_estoque | 1.616 |

Receita total: **US$ 14.444.572,35**, igual em refined e em todos os marts de vendas
(`cobertura_estoque` é de estoque e não tem receita).

## Painel

- **Filtros** na barra lateral: intervalo de meses, cidade, tipo de localização e categoria.
  Viram `WHERE` com parâmetros sobre `marts.vendas_mes_loja_produto` (grão mês × loja × produto);
  toda agregação é feita em SQL.
- **KPIs** (receita, margem, margem %, unidades) com variação vs. o mesmo período do ano anterior,
  quando o período começa em 01/2018 ou depois.
- **Evolução mensal**: alterna receita / margem / unidades e pode quebrar por categoria.
- **Clique numa barra de receita por categoria** filtra o resto do painel; clique numa área
  vazia do gráfico ou em *Restaurar filtros* para limpar.
- **Estoque**: contagem por status e tabela dos itens em ruptura, críticos e sem registro,
  a partir de `marts.cobertura_estoque` (média de vendas dos últimos 90 dias do dado).
  Responde a cidade, tipo de localização e categoria, mas não aos meses. Status, na carga real:

  | Status | Regra | Pares |
  |---|---|---:|
  | ruptura | estoque zero | 77 |
  | crítico | menos de 7 dias de cobertura | 289 |
  | ok | 7 dias ou mais de cobertura | 1.134 |
  | sem demanda | há estoque, mas nenhuma venda nos últimos 90 dias | 93 |
  | sem registro | vendido nos últimos 90 dias e ausente de `refined.inventory`; estoque NULL, não zero (todos os 23 são Jenga) | 23 |

- Cada seção tem *Ver tabela*, com mês em MM/AAAA, % e US$ com separador de milhar.

## Premissas

- **Receita** = units × product_price; **margem** = units × (product_price − product_cost).
- O dataset não tem histórico de preço: usa-se o preço e o custo atuais do produto.
- Pareto: classe A até 80% da receita acumulada, B até 95%, C o restante.
- Única correção de valor na refined: `Cuidad de Mexico` → `Ciudad de Mexico` (4 lojas).

## Grão das tabelas

| Tabela | Uma linha é | Chave |
|---|---|---|
| refined.products | um produto | `product_id` |
| refined.stores | uma loja | `store_id` |
| refined.sales | uma venda (transação) | `sale_id` |
| refined.inventory | um par loja × produto no estoque | `store_id, product_id` |
| marts.receita_por_mes | um mês | `mes` |
| marts.receita_margem_por_categoria | uma categoria de produto | `categoria` |
| marts.ranking_lojas | uma loja | `store_id` |
| marts.pareto_produtos | um produto | `product_id` |
| marts.receita_por_tipo_localizacao | um tipo de localização da loja | `tipo_localizacao` |
| marts.vendas_mes_loja_produto | um mês × loja × produto com pelo menos uma venda | `mes, store_id, product_id` |
| marts.cobertura_estoque | um par loja × produto do estoque, ou vendido nos últimos 90 dias sem registro no estoque | `store_id, product_id` |

## Onde a IA errou (e como foi pego)

- **Contagem de duplicatas.** A contagem de linhas duplicadas em `sales` deu 829.261,
  porque a consulta usava `GROUP BY ALL` só com `count(*)`. Recontado com `DISTINCT`, deu 0.
- **Hipótese da spec sobre estoque.** A spec supunha que estoque ausente significava
  "produto não vendido na loja". A hipótese caiu na conferência: 41 pares loja × produto
  vendidos não estão no estoque, 24 deles do Jenga.
- **Status da spec.** A spec ficou marcada como "pendente de aprovação" depois de a decisão
  já estar aplicada no código.
- **Painel.** Nomes de loja cortados, marcadores da classe C quase invisíveis, gráfico
  cortado na largura da coluna, *Restaurar filtros* que não fazia nada no segundo clique e
  variação em pontos percentuais formatada como "p,p,".
- **Afirmação falsa no README.** O README dizia que o painel travava o banco durante o
  pipeline. Testado, a afirmação se mostrou falsa e foi corrigida.
- **Teste que não testava.** Trocar `CAST` por `TRY_CAST` na refined não fez nenhum teste
  falhar, porque o `NOT NULL` ainda bloqueava a carga. Só falhou quando as duas proteções
  foram removidas juntas.
- **Painel estático.** A primeira versão do painel saiu estática e sem filtros. Pego por
  Wendislau na revisão.
- **Testes que não eram unitários.** Os testes abriam o banco real (`toys.duckdb`) e
  conferiam números fixos, ao contrário do que a aula 4 pede. Pego por Wendislau na revisão;
  daí a separação entre `tests/unit/` (unitários, com dado inventado) e `tests/quality/` (qualidade do dado).

## Origem e licença

Os dados são o **Mexico Toy Sales**, da Maven Analytics, obtidos via Kaggle:
<https://www.kaggle.com/datasets/mysarahmadbhat/toy-sales>.
Os arquivos são redistribuídos comprimidos em `raw/` (`.csv.gz`), sem alteração no conteúdo.

Os `.csv.gz` ficam versionados em `raw/` de propósito, como no repositório do curso: são
3,7 MB comprimidos, o projeto roda logo depois de um `git clone`, sem conta no Kaggle, e o
`.gitignore` (`raw/*.csv`) impede commitar os CSVs crus.
