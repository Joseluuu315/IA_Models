"""
Tests for the NLP helpers (normalización, tokenización, vectores) of pako_brain.
"""
import math

from pako_brain import (
    STOPWORDS_ES,
    cos_sim,
    normalizar,
    tokenizar,
    tokens_sig,
    vectorizar,
)


class TestNormalizar:
    def test_lowercase_and_strip(self):
        assert normalizar("  HoLa  ") == "hola"

    def test_strips_accents(self):
        assert normalizar("árbol") == "arbol"
        assert normalizar("Él Está Ahí") == "el esta ahi"
        assert normalizar("piñón") == "pinon"

    def test_removes_spanish_punctuation(self):
        assert normalizar("¿Qué es?") == "que es?"
        assert normalizar("¡Hola!") == "hola!"

    def test_preserves_other_chars(self):
        assert normalizar("2 + 2 = 4") == "2 + 2 = 4"


class TestTokenizar:
    def test_basic_tokens(self):
        assert tokenizar("hola mundo") == ["hola", "mundo"]

    def test_drops_single_chars(self):
        # tokenizar filters len > 1, so 'a' is dropped but 'ab' kept
        assert tokenizar("a ab") == ["ab"]

    def test_handles_accents_and_punct(self):
        assert tokenizar("¿Cómo estás?") == ["como", "estas"]

    def test_keeps_numbers(self):
        assert tokenizar("Pi es 314") == ["pi", "es", "314"]


class TestTokensSig:
    def test_removes_stopwords(self):
        tokens = tokenizar("el perro es marron")
        sig = tokens_sig(tokens)
        # "el" and "es" are stopwords
        assert "el" not in sig
        assert "es" not in sig
        assert "perro" in sig
        assert "marron" in sig

    def test_known_stopwords_in_module(self):
        # Sanity check that constants are exposed
        assert "el" in STOPWORDS_ES
        assert "que" in STOPWORDS_ES


class TestVectorizarYCosSim:
    def test_vector_matches_vocab_length(self):
        vocab = ["a", "b", "c"]
        vec = vectorizar(["a", "a", "b"], vocab)
        assert len(vec) == 3
        # Frequencies normalized by total tokens
        assert math.isclose(vec[0], 2 / 3)
        assert math.isclose(vec[1], 1 / 3)
        assert math.isclose(vec[2], 0.0)

    def test_cos_sim_identical_is_one(self):
        v = [1.0, 0.0, 2.0]
        assert math.isclose(cos_sim(v, v), 1.0)

    def test_cos_sim_orthogonal_is_zero(self):
        assert cos_sim([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_cos_sim_zero_vectors(self):
        assert cos_sim([0.0, 0.0], [1.0, 2.0]) == 0.0
        assert cos_sim([], []) == 0.0
