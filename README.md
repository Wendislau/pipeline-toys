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
| testes unitários | `test/` | Ingestão, transformação e mart 01 com dado inventado em banco temporário |
| testes de qualidade | `tests/` | Qualidade dos dados em `toys.duckdb`: contagens, unicidade das chaves, receita total entre refined e marts e fumaça do painel |
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

Receita total: **US$ 14.444.572,35**, igual em refined e em todos os marts.

## Painel

- **Filtros** na barra lateral: intervalo de meses, cidade, tipo de localização e categoria.
  Viram `WHERE` com parâmetros sobre `marts.vendas_mes_loja_produto` (grão mês × loja × produto);
  toda agregação é feita em SQL.
- **KPIs** (receita, margem, margem %, unidades) com variação vs. o mesmo período do ano anterior,
  quando o período começa em 01/2018 ou depois.
- **Evolução mensal**: alterna receita / margem / unidades e pode quebrar por categoria.
- **Clique numa barra de receita por categoria** filtra o resto do painel; clique numa área
  vazia do gráfico ou em *Restaurar filtros* para limpar.
- Cada seção tem *Ver tabela*, com mês em MM/AAAA, % e US$ com separador de milhar.

## Premissas

- **Receita** = units × product_price; **margem** = units × (product_price − product_cost).
- O dataset não tem histórico de preço: usa-se o preço e o custo atuais do produto.
- Pareto: classe A até 80% da receita acumulada, B até 95%, C o restante.
- Única correção de valor na refined: `Cuidad de Mexico` → `Ciudad de Mexico` (4 lojas).

## Origem e licença

Os dados são o **Mexico Toy Sales**, da Maven Analytics, obtidos via Kaggle:
<https://www.kaggle.com/datasets/mysarahmadbhat/toy-sales>.
Os arquivos são redistribuídos comprimidos em `raw/` (`.csv.gz`), sem alteração no conteúdo.
