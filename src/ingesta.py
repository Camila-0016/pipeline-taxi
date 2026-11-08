"""Parte 1 - Ingesta: descarga los archivos de la TLC sin modificarlos."""
import argparse
import csv
import hashlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq
import requests

RAIZ = Path(__file__).resolve().parent.parent
DATA_RAW = RAIZ / "data" / "raw"
LOG_PATH = RAIZ / "data" / "control" / "ingestion_log.csv"

URL_MES = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{anio}-{mes}.parquet"
URL_ZONAS = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"

CAMPOS_LOG = ["archivo", "url", "filas", "bytes", "hash_sha256",
              "fecha_hora", "estado", "detalle"]
REINTENTOS = 3


def calcular_hash(ruta):
    """Huella digital (SHA-256) del archivo, leyéndolo de a 1 MB."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def contar_filas(ruta):
    """Cantidad de filas, sin cargar el archivo entero en memoria."""
    if ruta.suffix == ".parquet":
        return pq.ParquetFile(ruta).metadata.num_rows
    with open(ruta, encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # menos la fila de encabezado


def leer_log():
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escribir_log(registro):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    es_nuevo = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS_LOG)
        if es_nuevo:
            escritor.writeheader()
        escritor.writerow(registro)


def ya_descargado(url, destino):
    """True si el archivo existe y su hash coincide con el de un 'ok' del log."""
    if not destino.exists():
        return False
    hash_actual = calcular_hash(destino)
    for fila in leer_log():
        if (fila["url"] == url and fila["estado"] == "ok"
                and fila["hash_sha256"] == hash_actual):
            return True
    return False


def descargar(url, destino):
    """Descarga con hasta 3 intentos y espera creciente (2 s, 4 s)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".part")
    ultimo_error = None
    for intento in range(1, REINTENTOS + 1):
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(temporal, "wb") as f:
                    for bloque in r.iter_content(chunk_size=1024 * 1024):
                        f.write(bloque)
            temporal.replace(destino)  # recién ahora aparece el archivo final
            return
        except (requests.RequestException, OSError) as e:
            ultimo_error = e
            if intento < REINTENTOS:
                espera = 2 ** intento
                print(f"[reintento {intento}/{REINTENTOS}] {e} - espero {espera} s")
                time.sleep(espera)
    temporal.unlink(missing_ok=True)
    raise ultimo_error


def ingestar(url, destino):
    """Descarga un archivo y lo registra en el log. Devuelve True si quedó ok."""
    if ya_descargado(url, destino):
        print(f"[omitido] {destino.name}: ya existe y el hash coincide con el log")
        return True
    registro = {
        "archivo": os.path.relpath(destino, RAIZ),
        "url": url,
        "fecha_hora": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        descargar(url, destino)
        registro.update(
            filas=contar_filas(destino),
            bytes=destino.stat().st_size,
            hash_sha256=calcular_hash(destino),
            estado="ok",
            detalle="",
        )
        print(f"[ok] {destino.name}: {registro['filas']} filas, {registro['bytes']} bytes")
        resultado = True
    except Exception as e:
        registro.update(filas="", bytes="", hash_sha256="", estado="error", detalle=str(e))
        print(f"[ERROR] {destino.name}: {e}")
        resultado = False
    escribir_log(registro)
    return resultado


def ruta_mensual(anio, mes):
    url = URL_MES.format(anio=anio, mes=mes)
    destino = (DATA_RAW / "yellow" / f"year={anio}" / f"month={mes}"
               / f"yellow_tripdata_{anio}-{mes}.parquet")
    return url, destino


def main():
    parser = argparse.ArgumentParser(description="Ingesta de taxis amarillos de NYC")
    parser.add_argument("--mes", required=True, help="Formato AAAA-MM, ej: 2025-03")
    args = parser.parse_args()
    try:
        fecha = datetime.strptime(args.mes, "%Y-%m")
    except ValueError:
        parser.error("--mes debe tener el formato AAAA-MM, por ejemplo 2025-03")

    mes = f"{fecha.month:02d}"
    pedidos = [
        ruta_mensual(fecha.year, mes),          # el mes asignado
        ruta_mensual(fecha.year - 1, mes),      # el mismo mes del año anterior
        (URL_ZONAS, DATA_RAW / "zones" / "taxi_zone_lookup.csv"),
    ]
    resultados = [ingestar(url, destino) for url, destino in pedidos]
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()