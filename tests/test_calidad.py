"""Tests de la Parte 3: reglas de calidad, cuarentena y reconciliación de conteos."""
from datetime import datetime

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

import calidad
from esquema import cargar_contrato

ARCHIVO = "yellow_tripdata_2025-03.parquet"


def fila(**cambios):
    """Un viaje válido de marzo de 2025. Cada test cambia solo lo que quiere probar."""
    base = {
        "vendor_id": 1,
        "tpep_pickup_datetime": datetime(2025, 3, 10, 10, 0, 0),
        "tpep_dropoff_datetime": datetime(2025, 3, 10, 10, 20, 0),
        "passenger_count": 1, "trip_distance": 3.0, "ratecode_id": 1,
        "store_and_fwd_flag": "N", "pu_location_id": 10, "do_location_id": 20,
        "payment_type": 1, "fare_amount": 15.0, "extra": 0.5, "mta_tax": 0.5,
        "tip_amount": 3.0, "tolls_amount": 0.0, "improvement_surcharge": 1.0,
        "total_amount": 21.0, "congestion_surcharge": 2.5, "airport_fee": 0.0,
        "cbd_congestion_fee": 0.75, "archivo_origen": ARCHIVO,
    }
    base.update(cambios)
    return base


def leer(ruta):
    """Lee un Parquet y lo devuelve como lista de diccionarios."""
    rel = duckdb.sql(f"SELECT * FROM read_parquet('{ruta}')")
    return [dict(zip(rel.columns, f)) for f in rel.fetchall()]


def ejecutar_calidad(tmp_path, filas):
    """Corre la evaluación de calidad sobre filas sintéticas.

    Devuelve (aceptadas, cuarentena, reporte).
    """
    entrada = tmp_path / "entrada.parquet"
    zonas = tmp_path / "zonas.csv"
    pq.write_table(pa.Table.from_pylist(filas), entrada)
    zonas.write_text("LocationID,Borough,Zone,service_zone\n"
                     + "".join(f"{i},B,Z{i},S\n" for i in range(1, 266)))

    columnas = [c["destino"] for c in cargar_contrato()] + ["archivo_origen"]
    reglas = calidad.cargar_reglas()
    con = duckdb.connect()
    evaluado = tmp_path / "evaluado.parquet"
    aceptadas = tmp_path / "aceptadas.parquet"
    cuarentena = tmp_path / "cuarentena.parquet"

    calidad.copiar_a_parquet(
        con, calidad.sql_evaluado(entrada, zonas, columnas, reglas), evaluado)
    calidad.separar(con, evaluado, columnas, reglas, aceptadas, cuarentena)
    reporte = calidad.armar_reporte(con, evaluado, reglas)
    return leer(aceptadas), leer(cuarentena), reporte


def test_regla_de_rechazo_manda_la_fila_a_cuarentena(tmp_path):
    # R02: la bajada es igual a la subida
    filas = [fila(), fila(tpep_dropoff_datetime=datetime(2025, 3, 10, 10, 0, 0))]
    aceptadas, cuarentena, _ = ejecutar_calidad(tmp_path, filas)
    assert len(aceptadas) == 1
    assert len(cuarentena) == 1
    assert cuarentena[0]["reglas_violadas"] == "R02"


def test_advertencia_conserva_la_fila_y_la_marca(tmp_path):
    # R03: distancia 0 es solo una advertencia
    filas = [fila(), fila(trip_distance=0.0)]
    aceptadas, cuarentena, _ = ejecutar_calidad(tmp_path, filas)
    assert cuarentena == []
    assert len(aceptadas) == 2
    marcadas = [f for f in aceptadas if f["flags"]]
    assert len(marcadas) == 1
    assert marcadas[0]["flags"] == "R03"


def test_pasajeros_nulos_no_se_rechazan(tmp_path):
    # R06: los viajes de tipo de pago 0 vienen sin pasajeros ni código de tarifa
    filas = [fila(), fila(passenger_count=None, ratecode_id=None, payment_type=0)]
    aceptadas, cuarentena, _ = ejecutar_calidad(tmp_path, filas)
    assert cuarentena == []
    assert sorted(str(f["flags"]) for f in aceptadas) == ["None", "R06"]


def test_duplicado_exacto_se_rechaza_y_se_conserva_la_primera_copia(tmp_path):
    # R08: dos filas idénticas; una se queda y la otra va a cuarentena
    filas = [fila(), fila(pu_location_id=11), fila(pu_location_id=11)]
    aceptadas, cuarentena, _ = ejecutar_calidad(tmp_path, filas)
    assert len(aceptadas) == 2
    assert len(cuarentena) == 1
    assert cuarentena[0]["reglas_violadas"] == "R08"


def test_fila_que_viola_dos_reglas_lista_ambas(tmp_path):
    # R02 (bajada anterior a la subida) y R04 (distancia enorme)
    filas = [fila(), fila(trip_distance=150.0,
                          tpep_dropoff_datetime=datetime(2025, 3, 10, 9, 0, 0))]
    _, cuarentena, _ = ejecutar_calidad(tmp_path, filas)
    assert cuarentena[0]["reglas_violadas"] == "R02,R04"


def test_reconciliacion_de_conteos_del_reporte(tmp_path):
    # leídas = aceptadas + cuarentena, tanto en el reporte como en los archivos
    filas = [fila(), fila(trip_distance=0.0), fila(total_amount=-5.0),
             fila(pu_location_id=999), fila(pu_location_id=12), fila(pu_location_id=12)]
    aceptadas, cuarentena, reporte = ejecutar_calidad(tmp_path, filas)
    assert reporte[ARCHIVO]["leidas"] == len(filas)
    assert calidad.reconciliar(reporte, len(filas), len(aceptadas), len(cuarentena)) == []


def test_reconciliacion_detecta_filas_perdidas():
    reporte = {ARCHIVO: {"leidas": 10, "aceptadas": 7, "cuarentena": 2, "por_regla": {}}}
    errores = calidad.reconciliar(reporte, 10, 7, 2)
    assert errores != []
