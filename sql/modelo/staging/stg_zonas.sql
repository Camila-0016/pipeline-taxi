select
    "LocationID"::int as zona_id,
    "Borough"         as distrito,
    "Zone"            as zona,
    service_zone      as zona_servicio
from {{ source('raw', 'zonas') }}