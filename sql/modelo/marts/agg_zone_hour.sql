select
    zona_subida_id,
    fecha_viaje,
    hora_subida,
    count(*)                     as viajes,
    round(sum(total), 2)         as ingreso_total,
    round(avg(duracion_min), 2)  as duracion_media_min
from {{ ref('fact_trips') }}
group by 1, 2, 3