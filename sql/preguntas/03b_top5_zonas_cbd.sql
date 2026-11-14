-- P3b: 5 zonas de origen con mayor proporcion de viajes con cbd_congestion_fee mayor a 0
-- Se exigen al menos 1000 viajes por zona para que la proporcion no dependa de zonas casi sin viajes
select z.zona, z.distrito,
       count(*)                                  as viajes,
       count(*) filter (where f.recargo_cbd > 0) as viajes_con_cbd,
       round(100.0 * count(*) filter (where f.recargo_cbd > 0) / count(*), 2) as pct_con_cbd
from analytics.fact_trips f
join analytics.dim_zone z on z.zona_id = f.zona_subida_id
where to_char(f.fecha_viaje, 'YYYY-MM') = %(mes)s
group by z.zona, z.distrito
having count(*) >= 1000
order by pct_con_cbd desc
limit 5;
