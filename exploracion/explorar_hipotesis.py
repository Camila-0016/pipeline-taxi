"""Exploración 2 (descartable): confirma las hipótesis antes de definir las reglas"""
import argparse
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent

SEGUNDOS = "date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime)"

CONSULTAS = [
    ("H1. ¿Los pasajeros NULL coinciden con payment_type = 0 y ratecode NULL?", """
        SELECT mes_archivo,
               count(*) FILTER (WHERE passenger_count IS NULL) AS pasajeros_nulos,
               count(*) FILTER (WHERE payment_type = 0) AS pago_tipo_0,
               count(*) FILTER (WHERE passenger_count IS NULL AND payment_type = 0)
                   AS pasajeros_nulos_y_pago_0,
               count(*) FILTER (WHERE passenger_count IS NULL AND ratecode_id IS NULL)
                   AS pasajeros_y_ratecode_nulos
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("H2. Bajada no posterior a la subida, por proveedor (vendor_id)", f"""
        SELECT mes_archivo, vendor_id, count(*) AS filas,
               count(*) FILTER (WHERE tpep_dropoff_datetime <= tpep_pickup_datetime)
                   AS bajada_no_posterior,
               count(*) FILTER (WHERE tpep_dropoff_datetime = tpep_pickup_datetime)
                   AS bajada_igual_a_subida
        FROM viajes GROUP BY ALL ORDER BY mes_archivo, vendor_id
    """),
    ("H3. Importe total negativo, por tipo de pago", """
        SELECT mes_archivo, payment_type, count(*) AS filas,
               count(*) FILTER (WHERE total_amount < 0) AS total_negativo
        FROM viajes GROUP BY ALL ORDER BY mes_archivo, payment_type
    """),
    ("H4. Tarifa negativa con total NO negativo", """
        SELECT mes_archivo,
               count(*) FILTER (WHERE fare_amount < 0) AS tarifa_negativa,
               count(*) FILTER (WHERE fare_amount < 0 AND total_amount >= 0)
                   AS tarifa_negativa_total_no_negativo
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("H5. Distancia <= 0: ¿qué tienen de particular?", f"""
        SELECT mes_archivo,
               count(*) FILTER (WHERE trip_distance <= 0) AS distancia_no_positiva,
               count(*) FILTER (WHERE trip_distance <= 0 AND pu_location_id = do_location_id)
                   AS con_misma_zona,
               count(*) FILTER (WHERE trip_distance <= 0 AND total_amount > 0) AS con_cobro,
               count(*) FILTER (WHERE trip_distance <= 0 AND {SEGUNDOS} > 60)
                   AS duran_mas_de_1_min
        FROM viajes GROUP BY mes_archivo ORDER BY mes_archivo
    """),
    ("H6. Velocidad > 100 mph: ¿son viajes de duración mínima?", f"""
        SELECT mes_archivo,
               count(*) FILTER (WHERE mph > 100) AS mas_de_100_mph,
               count(*) FILTER (WHERE mph > 100 AND segundos <= 60) AS duran_hasta_1_min,
               count(*) FILTER (WHERE mph > 100 AND distancia > 100) AS distancia_mayor_100
        FROM (SELECT mes_archivo, trip_distance AS distancia, {SEGUNDOS} AS segundos,
                     trip_distance / ({SEGUNDOS} / 3600.0) AS mph
              FROM viajes
              WHERE tpep_dropoff_datetime > tpep_pickup_datetime AND trip_distance > 0)
        GROUP BY mes_archivo ORDER BY mes_archivo
    """),
]


def main():
    parser = argparse.ArgumentParser(description="Exploración 2: hipótesis de calidad")
    parser.add_argument("--mes", required=True, help="Formato AAAA-MM, ej: 2025-03")
    args = parser.parse_args()

    staging = RAIZ / "data" / "staging" / f"yellow_unificado_{args.mes}.parquet"
    tmp = RAIZ / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.sql("SET memory_limit = '2GB'")
    con.sql(f"SET temp_directory = '{tmp}'")
    con.sql(f"""CREATE VIEW viajes AS
                SELECT *, substr(archivo_origen, 17, 7) AS mes_archivo
                FROM read_parquet('{staging}', hive_partitioning = false)""")

    for titulo, sql in CONSULTAS:
        print("\n" + "=" * 72)
        print(titulo)
        print("=" * 72)
        con.sql(sql).show(max_width=200, max_rows=60)


if __name__ == "__main__":
    main()