select
    v.*,
    case when v.duracion_min > 0
         then round((v.distancia_millas / (v.duracion_min / 60.0))::numeric, 2)
    end                  as velocidad_mph,
    zo.distrito          as distrito_origen,
    zo.zona              as zona_origen,
    zd.distrito          as distrito_destino,
    zd.zona              as zona_destino
from {{ ref('stg_viajes') }} v
left join {{ ref('stg_zonas') }} zo on zo.zona_id = v.zona_subida_id
left join {{ ref('stg_zonas') }} zd on zd.zona_id = v.zona_bajada_id