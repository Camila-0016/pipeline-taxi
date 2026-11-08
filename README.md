# Pipeline NYC Taxi

Pipeline batch reproducible que descarga, valida, limpia y modela los viajes de
taxis amarillos de Nueva York (TLC) para un mes y su mes de comparación del año anterior.

## Cómo instalar y ejecutar

Probado en Ubuntu 26.04 (WSL 2), Python 3.14.

```bash
git clone [URL del repositorio]
cd pipeline-taxi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ejecución por etapas (el comando único `make all MES=2025-03` se agrega al final):

```bash
python src/ingesta.py --mes 2025-03
python src/esquema.py --mes 2025-03
```

## Arquitectura

[Completar al final]

Estructura de datos (todo dentro de `data/`, que no se versiona):

- `data/raw/`: archivos originales tal como los publica la TLC, sin modificar.
- `data/control/ingestion_log.csv`: registro de cada descarga.
- `data/staging/`: tabla unificada de los dos meses.
- `data/reports/`: reportes de cada etapa.

## Decisiones

### Parte 1: Ingesta

- **Idempotencia con hash SHA-256.** Un archivo no se vuelve a descargar si ya existe
  y su hash coincide con el de una descarga registrada como `ok`. Si el archivo cambia
  o se corrompe, el hash no coincide y se descarga de nuevo.
- **Descarga atómica.** Se baja a un archivo `.part` y recién al terminar se renombra,
  para no dejar nunca un archivo a medias que parezca válido.
- **Reintentos.** Hasta 3 intentos con espera creciente (2 s y 4 s). Si sigue fallando se
  registra el error en el log y el programa termina con código de salida 1.
- **Registro de control.** `ingestion_log.csv` guarda archivo, URL, filas, bytes, hash,
  fecha y hora, estado y detalle del error.

### Parte 2: Esquema

- **Contrato en un archivo versionado** (`contracts/yellow_schema.yaml`), no en el código.
  Define nombre de origen, nombre destino (snake_case), tipo y si la columna es requerida.
- **`cbd_congestion_fee` en 2024 vale NULL, no 0.** Ese cargo no existía en 2024, así que
  NULL (no aplica) es más fiel que 0 (se cobró cero). Además evita confundir viajes de
  2024 con viajes de 2025 que pagaron 0 al calcular porcentajes.
- **Columna nueva que no está en el contrato:** no hace fallar el pipeline, pero no se
  carga en silencio: queda en el reporte de esquema y se ignora hasta que se agregue al contrato.
- **Columna requerida faltante:** el pipeline falla.
- **Tipo distinto al del contrato:** se reporta y se convierte al tipo del contrato; si la
  conversión no es posible, falla con un error claro.
- **Unificación:** se agrega la columna `archivo_origen`. El pipeline verifica que las filas
  unificadas sean igual a la suma de las filas de los archivos de origen
  (marzo 2025 + marzo 2024: 4.145.257 + 3.582.628 = 7.727.885).

## Limitaciones conocidas

- Ante un error HTTP 403 o 404 (archivo inexistente) se reintenta igual, aunque no se
  resuelva reintentando. Se podría limitar el reintento a errores de red o del servidor.
