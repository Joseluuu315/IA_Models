"""
Tests for the command/intent priority flow of PakoBrain.responder.

Covers the bugs that the v5.0 refactor explicitly fixed:
  1. Comandos de sistema antes que intenciones
  2. Aprendizaje explícito antes que memoria
  3. Intenciones de alta confianza antes que memoria
  4. "busca X" dispara web, no memoria basura
  5. Memoria solo si supera MEM_UMBRAL
  6. Fallback cuando todo falla
"""
import pytest

from pako_brain import PakoBrain
from pako_memory import PakoMemory


@pytest.fixture
def brain(tmp_path):
    mem = PakoMemory(data_dir=str(tmp_path))
    # Seed memory with the same entries that used to trigger false positives
    mem.guardar_conocimiento(
        clave="SOLID",
        valor="cinco principios de diseño orientado a objetos",
        fuente="manual", confianza=1.0, auto_ok=True,
    )
    mem.guardar_conocimiento(
        clave="A*",
        valor="algoritmo de búsqueda de caminos",
        fuente="manual", confianza=1.0, auto_ok=True,
    )
    mem.guardar_conocimiento(
        clave="Docker",
        valor="plataforma de contenedores Linux",
        fuente="manual", confianza=1.0, auto_ok=True,
    )
    return PakoBrain(mem)


class TestComandosDeSistemaPrimero:
    def test_nombre_usuario(self, brain):
        resp, fuente = brain.responder("mi nombre es Carlos")
        assert fuente == "sistema"
        assert "Carlos" in resp
        assert brain.memory.get_config("nombre_usuario") == "Carlos"

    def test_stats_command(self, brain):
        resp, fuente = brain.responder("estadísticas")
        assert fuente == "sistema"
        assert "PAKO" in resp
        assert "Conocimiento" in resp

    def test_limpiar_historial(self, brain):
        brain.memory.agregar_mensaje("user", "hola", "")
        brain.memory.agregar_mensaje("pako", "hola!", "")
        assert len(brain.memory.historial_conversacion) >= 2

        resp, fuente = brain.responder("limpia el historial")
        assert fuente == "sistema"
        assert "Historial" in resp or "empezamos" in resp.lower()
        # Historial limpio excepto por el mensaje de la respuesta
        # (agregar_mensaje se llama después de limpiar)
        assert len(brain.memory.historial_conversacion) <= 1

    def test_comando_gana_a_aprendizaje(self, brain):
        # Aunque la frase comience por "aprende de", el patrón de repo gana
        resp, fuente = brain.responder("aprende de mis repos")
        # Sin github_agent conectado → mensaje de sistema, no aprendizaje
        assert fuente == "sistema"


class TestAprendizajeExplicitoAntesDeMemoria:
    def test_aprendizaje_no_cae_en_memoria(self, brain):
        # "aprende que X es Y" con X=SOLID (ya en memoria) debe actualizar, no leer
        resp, fuente = brain.responder(
            "aprende que SOLID es cinco principios de diseño"
        )
        assert fuente == "manual"
        assert "aprendido" in resp.lower() or "sabía" in resp.lower()


class TestIntencionesAltaConfianzaAntesDeMemoria:
    def test_hola_saludo_no_tiempo(self, brain):
        resp, _ = brain.responder("hola")
        # Bug v4: "hola" → devolvía hora. v5: debe devolver saludo con "PAKO"
        assert "PAKO" in resp
        assert "Son las" not in resp

    def test_que_puedes_hacer_no_cae_en_solid(self, brain):
        resp, fuente = brain.responder("¿qué puedes hacer?")
        # Bug v4: devolvía SOLID desde memoria
        assert "SOLID" not in resp
        assert "Calcular" in resp or "Analizar" in resp or "Generar" in resp

    def test_hora_intent(self, brain):
        resp, _ = brain.responder("¿qué hora es?")
        assert "Son las" in resp or "🕒" in resp

    def test_gracias(self, brain):
        resp, _ = brain.responder("muchas gracias")
        assert "nada" in resp.lower() or "gusto" in resp.lower()

    def test_identidad(self, brain):
        resp, _ = brain.responder("¿quién eres?")
        assert "PAKO" in resp

    def test_despedida(self, brain):
        resp, _ = brain.responder("adios")
        # Mensajes definidos en INTENCIONES["despedida"]
        assert "luego" in resp.lower() or "cuídate" in resp.lower()

    def test_broma(self, brain):
        resp, _ = brain.responder("cuéntame un chiste")
        # Cualquiera de las bromas definidas → contienen emoji o signo
        assert len(resp) > 10

    def test_curiosidad(self, brain):
        resp, _ = brain.responder("dato curioso")
        assert len(resp) > 20

    def test_estado_animo(self, brain):
        resp, _ = brain.responder("¿cómo estás?")
        assert len(resp) > 10


