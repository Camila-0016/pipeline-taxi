"""Parte 2 - Esquema: compara contra el contrato, normaliza nombres y unifica."""
import argparse
import json
import sys
from datetime import datetime

import duckdb
import yaml

from ingesta import RAIZ, contar_filas, ruta_mensual

CONTRATO = RAIZ / "contracts" / "yellow_schema.yaml"
STAGING = RAIZ / "data" / "staging"
REPORTES = RAIZ / "data" / "reports"


def cargar_contrato(ruta=CONTRATO):
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)["columnas"]


def esquema_real(ruta):
    """Devuelve {nombre_columna: tipo} leyendo solo la estructura del Parquet."""
    rel = duckdb.read_parquet(str(ruta), hive_partitioning=False)
    return {n: str(t) for n, t in zip(rel.columns, rel.types)}


def comparar(contrato, real):
    """Compara el esquema real contra el contrato."""
    esperadas = {c["origen"]: c for c in contrato}
    return {
        "faltantes": [n for n in esperadas if n not in real],
        "nuevas": [n for n in real if n not in esperadas],
        "tipos_distintos": [
            {"columna": n, "esperado": c["tipo"], "real": real[n]}
            for n, c in esperadas.items()
            if n in real and real[n] != c["tipo"]
        ],
    }


def faltantes_requeridas(contrato, comparacion):
    """Columnas requeridas que faltan: son las que hacen fallar al pipeline."""
    requeridas = {c["origen"] for c in contrato if c["requerida"]}
    return [n for n in comparacion["faltantes"] if n in requeridas]


def imprimir_comparacion(nombre, comparacion, graves):
    print(f"[esquema] {nombre}")
    opcionales = [n for n in comparacion["faltantes"] if n not in graves]
    print("   faltantes requeridas :", ", ".join(graves) or "ninguna")
    print("   faltantes opcionales :", ", ".join(opcionales) or "ninguna",
          "(se completan con NULL)" if opcionales else "")
    print("   columnas nuevas      :", ", ".join(comparacion["nuevas"]) or "ninguna",
          "(se ignoran)" if comparacion["nuevas"] else "")
    distintos = [f"{t['columna']} ({t['real']} -> {t['esperado']})"
                 for t in comparacion["tipos_distintos"]]
    print("   tipos distintos      :", ", ".join(distintos) or "ninguno",
          "(se convierten al tipo del contrato)" if distintos else "")


def consulta_archivo(ruta, contrato, real):
    """SQL que lee un archivo y devuelve las columnas del contrato, renombradas."""
    columnas = []
    for c in contrato:
        if c["origen"] in real:
            columnas.append(f'CAST("{c["origen"]}" AS {c["tipo"]}) AS {c["destino"]}')
        else:
            columnas.append(f'CAST(NULL AS {c["tipo"]}) AS {c["destino"]}')
    return (f"SELECT {', '.join(columnas)}, '{ruta.name}' AS archivo_origen "
            f"FROM read_parquet('{ruta}', hive_partitioning = false)")


def unificar(rutas, contrato, salida):
    """Junta todos los archivos en una sola tabla Parquet."""
    consultas = [consulta_archivo(r, contrato, esquema_real(r)) for r in rutas]
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_name(salida.name + ".tmp")
    duckdb.sql(f"COPY ({' UNION ALL '.join(consultas)}) "
               f"TO '{temporal}' (FORMAT PARQUET)")
    temporal.replace(salida)


def main():
    parser = argparse.ArgumentParser(description="Esquema: contrato y unificación")
    parser.add_argument("--mes", required=True, help="Formato AAAA-MM, ej: 2025-03")
    args = parser.parse_args()
    try:
        fecha = datetime.strptime(args.mes, "%Y-%m")
    except ValueError:
        parser.error("--mes debe tener el formato AAAA-MM, por ejemplo 2025-03")

    mes = f"{fecha.month:02d}"
    rutas = [ruta_mensual(fecha.year, mes)[1], ruta_mensual(fecha.year - 1, mes)[1]]
    contrato = cargar_contrato()

    reporte, hubo_error = {}, False
    for ruta in rutas:
        if not ruta.exists():
            print(f"[ERROR] No existe {ruta.name}. Ejecutá primero la ingesta.")
            hubo_error = True
            continue
        comparacion = comparar(contrato, esquema_real(ruta))
        graves = faltantes_requeridas(contrato, comparacion)
        imprimir_comparacion(ruta.name, comparacion, graves)
        reporte[ruta.name] = {**comparacion, "faltantes_requeridas": graves}
        hubo_error = hubo_error or bool(graves)

    REPORTES.mkdir(parents=True, exist_ok=True)
    with open(REPORTES / f"esquema_{args.mes}.json", "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)
    if hubo_error:
        sys.exit(1)

    salida = STAGING / f"yellow_unificado_{args.mes}.parquet"
    try:
        unificar(rutas, contrato, salida)
    except duckdb.Error as e:
        print(f"[ERROR] No se pudo unificar: {e}")
        sys.exit(1)

    esperadas = sum(contar_filas(r) for r in rutas)
    obtenidas = contar_filas(salida)
    if esperadas != obtenidas:
        print(f"[ERROR] Filas esperadas {esperadas} pero se obtuvieron {obtenidas}")
        sys.exit(1)
    print(f"[ok] {salida.name}: {obtenidas} filas (= suma de los archivos de origen)")


if __name__ == "__main__":
    main()