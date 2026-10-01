"""
Merge sort instrumentado + utilidades de mezcla usadas por el resto del job.

Se implementan tres piezas:

* ``merge_sort``      -> merge sort bottom-up (iterativo) sobre una lista.
* ``merge``           -> la operacion ``Merge(A, B)`` del libro de Cormen,
                         con conteo de comparaciones.
* ``k_way_merge``     -> mezcla de ``k`` listas ya ordenadas con un heap
                         (O(N log k)), usada para recombinar particiones.
* ``distributed_merge_sort`` -> variante sobre RDD: cada particion ordena
                         con merge sort y luego los bloques se mezclan en
                         un arbol binario de profundidad log2(P).
"""

from __future__ import annotations

import heapq
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

from .complexity import ComplexityMeter

T = TypeVar("T")
KeyFn = Callable[[T], Any]


class _Reversed:
    """Envoltura que invierte el orden de una clave (para orden descendente)."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def __lt__(self, other: "_Reversed") -> bool:
        return other.value < self.value

    def __le__(self, other: "_Reversed") -> bool:
        return other.value <= self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Reversed) and other.value == self.value


def _sort_key(item: T, key: KeyFn | None, reverse: bool) -> Any:
    value = key(item) if key else item
    return _Reversed(value) if reverse else value


def merge(
    left: Sequence[T],
    right: Sequence[T],
    key: KeyFn | None = None,
    reverse: bool = False,
    meter: ComplexityMeter | None = None,
) -> list[T]:
    """
    Operacion ``Merge(A, B)``: funde dos sublistas ya ordenadas en una sola.

    Coste: O(|A| + |B|) tiempo, O(|A| + |B|) memoria. Estable.
    """
    if meter is not None:
        meter.merge()
    i = j = 0
    n_left, n_right = len(left), len(right)
    out: list[T] = []
    while i < n_left and j < n_right:
        if meter is not None:
            meter.compare()
        if _sort_key(left[i], key, reverse) <= _sort_key(right[j], key, reverse):
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    if i < n_left:
        out.extend(left[i:])
    if j < n_right:
        out.extend(right[j:])
    return out


def merge_sort(
    items: Iterable[T],
    key: KeyFn | None = None,
    reverse: bool = False,
    meter: ComplexityMeter | None = None,
) -> list[T]:
    """
    Merge sort bottom-up (de abajo hacia arriba, sin recursion).

    Se eligen bloques de tamano 1, 2, 4, 8, ... y en cada pasada se fusionan
    los bloques adyacentes con ``merge``. Coste Theta(n log n) siempre, incluso
    en el mejor caso, a diferencia de quicksort.
    """
    data = list(items)
    n = len(data)
    width = 1
    while width < n:
        for lo in range(0, n, 2 * width):
            mid = min(lo + width, n)
            hi = min(lo + 2 * width, n)
            if mid < hi:
                data[lo:hi] = merge(data[lo:mid], data[mid:hi], key, reverse, meter)
        width *= 2
    return data


def k_way_merge(
    sorted_lists: Sequence[Sequence[T]],
    key: KeyFn | None = None,
    reverse: bool = False,
    meter: ComplexityMeter | None = None,
) -> Iterator[T]:
    """
    Mezcla ``k`` secuencias ordenadas usando un heap minimo.

    Coste: O(N log k) donde ``N`` es el total de elementos y ``k`` el numero
    de listas. Se usa para recombinar los ``P`` bloques de una particion
    distribuida sin cargar el conjunto completo en un solo paso lineal.
    """
    iterators = [iter(seq) for seq in sorted_lists]
    heap: list[tuple[Any, int, T]] = []
    for idx, it in enumerate(iterators):
        try:
            first = next(it)
        except StopIteration:
            continue
        heap.append((_sort_key(first, key, reverse), idx, first))
    heapq.heapify(heap)

    while heap:
        if meter is not None:
            meter.compare()
        _, idx, item = heapq.heappop(heap)
        yield item
        try:
            nxt = next(iterators[idx])
        except StopIteration:
            continue
        heapq.heappush(heap, (_sort_key(nxt, key, reverse), idx, nxt))


def sorted_partition_merge(
    partitions: Iterable[Sequence[T]],
    key: KeyFn | None = None,
    reverse: bool = False,
    meter: ComplexityMeter | None = None,
) -> list[T]:
    """Atajo comodo: ordena cada bloque y los recombina con ``k_way_merge``."""
    return list(k_way_merge(list(partitions), key=key, reverse=reverse, meter=meter))


# ---------------------------------------------------------------------------
# Variante distribuida sobre RDD de Spark
# ---------------------------------------------------------------------------

def distributed_merge_sort(
    rdd,
    key: KeyFn | None = None,
    reverse: bool = False,
):
    """
    Merge sort distribuido sobre un RDD de ``(clave, valor)``.

    1. Cada particion ordena localmente con ``merge_sort`` (O(m log m)).
    2. Los bloques ordenados se recombinan en un arbol de profundidad
       ``log2(P)`` llamando a ``merge`` en cada nivel.

    El resultado es un RDD de una sola particion con la secuencia global
    ordenada. Pensado para el lado de baja cardinalidad del pipeline
    (ranking de palabras clave por micro-lote), no para barrer millones
    de filas.
    """

    def _sort_partition(rows):
        return iter(merge_sort(list(rows), key=key, reverse=reverse))

    def _as_single_block(rows):
        return iter([list(rows)])

    result = rdd.mapPartitions(_sort_partition).persist()
    while result.getNumPartitions() > 1:
        result = result.mapPartitions(_as_single_block).reduce(
            lambda left, right: merge(left, right, key=key, reverse=reverse)
        )
    return result