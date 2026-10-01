"""
Instrumentacion de complejidad.

El objetivo del proyecto es *demostrar* la complejidad del algoritmo, no
solo enunciarla. Para eso cada operacion de mezcla y cada comparacion de
token se cuenta en tiempo de ejecucion y luego se contrasta con el limite
teorico ``n log2(n) - n + 1`` del merge sort.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ComplexityMeter:
    """Contadores de una ejecucion del clasificador."""

    comparisons: int = 0      # comparaciones de mezcla (merge sort / merge)
    token_scans: int = 0      # tokens inspeccionados en los casos base
    decisions: int = 0        # decisiones de clasificacion de token en el caso base
    merges: int = 0           # operaciones de mezcla Merge(A,B)
    leaves: int = 0           # subproblemas base (caso base)
    subproblems: int = 0      # nodos del arbol de recursion
    max_depth: int = 0        # niveles de recursion

    def compare(self, n: int = 1) -> None:
        self.comparisons += n

    def scan(self, n: int = 1) -> None:
        self.token_scans += n

    def decide(self, n: int = 1) -> None:
        self.decisions += n

    def merge(self) -> None:
        self.merges += 1

    def leaf(self) -> None:
        self.leaves += 1

    def node(self, depth: int) -> None:
        self.subproblems += 1
        if depth > self.max_depth:
            self.max_depth = depth

    def as_dict(self) -> dict[str, int]:
        return {
            "comparisons": self.comparisons,
            "token_scans": self.token_scans,
            "decisions": self.decisions,
            "merges": self.merges,
            "leaves": self.leaves,
            "subproblems": self.subproblems,
            "max_depth": self.max_depth,
        }


def theoretical_merge_comparisons(n: int) -> int:
    """
    Cota superior de comparaciones de un merge sort de ``n`` elementos.

    Para ``n = 2^k`` el conteo es exactamente ``n*log2(n) - n + 1``; para
    ``n`` arbitrario el algoritmo hace como maximo ese valor, porque los
    bloques de la ultima pasada quedan desbalanceados y la mezcla termina
    antes. Por eso el valor medido siempre queda por debajo o por igual.
    """
    if n <= 1:
        return 0
    return int(math.ceil(n * math.log2(n) - n + 1))


def dandc_depth(n: int, base: int) -> int:
    """
    Numero de niveles de recursion del divide y venceras: la cantidad de
    veces que hay que partir ``n`` por la mitad hasta llegar al caso base.
    Vale ``ceil(log2(n / base))`` y es tambien el numero maximo de mezclas en
    las que puede participar un unico token.
    """
    if n <= base or base <= 0:
        return 0
    depth = 0
    size = n
    while size > base:
        size = (size + 1) // 2
        depth += 1
    return depth


def theoretical_dandc_comparisons(n: int, m: int, base: int) -> int:
    """
    Cota de comparaciones del clasificador.

    En cada nivel del arbol, cada item de opinion participa como mucho en una
    operacion ``Merge``. Con ``m`` items de opinion y ``d`` niveles, el total
    de comparaciones es a lo sumo ``m * d``. Como ``m <= n`` y
    ``d = log2(n/base)``, el algoritmo es ``Theta(n log n)`` en el peor caso y
    ``Theta(m log n)`` en el caso tipico (muy pocas palabras cargadas).
    """
    if m <= 0:
        return 0
    return m * dandc_depth(n, base)


def theoretical_dandc_merges(n: int, base: int) -> int:
    """
    Numero de mezclas Merge(A, B) que ejecuta el divide y venceras con
    tamano de caso base ``base`` sobre ``n`` tokens.

    El arbol es casi completo: ``2^d - 1`` nodos internos, donde
    ``d = ceil(log2(n / base))``.
    """
    if n <= base:
        return 0
    depth = 0
    size = n
    while size > base:
        size = (size + 1) // 2
        depth += 1
    return (1 << depth) - 1