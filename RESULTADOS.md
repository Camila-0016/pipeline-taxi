# Resultados: 2025-03 vs 2024-03

Generado por `src/preguntas.py`. Los resultados salen de las filas aceptadas (las de cuarentena no se cuentan). Cada consulta esta en `sql/preguntas/`.

## P1: 10 zonas de origen con mas viajes en el mes y variacion contra el mismo mes del año anterior

| zona | distrito | viajes_mes | viajes_comp | variacion_abs | variacion_pct |
|---|---|---|---|---|---|
| Midtown Center | Manhattan | 177778 | 161248 | 16530 | 10.25 |
| Upper East Side South | Manhattan | 167143 | 153949 | 13194 | 8.57 |
| JFK Airport | Queens | 151143 | 152151 | -1008 | -0.66 |
| Upper East Side North | Manhattan | 150096 | 144800 | 5296 | 3.66 |
| Times Sq/Theatre District | Manhattan | 132649 | 120857 | 11792 | 9.76 |
| Penn Station/Madison Sq West | Manhattan | 129524 | 113203 | 16321 | 14.42 |
| Midtown East | Manhattan | 125944 | 122379 | 3565 | 2.91 |
| Lincoln Square East | Manhattan | 114814 | 113603 | 1211 | 1.07 |
| Union Sq | Manhattan | 112181 | 96370 | 15811 | 16.41 |
| East Village | Manhattan | 108502 | 92276 | 16226 | 17.58 |

**Interpretacion:** Nueve de las diez zonas son de Manhattan; la unica de otro distrito es JFK Airport (Queens). Midtown Center lidera con 177778 viajes (+10.25%). Los mayores aumentos estan en zonas del sur de Manhattan (East Village +17.58%, Union Sq +16.41%, Penn Station +14.42%), y JFK Airport es la unica de las diez que baja (-0.66%).

Consulta (`sql/preguntas/01_top10_zonas_origen.sql`):

```sql
-- P1: 10 zonas de origen con mas viajes en el mes y variacion contra el mismo mes del año anterior
with m as (
    select zona_subida_id,
           count(*) filter (where to_char(fecha_viaje, 'YYYY-MM') = '2025-03')      as viajes_mes,
           count(*) filter (where to_char(fecha_viaje, 'YYYY-MM') = '2024-03') as viajes_comp
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
```

## P2: hora del dia con mayor ingreso promedio por viaje (total pagado), en cada mes

| mes | hora_subida | ingreso_prom | viajes |
|---|---|---|---|
| 2024-03 | 5 | 35.19 | 22685 |
| 2025-03 | 5 | 33.75 | 32593 |

**Interpretacion:** La hora con mayor ingreso promedio por viaje es las 5 AM en ambos meses (35.19 en 2024-03 y 33.75 en 2025-03). A esa hora hay pocos viajes y mas largos y caros; una explicacion plausible son los traslados al aeropuerto, aunque esta consulta no lo mide. El ingreso es el total pagado (total_amount).

Consulta (`sql/preguntas/02_hora_mayor_ingreso.sql`):

```sql
-- P2: hora del dia con mayor ingreso promedio por viaje (total pagado), en cada mes
with h as (
    select to_char(fecha_viaje, 'YYYY-MM') as mes, hora_subida,
           round(avg(total), 2) as ingreso_prom, count(*) as viajes
    from analytics.fact_trips
    where to_char(fecha_viaje, 'YYYY-MM') in ('2025-03', '2024-03')
    group by 1, 2
), r as (
    select *, row_number() over (partition by mes order by ingreso_prom desc) as rn
    from h
)
select mes, hora_subida, ingreso_prom, viajes
from r
where rn = 1
order by mes;
```

## P3a: porcentaje de viajes con cbd_congestion_fee mayor a 0 en el mes asignado

| viajes_totales | viajes_con_cbd | pct_con_cbd |
|---|---|---|
| 4053277 | 2995164 | 73.89 |

**Interpretacion:** En 2025-03 el 73.89% de los viajes (2995164 de 4053277) pago el recargo de congestion (cbd_congestion_fee). El resto probablemente no toca la zona de cobro del sur de Manhattan. En 2024 el campo no existia (NULL), por eso solo se calcula para el mes asignado.

Consulta (`sql/preguntas/03a_pct_cbd.sql`):

```sql
-- P3a: porcentaje de viajes con cbd_congestion_fee mayor a 0 en el mes asignado
select count(*)                                      as viajes_totales,
       count(*) filter (where recargo_cbd > 0)       as viajes_con_cbd,
       round(100.0 * count(*) filter (where recargo_cbd > 0) / count(*), 2) as pct_con_cbd
from analytics.fact_trips
where to_char(fecha_viaje, 'YYYY-MM') = '2025-03';
```

## P3b: 5 zonas de origen con mayor proporcion de viajes con cbd_congestion_fee mayor a 0

| zona | distrito | viajes | viajes_con_cbd | pct_con_cbd |
|---|---|---|---|---|
| SoHo | Manhattan | 35534 | 35455 | 99.78 |
| Greenwich Village South | Manhattan | 65098 | 64925 | 99.73 |
| West Village | Manhattan | 97376 | 97107 | 99.72 |
| Greenwich Village North | Manhattan | 59323 | 59158 | 99.72 |
| East Village | Manhattan | 108502 | 108186 | 99.71 |

**Interpretacion:** Las cinco zonas con mayor proporcion son del sur de Manhattan, todas por encima de 99.7% (SoHo 99.78%, Greenwich Village South 99.73%, West Village 99.72%, Greenwich Village North 99.72%, East Village 99.71%), coherente con estar dentro de la zona de cobro. Se exigen al menos 1000 viajes por zona.

