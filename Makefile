# Pipeline NYC Taxi. Uso: make all MES=2025-03
# (MES es el mes asignado; la ingesta y las preguntas usan tambien el mismo mes del año anterior)
.RECIPEPREFIX = >
SHELL := /bin/bash
MES ?= 2025-03
PYTHON ?= python

.PHONY: all up ingesta esquema calidad carga dbt preguntas test down

all: ingesta esquema calidad up carga dbt preguntas

# 0. Levanta Postgres en Docker y espera a que este healthy
up:
> docker compose up -d --wait

# 1. Descarga los parquet del mes y del mismo mes del año anterior, mas la tabla de zonas
ingesta:
> $(PYTHON) src/ingesta.py --mes $(MES)

# 2. Valida el esquema contra contracts/yellow_schema.yaml y unifica ambos meses
esquema:
> $(PYTHON) src/esquema.py --mes $(MES)

# 3. Reglas de calidad: separa aceptadas y cuarentena, y genera el reporte
calidad:
> $(PYTHON) src/calidad.py --mes $(MES)

# 4. Carga aceptadas, cuarentena y zonas a Postgres (esquema raw), reemplazando solo este mes
carga:
> $(PYTHON) src/cargar_postgres.py --mes $(MES)

# 5. Modelo con dbt: staging, intermediate, marts (estrella) y tests
dbt:
> cd dbt && dbt run --profiles-dir . && dbt test --profiles-dir .

# 6. Responde las 6 preguntas de negocio y genera RESULTADOS.md
preguntas:
> $(PYTHON) src/preguntas.py --mes $(MES)

test:
> $(PYTHON) -m pytest

down:
> docker compose down

# Alternativa a "make all": el mismo pipeline orquestado por Dagster (grafo de activos)
.PHONY: dagster
dagster:
> dagster asset materialize -f src/orquestacion.py --select "*" --config-json '{"ops": {"viajes_en_postgres": {"config": {"mes": "$(MES)"}}, "resultados_md": {"config": {"mes": "$(MES)"}}}}'
