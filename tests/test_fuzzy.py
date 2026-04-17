"""
Tests for the pako_fuzzy module (Levenshtein, Jaro-Winkler, n-gramas,
corrección de palabras y texto).
"""
from pako_fuzzy import (
    PakoFuzzy,
    jaro,
    jaro_winkler,
    levenshtein,
    ngramas,
    similitud_levenshtein,
    similitud_ngramas,
    similitud_total,
)


class TestLevenshtein:
    def test_identical_is_zero(self):
        assert levenshtein("hola", "hola") == 0

    def test_empty_strings(self):
        assert levenshtein("", "hola") == 4
        assert levenshtein("hola", "") == 4
        assert levenshtein("", "") == 0

    def test_single_substitution(self):
        assert levenshtein("gato", "gato") == 0
        assert levenshtein("gato", "pato") == 1

    def test_similitud_normalizada(self):
        assert similitud_levenshtein("hola", "hola") == 1.0
        assert 0.0 <= similitud_levenshtein("hola", "mundo") <= 1.0


class TestJaroWinkler:
    def test_identical(self):
        assert jaro("abc", "abc") == 1.0
        assert jaro_winkler("abc", "abc") == 1.0

    def test_empty(self):
        assert jaro("", "abc") == 0.0
        assert jaro("abc", "") == 0.0

    def test_winkler_prefers_common_prefix(self):
        base = jaro("martha", "marhta")
        # Jaro-Winkler con prefijo común debe ser ≥ Jaro puro
        assert jaro_winkler("martha", "marhta") >= base


class TestNgramas:
    def test_bigrams_include_boundaries(self):
        g = ngramas("ab", 2)
        assert "#a" in g
        assert "b#" in g

    def test_similitud_ngramas_identicos(self):
        assert similitud_ngramas("hola", "hola") == 1.0

    def test_similitud_ngramas_disjoint(self):
        # Cadenas sin bigramas en común
        assert similitud_ngramas("aaa", "xyz") == 0.0


class TestSimilitudTotal:
    def test_identical(self):
        assert similitud_total("python", "python") == 1.0

    def test_very_different_lengths(self):
        # len_ratio < 0.4 → 0.0
        assert similitud_total("a", "abcdefghijkl") == 0.0

    def test_capped_at_one(self):
        # Valores siempre en [0, 1]
        for a, b in [("hola", "holo"), ("workflow", "werflow"), ("docker", "dockr")]:
            s = similitud_total(a, b)
            assert 0.0 <= s <= 1.0


class TestPakoFuzzy:
    def test_does_not_touch_protected_words(self):
        f = PakoFuzzy()
        # "hola" jamás se corrige (está en _NO_TOCAR)
        assert f.corregir_palabra("hola") == "hola"
        assert f.corregir_palabra("busca") == "busca"
        assert f.corregir_palabra("como") == "como"

    def test_expands_known_abbreviation(self):
        f = PakoFuzzy()
        assert f.corregir_palabra("wf") == "workflow"
        assert f.corregir_palabra("cfg") == "configuración"

    def test_corrects_misspelled_long_word(self):
        f = PakoFuzzy()
        # "automatizcion" → "automatización"
        corrected = f.corregir_palabra("automatizcion")
        assert "automatiza" in corrected or corrected == "automatización"

    def test_short_words_not_corrected(self):
        f = PakoFuzzy()
        # Palabras cortas se dejan intactas para evitar falsos positivos
        assert f.corregir_palabra("abc") == "abc"

    def test_enriquecer_vocabulario_accepts_only_long_words(self):
        f = PakoFuzzy()
        f.enriquecer_vocabulario(["xy", "algo", "palabralarga"])
        vocab = f._vocabulario_completo()
        assert "xy" not in vocab  # demasiado corta
        assert "palabralarga" in vocab

    def test_corregir_texto_returns_tuple(self):
        f = PakoFuzzy()
        out, cambios = f.corregir_texto("hola mundo")
        assert isinstance(out, str)
        assert isinstance(cambios, bool)

    def test_corregir_texto_expands_abbreviations(self):
        f = PakoFuzzy()
        # Las abreviaturas se expanden aunque el flag `cambios` se reserve
        # para correcciones por token.
        out, _ = f.corregir_texto("crea un wf nuevo")
        assert "workflow" in out

    def test_corregir_texto_flags_token_corrections(self):
        f = PakoFuzzy()
        # Palabra larga mal escrita del vocabulario → el corrector la arregla
        # y el flag `cambios` debe marcarse
        out, cambios = f.corregir_texto("automatizcion de procesos")
        assert cambios is True
        assert "automatiz" in out

    def test_similitud_consulta_identica(self):
        f = PakoFuzzy()
        assert f.similitud_consulta("python es genial", "python es genial") == 1.0

    def test_similitud_consulta_vacia(self):
        f = PakoFuzzy()
        assert f.similitud_consulta("", "python") == 0.0
        assert f.similitud_consulta("python", "") == 0.0
