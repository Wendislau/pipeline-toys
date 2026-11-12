"""Fumaça do painel: roda app.py headless e confere KPIs e filtros."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(con):  # depende de con: falha cedo se o banco não existir
    return AppTest.from_file(APP, default_timeout=60)


KPIS = ("Receita", "Margem", "Margem % da receita", "Unidades vendidas")


def metricas(at):
    return {m.label: (m.value, m.delta) for m in at.metric}


def test_painel_sem_filtros_bate_com_totais(app):
    at = app.run()
    assert not at.exception
    m = metricas(at)
    assert m["Receita"][0] == "US$ 14,44 mi"
    assert m["Margem"][0] == "US$ 4,01 mi"
    assert m["Unidades vendidas"][0] == "1.090.565"
    # Período completo começa em 01/2017: não há ano anterior para comparar.
    assert all(not m[k][1] for k in KPIS)


def test_periodo_2018_mostra_variacao_ano_anterior(app):
    at = app.run()
    at.select_slider(key="f_meses").set_value(
        (date(2018, 1, 1), date(2018, 9, 1))
    ).run()
    assert not at.exception
    m = metricas(at)
    assert all(m[k][1] for k in KPIS)
    assert m["Margem % da receita"][1].endswith("p.p.")


def test_filtro_categoria_muda_kpis(app):
    at = app.run()
    at.multiselect(key="f_categorias").set_value(["Electronics"]).run()
    assert not at.exception
    assert metricas(at)["Receita"][0] == "US$ 2,25 mi"


def test_filtro_vazio_avisa_sem_quebrar(app):
    at = app.run()
    at.multiselect(key="f_cidades").set_value([]).run()
    assert not at.exception
    assert at.warning


@pytest.mark.parametrize("metrica", ["Receita", "Margem", "Unidades"])
@pytest.mark.parametrize("por_categoria", [False, True])
def test_evolucao_mensal_alterna_metrica_e_quebra(app, metrica, por_categoria):
    at = app.run()
    at.radio[0].set_value(metrica)
    at.toggle[0].set_value(por_categoria)
    at.run()
    assert not at.exception


ROTULOS_ESTOQUE = ("Em ruptura", "Crítico", "OK", "Sem demanda", "Sem registro")


def test_secao_estoque_conta_status_e_respeita_filtro(app):
    at = app.run()
    assert "Estoque" in [s.value for s in at.subheader]
    total = sum(
        int(m.value.replace(".", ""))
        for m in at.metric
        if m.label.startswith(ROTULOS_ESTOQUE)
    )
    assert total == 1_616  # 1.593 pares do estoque + 23 sem registro, sem filtro
    m = metricas(at)
    # 23 = Jenga vendido nos últimos 90 dias e ausente do arquivo de estoque.
    assert m["Sem registro de estoque"][0] == "23"
    assert m["Sem demanda (90 dias)"][0] == "93"
    at.multiselect(key="f_categorias").set_value(["Electronics"]).run()
    assert not at.exception
    total_filtrado = sum(
        int(m.value.replace(".", ""))
        for m in at.metric
        if m.label.startswith(ROTULOS_ESTOQUE)
    )
    assert 0 < total_filtrado < total
