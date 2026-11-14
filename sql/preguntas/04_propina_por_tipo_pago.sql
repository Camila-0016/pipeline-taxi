-- P4: propina promedio como porcentaje de la tarifa, por tipo de pago
-- Se calcula suma de propinas sobre suma de tarifas (promedio ponderado); se excluyen tarifas en 0 o negativas
-- tipo_pago: 0 flex, 1 tarjeta, 2 efectivo, 3 sin cargo, 4 disputa, 5 desconocido, 6 anulado
select to_char(fecha_viaje, 'YYYY-MM') as mes,
       tipo_pago,
       count(*) as viajes,
       round(100.0 * sum(propina) / nullif(sum(tarifa_base), 0), 2) as propina_pct_de_tarifa
from analytics.fact_trips
where tarifa_base > 0
  and to_char(fecha_viaje, 'YYYY-MM') in (%(mes)s, %(mes_comp)s)
group by 1, 2
order by 1, 2;
