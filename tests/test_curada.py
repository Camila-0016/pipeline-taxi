"""Tests de la Parte 4: capa curada particionada; reprocesar un mes reemplaza solo su partición."""
import os
from datetime import datetime

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import curada


def viaje(subida, bajada, **cambios):
    base = {"vendor_id": 1, "tpep_pickup_datetime": subida, "tpep_dropoff_datetime": bajada,
            "trip_distance": 3.0, "fare_amount": 20.0, "tip_amount": 5.0,
            "pu_location_id": 1, "do_location_id": 2, "archivo_origen": "x.parquet", "flags": None}
    base.update(cambios)
    return base


@pytest.fixture
def entorno(tmp_path):
    filas = [
        viaje(datetime(2024, 3, 4, 8, 0), datetime(2024, 3, 4, 8, 30)),
        viaje(datetime(2024, 3, 5, 9, 0), datetime(2024, 3, 5, 9, 15)),
        viaje(datetime(2025, 3, 3, 10, 0), datetime(2025, 3, 3, 10, 30)),            # lunes
        viaje(datetime(2025, 3, 4, 11, 0), datetime(2025, 3, 4, 11, 20), fare_amount=0.0),
        viaje(datetime(2025, 3, 5, 12, 0), datetime(2025, 3, 5, 12, 10)),
    ]
    aceptadas = tmp_path / "aceptadas.parquet"
    pq.write_table(pa.Table.from_pylist(filas), aceptadas)
    zonas = tmp_path / "zonas.csv"
    zonas.write_text("LocationID,Borough,Zone,service_zone\n1,Manhattan,Midtown,Yellow Zone\n2,Queens,JFK Airport,Airports\n")
    return aceptadas, zonas, tmp_path / "curada"


def test_escribe_particiones_estilo_hive_con_columnas_derivadas(entorno):
    aceptadas, zonas, raiz = entorno
    con = duckdb.connect()
    assert curada.escribir_particion(con, aceptadas, zonas, 2024, 3, raiz) == 2
    assert curada.escribir_particion(con, aceptadas, zonas, 2025, 3, raiz) == 3

    assert (raiz / "year=2024" / "month=03" / "part-0.parquet").exists()
    assert (raiz / "year=2025" / "month=03" / "part-0.parquet").exists()

    fila = con.execute(
        f"SELECT dia_semana, duracion_min, velocidad_mph, propina_pct, distrito_origen, zona_destino "
        f"FROM read_parquet('{raiz}/year=2025/month=03/part-0.parquet') "
        f"WHERE tpep_pickup_datetime = TIMESTAMP '2025-03-03 10:00:00'").fetchone()
    assert fila == (1, 30.0, 6.0, 25.0, "Manhattan", "JFK Airport")

    sin_tarifa = con.execute(
        f"SELECT propina_pct FROM read_parquet('{raiz}/year=2025/month=03/part-0.parquet') "
        f"WHERE fare_amount = 0").fetchone()[0]
    assert sin_tarifa is None            # sin tarifa no hay porcentaje de propina


def test_reprocesar_un_mes_reemplaza_solo_su_particion(entorno):
    aceptadas, zonas, raiz = entorno
    con = duckdb.connect()
    curada.escribir_particion(con, aceptadas, zonas, 2024, 3, raiz)
    curada.escribir_particion(con, aceptadas, zonas, 2025, 3, raiz)

    otra = raiz / "year=2024" / "month=03" / "part-0.parquet"
    propia = raiz / "year=2025" / "month=03" / "part-0.parquet"
    otra_antes = otra.stat().st_mtime_ns
    propia_antes = propia.stat().st_mtime_ns
    antes = curada.contar_particiones(con, raiz)

    os.utime(propia, ns=(propia_antes - 10**9, propia_antes - 10**9))  # que se note el reemplazo
    propia_vieja = propia.stat().st_mtime_ns
    curada.escribir_particion(con, aceptadas, zonas, 2025, 3, raiz)

    assert otra.stat().st_mtime_ns == otra_antes            # la otra partición no se tocó
    assert propia.stat().st_mtime_ns > propia_vieja         # la propia se reescribió
    assert [(n, f) for n, f, _ in curada.contar_particiones(con, raiz)] == [(n, f) for n, f, _ in antes]
    assert not [p for p in raiz.iterdir() if p.name.startswith(".")]   # sin carpetas temporales


def test_si_el_conteo_no_coincide_no_se_toca_la_particion_vigente(entorno, monkeypatch):
    aceptadas, zonas, raiz = entorno
    con = duckdb.connect()
    curada.escribir_particion(con, aceptadas, zonas, 2025, 3, raiz)
    propia = raiz / "year=2025" / "month=03" / "part-0.parquet"
    contenido = propia.read_bytes()

    original = curada.sql_curado
    monkeypatch.setattr(curada, "sql_curado",
                        lambda *a, **k: original(*a, **k) + " LIMIT 1")   # simula pérdida de filas
    with pytest.raises(RuntimeError):
        curada.escribir_particion(con, aceptadas, zonas, 2025, 3, raiz)
    assert propia.read_bytes() == contenido                 # la partición vigente quedó intacta
