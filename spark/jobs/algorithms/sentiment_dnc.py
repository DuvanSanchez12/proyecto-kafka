"""
Clasificador de sentimiento por DIVIDE Y VENCERAS.

Idea central
------------
El sentimiento de una mencion no se puede leer token a token sin perder el
alcance de los modificadores:

* "es increible"                        -> positivo
* "no es nada increible"                -> negativo (negacion de clausula)
* "es increible, pero es terrible"      -> negativo (contraste adversativo)
* "es bonito aunque el envio fue mal"   -> pesa la ultima clausula

El algoritmo divide la secuencia de tokens en dos, resuelve cada mitad por
recursion y **combina** los resultados. La combinacion es una operacion
``Merge(A, B)`` sobre los items de opinion ya ordenados por posicion: el
algoritmo es, en esencia, un merge sort con semantica de lenguaje.

La clave para que el resultado NO dependa de donde se corta la recursion
(propiedad que se verifica en ``tests``) es separar dos cosas que viajan
distinto por el arbol:

* la **magnitud** (polaridad de la palabra por los intensificadores que la
  preceden) -> se multiplica, y se propaga hacia la derecha;
* la **negacion** -> es un booleano por clausula, se propaga hacia la derecha
  y es idempotente ("no ... nada" refuerza, no cancela).

La negacion en espanol tiene alcance hacia adelante, asi que un modificador
que aparece en la mitad derecha nunca alcanza a la mitad izquierda. Esa
asimetria es justo lo que hace que el arbol completo sea consistente.

Recursion
---------
    D&C(t, lo, hi)
      caso base   : |t| <= BASE  -> escaneo lineal, deja el estado de la clausula
      division    : mid = lo + |t| // 2
      conquista   : (L, R) = (D&C(t, lo, mid), D&C(t, mid, hi))
      combinacion : Merge(L, R) + traspaso del estado de L a la clausula de R

Coste
-----
    T(n) = 2 T(n/2) + Theta(m)   con m = items de opinion del tramo
        = Theta(n log n)         (m <= n, y Theta(n) items en el peor caso)

Como el pivote no existe (siempre se parte por la mitad), la profundidad es
``ceil(log2(n / BASE))`` y el numero de mezclas es ``2^d - 1`` sin importar
los datos: el peor caso es igual al mejor, Theta(n log n) garantizado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..text import lexicon as lex
from .complexity import (
    ComplexityMeter,
    theoretical_dandc_comparisons,
    theoretical_dandc_merges,
)
from .merge_sort import merge

BASE_CASE = 2            # tokens que se resuelven con un escaneo lineal
CONTRAST_GAIN = 1.9      # peso de la clausula que sigue a un "pero"/"aunque"
SCORE_SCALE = 1.9        # divisor antes de aplicar tanh
NEUTRAL_BAND = 0.06      # |score| por debajo de esto es neutral
CONFIDENCE_FULL = 2.2    # |score bruto| a partir del cual la confianza es 1.0
MAX_KEYWORDS = 4

POSITIVO = "POSITIVO"
NEUTRAL = "NEUTRAL"
NEGATIVO = "NEGATIVO"

NEG = "neg"
BOOST = "boost"


@dataclass
class Opinion:
    """Un token con carga de sentimiento y el contexto que lo modula."""

    index: int
    token: str
    weight: float        # polaridad * intensificadores (con signo, sin negar)
    negated: bool        # hay un negador antes en la misma clausula
    clause: int
    contrast_depth: int

    @property
    def signed_weight(self) -> float:
        value = -self.weight if self.negated else self.weight
        return max(-1.0, min(1.0, value))


@dataclass
class Fragment:
    """Resultado de resolver un tramo ``[lo, hi)`` de la mencion."""

    lo: int
    hi: int
    opinions: list[Opinion]     # ordenada por indice (Merge produce esto)
    end_factor: float           # factor acumulado de intensificadores al cierre
    end_negated: bool           # hay negador activo al cierre
    clause: int                 # clausula en la que termina el tramo
    contrast_depth: int         # contrastes vistos hasta el final
    open_start: bool            # empieza a mitad de clausula
    open_end: bool              # termina a mitad de clausula
    depth: int

    @property
    def size(self) -> int:
        return self.hi - self.lo


@dataclass
class SentimentResult:
    sentiment: str
    score: float
    raw_score: float
    confidence: float
    tokens: int
    opinions: list[Opinion]
    clauses: list[dict]
    keywords: list[str]
    meter: ComplexityMeter
    theoretical_merges: int
    theoretical_comparisons: int

    def as_dict(self) -> dict:
        return {
            "sentiment": self.sentiment,
            "score": round(self.score, 6),
            "raw_score": round(self.raw_score, 6),
            "confidence": round(self.confidence, 6),
            "tokens": self.tokens,
            "keywords": self.keywords,
            "dnc_comparisons": self.meter.comparisons,
            "dnc_decisions": self.meter.decisions,
            "dnc_levels": self.meter.max_depth,
            "dnc_subproblems": self.meter.subproblems,
            "merge_operations": self.meter.merges,
            "token_scans": self.meter.token_scans,
            "theoretical_comparisons": self.theoretical_comparisons,
            "theoretical_merges": self.theoretical_merges,
            "clauses": self.clauses,
        }


# ---------------------------------------------------------------------------
# CASO BASE: escaneo lineal del tramo
# ---------------------------------------------------------------------------

def _solve_leaf(tokens: list[str], lo: int, hi: int, meter: ComplexityMeter, depth: int) -> Fragment:
    """
    Resuelve un tramo corto escaneandolo de izquierda a derecha.

    El estado del escaneo es (negated, factor):

    * un negador activa ``negated`` y lo mantiene hasta el final de la
      clausula. En espanol la concordancia negativa es lo normal ("no ... nada
      increible" sigue siendo negativo), asi que varios negadores no se
      cancelan entre si: refuerzan.
    * un intensificador o atenuador multiplica ``factor``.
    * un corte de clausula (puntuacion o conector adversativo) reinicia
      (negated, factor) y abre una clausula nueva.

    Al terminar deja (``end_negated``, ``end_factor``): el estado vigente en el
    borde derecho. El combine lo traspasa a la clausula que continua en el
    subproblema vecino.
    """
    meter.leaf()
    opinions: list[Opinion] = []
    clause = 0
    contrast_depth = 0
    negated = False
    factor = 1.0

    for i in range(lo, hi):
        token = tokens[i]
        meter.scan()

        if lex.is_clause_break(token):
            meter.decide()
            clause += 1
            if lex.is_contrast(token):
                contrast_depth += 1
            negated = False
            factor = 1.0
            continue

        kind, value = lex.modifier(token)
        if kind:
            meter.decide()
            if kind == NEG:
                negated = True
            else:
                factor *= value
            continue

        base_weight = lex.polarity(token)
        if base_weight is None:
            continue

        meter.decide()
        opinions.append(
            Opinion(
                index=i,
                token=token,
                weight=base_weight * factor,
                negated=negated,
                clause=clause,
                contrast_depth=contrast_depth,
            )
        )

    open_start = not lex.is_clause_break(tokens[lo])
    open_end = not lex.is_clause_break(tokens[hi - 1])
    return Fragment(
        lo=lo,
        hi=hi,
        opinions=opinions,
        end_factor=factor,
        end_negated=negated,
        clause=clause,
        contrast_depth=contrast_depth,
        open_start=open_start,
        open_end=open_end,
        depth=depth,
    )


# ---------------------------------------------------------------------------
# COMBINACION: Merge(A, B) + traspaso del estado de la clausula
# ---------------------------------------------------------------------------

def _clause_opinions(opinions: list[Opinion], clause: int) -> list[Opinion]:
    """
    Todos los items de ``opinions`` que pertenecen a ``clause``.

    El alcance de un modificador es la clausula completa, no una ventana de
    ``k`` items: por eso el traspaso afecta a *todos* los items de la clausula
    que continua. Recortar aqui rompe la asociatividad del combine y el
    resultado pasaria a depender de donde se detiene la recursion.
    """
    return [opinion for opinion in opinions if opinion.clause == clause]


def _combine(left: Fragment, right: Fragment, meter: ComplexityMeter) -> Fragment:
    """
    ``Merge(L, R)`` sobre los items de opinion de ambos subproblemas.

      1. ``merge`` de las dos listas ordenadas por indice -> Theta(m).
      2. Traspaso: si la clausula sigue abierta a traves del corte, el estado
         (factor, negado) vigente al final de ``left`` se aplica a la primera
         clausula de ``right``. Como la negacion es idempotente y la magnitud
         multiplicativa, aplicar el estado completo es equivalente a haber
         escaneado la mencion entera de un tiron: por eso el arbol no altera
         el resultado.
    """
    merged = merge(left.opinions, right.opinions, key=lambda o: o.index, meter=meter)

    # Numeracion LOCAL -> GLOBAL. Cada hoja numera sus clausulas desde 0, asi
    # que al combinar hay que reubicar las del subproblema derecho:
    #   * si la clausula continua (cruza), su clausula 0 es la MISMA que la
    #     ultima de `left`  -> offset = left.clause
    #   * si hay un corte en la frontera, su clausula 0 es NUEVA
    #                       -> offset = left.clause + 1
    cruza = left.open_end and right.open_start
    clause_offset = left.clause if cruza else left.clause + 1
    if clause_offset or left.contrast_depth:
        for opinion in right.opinions:
            opinion.clause += clause_offset
            opinion.contrast_depth += left.contrast_depth

    # Traspaso del estado de clausula. Como la negacion es idempotente y la
    # magnitud multiplicativa, aplicar el estado completo al final de `left`
    # sobre la primera clausula de `right` equivale a haber escaneado la
    # mencion entera de un tiron: por eso el arbol no altera el resultado.
    if cruza:
        for opinion in _clause_opinions(right.opinions, left.clause):
            if left.end_factor != 1.0:
                opinion.weight *= left.end_factor
            if left.end_negated:
                opinion.negated = True

    # El estado vigente al cierre del tramo combinado. Si la clausula continua
    # (cruza), el estado de `left` sigue vivo sumado al propio de `right`; si
    # hubo un corte en la frontera, `left` murio con su clausula.
    if cruza:
        end_factor = left.end_factor * right.end_factor
        end_negated = left.end_negated or right.end_negated
    else:
        end_factor = right.end_factor
        end_negated = right.end_negated

    return Fragment(
        lo=left.lo,
        hi=right.hi,
        opinions=merged,
        end_factor=end_factor,
        end_negated=end_negated,
        clause=clause_offset + right.clause,
        contrast_depth=left.contrast_depth + right.contrast_depth,
        open_start=left.open_start,
        open_end=right.open_end,
        depth=max(left.depth, right.depth),
    )


# ---------------------------------------------------------------------------
# DIVIDE Y VENCERAS
# ---------------------------------------------------------------------------

def _divide(
    tokens: list[str],
    lo: int,
    hi: int,
    meter: ComplexityMeter,
    depth: int,
    base: int,
) -> Fragment:
    meter.node(depth)
    size = hi - lo
    if size <= base:
        return _solve_leaf(tokens, lo, hi, meter, depth)

    mid = lo + size // 2
    left = _divide(tokens, lo, mid, meter, depth + 1, base)
    right = _divide(tokens, mid, hi, meter, depth + 1, base)
    return _combine(left, right, meter)


def classify_tokens(
    tokens: list[str],
    meter: ComplexityMeter | None = None,
    base: int = BASE_CASE,
) -> Fragment:
    meter = meter or ComplexityMeter()
    if not tokens:
        return Fragment(0, 0, [], 1.0, False, 0, 0, False, False, 0)
    return _divide(tokens, 0, len(tokens), meter, 0, base)


# ---------------------------------------------------------------------------
# Reduccion final: de los items de opinion a una clase
# ---------------------------------------------------------------------------

def _clause_breakdown(opinions: list[Opinion]) -> tuple[float, list[dict]]:
    """
    Suma los items agrupados por clausula.

    El contraste adversativo ("pero", "aunque") abre una clausula nueva y la
    opinion dominante no es la primera sino la de la ultima clausula: es la
    que el autor quiere que retengamos. Por eso el aporte de una clausula se
    multiplica por ``CONTRAST_GAIN ** contrastes_previos``.
    """
    if not opinions:
        return 0.0, []

    buckets: dict[int, list[Opinion]] = {}
    for opinion in opinions:
        buckets.setdefault(opinion.clause, []).append(opinion)

    total = 0.0
    detail: list[dict] = []
    for clause_index in sorted(buckets):
        items = buckets[clause_index]
        base = sum(item.signed_weight for item in items)
        dominant = max(items, key=lambda o: abs(o.signed_weight))
        depth = items[0].contrast_depth
        gain = CONTRAST_GAIN ** depth
        weighted = base * gain
        total += weighted
        detail.append(
            {
                "clausula": clause_index,
                "tokens": [item.token for item in items],
                "peso_bruto": round(base, 4),
                "ganador": dominant.token,
                "ganador_polaridad": round(dominant.signed_weight, 4),
                "factor_contraste": round(gain, 4),
                "peso_contrastado": round(weighted, 4),
                "es_contraste": depth > 0,
                "negada": any(item.negated for item in items),
            }
        )
    return total, detail


def _decide(raw: float, evidence: int) -> tuple[str, float, float]:
    score = math.tanh(raw / SCORE_SCALE)
    if score > NEUTRAL_BAND:
        sentiment = POSITIVO
    elif score < -NEUTRAL_BAND:
        sentiment = NEGATIVO
    else:
        sentiment = NEUTRAL
    magnitude = min(1.0, abs(raw) / CONFIDENCE_FULL)
    support = min(1.0, evidence / 3.0)
    confidence = round(magnitude * (0.6 + 0.4 * support), 4)
    return sentiment, round(score, 6), confidence


def analyze(text: str, base: int = BASE_CASE) -> SentimentResult:
    """Punto de entrada: texto crudo -> sentimiento + trazabilidad."""
    from ..text.normalize import tokenize

    tokens = tokenize(text)
    meter = ComplexityMeter()
    fragment = classify_tokens(tokens, meter, base)
    raw, detail = _clause_breakdown(fragment.opinions)
    sentiment, score, confidence = _decide(raw, len(fragment.opinions))
    keywords = [item.token for item in fragment.opinions[:MAX_KEYWORDS]]
    items = len(fragment.opinions)
    return SentimentResult(
        sentiment=sentiment,
        score=score,
        raw_score=round(raw, 6),
        confidence=confidence,
        tokens=len(tokens),
        opinions=fragment.opinions,
        clauses=detail,
        keywords=keywords,
        meter=meter,
        theoretical_merges=theoretical_dandc_merges(len(tokens), base),
        theoretical_comparisons=theoretical_dandc_comparisons(len(tokens), items, base),
    )