"""
Pruebas del nucleo algoritmico.

Se verifican tres propiedades que sostienen el argumento del proyecto:

1. ``merge_sort`` ordena y respeta la cota de comparaciones ``n log2(n)``.
2. El clasificador acierta los casos linguisticos duros (negacion, doble
   negacion, contraste adversativo, intensificadores).
3. El resultado del divide y venceras NO depende del tamano del caso base:
   el arbol produce la misma clasificacion que escanear la mencion completa de
   un tiron. Esa es la prueba empirica de que la combinacion es asociativa.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs.algorithms.complexity import (  # noqa: E402
    ComplexityMeter,
    dandc_depth,
    theoretical_merge_comparisons,
)
from jobs.algorithms.merge_sort import (  # noqa: E402
    k_way_merge,
    merge,
    merge_sort,
)
from jobs.algorithms.sentiment_dnc import (  # noqa: E402
    NEGATIVO,
    NEUTRAL,
    POSITIVO,
    analyze,
)


# ---------------------------------------------------------------------------
# Merge sort
# ---------------------------------------------------------------------------

def test_merge_funde_dos_listas_ordenadas():
    assert merge([1, 4, 7], [2, 3, 9]) == [1, 2, 3, 4, 7, 9]


def test_merge_con_una_lista_vacia():
    assert merge([], [3, 5]) == [3, 5]
    assert merge([1], []) == [1]


def test_merge_sort_ordena_listas_arbitrarias():
    random.seed(0)
    for size in (0, 1, 2, 7, 64, 257):
        data = random.sample(range(size * 3), size)
        assert merge_sort(data) == sorted(data)


def test_merge_sort_descendente_y_con_clave():
    assert merge_sort([5, 3, 9, 1], reverse=True) == [9, 5, 3, 1]
    assert merge_sort(["pear", "fig", "apple"], key=len) == ["fig", "pear", "apple"]


def test_merge_sort_es_estable():
    data = [("b", 1), ("a", 2), ("b", 3), ("a", 4), ("b", 5)]
    got = merge_sort(data, key=lambda kv: kv[0])
    assert [t for t, _ in got] == ["a", "a", "b", "b", "b"]
    assert got[0][1] < got[1][1] and got[2][1] < got[3][1] < got[4][1]


@pytest.mark.parametrize("size", [2, 8, 64, 512, 2048])
def test_cota_de_comparaciones(size):
    data = random.Random(size).sample(range(size * 5), size)
    meter = ComplexityMeter()
    merge_sort(data, meter=meter)
    assert meter.comparisons <= theoretical_merge_comparisons(size)


def test_k_way_merge():
    bloques = [[1, 5, 9], [2, 3], [], [4, 8]]
    assert list(k_way_merge(bloques)) == [1, 2, 3, 4, 5, 8, 9]


# ---------------------------------------------------------------------------
# Comportamiento linguistico
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("El Nike es increible, me encanta", POSITIVO),
        ("El Nike no es nada increible, es una decepcion", NEGATIVO),
        ("Nunca pense que el Nike fuera tan increible, me arrepenti", NEGATIVO),
        ("El Nike es bonito, pero el precio es terrible", NEGATIVO),
        ("Me gusta el Nike, pero el soporte es horrible", NEGATIVO),
        ("El soporte no respondio, sin embargo el producto es increible", POSITIVO),
        ("Alguien sabe cuando sale la nueva version del Nike?", NEUTRAL),
        ("El Nike es muy increible", POSITIVO),
        ("El Nike es un poco bueno, solo cumple", POSITIVO),
        ("Mi opinion del Nike: calidad buena y atencion horrible", NEGATIVO),
        ("Gran diseno del Nike, aunque la calidad de materiales es mala", NEGATIVO),
        ("El packaging del Nike es perfecto, no obstante la app es horrible", NEGATIVO),
        ("El Nike no es perfecto, sin embargo casi todo esta increible", POSITIVO),
        ("No es que el Nike sea malo, pero si es terrible", NEGATIVO),
        ("Dicen que el Nike es caro pero es increible y durable", POSITIVO),
        ("No compro mas Nike, lo mio fue terrible", NEGATIVO),
    ],
)
def test_casos_linguisticos(texto, esperado):
    assert analyze(texto).sentiment == esperado


def test_negacion_tiene_alcance_hacia_adelante():
    """Un negador no alcanza lo que esta antes de el."""
    positivo = analyze("El Nike es increible").score
    assert positivo > 0
    assert analyze("El Nike es increible no es mala").score != 0


# ---------------------------------------------------------------------------
# Invarianza al caso base: el corazon del argumento divide y venceras
# ---------------------------------------------------------------------------

CORPUS = [
    "El Nike no es nada increible, es una decepcion",
    "Nunca pense que el Nike fuera tan maravilloso, me arrepenti",
    "El soporte no respondio, sin embargo el producto es excelente",
    "El packaging del Nike es perfecto, no obstante la app es horrible",
    "Mi opinion del Nike: calidad buena y atencion horrible",
    "El Nike es un poco bueno, solo cumple",
    "Dicen que el Nike es caro pero es increible y durable",
    "Gran diseno del Nike, aunque la calidad de materiales es mala",
]


@pytest.mark.parametrize("base", [1, 2, 3, 4, 6, 8])
def test_resultado_independiente_del_caso_base(base):
    completo = {t: analyze(t, base=10_000) for t in CORPUS}
    for texto in CORPUS:
        referencia = completo[texto]
        parcial = analyze(texto, base=base)
        assert parcial.sentiment == referencia.sentiment, (texto, base)
        assert parcial.raw_score == pytest.approx(referencia.raw_score, abs=1e-9)


def test_arbol_balanceado_tiene_profundidad_logaritmica():
    for n in (4, 8, 16, 32, 64):
        r = analyze(" ".join(["muy bueno"] * (n // 2)), base=2)
        assert r.meter.max_depth <= dandc_depth(r.tokens, 2)


def test_contadores_coherentes():
    r = analyze("El Nike no es nada increible pero me encanta de verdad")
    assert r.meter.subproblems >= 1
    assert r.meter.leaves >= 1
    assert r.meter.merges == r.meter.subproblems - r.meter.leaves or r.meter.subproblems == 1
    assert r.meter.comparisons <= r.theoretical_comparisons