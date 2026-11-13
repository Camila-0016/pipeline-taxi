"""Parte 3 - Calidad: aplica las reglas, separa la cuarentena y reconcilia conteos."""
import argparse
import json
import sys
from datetime import datetime

import duckdb
import yaml

from esquema import REPORTES, STAGING, cargar_contrato
from ingesta import RAIZ, contar_filas

REGLAS = RAIZ / "contracts" / "quality_rules.yaml"
ZONAS = RAIZ / "data" / "raw" / "zones" / "taxi_zone_lookup.csv"
CUARENTENA = RAIZ / "data" / "quarantine"
TMP = RAIZ / "data" / "tmp"


def cargar_reglas(ruta=REGLAS):
    with open(ruta, encoding="utf-8") as f:
        reglas = yaml.safe_load(f)["reglas"]
    ids = [r["id"] for r in reglas]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay identificadores de regla repetidos")
    for r in reglas:
        if r["severidad"] not in ("rechazo", "advertencia"):
            raise ValueError(f"{r['id']}: la severidad debe ser rechazo o advertencia")
    return reglas


def conectar():
    """Conexión a DuckDB con tope de memoria; si falta RAM, usa disco."""
    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql("SET memory_limit = '2GB'")
    con.sql(f"SET temp_directory = '{TMP}'")
    return con


def sql_evaluado(entrada, zonas, columnas, reglas):
    """SQL que agrega una columna v_Rxx (verdadero/falso) por cada regla."""
    particion = ", ".join(columnas)
    marcas = ",\n               ".join(
        f"coalesce(({r['condicion']}), false) AS v_{r['id']}" for r in reglas)
    return f"""
        WITH base AS (
            SELECT v.*,
                   zo.LocationID AS zona_origen_id,
                   zd.LocationID AS zona_destino_id,
                   row_number() OVER (PARTITION BY {particion}) AS ocurrencia
            FROM read_parquet('{entrada}', hive_partitioning = false) v
            LEFT JOIN read_csv('{zonas}') zo ON v.pu_location_id = zo.LocationID
            LEFT JOIN read_csv('{zonas}') zd ON v.do_location_id = zd.LocationID
        )
        SELECT *,
               {marcas}
        FROM base
    """


def lista_de_reglas(reglas):
    """SQL que arma un texto como 'R02,R04' con las reglas violadas (concat_ws ignora NULL)."""
    if not reglas:
        return "NULL"
    partes = ", ".join(f"CASE WHEN v_{r['id']} THEN '{r['id']}' END" for r in reglas)
    return f"concat_ws(',', {partes})"


def condicion_rechazo(reglas):
    ids = [f"v_{r['id']}" for r in reglas if r["severidad"] == "rechazo"]
    return " OR ".join(ids) if ids else "false"


