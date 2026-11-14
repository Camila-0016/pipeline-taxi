-- P5: viajes y tarifa media de los que empiezan o terminan en JFK o LaGuardia (por nombre de zona)
select to_char(fecha_viaje, 'YYYY-MM') as mes,
       count(*) as viajes,
       round(avg(tarifa_base), 2) as tarifa_media
from analytics.fact_trips
where (zona_origen ilike '%%JFK%%' or zona_origen ilike '%%LaGuardia%%'
       or zona_destino ilike '%%JFK%%' or zona_destino ilike '%%LaGuardia%%')
  and to_char(fecha_viaje, 'YYYY-MM') in (%(mes)s, %(mes_comp)s)
group by 1
order by 1;
