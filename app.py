"""Painel Streamlit interativo sobre marts.vendas_mes_loja_produto.

Só leitura: a conexão é aberta com read_only=True e só durante cada consulta.
Toda agregação é feita em SQL (SELECT) sobre o mart; os filtros da barra
lateral e o clique nas categorias viram WHERE com parâmetros. O pandas só
recebe o resultado pronto para desenhar.

Rodar:  uv run streamlit run app.py
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent / "toys.duckdb"
MART = "marts.vendas_mes_loja_produto"

# Métricas que o usuário pode escolher: rótulo -> expressão SQL (lista fixa,
# nunca texto livre do usuário dentro do SQL).
METRICAS = {
    "Receita": "sum(receita)",
    "Margem": "sum(margem)",
    "Unidades": "sum(unidades)",
}

# Paleta de referência (skill dataviz), com passos próprios para o tema escuro.
# Categóricas em ordem fixa por entidade: a cor segue a categoria, nunca a posição.
PALETA = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
}
FILTROS_SIDEBAR = ["f_meses", "f_cidades", "f_tipos", "f_categorias"]


# --- Acesso ao banco ------------------------------------------------------------


@st.cache_data(ttl=300)
def consulta(sql: str, params: tuple = ()) -> pd.DataFrame:
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        raise ValueError("o painel só executa SELECT")
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        df = con.execute(
            sql, [list(p) if isinstance(p, tuple) else p for p in params]
        ).df()
    # DECIMAL chega como objeto Decimal; converte para float para Altair e tabelas.
    for col in df.columns:
        if (
            df[col].dtype == object
            and df[col].map(lambda v: isinstance(v, Decimal)).any()
        ):
            df[col] = df[col].astype(float)
    return df


@dataclass(frozen=True)
class Filtro:
    inicio: date
    fim: date
    cidades: tuple[str, ...]
    tipos: tuple[str, ...]
    categorias: tuple[str, ...]

    def where(self) -> tuple[str, tuple]:
        sql = (
            "mes BETWEEN ? AND ? "
            "AND list_contains(?::VARCHAR[], cidade) "
            "AND list_contains(?::VARCHAR[], tipo_localizacao) "
            "AND list_contains(?::VARCHAR[], categoria)"
        )
        return sql, (self.inicio, self.fim, self.cidades, self.tipos, self.categorias)

    def ano_anterior(self) -> Filtro:
        return replace(
            self,
            inicio=self.inicio.replace(year=self.inicio.year - 1),
            fim=self.fim.replace(year=self.fim.year - 1),
        )


def agrega(
    filtro: Filtro, select: str, group_by: str = "", order_by: str = ""
) -> pd.DataFrame:
    where, params = filtro.where()
    sql = f"SELECT {select} FROM {MART} WHERE {where}"
    if group_by:
        sql += f" GROUP BY {group_by}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return consulta(sql, params)


# --- Formatação -----------------------------------------------------------------


def br(texto: str) -> str:
    """Troca separadores do formato americano pelo brasileiro."""
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def moeda(valor: float) -> str:
    if abs(valor) >= 1e6:
        return f"US$ {br(f'{valor / 1e6:,.2f}')} mi"
    if abs(valor) >= 1e3:
        return f"US$ {br(f'{valor / 1e3:,.1f}')} mil"
    return f"US$ {br(f'{valor:,.2f}')}"


def mes_ano(d) -> str:
    return pd.Timestamp(d).strftime("%m/%Y")


COLUNAS_MOEDA = {"receita", "margem", "receita_por_loja", "receita_acumulada", "valor"}
COLUNAS_PCT = {"margem_pct", "participacao_receita", "participacao_acumulada"}
COLUNAS_INTEIRAS = {
    "unidades",
    "lojas",
    "produtos",
    "posicao",
    "ranking_receita",
    "ranking_margem",
}


def tabela(df: pd.DataFrame, moeda_valor: bool = True) -> None:
    """Tabela com mês MM/AAAA, % e US$ com separador de milhar (ordenação continua numérica)."""
    config = {}
    for col in df.columns:
        if col == "mes":
            config[col] = st.column_config.DateColumn("mes", format="MM/YYYY")
        elif col in COLUNAS_MOEDA and (col != "valor" or moeda_valor):
            config[col] = st.column_config.NumberColumn(col, format="US$ %,.2f")
        elif col in COLUNAS_PCT:
            config[col] = st.column_config.NumberColumn(col, format="percent")
        elif col in COLUNAS_INTEIRAS or col == "valor":
            config[col] = st.column_config.NumberColumn(col, format="%,d")
    with st.expander("Ver tabela"):
        st.dataframe(df, hide_index=True, column_config=config)


def variacao(atual: float, anterior: float | None) -> str | None:
    if anterior is None or not anterior:
        return None
    return br(f"{(atual / anterior - 1):+.1%}")


# --- Página ---------------------------------------------------------------------

st.set_page_config(page_title="Maven Toys — Painel", layout="wide")

if not DB_PATH.exists():
    st.error(
        "toys.duckdb não encontrado. Rode ingestao.py, transformacao.py e marts.py."
    )
    st.stop()

tema = "dark" if st.context.theme.type == "dark" else "light"
cores_serie = PALETA[tema]
AZUL, LARANJA, VERDE_AGUA = cores_serie[:3]

# Domínios dos filtros, direto do mart.
dominio = consulta(
    f"SELECT list(DISTINCT mes ORDER BY mes) meses, list(DISTINCT cidade ORDER BY cidade) cidades, "
    f"list(DISTINCT tipo_localizacao ORDER BY tipo_localizacao) tipos, "
    f"list(DISTINCT categoria ORDER BY categoria) categorias FROM {MART}"
).iloc[0]
MESES = [pd.Timestamp(m).date() for m in dominio["meses"]]
CIDADES, TIPOS, CATEGORIAS = (
    list(dominio[c]) for c in ("cidades", "tipos", "categorias")
)
ESCALA_CATEGORIAS = alt.Scale(domain=CATEGORIAS, range=cores_serie)

# A chave do gráfico de categorias muda a cada "Restaurar filtros": o Vega guarda a
# seleção no navegador, e só uma instância nova volta a aceitar clique na mesma barra.
st.session_state.setdefault("versao_grafico_categorias", 0)
CHAVE_GRAFICO_CATEGORIAS = (
    f"grafico_categorias_{st.session_state.versao_grafico_categorias}"
)

# --- Barra lateral --------------------------------------------------------------

with st.sidebar:
    st.header("Filtros")
    if st.button("Restaurar filtros", width="stretch"):
        for chave in [*FILTROS_SIDEBAR, CHAVE_GRAFICO_CATEGORIAS]:
            st.session_state.pop(chave, None)
        st.session_state.versao_grafico_categorias += 1
        st.rerun()
    inicio, fim = st.select_slider(
        "Meses",
        options=MESES,
        value=(MESES[0], MESES[-1]),
        format_func=mes_ano,
        key="f_meses",
    )
    cidades = st.multiselect("Cidade", CIDADES, default=CIDADES, key="f_cidades")
    tipos = st.multiselect("Tipo de localização", TIPOS, default=TIPOS, key="f_tipos")
    categorias = st.multiselect(
        "Categoria", CATEGORIAS, default=CATEGORIAS, key="f_categorias"
    )

if not (cidades and tipos and categorias):
    st.warning("Selecione ao menos uma cidade, um tipo de localização e uma categoria.")
    st.stop()

filtro_lateral = Filtro(inicio, fim, tuple(cidades), tuple(tipos), tuple(categorias))

# Clique numa barra de categoria: o estado do gráfico já está na sessão no início do rerun.
estado = st.session_state.get(CHAVE_GRAFICO_CATEGORIAS) or {}
clicadas = [
    item["categoria"]
    for item in (estado.get("selection") or {}).get("cat", [])
    if isinstance(item, dict) and "categoria" in item
]
clicadas_validas = tuple(c for c in categorias if c in clicadas)
filtro = (
    replace(filtro_lateral, categorias=clicadas_validas)
    if clicadas_validas
    else filtro_lateral
)

st.title("Maven Toys — vendas no México")
st.caption(
    f"{mes_ano(inicio)} a {mes_ano(fim)} · receita = unidades × preço · "
    "margem = unidades × (preço − custo) · preço e custo atuais do produto"
)
if clicadas_validas:
    st.info(
        f"Filtrando pela categoria clicada: **{', '.join(clicadas_validas)}**. "
        "Clique numa área vazia do gráfico (ou em *Restaurar filtros*) para limpar."
    )

# --- KPIs -----------------------------------------------------------------------

SELECT_TOTAIS = "sum(receita) receita, sum(margem) margem, sum(unidades) unidades"
atual = agrega(filtro, SELECT_TOTAIS).iloc[0]
if pd.isna(atual["receita"]):
    st.warning("Nenhuma venda com esses filtros.")
    st.stop()

anterior = None
filtro_aa = filtro.ano_anterior()
if filtro_aa.inicio >= MESES[0]:
    linha = agrega(filtro_aa, SELECT_TOTAIS).iloc[0]
    anterior = None if pd.isna(linha["receita"]) else linha


def anterior_de(campo: str) -> float | None:
    return None if anterior is None else anterior[campo]


margem_pct = atual["margem"] / atual["receita"]
delta_mpct = None
if anterior is not None:
    pp = (margem_pct - anterior["margem"] / anterior["receita"]) * 100
    delta_mpct = br(f"{pp:+.1f}") + " p.p."

ajuda = (
    f"Comparado com {mes_ano(filtro_aa.inicio)} a {mes_ano(filtro_aa.fim)}, mesmos filtros."
    if anterior is not None
    else None
)
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Receita",
    moeda(atual["receita"]),
    variacao(atual["receita"], anterior_de("receita")),
    help=ajuda,
    border=True,
)
k2.metric(
    "Margem",
    moeda(atual["margem"]),
    variacao(atual["margem"], anterior_de("margem")),
    help=ajuda,
    border=True,
)
k3.metric(
    "Margem % da receita", br(f"{margem_pct:.1%}"), delta_mpct, help=ajuda, border=True
)
k4.metric(
    "Unidades vendidas",
    br(f"{atual['unidades']:,.0f}"),
    variacao(atual["unidades"], anterior_de("unidades")),
    help=ajuda,
    border=True,
)
if anterior is not None:
    st.caption(f"Variação vs. {mes_ano(filtro_aa.inicio)} a {mes_ano(filtro_aa.fim)}.")
else:
    st.caption(
        "Variação vs. ano anterior aparece quando o período começa em "
        f"{mes_ano(MESES[12])} ou depois (os dados começam em {mes_ano(MESES[0])})."
    )

# --- Evolução mensal ------------------------------------------------------------

st.subheader("Evolução mensal")
c_metrica, c_quebra = st.columns([3, 1])
metrica = c_metrica.radio(
    "Métrica", list(METRICAS), horizontal=True, label_visibility="collapsed"
)
por_categoria = c_quebra.toggle("Quebrar por categoria")

eh_moeda = metrica != "Unidades"
formato_eixo = "$~s" if eh_moeda else "~s"
formato_tooltip = "$,.2f" if eh_moeda else ","
mensal = agrega(
    filtro,
    f"mes, {'categoria, ' if por_categoria else ''}{METRICAS[metrica]} AS valor",
    group_by="ALL",
    order_by="ALL",
)
base = alt.Chart(mensal).encode(
    x=alt.X("mes:T", title=None, axis=alt.Axis(format="%m/%Y")),
    y=alt.Y("valor:Q", title=metrica, axis=alt.Axis(format=formato_eixo)),
)
tooltip_mes = [
    alt.Tooltip("mes:T", title="Mês", format="%m/%Y"),
    alt.Tooltip("valor:Q", title=metrica, format=formato_tooltip),
]
hover = alt.selection_point(
    fields=["mes", "categoria"] if por_categoria else ["mes"],
    nearest=True,
    on="pointerover",
    empty=False,
)
if por_categoria:
    # Escala fixa (cor segue a categoria); a legenda lista só as que aparecem.
    cor = alt.Color(
        "categoria:N",
        title="Categoria",
        scale=ESCALA_CATEGORIAS,
        legend=alt.Legend(values=sorted(mensal["categoria"].unique())),
    )
    linhas = base.mark_line(strokeWidth=2).encode(color=cor)
    pontos = base.mark_point(filled=True, size=70).encode(
        color=cor, tooltip=[alt.Tooltip("categoria:N", title="Categoria"), *tooltip_mes]
    )
else:
    linhas = base.mark_line(strokeWidth=2, color=AZUL)
    pontos = base.mark_point(filled=True, size=70, color=AZUL).encode(
        tooltip=tooltip_mes
    )
grafico_mensal = alt.layer(
    linhas,
    pontos.encode(opacity=alt.condition(hover, alt.value(1), alt.value(0))).add_params(
        hover
    ),
).properties(height=320)
st.altair_chart(grafico_mensal, width="stretch")
tabela(mensal, moeda_valor=eh_moeda)

# --- Categorias (clicável) ------------------------------------------------------

st.subheader("Categorias")
st.caption(
    "Clique numa barra de receita para filtrar o resto do painel por aquela categoria; "
    "clique numa área vazia do gráfico para limpar."
)
# Usa só os filtros laterais: as barras continuam todas visíveis e a clicada fica destacada.
cats = agrega(
    filtro_lateral,
    "categoria, sum(unidades) unidades, sum(receita) receita, sum(margem) margem, "
    "sum(margem) / sum(receita) margem_pct, "
    "sum(receita) / sum(sum(receita)) OVER () participacao_receita",
    group_by="categoria",
    order_by="receita DESC",
)
sel_cat = alt.selection_point(name="cat", fields=["categoria"])
tooltip_cat = [
    alt.Tooltip("categoria:N", title="Categoria"),
    alt.Tooltip("receita:Q", title="Receita", format="$,.2f"),
    alt.Tooltip("margem:Q", title="Margem", format="$,.2f"),
    alt.Tooltip("margem_pct:Q", title="Margem %", format=".1%"),
    alt.Tooltip("participacao_receita:Q", title="% da receita", format=".1%"),
]
ordem_cat = list(cats["categoria"])


def barras_categoria(campo: str, titulo: str, formato: str, opacidade) -> alt.Chart:
    return (
        alt.Chart(cats, title=titulo)
        .mark_bar(color=AZUL, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("categoria:N", sort=ordem_cat, title=None),
            x=alt.X(f"{campo}:Q", title=None, axis=alt.Axis(format=formato)),
            opacity=opacidade,
            tooltip=tooltip_cat,
        )
        .properties(height=alt.Step(28))
    )


# Só o gráfico de receita é clicável; o de margem destaca a mesma categoria.
# (hconcat num único gráfico não se ajusta à largura da coluna no Streamlit.)
if clicadas_validas:
    destaque = alt.condition(
        alt.FieldOneOfPredicate(field="categoria", oneOf=list(clicadas_validas)),
        alt.value(1),
        alt.value(0.3),
    )
else:
    destaque = alt.value(1)
g1, g2 = st.columns(2)
with g1:
    st.altair_chart(
        barras_categoria(
            "receita",
            "Receita",
            "$~s",
            alt.condition(sel_cat, alt.value(1), alt.value(0.3)),
        )
        .add_params(sel_cat)
        .mark_bar(color=AZUL, cornerRadiusEnd=4, cursor="pointer"),
        width="stretch",
        on_select="rerun",
        selection_mode="cat",
        key=CHAVE_GRAFICO_CATEGORIAS,
    )
with g2:
    st.altair_chart(
        barras_categoria("margem_pct", "Margem % da receita", "%", destaque),
        width="stretch",
    )
tabela(cats)


def barras_horizontais(df, y, x, titulo_x, formato_x, tooltip):
    return (
        alt.Chart(df)
        .mark_bar(color=AZUL, cornerRadiusEnd=4)
        .encode(
            y=alt.Y(y, sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X(x, title=titulo_x, axis=alt.Axis(format=formato_x)),
            tooltip=tooltip,
        )
    )


# --- Ranking de lojas -----------------------------------------------------------

st.subheader("Ranking de lojas por receita")
lojas = agrega(
    filtro,
    "rank() OVER (ORDER BY sum(receita) DESC) ranking_receita, "
    "rank() OVER (ORDER BY sum(margem) DESC) ranking_margem, "
    "store_id, loja, cidade, tipo_localizacao, sum(unidades) unidades, "
    "sum(receita) receita, sum(margem) margem, sum(margem) / sum(receita) margem_pct",
    group_by="store_id, loja, cidade, tipo_localizacao",
    order_by="ranking_receita, store_id",
)
top_n = (
    st.slider("Quantas lojas mostrar", 1, len(lojas), min(10, len(lojas)))
    if len(lojas) > 1
    else 1
)
top = lojas.head(top_n).assign(loja=lambda d: d["loja"].str.removeprefix("Maven Toys "))
st.altair_chart(
    barras_horizontais(
        top,
        "loja:N",
        "receita:Q",
        "Receita",
        "$~s",
        [
            alt.Tooltip("ranking_receita:Q", title="Posição (receita)"),
            alt.Tooltip("ranking_margem:Q", title="Posição (margem)"),
            alt.Tooltip("loja:N", title="Loja"),
            alt.Tooltip("tipo_localizacao:N", title="Localização"),
            alt.Tooltip("receita:Q", title="Receita", format="$,.2f"),
            alt.Tooltip("margem_pct:Q", title="Margem %", format=".1%"),
        ],
    ).properties(height=alt.Step(22)),
    width="stretch",
)
tabela(lojas)

# --- Pareto ---------------------------------------------------------------------

st.subheader("Pareto de produtos")
where, params = filtro.where()
pareto = consulta(
    f"""
    WITH por_produto AS (
        SELECT product_id, produto, categoria,
               sum(unidades) unidades, sum(receita) receita, sum(margem) margem
        FROM {MART} WHERE {where}
        GROUP BY ALL
    ),
    acumulado AS (
        SELECT *,
               row_number() OVER w posicao,
               sum(receita) OVER w receita_acumulada,
               sum(receita) OVER () receita_total
        FROM por_produto
        WINDOW w AS (ORDER BY receita DESC, product_id
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    )
    SELECT posicao, product_id, produto, categoria, unidades, receita, margem,
           receita / receita_total participacao_receita,
           receita_acumulada,
           receita_acumulada / receita_total participacao_acumulada,
           CASE WHEN (receita_acumulada - receita) / receita_total < 0.80 THEN 'A'
                WHEN (receita_acumulada - receita) / receita_total < 0.95 THEN 'B'
                ELSE 'C' END classe_abc
    FROM acumulado ORDER BY posicao
    """,
    params,
)
classe_a = pareto[pareto["classe_abc"] == "A"]
participacao_a = br(f"{classe_a['participacao_receita'].sum():.0%}")
st.caption(
    f"{len(classe_a)} de {len(pareto)} produtos (classe A) somam {participacao_a} da receita. "
    "A até 80% acumulado, B até 95%, C o restante."
)
cores_abc = alt.Scale(domain=["A", "B", "C"], range=[AZUL, LARANJA, VERDE_AGUA])
base_pareto = alt.Chart(pareto).encode(
    x=alt.X(
        "posicao:O",
        title="Produtos, da maior para a menor receita",
        axis=alt.Axis(labelAngle=0),
    ),
    y=alt.Y(
        "participacao_acumulada:Q",
        title="% acumulado da receita",
        axis=alt.Axis(format="%"),
        scale=alt.Scale(domain=[0, 1]),
    ),
)
grafico_pareto = alt.layer(
    base_pareto.mark_line(color="gray", strokeWidth=2),
    base_pareto.mark_point(filled=True, size=110, opacity=1).encode(
        color=alt.Color("classe_abc:N", title="Classe", scale=cores_abc),
        shape=alt.Shape(
            "classe_abc:N",
            title="Classe",
            scale=alt.Scale(
                domain=["A", "B", "C"], range=["circle", "square", "diamond"]
            ),
        ),
        tooltip=[
            alt.Tooltip("posicao:O", title="Posição"),
            alt.Tooltip("produto:N", title="Produto"),
            alt.Tooltip("categoria:N", title="Categoria"),
            alt.Tooltip("receita:Q", title="Receita", format="$,.2f"),
            alt.Tooltip("participacao_receita:Q", title="% da receita", format=".1%"),
            alt.Tooltip("participacao_acumulada:Q", title="% acumulado", format=".1%"),
            alt.Tooltip("classe_abc:N", title="Classe"),
        ],
    ),
    alt.Chart(pd.DataFrame({"y": [0.8, 0.95]}))
    .mark_rule(strokeDash=[4, 4], color="gray")
    .encode(y="y:Q"),
).properties(height=320)
st.altair_chart(grafico_pareto, width="stretch")
tabela(pareto)

# --- Tipo de localização --------------------------------------------------------

st.subheader("Receita por tipo de localização")
localizacao = agrega(
    filtro,
    "tipo_localizacao, count(DISTINCT store_id) lojas, sum(unidades) unidades, "
    "sum(receita) receita, sum(margem) margem, sum(margem) / sum(receita) margem_pct, "
    "sum(receita) / count(DISTINCT store_id) receita_por_loja, "
    "sum(receita) / sum(sum(receita)) OVER () participacao_receita",
    group_by="tipo_localizacao",
    order_by="receita DESC",
)
tooltip_loc = [
    alt.Tooltip("tipo_localizacao:N", title="Localização"),
    alt.Tooltip("lojas:Q", title="Lojas"),
    alt.Tooltip("receita:Q", title="Receita", format="$,.2f"),
    alt.Tooltip("receita_por_loja:Q", title="Receita por loja", format="$,.2f"),
    alt.Tooltip("participacao_receita:Q", title="% da receita", format=".1%"),
]
l1, l2 = st.columns(2)
l1.markdown("**Receita total**")
l1.altair_chart(
    barras_horizontais(
        localizacao, "tipo_localizacao:N", "receita:Q", None, "$~s", tooltip_loc
    ),
    width="stretch",
)
l2.markdown("**Receita por loja**")
l2.altair_chart(
    barras_horizontais(
        localizacao,
        "tipo_localizacao:N",
        "receita_por_loja:Q",
        None,
        "$~s",
        tooltip_loc,
    ),
    width="stretch",
)
tabela(localizacao)

# --- Estoque --------------------------------------------------------------------

MART_ESTOQUE = "marts.cobertura_estoque"
st.subheader("Estoque")
st.caption(
    "O estoque é uma foto do fim do período, sem data, comparada com a média diária de "
    "vendas dos últimos 90 dias do dado. Os filtros de cidade, tipo de localização e "
    "categoria valem aqui; o de meses não. *Sem registro*: par vendido nos últimos 90 "
    "dias que não existe no arquivo de estoque (na carga real, Jenga em 23 lojas); o "
    "estoque fica vazio, não zero. *Sem demanda*: há estoque, mas nenhuma venda em 90 dias."
)
where_estoque = (
    "list_contains(?::VARCHAR[], cidade) "
    "AND list_contains(?::VARCHAR[], tipo_localizacao) "
    "AND list_contains(?::VARCHAR[], categoria)"
)
params_estoque = (filtro.cidades, filtro.tipos, filtro.categorias)
por_status = consulta(
    f"SELECT status, count(*) AS itens FROM {MART_ESTOQUE} WHERE {where_estoque} GROUP BY status",
    params_estoque,
)
itens_por_status = dict(zip(por_status["status"], por_status["itens"]))
for coluna, (status, rotulo) in zip(
    st.columns(5),
    [
        ("ruptura", "Ruptura"),
        ("critico", "Crítico"),
        ("ok", "OK"),
        ("sem demanda", "Sem demanda"),
        ("sem registro", "Sem registro"),
    ],
):
    coluna.metric(rotulo, br(f"{itens_por_status.get(status, 0):,}"), border=True)

alertas = consulta(
    f"""
    SELECT status, replace(loja, 'Maven Toys ', '') AS loja, produto, categoria,
           stock_on_hand, unidades_90d,
           media_diaria_unidades, dias_cobertura
    FROM {MART_ESTOQUE}
    WHERE status IN ('ruptura', 'critico', 'sem registro') AND {where_estoque}
    ORDER BY CASE status WHEN 'ruptura' THEN 1 WHEN 'critico' THEN 2 ELSE 3 END,
             dias_cobertura, loja, produto
    """,
    params_estoque,
)
st.markdown(
    f"**Itens em ruptura, críticos e sem registro de estoque** ({br(f'{len(alertas):,}')})"
)
st.dataframe(
    alertas,
    hide_index=True,
    column_config={
        "stock_on_hand": st.column_config.NumberColumn("estoque", format="%,d"),
        "unidades_90d": st.column_config.NumberColumn("unidades 90 dias", format="%,d"),
        "media_diaria_unidades": st.column_config.NumberColumn(
            "média diária", format="%.2f"
        ),
        "dias_cobertura": st.column_config.NumberColumn(
            "dias de cobertura", format="%.1f"
        ),
    },
)
