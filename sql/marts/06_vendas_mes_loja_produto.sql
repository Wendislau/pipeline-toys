-- Grão: uma linha por mês × loja × produto com pelo menos uma venda.
--   Combinações sem venda no mês não aparecem (não há linhas com zero).
-- Premissas: receita = units × product_price; margem = units × (product_price − product_cost).
--   Usa o preço e o custo atuais do produto (o dataset não tem histórico de preço).
-- Base do painel: os filtros do app.py viram WHERE sobre este mart.
SELECT
    date_trunc('month', s.sale_date)::DATE                  AS mes,
    st.store_id,
    st.store_name                                           AS loja,
    st.store_city                                           AS cidade,
    st.store_location                                       AS tipo_localizacao,
    p.product_id,
    p.product_name                                          AS produto,
    p.product_category                                      AS categoria,
    sum(s.units)                                            AS unidades,
    sum(s.units * p.product_price)                          AS receita,
    sum(s.units * (p.product_price - p.product_cost))       AS margem
FROM refined.sales s
JOIN refined.products p USING (product_id)
JOIN refined.stores st USING (store_id)
GROUP BY ALL
ORDER BY mes, st.store_id, p.product_id