Consulta (`sql/preguntas/03b_top5_zonas_cbd.sql`):

```sql
-- P3b: 5 zonas de origen con mayor proporcion de viajes con cbd_congestion_fee mayor a 0
-- Se exigen al menos 1000 viajes por zona para que la proporcion no dependa de zonas casi sin viajes
select z.zona, z.distrito,
       count(*)                                  as viajes,
       count(*) filter (where f.recargo_cbd > 0) as viajes_con_cbd,
       round(100.0 * count(*) filter (where f.recargo_cbd > 0) / count(*), 2) as pct_con_cbd
from analytics.fact_trips f
join analytics.dim_zone z on z.zona_id = f.zona_subida_id
where to_char(f.fecha_viaje, 'YYYY-MM') = '2025-03'
group by z.zona, z.distrito
having count(*) >= 1000
order by pct_con_cbd desc
limit 5;
```

## P4: propina promedio como porcentaje de la tarifa, por tipo de pago

| mes | tipo_pago | viajes | propina_pct_de_tarifa |
|---|---|---|---|
| 2024-03 | 0 | 411120 | 3.34 |
| 2024-03 | 1 | 2596241 | 22.28 |
| 2024-03 | 2 | 466070 | 0.00 |
| 2024-03 | 3 | 16042 | 0.04 |
| 2024-03 | 4 | 31175 | 0.11 |
| 2025-03 | 0 | 775723 | 2.07 |
| 2025-03 | 1 | 2684909 | 22.53 |
| 2025-03 | 2 | 385092 | 0.00 |
| 2025-03 | 3 | 17646 | 0.03 |
| 2025-03 | 4 | 48328 | 0.06 |

**Interpretacion:** Con tarjeta (tipo 1) la propina es 22.28% de la tarifa en 2024-03 y 22.53% en 2025-03. En efectivo (tipo 2) da 0.00%, pero no es interpretable. El taximetro solo registra las propinas pagadas con tarjeta; la propina en efectivo se entrega en mano y no queda registrada, asi que 0 significa no registrada y no que no hubo propina. Los tipos 3 (sin cargo) y 4 (disputa) rondan 0 por su naturaleza.

Consulta (`sql/preguntas/04_propina_por_tipo_pago.sql`):

```sql
-- P4: propina promedio como porcentaje de la tarifa, por tipo de pago
-- Se calcula suma de propinas sobre suma de tarifas (promedio ponderado); se excluyen tarifas en 0 o negativas
-- tipo_pago: 0 flex, 1 tarjeta, 2 efectivo, 3 sin cargo, 4 disputa, 5 desconocido, 6 anulado
select to_char(fecha_viaje, 'YYYY-MM') as mes,
       tipo_pago,
       count(*) as viajes,
       round(100.0 * sum(propina) / nullif(sum(tarifa_base), 0), 2) as propina_pct_de_tarifa
from analytics.fact_trips
where tarifa_base > 0
  and to_char(fecha_viaje, 'YYYY-MM') in ('2025-03', '2024-03')
group by 1, 2
order by 1, 2;
```

## P5: viajes y tarifa media de los que empiezan o terminan en JFK o LaGuardia (por nombre de zona)

| mes | viajes | tarifa_media |
|---|---|---|
| 2024-03 | 324238 | 55.51 |
| 2025-03 | 322947 | 55.14 |

**Interpretacion:** Los viajes que empiezan o terminan en JFK o LaGuardia son 322947 en 2025-03 contra 324238 en 2024-03 (-0.40%), con tarifa media de 55.14 contra 55.51 (-0.67%): el segmento aeroportuario casi no cambio. La tarifa es fare_amount, sin propinas, peajes ni recargos.

Consulta (`sql/preguntas/05_aeropuertos_jfk_lga.sql`):

```sql
-- P5: viajes y tarifa media de los que empiezan o terminan en JFK o LaGuardia (por nombre de zona)
select to_char(fecha_viaje, 'YYYY-MM') as mes,
       count(*) as viajes,
       round(avg(tarifa_base), 2) as tarifa_media
from analytics.fact_trips
where (zona_origen ilike '%JFK%' or zona_origen ilike '%LaGuardia%'
       or zona_destino ilike '%JFK%' or zona_destino ilike '%LaGuardia%')
  and to_char(fecha_viaje, 'YYYY-MM') in ('2025-03', '2024-03')
group by 1
order by 1;
```

## P6: variacion de viajes totales y de tarifa media entre el mes asignado y el mismo mes del año anterior

| viajes_mes | viajes_comp | var_viajes_pct | tarifa_mes | tarifa_comp | var_tarifa_pct |
|---|---|---|---|---|---|
| 4053277 | 3535967 | 14.63 | 18.47 | 19.17 | -3.65 |

**Interpretacion:** Los viajes crecieron 14.63% (3535967 a 4053277) y la tarifa media bajo 3.65% (19.17 a 18.47). Hipotesis: desde enero de 2025 rige el peaje de congestion en Manhattan; el recargo de los taxis amarillos es menor que el de las aplicaciones, lo que pudo traer mas viajes al taxi en el centro (en P1 crecen sobre todo las zonas del sur de Manhattan). La tarifa baja sin que los viajes sean mas cortos (distancia media 3.28 a 3.25 millas) pero si mas rapidos: duracion media 16.70 a 16.09 min (-3.65%, igual que la tarifa) y velocidad 10.91 a 11.07 mph, coherente con menos trafico. Es una asociacion, no una prueba: no se controlo clima ni dias habiles.

Consulta (`sql/preguntas/06_variacion_entre_meses.sql`):

```sql
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
join m b on a.mes = '2025-03' and b.mes = '2024-03';
```