class TestBusquedaWebExplicita:
    def test_busca_docker_no_devuelve_memoria_irrelevante(self, brain):
        # Sin web_agent el brain no puede completar la búsqueda web,
        # pero la memoria sólo se usa si el score ≥ 0.70.
        # "busca Docker" → la clave "Docker" SÍ tiene score alto, está OK devolverla
        resp, fuente = brain.responder("busca Docker")
        # Debe ser memoria (alta confianza) o caer al final
        assert fuente in ("memoria", "web", "")

    def test_busca_a_estrella_no_devuelve_solid(self, brain):
        # La memoria contiene "A*" pero no "Docker" con score alto para esta query
        resp, fuente = brain.responder("busca algoritmo de rutas")
        # SOLID no debe aparecer — verifica corrección del bug v4
        assert "SOLID" not in resp or fuente != "memoria"

    def test_prefijo_que_es_sin_web_cae_a_fallback(self, brain):
        # Sin web_agent y sin memoria relevante → baja confianza o fallback
        resp, fuente = brain.responder("qué es zzzxxxyyy")
        assert "SOLID" not in resp


class TestCalculadoraYAnalisis:
    def test_calculo_basico(self, brain):
        resp, fuente = brain.responder("¿cuánto es 7 por 8?")
        assert fuente == "calculo"
        assert "56" in resp

    def test_expresion_con_operador_directo(self, brain):
        resp, fuente = brain.responder("100 / 4")
        assert fuente == "calculo"
        assert "25" in resp

    def test_analisis_numeros(self, brain):
        resp, fuente = brain.responder("analiza: 10, 20, 30, 40")
        assert fuente == "calculo"
        assert "Media" in resp
        assert "Mediana" in resp


class TestCodigo:
    def test_genera_codigo_flask(self, brain):
        resp, fuente = brain.responder("escribe un servidor flask en python")
        assert fuente == "codigo"
        assert "Flask" in resp
        assert "```python" in resp

    def test_peticion_sin_plantilla_no_responde_codigo(self, brain):
        # "hola" no dispara código
        resp, fuente = brain.responder("hola")
        assert fuente != "codigo"


class TestFallbackDesconocido:
    def test_entrada_desconocida_no_explota(self, brain):
        # Texto sin sentido, no en memoria → debe dar respuesta de desconocido
        resp, fuente = brain.responder("zzzqqqxxx wwwppp")
        assert isinstance(resp, str) and resp
        # SOLID/Docker/A* NO deben filtrarse
        assert "SOLID" not in resp
        assert "Docker" not in resp

    def test_entrada_vacia(self, brain):
        resp, _ = brain.responder("")
        assert "oído" in resp.lower() or "repetir" in resp.lower()

    def test_entrada_whitespace(self, brain):
        resp, _ = brain.responder("   ")
        assert "oído" in resp.lower() or "repetir" in resp.lower()


class TestContextoYReferencias:
    def test_resolver_contexto_con_eso(self, brain):
        brain._ultimo_tema = "Python"
        resolved = brain._resolver_contexto("dime más sobre eso")
        assert "Python" in resolved

    def test_resolver_contexto_sin_tema(self, brain):
        brain._ultimo_tema = ""
        original = "dime más sobre eso"
        assert brain._resolver_contexto(original) == original

    def test_upd_ctx_limits_history(self, brain):
        for i in range(20):
            brain._upd_ctx(f"q{i}", f"r{i}", "test")
        assert len(brain._contexto) == 10


class TestStats:
    def test_stats_endpoint_shape(self, brain):
        s = brain.stats()
        assert "total" in s
        assert "vocabulario" in s
        assert "web_agent" in s
        assert "github_agent" in s
        assert "github_conectado" in s
        assert "buscando_web" in s
