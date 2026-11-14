-- P1: 10 zonas de origen con mas viajes en el mes y variacion contra el mismo mes del año anterior
with m as (
    select zona_subida_id,
           count(*) filter (where to_char(fecha_viaje, 'YYYY-MM') = %(mes)s)      as viajes_mes,
           count(*) filter (where to_char(fecha_viaje, 'YYYY-MM') = %(mes_comp)s) as viajes_comp
    from analytics.fact_trips
    group by 1
)
select z.zona, z.distrito, m.viajes_mes, m.viajes_comp,
       m.viajes_mes - m.viajes_comp as variacion_abs,
       round(100.0 * (m.viajes_mes - m.viajes_comp) / nullif(m.viajes_comp, 0), 2) as variacion_pct
from m
join analytics.dim_zone z on z.zona_id = m.zona_subida_id
order by m.viajes_mes desc
limit 10;
