"""
Tests for the calculator (`calcular`, `_fmt`) and data analysis (`analizar_datos`)
helpers of pako_brain.
"""
import math

from pako_brain import _fmt, analizar_datos, calcular


class TestFmt:
    def test_integer_thousands_separator(self):
        assert _fmt(1234567) == "1.234.567"

    def test_float_integer_value(self):
        assert _fmt(3.0) == "3"

    def test_float_rounded(self):
        assert _fmt(3.141592653589793) == "3.141593"

    def test_negative_integer(self):
        assert _fmt(-5) == "-5"


class TestCalcular:
    def test_basic_sum_with_operators(self):
        assert calcular("2+2") == "4"

    def test_natural_language_multiplication(self):
        assert calcular("cuanto es 7 por 8") == "56"

    def test_natural_language_division(self):
        assert calcular("100 dividido entre 4") == "25"

    def test_natural_language_plus_minus(self):
        assert calcular("10 mas 5") == "15"
        assert calcular("10 menos 3") == "7"

    def test_percentage(self):
        # 20% de 150 = 30
        assert calcular("20% de 150") == "30"

    def test_square_root(self):
        assert calcular("raiz cuadrada de 16") == "4"

    def test_power(self):
        assert calcular("3 elevado al cuadrado") == "9"
        assert calcular("2 elevado al cubo") == "8"
        assert calcular("2 elevado a 10") == "1.024"

    def test_unicode_operators(self):
        assert calcular("6 × 7") == "42"
        assert calcular("18 ÷ 3") == "6"

    def test_no_operation_returns_none(self):
        assert calcular("hola amigo") is None

    def test_single_number_without_operator_returns_none(self):
        # There's no expression, just a number → no operator, no result
        assert calcular("42") is None

    def test_non_integer_result(self):
        # 10 / 4 = 2.5
        assert calcular("10 dividido entre 4") == "2.5"


class TestAnalizarDatos:
    def test_requires_at_least_two_numbers(self):
        assert analizar_datos("solo un 5") is None
        assert analizar_datos("sin numeros") is None

    def test_basic_analysis_output(self):
        out = analizar_datos("analiza: 1, 2, 3, 4, 5")
        assert out is not None
        # Media = 3, Mediana = 3, Mín = 1, Máx = 5
        assert "Media: 3" in out
        assert "Mediana: 3" in out
        assert "Mín: 1" in out
        assert "Máx: 5" in out
        assert "Suma: 15" in out
        assert "5 valores" in out

    def test_even_count_median_average(self):
        # mediana de [1,2,3,4] = 2.5
        out = analizar_datos("1 2 3 4")
        assert out is not None
        assert "Mediana: 2.5" in out

    def test_standard_deviation_calculated(self):
        out = analizar_datos("10 10 10 10")
        assert out is not None
        # All equal ⇒ desviación 0
        assert "Desviación estándar: 0" in out

    def test_negative_numbers(self):
        out = analizar_datos("-2 0 2")
        assert out is not None
        assert "Media: 0" in out
        # range = 4
        assert "Rango: 4" in out
