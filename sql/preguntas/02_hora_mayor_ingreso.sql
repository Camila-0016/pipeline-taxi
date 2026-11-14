-- P2: hora del dia con mayor ingreso promedio por viaje (total pagado), en cada mes
with h as (
    select to_char(fecha_viaje, 'YYYY-MM') as mes, hora_subida,
           round(avg(total), 2) as ingreso_prom, count(*) as viajes
    from analytics.fact_trips
    where to_char(fecha_viaje, 'YYYY-MM') in (%(mes)s, %(mes_comp)s)
    group by 1, 2
), r as (
    select *, row_number() over (partition by mes order by ingreso_prom desc) as rn
    from h
)
select mes, hora_subida, ingreso_prom, viajes
from r
where rn = 1
order by mes;
