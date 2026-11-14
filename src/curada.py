"""Etapa 4: capa curada en Parquet particionado (estilo Hive) por year y month.

Lee las filas aceptadas (salida de la etapa de calidad), agrega las columnas
derivadas, las enriquece con la tabla de zonas y escribe una partición por mes:

    data/curated/yellow/year=2025/month=03/part-0.parquet

Reprocesar un mes reemplaza solo su partición: se escribe en una carpeta
temporal, se verifica el conteo y recién entonces se intercambia con la
partición vieja. Las demás particiones no se tocan.
"""
import argparse
import glob
import shutil
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
CURADA = RAIZ / "data" / "curated" / "yellow"


def mes_comparacion(mes):
    """Mismo mes del año anterior: 2025-03 -> 2024-03."""
    anio, m = mes.split("-")
    return f"{int(anio) - 1}-{m}"


def conectar():
    con = duckdb.connect()
    tmp = RAIZ / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute("SET memory_limit='3GB'")
    con.execute("SET threads=4")                       # menos hilos = menos buffers a la vez
    con.execute("SET preserve_insertion_order=false")  # el orden de las filas no importa y ahorra memoria
    con.execute(f"SET temp_directory='{tmp}'")
    return con


def filtro_mes(anio, mes):
    return (f"year(tpep_pickup_datetime) = {int(anio)} "
            f"AND month(tpep_pickup_datetime) = {int(mes)}")


def sql_curado(aceptadas, zonas, anio, mes):
    """Consulta que arma la capa curada de un mes: columnas originales + derivadas + zonas."""
    return f"""
        SELECT a.*,
               CAST(a.tpep_pickup_datetime AS DATE)                         AS fecha_viaje,
               CAST(hour(a.tpep_pickup_datetime) AS INTEGER)                AS hora_subida,
               CAST(isodow(a.tpep_pickup_datetime) AS INTEGER)              AS dia_semana,
               ROUND(date_diff('second', a.tpep_pickup_datetime,
                               a.tpep_dropoff_datetime) / 60.0, 2)          AS duracion_min,
               CASE WHEN a.tpep_dropoff_datetime > a.tpep_pickup_datetime
                    THEN ROUND(a.trip_distance / (date_diff('second', a.tpep_pickup_datetime,
                               a.tpep_dropoff_datetime) / 3600.0), 2) END   AS velocidad_mph,
               CASE WHEN a.fare_amount > 0
                    THEN ROUND(100.0 * a.tip_amount / a.fare_amount, 2) END AS propina_pct,
               zo."Borough" AS distrito_origen,  zo."Zone" AS zona_origen,
               zd."Borough" AS distrito_destino, zd."Zone" AS zona_destino
        FROM read_parquet('{aceptadas}') a
        LEFT JOIN read_csv('{zonas}') zo ON zo."LocationID" = a.pu_location_id
        LEFT JOIN read_csv('{zonas}') zd ON zd."LocationID" = a.do_location_id
        WHERE {filtro_mes(anio, mes).replace('tpep_pickup_datetime', 'a.tpep_pickup_datetime')}
    """


def escribir_particion(con, aceptadas, zonas, anio, mes, raiz=CURADA):
    """Escribe (o reemplaza) la partición year=AAAA/month=MM. Devuelve las filas escritas."""
    anio, mes = int(anio), int(mes)
    destino = raiz / f"year={anio}" / f"month={mes:02d}"
    temporal = raiz / f".tmp_year={anio}_month={mes:02d}"
    viejo = raiz / f".old_year={anio}_month={mes:02d}"
    for sobrante in (temporal, viejo):
        if sobrante.exists():
            shutil.rmtree(sobrante)
    temporal.mkdir(parents=True)
    archivo = temporal / "part-0.parquet"

    con.execute(f"COPY ({sql_curado(aceptadas, zonas, anio, mes)}) "
                f"TO '{archivo}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    filas = con.execute(f"SELECT count(*) FROM read_parquet('{archivo}')").fetchone()[0]
    esperado = con.execute(f"SELECT count(*) FROM read_parquet('{aceptadas}') "
                           f"WHERE {filtro_mes(anio, mes)}").fetchone()[0]
    if filas != esperado:                       # no se toca la partición vigente
        shutil.rmtree(temporal)
        raise RuntimeError(f"year={anio}/month={mes:02d}: se escribieron {filas} filas "
                           f"y se esperaban {esperado}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.rename(viejo)
    temporal.rename(destino)
    if viejo.exists():
        shutil.rmtree(viejo)
    return filas


def contar_particiones(con, raiz=CURADA):
    """Devuelve [(partición, filas, hora de última modificación)] de todas las particiones."""
    resultado = []
    for carpeta in sorted(raiz.glob("year=*/month=*")):
        archivos = sorted(carpeta.glob("*.parquet"))
        if not archivos:
            continue
        lista = "[" + ", ".join(f"'{a}'" for a in archivos) + "]"
        filas = con.execute(f"SELECT count(*) FROM read_parquet({lista})").fetchone()[0]
        modificado = max(a.stat().st_mtime for a in archivos)
        resultado.append((f"{carpeta.parent.name}/{carpeta.name}", filas,
                          time.strftime("%H:%M:%S", time.localtime(modificado))))
    return resultado


def imprimir_particiones(con, raiz=CURADA):
    print(f"{'partición':<22}{'filas':>12}   modificada")
    for nombre, filas, hora in contar_particiones(con, raiz):
        print(f"{nombre:<22}{filas:>12,}   {hora}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True, help="Formato AAAA-MM, ej: 2025-03")
    ap.add_argument("--solo", help="Reprocesar solo esta partición (AAAA-MM)")
    ap.add_argument("--contar", action="store_true", help="Mostrar las particiones y salir")
    args = ap.parse_args()
    con = conectar()

    if args.contar:
        imprimir_particiones(con)
        return 0

    comparacion = mes_comparacion(args.mes)
    meses = [comparacion, args.mes]
    if args.solo:
        if args.solo not in meses:
            print(f"ERROR: --solo debe ser {comparacion} o {args.mes}")
            return 1
        meses = [args.solo]

    aceptadas = RAIZ / "data" / "staging" / f"yellow_aceptado_{args.mes}.parquet"
    zonas = glob.glob(str(RAIZ / "data" / "**" / "taxi_zone_lookup.csv"), recursive=True)
    if not aceptadas.exists() or not zonas:
        print("ERROR: falta el archivo de aceptadas o la tabla de zonas. Corré antes ingesta y calidad.")
        return 1

    total = 0
    for m in meses:
        anio, mm = m.split("-")
        filas = escribir_particion(con, aceptadas, zonas[0], anio, mm)
        total += filas
        print(f"[curada] year={anio}/month={mm}: {filas:,} filas")

    if not args.solo:
        leidas = con.execute(f"SELECT count(*) FROM read_parquet('{aceptadas}')").fetchone()[0]
        if total != leidas:
            print(f"ERROR de reconciliación: aceptadas {leidas:,} y curada {total:,}")
            return 1
        print(f"[ok] Reconciliación: aceptadas = curada ({total:,} filas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
