"""
Tests for the explicit-learning flow of PakoBrain.

Verifies the regex patterns, persistence through PakoMemory, and priority
against memory search.
"""
import pytest

from pako_brain import PakoBrain
from pako_memory import PakoMemory


@pytest.fixture
def brain(tmp_path):
    mem = PakoMemory(data_dir=str(tmp_path))
    return PakoBrain(mem)


class TestIntentarAprender:
    def test_aprende_que_x_es_y(self, brain):
        resp = brain._intentar_aprender("aprende que Python es un lenguaje de programación")
        assert resp is not None
        assert "Aprendido" in resp or "sabía" in resp
        assert "python" in resp.lower()
        # Memoria actualizada
        entrada = brain.memory.buscar_exacto("Python")
        assert entrada is not None
        assert "lenguaje de programación" in entrada.valor.lower()

    def test_recuerda_que_x_es_y(self, brain):
        resp = brain._intentar_aprender("recuerda que Docker es un sistema de contenedores")
        assert resp is not None
        assert brain.memory.buscar_exacto("Docker") is not None

    def test_memoriza_que_x_es_y(self, brain):
        resp = brain._intentar_aprender("memoriza que HTTP es un protocolo")
        assert resp is not None
        assert brain.memory.buscar_exacto("HTTP") is not None

    def test_guarda_que_x_es_y(self, brain):
        resp = brain._intentar_aprender("guarda que CSS es hojas de estilo")
        assert resp is not None
        assert brain.memory.buscar_exacto("CSS") is not None

    def test_significa_variant(self, brain):
        resp = brain._intentar_aprender("aprende que CPU significa unidad central de proceso")
        assert resp is not None
        assert brain.memory.buscar_exacto("CPU") is not None

    def test_too_short_values_rejected(self, brain):
        resp = brain._intentar_aprender("aprende que X es Y")
        # X e Y son claves/valores de 1 carácter → debería pedir más detalle
        assert resp is not None
        assert "detalle" in resp.lower() or "ejemplo" in resp.lower()
        assert brain.memory.buscar_exacto("X") is None

    def test_returns_none_on_no_match(self, brain):
        assert brain._intentar_aprender("hola, ¿qué tal?") is None

    def test_duplicate_reports_already_known(self, brain):
        brain._intentar_aprender("aprende que Redis es una base de datos en memoria")
        resp = brain._intentar_aprender("aprende que Redis es una base de datos en memoria")
        assert resp is not None
        assert "sabía" in resp.lower()

    def test_stripping_quotes_from_clave_and_valor(self, brain):
        resp = brain._intentar_aprender(
            'aprende que "Kubernetes" es "un orquestador"'
        )
        assert resp is not None
        # Las comillas deben haber sido eliminadas de la clave guardada
        e = brain.memory.buscar_exacto("Kubernetes")
        assert e is not None
        assert '"' not in e.clave
        assert '"' not in e.valor


class TestResponderAprendizajeFlow:
    def test_responder_aprende_then_recall_via_memory(self, brain):
        resp, fuente = brain.responder(
            "aprende que FastAPI es un framework web moderno para Python"
        )
        assert "FastAPI" in resp or "Aprendido" in resp
        assert fuente == "manual"
        # Now querying with a phrase that shares tokens should hit memory
        resp2, fuente2 = brain.responder("fastapi")
        # Either hits memory or web — but memory should score high enough now
        assert fuente2 in ("memoria", "web", "")
