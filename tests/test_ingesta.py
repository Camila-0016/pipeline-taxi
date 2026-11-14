"""Tests de la Parte 1: la ingesta es idempotente."""
import http.server
import io
import threading

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import ingesta


@pytest.fixture
def servidor():
    """Servidor web local que entrega un Parquet chico y cuenta cuántas descargas recibe."""
    buffer = io.BytesIO()
    pq.write_table(pa.table({"a": [1, 2, 3]}), buffer)
    contenido = buffer.getvalue()
    peticiones = []

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            peticiones.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(len(contenido)))
            self.end_headers()
            self.wfile.write(contenido)

        def log_message(self, *args):
            pass  # sin ruido en la salida de los tests

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}/archivo.parquet", peticiones
    servidor.shutdown()


def test_ingesta_es_idempotente(tmp_path, monkeypatch, servidor):
    url, peticiones = servidor
    monkeypatch.setattr(ingesta, "LOG_PATH", tmp_path / "ingestion_log.csv")
    destino = tmp_path / "raw" / "archivo.parquet"

    assert ingesta.ingestar(url, destino) is True
    hash_primera_vez = ingesta.calcular_hash(destino)
    assert ingesta.ingestar(url, destino) is True

    assert len(peticiones) == 1                              # no volvió a descargar
    assert ingesta.calcular_hash(destino) == hash_primera_vez  # el archivo no cambió
    assert len(ingesta.leer_log()) == 1                      # ni agregó otra fila al log


def test_ingesta_vuelve_a_descargar_si_el_archivo_cambio(tmp_path, monkeypatch, servidor):
    url, peticiones = servidor
    monkeypatch.setattr(ingesta, "LOG_PATH", tmp_path / "ingestion_log.csv")
    destino = tmp_path / "raw" / "archivo.parquet"

    ingesta.ingestar(url, destino)
    hash_original = ingesta.calcular_hash(destino)
    with open(destino, "ab") as f:      # simulamos un archivo corrupto
        f.write(b"basura")
    ingesta.ingestar(url, destino)

    assert len(peticiones) == 2                             # el hash no coincidía: bajó de nuevo
    assert ingesta.calcular_hash(destino) == hash_original  # y quedó el archivo bueno
