-- Staging de viajes: renombra, castea y deriva campos, No filtra filas
-- (el filtrado de calidad ya se hizo antes, en la etapa 3)
select
    md5(concat_ws('|',
        vendor_id, tpep_pickup_datetime, tpep_dropoff_datetime,
        pu_location_id, do_location_id, total_amount, trip_distance
    ))                                                   as viaje_id,
    vendor_id::int                                       as vendor_id,
    tpep_pickup_datetime                                 as subida_ts,
    tpep_dropoff_datetime                                as bajada_ts,
    tpep_pickup_datetime::date                           as fecha_viaje,
    extract(hour from tpep_pickup_datetime)::int         as hora_subida,
    passenger_count::int                                 as pasajeros,
    trip_distance::numeric(10,2)                         as distancia_millas,
    ratecode_id::int                                     as tarifa_codigo,
    store_and_fwd_flag                                   as store_and_fwd,
    pu_location_id                                       as zona_subida_id,
    do_location_id                                       as zona_bajada_id,
    payment_type::int                                    as tipo_pago,
    fare_amount::numeric(10,2)                           as tarifa_base,
    extra::numeric(10,2)                                 as extra,
    mta_tax::numeric(10,2)                               as mta_tax,
    tip_amount::numeric(10,2)                            as propina,
    tolls_amount::numeric(10,2)                          as peajes,
    improvement_surcharge::numeric(10,2)                 as recargo_mejora,
    congestion_surcharge::numeric(10,2)                  as recargo_congestion,
    airport_fee::numeric(10,2)                           as recargo_aeropuerto,
    cbd_congestion_fee::numeric(10,2)                    as recargo_cbd,
    total_amount::numeric(10,2)                          as total,
    round((extract(epoch from (tpep_dropoff_datetime - tpep_pickup_datetime)) / 60.0)::numeric, 2)
                                                         as duracion_min,
    flags                                                as advertencias
from {{ source('raw', 'yellow_aceptado') }}