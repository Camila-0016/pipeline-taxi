"""Etapa 5: ejecuta sql/preguntas/*.sql sobre el modelo y genera RESULTADOS.md
(resultado, consulta e interpretacion de cada pregunta)"""
import argparse
import sys
from pathlib import Path

import psycopg2
import yaml

RAIZ = Path(__file__).resolve().parent.parent
SQL_DIR = RAIZ / "sql" / "preguntas"
INTERPRETACIONES = SQL_DIR / "interpretaciones.yaml"
DESTINO = RAIZ / "RESULTADOS.md"


def mes_comparacion(mes):
    """Mismo mes del año anterior: 2025-03 -> 2024-03."""
    anio, m = mes.split("-")
    return f"{int(anio) - 1}-{m}"


def tabla_markdown(columnas, filas):
    lineas = ["| " + " | ".join(columnas) + " |",
              "|" + "|".join(["---"] * len(columnas)) + "|"]
    for fila in filas:
        lineas.append("| " + " | ".join("" if v is None else str(v) for v in fila) + " |")
    return "\n".join(lineas)


def sql_legible(texto, params):
    """Reemplaza los parametros por el mes real para mostrar la consulta lista para correr."""
    return (texto.replace("%(mes)s", f"'{params['mes']}'")
                 .replace("%(mes_comp)s", f"'{params['mes_comp']}'")
                 .replace("%%", "%"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", required=True, help="AAAA-MM")
    mes = ap.parse_args().mes
    params = {"mes": mes, "mes_comp": mes_comparacion(mes)}
    interpretaciones = yaml.safe_load(INTERPRETACIONES.read_text(encoding="utf-8")) or {}

    con = psycopg2.connect(host="localhost", port=5432, dbname="taxi",
                           user="taxi", password="taxi")
    salida = [f"# Resultados: {mes} vs {params['mes_comp']}\n",
              "Generado por `src/preguntas.py`. Los resultados salen de las filas aceptadas "
              "(las de cuarentena no se cuentan). Cada consulta esta en `sql/preguntas/`.\n"]
    for archivo in sorted(SQL_DIR.glob("*.sql")):
        texto = archivo.read_text(encoding="utf-8")
        titulo = texto.splitlines()[0].lstrip("- ").strip()
        with con.cursor() as cur:
            cur.execute(texto, params)
            columnas = [d[0] for d in cur.description]
            filas = cur.fetchall()
        interp = interpretaciones.get(archivo.stem, "(pendiente)").strip()
        salida += [f"## {titulo}\n",
                   tabla_markdown(columnas, filas) + "\n",
                   f"**Interpretacion:** {interp}\n",
                   f"Consulta (`sql/preguntas/{archivo.name}`):\n",
                   "```sql\n" + sql_legible(texto, params).strip() + "\n```\n"]
        print(f"OK {archivo.name}: {len(filas)} filas")

    DESTINO.write_text("\n".join(salida), encoding="utf-8")
    print(f"Resultados guardados en {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())