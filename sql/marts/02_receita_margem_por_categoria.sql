-- Grão: uma linha por categoria de produto (product_category).
-- Premissas: receita = units × product_price; margem = units × (product_price − product_cost).
--   Usa o preço e o custo atuais do produto (o dataset não tem histórico de preço).
SELECT
    p.product_category                                      AS categoria,
    count(DISTINCT p.product_id)                            AS produtos,
    sum(s.units)                                            AS unidades,
    sum(s.units * p.product_price)                          AS receita,
    sum(s.units * (p.product_price - p.product_cost))       AS margem,
    round(sum(s.units * (p.product_price - p.product_cost))
          / sum(s.units * p.product_price), 4)              AS margem_pct,
    round(sum(s.units * p.product_price)
          / sum(sum(s.units * p.product_price)) OVER (), 4) AS participacao_receita
FROM refined.sales s
JOIN refined.products p USING (product_id)
GROUP BY 1
ORDER BY receita DESC
