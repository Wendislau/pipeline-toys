"""Painel Streamlit sobre os marts de toys.duckdb.

Só leitura: a conexão é aberta com read_only=True e o app só faz
SELECT * em tabelas do schema marts, de uma lista fixa.

Rodar:  uv run streamlit run app.py
"""

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent / "toys.duckdb"

MARTS = {
    "receita_por_mes",
    "receita_margem_por_categoria",
    "ranking_lojas",
    "pareto_produtos",
    "receita_por_tipo_localizacao",
}

# Paleta de referência (skill dataviz): azul para série única; as três primeiras
# posições categóricas para as classes A/B/C, validadas para todos os pares.
AZUL = "#2a78d6"
CORES_ABC = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}


@st.cache_data(ttl=300)
def ler_mart(nome: str) -> pd.DataFrame:
    if nome not in MARTS:
        raise ValueError(f"mart desconhecido: {nome}")
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        df = con.execute(f"SELECT * FROM marts.{nome}").df()
    # DECIMAL vira objeto Decimal no pandas; converte para float para os gráficos.
    for col in df.columns:
        if (
            df[col].dtype == object
            and df[col].map(type).astype(str).str.contains("Decimal").any()
        ):
            df[col] = df[col].astype(float)
    return df


def moeda(valor: float) -> str:
    """US$ no formato brasileiro: US$ 14,44 mi / US$ 283,4 mil."""
    if abs(valor) >= 1e6:
        texto, sufixo = f"{valor / 1e6:,.2f}", " mi"
    elif abs(valor) >= 1e3:
        texto, sufixo = f"{valor / 1e3:,.1f}", " mil"
    else:
        texto, sufixo = f"{valor:,.2f}", ""
    return "US$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".") + sufixo


