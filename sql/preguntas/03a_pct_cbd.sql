-- P3a: porcentaje de viajes con cbd_congestion_fee mayor a 0 en el mes asignado
select count(*)                                      as viajes_totales,
       count(*) filter (where recargo_cbd > 0)       as viajes_con_cbd,
       round(100.0 * count(*) filter (where recargo_cbd > 0) / count(*), 2) as pct_con_cbd
from analytics.fact_trips
where to_char(fecha_viaje, 'YYYY-MM') = %(mes)s;
