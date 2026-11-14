-- P6: variacion de viajes totales y de tarifa media entre el mes asignado y el mismo mes del año anterior
with m as (
    select to_char(fecha_viaje, 'YYYY-MM') as mes,
           count(*) as viajes,
           round(avg(tarifa_base), 2) as tarifa_media
    from analytics.fact_trips
    group by 1
)
select a.viajes as viajes_mes, b.viajes as viajes_comp,
       round(100.0 * (a.viajes - b.viajes) / b.viajes, 2) as var_viajes_pct,
       a.tarifa_media as tarifa_mes, b.tarifa_media as tarifa_comp,
       round(100.0 * (a.tarifa_media - b.tarifa_media) / b.tarifa_media, 2) as var_tarifa_pct
from m a
join m b on a.mes = %(mes)s and b.mes = %(mes_comp)s;
