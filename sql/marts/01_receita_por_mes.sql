-- Grão: uma linha por mês (primeiro dia do mês de sale_date).
-- Premissas: receita = units × product_price; margem = units × (product_price − product_cost).
--   Usa o preço e o custo atuais do produto (o dataset não tem histórico de preço).
--   2018 vai só até setembro (último dia com venda: 2018-09-30).
SELECT
    date_trunc('month', s.sale_date)::DATE                  AS mes,
    count(*)                                                AS vendas,
    sum(s.units)                                            AS unidades,
    sum(s.units * p.product_price)                          AS receita,
    sum(s.units * (p.product_price - p.product_cost))       AS margem,
    round(sum(s.units * (p.product_price - p.product_cost))
          / sum(s.units * p.product_price), 4)              AS margem_pct
FROM refined.sales s
JOIN refined.products p USING (product_id)
GROUP BY 1
ORDER BY 1