def inteiro(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def tabela(df: pd.DataFrame) -> None:
    with st.expander("Ver tabela"):
        st.dataframe(df, hide_index=True)


def barras_horizontais(df, y, x, titulo_x, formato_x, tooltip, ordem=None):
    return (
        alt.Chart(df)
        .mark_bar(color=AZUL, cornerRadiusEnd=4)
        .encode(
            y=alt.Y(y, sort=ordem or "-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X(x, title=titulo_x, axis=alt.Axis(format=formato_x)),
            tooltip=tooltip,
        )
    )


st.set_page_config(page_title="Maven Toys — Painel", layout="wide")

if not DB_PATH.exists():
    st.error(
        "toys.duckdb não encontrado. Rode ingestao.py, transformacao.py e marts.py."
    )
    st.stop()

mes = ler_mart("receita_por_mes")
categorias = ler_mart("receita_margem_por_categoria")
lojas = ler_mart("ranking_lojas")
pareto = ler_mart("pareto_produtos")
localizacao = ler_mart("receita_por_tipo_localizacao")

inicio, fim = mes["mes"].min(), mes["mes"].max()
st.title("Maven Toys — vendas no México")
st.caption(
    f"{inicio:%m/%Y} a {fim:%m/%Y} · receita = unidades × preço · "
    "margem = unidades × (preço − custo) · preço e custo atuais do produto"
)

# --- KPIs ---------------------------------------------------------------------
receita, margem, unidades = (
    mes["receita"].sum(),
    mes["margem"].sum(),
    mes["unidades"].sum(),
)
k1, k2, k3 = st.columns(3)
k1.metric("Receita", moeda(receita), border=True)
k2.metric(
    "Margem",
    moeda(margem),
    delta=f"{margem / receita:.1%} da receita".replace(".", ","),
    delta_color="off",
    delta_arrow="off",
    border=True,
)
k3.metric("Unidades vendidas", inteiro(unidades), border=True)

# --- Receita por mês ----------------------------------------------------------
st.subheader("Receita por mês")
linha = alt.Chart(mes).encode(
    x=alt.X("mes:T", title=None, axis=alt.Axis(format="%m/%Y")),
    y=alt.Y("receita:Q", title="Receita (US$)", axis=alt.Axis(format="~s")),
)
hover = alt.selection_point(fields=["mes"], nearest=True, on="pointerover", empty=False)
grafico_mes = alt.layer(
    linha.mark_line(color=AZUL, strokeWidth=2),
    linha.mark_point(color=AZUL, filled=True, size=70)
    .encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[
            alt.Tooltip("mes:T", title="Mês", format="%m/%Y"),
            alt.Tooltip("receita:Q", title="Receita (US$)", format=",.2f"),
            alt.Tooltip("margem_pct:Q", title="Margem %", format=".1%"),
            alt.Tooltip("unidades:Q", title="Unidades", format=","),
        ],
    )
    .add_params(hover),
    linha.mark_rule(color="gray").encode(
        opacity=alt.condition(hover, alt.value(0.4), alt.value(0))
    ),
).properties(height=300)
st.altair_chart(grafico_mes, width="stretch")
tabela(mes)

# --- Categorias ---------------------------------------------------------------
st.subheader("Categorias")
tooltip_cat = [
    alt.Tooltip("categoria:N", title="Categoria"),
    alt.Tooltip("receita:Q", title="Receita (US$)", format=",.2f"),
    alt.Tooltip("margem:Q", title="Margem (US$)", format=",.2f"),
    alt.Tooltip("margem_pct:Q", title="Margem %", format=".1%"),
    alt.Tooltip("participacao_receita:Q", title="% da receita", format=".1%"),
]
c1, c2 = st.columns(2)
c1.markdown("**Receita**")
c1.altair_chart(
    barras_horizontais(
        categorias, "categoria:N", "receita:Q", "US$", "~s", tooltip_cat
    ),
    width="stretch",
)
c2.markdown("**Margem % da receita**")
c2.altair_chart(
    barras_horizontais(
        categorias, "categoria:N", "margem_pct:Q", None, "%", tooltip_cat
    ),
    width="stretch",
)
tabela(categorias)

# --- Ranking de lojas ---------------------------------------------------------
st.subheader("Ranking de lojas por receita")
top_n = st.slider("Quantas lojas mostrar", 5, len(lojas), 10)
top = lojas.nsmallest(top_n, "ranking_receita").assign(
    loja=lambda d: d["loja"].str.removeprefix("Maven Toys ")
)
st.altair_chart(
    barras_horizontais(
        top,
        "loja:N",
        "receita:Q",
        "Receita (US$)",
        "~s",
        [
            alt.Tooltip("ranking_receita:Q", title="Posição (receita)"),
            alt.Tooltip("ranking_margem:Q", title="Posição (margem)"),
            alt.Tooltip("loja:N", title="Loja"),
            alt.Tooltip("tipo_localizacao:N", title="Localização"),
            alt.Tooltip("receita:Q", title="Receita (US$)", format=",.2f"),
            alt.Tooltip("margem_pct:Q", title="Margem %", format=".1%"),
        ],
    ).properties(height=alt.Step(22)),
    width="stretch",
)
tabela(lojas)

# --- Pareto -------------------------------------------------------------------
st.subheader("Pareto de produtos")
n_a = int((pareto["classe_abc"] == "A").sum())
st.caption(
    f"{n_a} de {len(pareto)} produtos (classe A) somam "
    f"{pareto.loc[pareto['classe_abc'] == 'A', 'participacao_receita'].sum():.0%} da receita. "
    "A até 80% acumulado, B até 95%, C o restante."
)
cores = alt.Scale(domain=list(CORES_ABC), range=list(CORES_ABC.values()))
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
        color=alt.Color("classe_abc:N", title="Classe", scale=cores),
        shape=alt.Shape(
            "classe_abc:N",
            title="Classe",
            scale=alt.Scale(
                domain=list(CORES_ABC), range=["circle", "square", "diamond"]
            ),
        ),
        tooltip=[
            alt.Tooltip("posicao:O", title="Posição"),
            alt.Tooltip("produto:N", title="Produto"),
            alt.Tooltip("categoria:N", title="Categoria"),
            alt.Tooltip("receita:Q", title="Receita (US$)", format=",.2f"),
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

# --- Tipo de localização ------------------------------------------------------
st.subheader("Receita por tipo de localização")
tooltip_loc = [
    alt.Tooltip("tipo_localizacao:N", title="Localização"),
    alt.Tooltip("lojas:Q", title="Lojas"),
    alt.Tooltip("receita:Q", title="Receita (US$)", format=",.2f"),
    alt.Tooltip("receita_por_loja:Q", title="Receita por loja (US$)", format=",.2f"),
    alt.Tooltip("participacao_receita:Q", title="% da receita", format=".1%"),
]
l1, l2 = st.columns(2)
l1.markdown("**Receita total**")
l1.altair_chart(
    barras_horizontais(
        localizacao, "tipo_localizacao:N", "receita:Q", "US$", "~s", tooltip_loc
    ),
    width="stretch",
)
l2.markdown("**Receita por loja**")
l2.altair_chart(
    barras_horizontais(
        localizacao,
        "tipo_localizacao:N",
        "receita_por_loja:Q",
        "US$",
        "~s",
        tooltip_loc,
    ),
    width="stretch",
)
tabela(localizacao)
