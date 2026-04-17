"""
Tests for the code-generation helper `detectar_peticion_codigo`
and the `_CODE_TEMPLATES` catalog.
"""
from pako_brain import _CODE_TEMPLATES, detectar_peticion_codigo


class TestDetectarPeticionCodigo:
    def test_requires_trigger_word(self):
        # Sin "código", "ejemplo", "escribe"... devuelve None aunque mencione python
        assert detectar_peticion_codigo("me gusta python") is None

    def test_returns_template_for_known_topic(self):
        tpl = detectar_peticion_codigo("escribe un servidor Flask en Python")
        assert tpl is not None
        assert tpl["lang"] == "python"
        assert "Flask" in tpl["code"]

    def test_returns_template_fastapi(self):
        tpl = detectar_peticion_codigo("codigo de un servidor fastapi")
        assert tpl is not None
        assert "FastAPI" in tpl["code"]

    def test_returns_none_for_non_code_request(self):
        assert detectar_peticion_codigo("hola") is None
        assert detectar_peticion_codigo("cuanto es 2 + 2") is None

    def test_ignores_unrelated_topic_even_with_trigger(self):
        # Trigger word present, but no template keyword matches → None
        assert (
            detectar_peticion_codigo("escribe un poema sobre amor") is None
        )

    def test_react_component_template(self):
        tpl = detectar_peticion_codigo("ejemplo de react componente")
        assert tpl is not None
        assert tpl["lang"] == "jsx"
        assert "useState" in tpl["code"]

    def test_docker_detection(self):
        tpl = detectar_peticion_codigo("hazme un dockerfile")
        assert tpl is not None
        assert tpl["lang"] == "dockerfile"


class TestCodeTemplatesShape:
    def test_every_template_has_required_fields(self):
        assert _CODE_TEMPLATES, "expected at least one template"
        for key, tpl in _CODE_TEMPLATES.items():
            assert "lang" in tpl, f"{key} missing lang"
            assert "code" in tpl, f"{key} missing code"
            assert "desc" in tpl, f"{key} missing desc"
            assert isinstance(tpl["code"], str) and tpl["code"].strip()
            assert isinstance(tpl["lang"], str) and tpl["lang"].strip()
            assert isinstance(tpl["desc"], str) and tpl["desc"].strip()
