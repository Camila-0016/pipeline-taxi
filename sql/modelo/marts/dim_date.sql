select
    d::date                          as fecha,
    extract(year  from d)::int       as anio,
    extract(month from d)::int       as mes,
    extract(day   from d)::int       as dia,
    extract(isodow from d)::int      as dia_semana,
    case extract(isodow from d)::int
        when 1 then 'lunes' when 2 then 'martes' when 3 then 'miércoles'
        when 4 then 'jueves' when 5 then 'viernes' when 6 then 'sábado'
        else 'domingo' end           as nombre_dia,
    extract(isodow from d)::int >= 6 as es_fin_de_semana
from generate_series(
    (select min(fecha_viaje) from {{ ref('stg_viajes') }}),
    (select max(fecha_viaje) from {{ ref('stg_viajes') }}),
    interval '1 day'
) as g(d)