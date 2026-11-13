"""Etapa 4a: carga de aceptadas, cuarentena y zonas a Postgres (esquema raw).
Idempotente: borra las filas del mes y las reinserta"""
import argparse
import glob
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
CONEXION = "host=localhost port=5432 dbname=taxi user=taxi password=taxi"


def cargar_tabla(con, nombre, origen_sql, mes):
    """Crea la tabla si no existe; si existe, borra el mes y reinserta."""
    existe = con.execute(
        "select count(*) from duckdb_tables() "
        "where database_name='pg' and schema_name='raw' and table_name=?",
        [nombre],
    ).fetchone()[0]
    if not existe:
        con.execute(f"create table pg.raw.{nombre} as {origen_sql}")
    else:
        con.execute(f"delete from pg.raw.{nombre} where mes_proceso = ?", [mes])
        con.execute(f"insert into pg.raw.{nombre} {origen_sql}")
    n = con.execute(
        f"select count(*) from pg.raw.{nombre} where mes_proceso = ?", [mes]
    ).fetchone()[0]
    print(f"raw.{nombre}: {n:,} filas para {mes}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True, help="AAAA-MM")
    mes = ap.parse_args().mes

    acept = RAIZ / f"data/staging/yellow_aceptado_{mes}.parquet"
    cuar = RAIZ / f"data/quarantine/yellow_cuarentena_{mes}.parquet"
    zonas = glob.glob(str(RAIZ / "data/**/taxi_zone_lookup.csv"), recursive=True)
    for f in (acept, cuar):
        if not f.exists():
            print(f"ERROR: falta {f}. Corré antes la etapa de calidad.")
            return 1
    if not zonas:
        print("ERROR: no encuentro taxi_zone_lookup.csv")
        return 1

    con = duckdb.connect()
    con.execute("set memory_limit='2GB'")
    con.execute("install postgres; load postgres;")
    con.execute(f"attach '{CONEXION}' as pg (type postgres)")
    con.execute("create schema if not exists pg.raw")

    cargar_tabla(con, "yellow_aceptado",
                 f"select *, '{mes}' as mes_proceso from read_parquet('{acept}')", mes)
    cargar_tabla(con, "yellow_cuarentena",
                 f"select *, '{mes}' as mes_proceso from read_parquet('{cuar}')", mes)
    cargar_tabla(con, "zonas",
                 f"select *, '{mes}' as mes_proceso from read_csv('{zonas[0]}')", mes)
    return 0


if __name__ == "__main__":
    sys.exit(main())