select zona_id, distrito, zona, zona_servicio
from {{ ref('stg_zonas') }}