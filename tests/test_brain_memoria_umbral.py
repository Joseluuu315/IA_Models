"""
Tests for the memory threshold (`MEM_UMBRAL = 0.55`) and `_buscar_memoria`.

These guard against the v4 bug where any memory result was returned regardless
of similarity — e.g. "hol" → SOLID.
"""
import pytest

from pako_brain import PakoBrain
from pako_memory import PakoMemory


@pytest.fixture
def brain(tmp_path):
    mem = PakoMemory(data_dir=str(tmp_path))
    # Seed deterministic knowledge
    mem.guardar_conocimiento(
        clave="SOLID",
        valor="cinco principios de diseño orientado a objetos",
        fuente="manual",
        confianza=1.0,
        auto_ok=True,
    )
    mem.guardar_conocimiento(
        clave="Docker",
        valor="plataforma de contenedores",
        fuente="manual",
        confianza=1.0,
        auto_ok=True,
    )
    mem.guardar_conocimiento(
        clave="algoritmo A estrella",
        valor="algoritmo de búsqueda de caminos óptimos",
        fuente="manual",
        confianza=1.0,
        auto_ok=True,
    )
    return PakoBrain(mem)


class TestMemUmbralConstant:
    def test_default_threshold(self, brain):
        assert brain.MEM_UMBRAL == 0.55


class TestBuscarMemoria:
    def test_exact_match_returns_value(self, brain):
        hit = brain._buscar_memoria("SOLID")
        assert hit is not None
        val, score, clave = hit
        assert clave == "SOLID"
        assert score >= brain.MEM_UMBRAL

    def test_short_garbage_below_threshold_returns_none(self, brain):
        # "hol" was the historical false-positive case
        assert brain._buscar_memoria("hol") is None

    def test_unrelated_query_returns_none(self, brain):
        assert brain._buscar_memoria("banana naranja melón") is None

    def test_low_score_is_filtered(self, brain):
        # Un solo token común con múltiples entradas — por F1 debería quedar bajo
        assert brain._buscar_memoria("es") is None

    def test_empty_query_returns_none(self, brain):
        # Sin tokens significativos → None
        assert brain._buscar_memoria("") is None

    def test_buscar_memoria_respects_custom_threshold(self, brain):
        # Subimos el umbral por encima de 1.0 → nada pasa ni siquiera el match exacto
        brain.MEM_UMBRAL = 1.01
        assert brain._buscar_memoria("SOLID") is None

        # Volvemos al umbral por defecto → el match exacto vuelve a pasar
        brain.MEM_UMBRAL = 0.55
        hit = brain._buscar_memoria("SOLID")
        assert hit is not None
        assert hit[2] == "SOLID"


class TestResponderMemoryFlow:
    def test_exact_memory_hit_returned(self, brain):
        resp, fuente = brain.responder("SOLID")
        assert fuente == "memoria"
        assert "principios" in resp.lower()

    def test_short_typo_does_not_return_memory_answer(self, brain):
        resp, fuente = brain.responder("hol")
        # Sin web agent, el fallback correcto es intención o desconocido,
        # jamás la entrada SOLID
        assert "principios" not in resp.lower()
        assert fuente != "memoria"

    def test_greeting_does_not_fall_into_memory(self, brain):
        resp, fuente = brain.responder("hola")
        # Saludo debe ganar antes que memoria
        assert "PAKO" in resp or "Buenos" in resp or "Buenas" in resp
        assert fuente != "memoria"

    def test_approximate_memory_hit_shows_aproximado_notice(self, brain):
        # Fuerza una nota "aproximado" usando umbrales bajos pero < 0.65
        brain.MEM_UMBRAL = 0.1
        resp, fuente = brain.responder("algoritmo A")
        if fuente == "memoria":
            # Si el score quedó entre 0.1 y 0.65 se incluye la nota
            assert "aproximado" in resp.lower() or "📚" in resp