def copiar_a_parquet(con, consulta, salida):
    """Escribe a un archivo temporal y recién después lo renombra."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_name(salida.name + ".tmp")
    con.sql(f"COPY ({consulta}) TO '{temporal}' (FORMAT PARQUET)")
    temporal.replace(salida)


def separar(con, evaluado, columnas, reglas, aceptadas, cuarentena):
    """Reparte las filas: aceptadas (con flags) y cuarentena (con reglas violadas)."""
    rechazo = [r for r in reglas if r["severidad"] == "rechazo"]
    advertencia = [r for r in reglas if r["severidad"] == "advertencia"]
    cols = ", ".join(columnas)
    hay_rechazo = condicion_rechazo(reglas)
    copiar_a_parquet(con, f"""
        SELECT {cols}, NULLIF({lista_de_reglas(advertencia)}, '') AS flags
        FROM read_parquet('{evaluado}', hive_partitioning = false)
        WHERE NOT ({hay_rechazo})""", aceptadas)
    copiar_a_parquet(con, f"""
        SELECT {cols}, {lista_de_reglas(rechazo)} AS reglas_violadas
        FROM read_parquet('{evaluado}', hive_partitioning = false)
        WHERE {hay_rechazo}""", cuarentena)


def armar_reporte(con, evaluado, reglas):
    """Filas leídas, aceptadas, en cuarentena y violaciones por regla, por archivo."""
    sumas = ", ".join(f"sum(v_{r['id']}::INTEGER) AS {r['id']}" for r in reglas)
    hay_rechazo = condicion_rechazo(reglas)
    rel = con.sql(f"""
        SELECT archivo_origen, count(*) AS leidas,
               count(*) FILTER (WHERE NOT ({hay_rechazo})) AS aceptadas,
               count(*) FILTER (WHERE {hay_rechazo}) AS cuarentena,
               {sumas}
        FROM read_parquet('{evaluado}', hive_partitioning = false)
        GROUP BY archivo_origen ORDER BY archivo_origen""")
    nombres = rel.columns
    reporte = {}
    for fila in rel.fetchall():
        datos = dict(zip(nombres, fila))
        archivo = datos.pop("archivo_origen")
        reporte[archivo] = {
            "leidas": datos.pop("leidas"),
            "aceptadas": datos.pop("aceptadas"),
            "cuarentena": datos.pop("cuarentena"),
            "por_regla": {k: int(v or 0) for k, v in datos.items()},
        }
    return reporte


def reconciliar(reporte, leidas_entrada, aceptadas_archivo, cuarentena_archivo):
    """Devuelve la lista de errores de conteo (vacía si todo cierra)."""
    errores = []
    for archivo, r in reporte.items():
        if r["leidas"] != r["aceptadas"] + r["cuarentena"]:
            errores.append(f"{archivo}: leídas {r['leidas']} != aceptadas {r['aceptadas']} "
                           f"+ cuarentena {r['cuarentena']}")
    total = sum(r["leidas"] for r in reporte.values())
    if total != leidas_entrada:
        errores.append(f"Filas del reporte {total} != filas de la entrada {leidas_entrada}")
    if aceptadas_archivo + cuarentena_archivo != leidas_entrada:
        errores.append(f"Archivos de salida {aceptadas_archivo} + {cuarentena_archivo} "
                       f"!= entrada {leidas_entrada}")
    return errores


def imprimir_reporte(reporte, reglas):
    for archivo, r in reporte.items():
        pct = 100 * r["cuarentena"] / r["leidas"] if r["leidas"] else 0
        print(f"\n[calidad] {archivo}")
        print(f"   leídas {r['leidas']:>9,} | aceptadas {r['aceptadas']:>9,} | "
              f"cuarentena {r['cuarentena']:>7,} ({pct:.2f}%)")
        for regla in reglas:
            n = r["por_regla"][regla["id"]]
            print(f"   {regla['id']} {regla['severidad']:<11} {regla['nombre']:<30} {n:>9,}")


def main():
    parser = argparse.ArgumentParser(description="Calidad de datos y cuarentena")
    parser.add_argument("--mes", required=True, help="Formato AAAA-MM, ej: 2025-03")
    args = parser.parse_args()
    try:
        datetime.strptime(args.mes, "%Y-%m")
    except ValueError:
        parser.error("--mes debe tener el formato AAAA-MM, por ejemplo 2025-03")

    entrada = STAGING / f"yellow_unificado_{args.mes}.parquet"
    if not entrada.exists():
        print(f"[ERROR] No existe {entrada.name}. Ejecutá primero la ingesta y el esquema.")
        sys.exit(1)

    columnas = [c["destino"] for c in cargar_contrato()] + ["archivo_origen"]
    reglas = cargar_reglas()
    evaluado = TMP / f"evaluado_{args.mes}.parquet"
    aceptadas = STAGING / f"yellow_aceptado_{args.mes}.parquet"
    cuarentena = CUARENTENA / f"yellow_cuarentena_{args.mes}.parquet"

    con = conectar()
    copiar_a_parquet(con, sql_evaluado(entrada, ZONAS, columnas, reglas), evaluado)
    separar(con, evaluado, columnas, reglas, aceptadas, cuarentena)
    reporte = armar_reporte(con, evaluado, reglas)
    evaluado.unlink(missing_ok=True)

    REPORTES.mkdir(parents=True, exist_ok=True)
    with open(REPORTES / f"calidad_{args.mes}.json", "w", encoding="utf-8") as f:
        json.dump({
            "reglas": [{k: r[k] for k in ("id", "nombre", "severidad", "umbral")}
                       for r in reglas],
            "archivos": reporte,
        }, f, indent=2, ensure_ascii=False)
    imprimir_reporte(reporte, reglas)

    errores = reconciliar(reporte, contar_filas(entrada),
                          contar_filas(aceptadas), contar_filas(cuarentena))
    if errores:
        for e in errores:
            print(f"[ERROR] Reconciliación: {e}")
        sys.exit(1)
    print("\n[ok] Reconciliación: leídas = aceptadas + cuarentena")


if __name__ == "__main__":
    main()