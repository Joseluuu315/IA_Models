"""
Tests for PakoBrain.detectar_intencion. Uses an in-memory PakoMemory backed
by a temp data directory.
"""
import pytest

from pako_brain import INTENCIONES, PakoBrain
from pako_memory import PakoMemory


@pytest.fixture
def brain(tmp_path):
    mem = PakoMemory(data_dir=str(tmp_path))
    return PakoBrain(mem)


class TestDetectarIntencion:
    def test_saludo(self, brain):
        intent, conf = brain.detectar_intencion("hola")
        assert intent == "saludo"
        assert conf >= 0.25

    def test_tiempo(self, brain):
        intent, conf = brain.detectar_intencion("¿qué hora es?")
        assert intent == "tiempo"
        assert conf >= 0.45

    def test_ayuda(self, brain):
        intent, conf = brain.detectar_intencion("¿qué puedes hacer?")
        assert intent == "ayuda"
        assert conf >= 0.30

    def test_identidad(self, brain):
        intent, conf = brain.detectar_intencion("¿quién eres?")
        assert intent == "identidad"

    def test_buscar_web(self, brain):
        intent, conf = brain.detectar_intencion("busca qué es Docker")
        # Cualquiera de los dos es válido — busca o buscar_web deben prevalecer
        assert intent == "buscar_web"

    def test_despedida(self, brain):
        intent, _ = brain.detectar_intencion("adios")
        assert intent == "despedida"

    def test_substring_boost_returns_high_confidence(self, brain):
        # "hola" is a long-enough substring → confidence clamped up
        _, conf = brain.detectar_intencion("hola, ¿qué tal?")
        assert conf >= 0.90

    def test_unknown_returns_desconocido_or_low(self, brain):
        intent, conf = brain.detectar_intencion("xyzqqq zzz plpl")
        # O bien "desconocido" o bien un intent con confianza muy baja
        assert intent == "desconocido" or conf < 0.2


class TestIntencionesCatalog:
    def test_every_intencion_has_patrones_and_respuestas(self):
        for name, data in INTENCIONES.items():
            assert "patrones" in data, name
            assert "respuestas" in data, name

    def test_desconocido_has_fallback_responses(self):
        assert INTENCIONES["desconocido"]["respuestas"]
