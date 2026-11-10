"""Exploración de calidad (descartable): mira los datos para elegir reglas y umbrales."""
import argparse
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent

DURACION_MIN = "date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0"

CONSULTAS = [
    ("1. Filas por archivo y rango de fechas de subida", """
        SELECT mes_archivo, count(*) AS filas,
               min(tpep_pickup_datetime) AS primera_subida,
               max(tpep_pickup_datetime) AS ultima_subida
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("2. Subidas fuera del mes del archivo (cantidad por archivo)", """
        SELECT mes_archivo,
               count(*) FILTER (WHERE strftime(tpep_pickup_datetime, '%Y-%m') <> mes_archivo)
                   AS subida_fuera_del_mes
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("2b. Los 10 meses 'equivocados' más frecuentes", """
        SELECT mes_archivo, strftime(tpep_pickup_datetime, '%Y-%m') AS mes_de_la_subida,
               count(*) AS filas
        FROM viajes
        WHERE strftime(tpep_pickup_datetime, '%Y-%m') <> mes_archivo
        GROUP BY ALL ORDER BY filas DESC LIMIT 10
    """),
    ("3. Duración: bajada no posterior a la subida y viajes larguísimos", f"""
        SELECT mes_archivo,
               count(*) FILTER (WHERE tpep_dropoff_datetime <= tpep_pickup_datetime)
                   AS bajada_no_posterior,
               count(*) FILTER (WHERE tpep_dropoff_datetime > tpep_pickup_datetime
                                AND {DURACION_MIN} > 180) AS mas_de_3_horas,
               count(*) FILTER (WHERE tpep_dropoff_datetime > tpep_pickup_datetime
                                AND {DURACION_MIN} > 1440) AS mas_de_24_horas
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("3b. Duración en minutos (solo viajes con bajada posterior a la subida)", f"""
        SELECT mes_archivo,
               round(quantile_cont({DURACION_MIN}, 0.5), 1) AS mediana,
               round(quantile_cont({DURACION_MIN}, 0.99), 1) AS p99,
               round(quantile_cont({DURACION_MIN}, 0.999), 1) AS p99_9,
               round(max({DURACION_MIN}), 1) AS maximo
        FROM viajes WHERE tpep_dropoff_datetime > tpep_pickup_datetime
        GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("4. Distancia (millas): cero o negativa y valores enormes", """
        SELECT mes_archivo,
               count(*) FILTER (WHERE trip_distance <= 0) AS distancia_cero_o_negativa,
               count(*) FILTER (WHERE trip_distance > 50) AS mas_de_50,
               count(*) FILTER (WHERE trip_distance > 100) AS mas_de_100,
               count(*) FILTER (WHERE trip_distance > 200) AS mas_de_200
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("4b. Distancia en millas (solo distancias positivas)", """
        SELECT mes_archivo,
               round(quantile_cont(trip_distance, 0.5), 2) AS mediana,
               round(quantile_cont(trip_distance, 0.99), 2) AS p99,
               round(quantile_cont(trip_distance, 0.999), 2) AS p99_9,
               max(trip_distance) AS maximo
        FROM viajes WHERE trip_distance > 0
        GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("5. Velocidad promedio imposible (millas por hora)", f"""
        SELECT mes_archivo,
               count(*) FILTER (WHERE mph > 60) AS mas_de_60_mph,
               count(*) FILTER (WHERE mph > 80) AS mas_de_80_mph,
               count(*) FILTER (WHERE mph > 100) AS mas_de_100_mph
        FROM (SELECT mes_archivo, trip_distance / ({DURACION_MIN} / 60.0) AS mph
              FROM viajes
              WHERE tpep_dropoff_datetime > tpep_pickup_datetime AND trip_distance > 0)
        GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("6. Importes: negativos, ceros y valores enormes", """
        SELECT mes_archivo,
               count(*) FILTER (WHERE total_amount < 0) AS total_negativo,
               count(*) FILTER (WHERE total_amount = 0) AS total_cero,
               count(*) FILTER (WHERE fare_amount < 0) AS tarifa_negativa,
               count(*) FILTER (WHERE tip_amount < 0) AS propina_negativa,
               count(*) FILTER (WHERE tolls_amount < 0) AS peajes_negativos,
               count(*) FILTER (WHERE total_amount > 500) AS total_mayor_500,
               count(*) FILTER (WHERE total_amount > 1000) AS total_mayor_1000
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("6b. Importe total (solo positivos)", """
        SELECT mes_archivo,
               round(quantile_cont(total_amount, 0.5), 2) AS mediana,
               round(quantile_cont(total_amount, 0.99), 2) AS p99,
               round(quantile_cont(total_amount, 0.999), 2) AS p99_9,
               max(total_amount) AS maximo
        FROM viajes WHERE total_amount > 0
        GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("7. Cantidad de pasajeros (incluye NULL)", """
        SELECT mes_archivo, passenger_count, count(*) AS filas
        FROM viajes GROUP BY ALL ORDER BY mes_archivo, passenger_count
    """),
    ("8. Zonas: nulas, inexistentes en la tabla y 'desconocidas' (264 y 265)", """
        SELECT v.mes_archivo,
               count(*) FILTER (WHERE v.pu_location_id IS NULL) AS origen_nulo,
               count(*) FILTER (WHERE v.pu_location_id IS NOT NULL AND zo.LocationID IS NULL)
                   AS origen_inexistente,
               count(*) FILTER (WHERE v.do_location_id IS NULL) AS destino_nulo,
               count(*) FILTER (WHERE v.do_location_id IS NOT NULL AND zd.LocationID IS NULL)
                   AS destino_inexistente,
               count(*) FILTER (WHERE v.pu_location_id IN (264, 265)) AS origen_desconocido,
               count(*) FILTER (WHERE v.do_location_id IN (264, 265)) AS destino_desconocido
        FROM viajes v
        LEFT JOIN zonas zo ON v.pu_location_id = zo.LocationID
        LEFT JOIN zonas zd ON v.do_location_id = zd.LocationID
        GROUP BY v.mes_archivo ORDER BY v.mes_archivo
    """),
    ("8b. Zonas especiales en la tabla de zonas", """
        SELECT * FROM zonas WHERE LocationID IN (1, 132, 138, 264, 265) ORDER BY LocationID
    """),
    ("9. Tipos de pago y propina media", """
        SELECT mes_archivo, payment_type, count(*) AS filas,
               round(avg(tip_amount), 2) AS propina_media,
               round(avg(total_amount), 2) AS total_medio
        FROM viajes GROUP BY ALL ORDER BY mes_archivo, payment_type
    """),
    ("10. Códigos de tarifa (ratecode_id)", """
        SELECT mes_archivo, ratecode_id, count(*) AS filas
        FROM viajes GROUP BY ALL ORDER BY mes_archivo, ratecode_id
    """),
    ("11. Filas duplicadas exactas (tabla vacía = no hay). Puede tardar un rato", """
        SELECT mes_archivo, count(*) AS grupos_duplicados, sum(n - 1) AS filas_sobrantes
        FROM (SELECT *, count(*) AS n FROM viajes GROUP BY ALL HAVING count(*) > 1)
        GROUP BY mes_archivo ORDER BY mes_archivo
    """),
]


def main():
    parser = argparse.ArgumentParser(description="Exploración de calidad de datos")
    parser.add_argument("--mes", required=True, help="Formato AAAA-MM, ej: 2025-03")
    args = parser.parse_args()

    staging = RAIZ / "data" / "staging" / f"yellow_unificado_{args.mes}.parquet"
    zonas = RAIZ / "data" / "raw" / "zones" / "taxi_zone_lookup.csv"
    tmp = RAIZ / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.sql("SET memory_limit = '2GB'")          # tope de RAM para cuidar tu notebook
    con.sql(f"SET temp_directory = '{tmp}'")     # si falta RAM, usa disco
    con.sql(f"""CREATE VIEW viajes AS
                SELECT *, substr(archivo_origen, 17, 7) AS mes_archivo
                FROM read_parquet('{staging}', hive_partitioning = false)""")
    con.sql(f"CREATE VIEW zonas AS SELECT * FROM read_csv('{zonas}')")

    for titulo, sql in CONSULTAS:
        print("\n" + "=" * 72)
        print(titulo)
        print("=" * 72)
        con.sql(sql).show(max_width=200, max_rows=60)


if __name__ == "__main__":
    main()