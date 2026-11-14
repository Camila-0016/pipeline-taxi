"""Orquestación con Dagster: el pipeline como un grafo de activos (assets)

Cada activo es un paso del pipeline. Dagster los ejecuta en orden de dependencia
y permite elegir el mes: el parámetro `mes` se le pasa al primer activo

Los modelos de dbt se invocan por línea de comandos (el paquete dagster-dbt no
soporta todavía Python 3.14 ni dbt-core 1.13)
"""
import subprocess
import sys
from pathlib import Path

from dagster import AssetExecutionContext, Config, Definitions, asset

RAIZ = Path(__file__).resolve().parent.parent
DBT_DIR = RAIZ / "dbt"
DBT = Path(sys.executable).parent / "dbt"  # el dbt instalado en el mismo entorno


class ConfigMes(Config):
    """Parámetro de la corrida: mes asignado (el de comparación se deduce)."""
    mes: str = "2025-03"


def ejecutar(context, comando, cwd=RAIZ):
    """Corre un comando y falla el activo si el comando falla."""
    context.log.info("Ejecutando: " + " ".join(comando))
    subprocess.run(comando, cwd=cwd, check=True)


def dbt(context, *argumentos):
    ejecutar(context, [str(DBT), *argumentos, "--profiles-dir", "."], cwd=DBT_DIR)


@asset(description="Ingesta, esquema, calidad y carga a Postgres (esquema raw) del mes y su comparación.")
def viajes_en_postgres(context: AssetExecutionContext, config: ConfigMes):
    for script in ("ingesta", "esquema", "calidad", "curada"):
        ejecutar(context, [sys.executable, f"src/{script}.py", "--mes", config.mes])
    ejecutar(context, ["docker", "compose", "up", "-d", "--wait"])  # Postgres recién acá, para ahorrar RAM
    ejecutar(context, [sys.executable, "src/cargar_postgres.py", "--mes", config.mes])


# Los modelos de dbt se encadenan (no corren en paralelo) para no competir por
# memoria en una notebook de 8 GB y para que dos corridas de dbt no recreen
# la misma vista a la vez.
@asset(deps=[viajes_en_postgres], description="Modelo dbt dim_zone (más su staging).")
def dim_zone(context: AssetExecutionContext):
    dbt(context, "run", "--select", "+dim_zone")


@asset(deps=[dim_zone], description="Modelo dbt dim_date (más su staging).")
def dim_date(context: AssetExecutionContext):
    dbt(context, "run", "--select", "+dim_date")


@asset(deps=[dim_date], description="Modelo dbt fact_trips (staging, intermediate y la tabla de hechos).")
def fact_trips(context: AssetExecutionContext):
    dbt(context, "run", "--select", "+fact_trips")


@asset(deps=[fact_trips], description="Modelo dbt agg_zone_hour: viajes, ingreso y duración por zona, fecha y hora.")
def agg_zone_hour(context: AssetExecutionContext):
    dbt(context, "run", "--select", "agg_zone_hour")


@asset(deps=[agg_zone_hour], description="Tests de dbt sobre el modelo estrella.")
def pruebas_dbt(context: AssetExecutionContext):
    dbt(context, "test")


@asset(deps=[pruebas_dbt], description="Las 6 preguntas de negocio y RESULTADOS.md.")
def resultados_md(context: AssetExecutionContext, config: ConfigMes):
    ejecutar(context, [sys.executable, "src/preguntas.py", "--mes", config.mes])


defs = Definitions(assets=[viajes_en_postgres, dim_zone, dim_date, fact_trips,
                           agg_zone_hour, pruebas_dbt, resultados_md])
