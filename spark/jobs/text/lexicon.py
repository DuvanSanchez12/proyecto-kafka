"""
Lexicon de sentimiento (es/en) usado por el clasificador.

Cada palabra tiene un peso en [-1, 1]. Los negadores y los
intensificadores no son palabras de opinion: son modificadores que el
algoritmo de divide y venceras propaga entre subproblemas.
"""

from __future__ import annotations

from . import normalize as normalize_module
from .normalize import (
    COMMA_TOKEN,
    CONTRAST_TOKEN,
    PAUSE_TOKEN,
    strip_accents,
)

RAW_POSITIVE: dict[str, float] = {
    #ivered adverbios y adjetivos de intensidad positiva
    "increible": 0.90, "impecable": 0.88, "excelente": 0.85, "maravilloso": 0.90,
    "magnifico": 0.85, "fantastico": 0.85, "perfecto": 0.90, "genial": 0.72,
    "encanta": 0.88, "encantado": 0.88, "encantada": 0.88, "adoro": 0.88,
    "amo": 0.80, "recomiendo": 0.78, "recomendado": 0.72, "recomendada": 0.72,
    "brutal": 0.76, "godmode": 0.80, "amazing": 0.88, "awesome": 0.84,
    "great": 0.70, "excellent": 0.85, "perfect": 0.85, "love": 0.82, "loved": 0.82,
    "happy": 0.72, "glad": 0.62, "best": 0.80, "solid": 0.55, "helpful": 0.65,
    "responsive": 0.60, "amable": 0.66, "rapido": 0.55, "rapida": 0.55, "rapidas": 0.55,
    "bonito": 0.60, "bonita": 0.60, "hermoso": 0.75, "elegante": 0.60,
    "comodo": 0.58, "comoda": 0.58, "durable": 0.62, "duradero": 0.62, "duradera": 0.62,
    "asequible": 0.55, "favorito": 0.70, "favorita": 0.70, "supera": 0.60, "super": 0.60,
    "cumple": 0.20, "tranquilo": 0.45, "util": 0.45, "claro": 0.25, "limpio": 0.45,
    "bueno": 0.45, "buena": 0.45, "buen": 0.45, "buenos": 0.45, "buenas": 0.45,
    "buenazo": 0.80, "buenaza": 0.80, "resuelve": 0.30, "resolvio": 0.40,
    "gusto": 0.45, "gustó": 0.55, "gusta": 0.50, "gustaron": 0.55, "guste": 0.50,
    "feliz": 0.75, "felices": 0.70, "alegre": 0.65, "contento": 0.55,
    "vale": 0.20, "paga": 0.25, "mejor": 0.72, "bien": 0.42,
    "gracias": 0.35, "gentil": 0.55, "pro": 0.40, "top": 0.66,
    "responsable": 0.50, "respetable": 0.45, "serio": 0.40, "cercano": 0.40,
    "curioso": 0.25, "atractivo": 0.55, "llamativo": 0.20,
}

RAW_NEGATIVE: dict[str, float] = {
    "terrible": -0.90, "horrible": -0.90, "pesimo": -0.90, "peor": -0.86,
    "mal": -0.48, "malo": -0.72, "mala": -0.72, "malas": -0.72, "malos": -0.72,
    "basura": -0.95, "lata": -0.62, "paja": -0.70, "falso": -0.70, "falsa": -0.70,
    "decepcionante": -0.88, "decepcion": -0.82, "frustrante": -0.84, "frustrado": -0.82,
    "engano": -0.95, "estafa": -0.96, "ignorante": -0.65, "ignorancia": -0.60,
    "caro": -0.55, "carisimo": -0.78, "carisima": -0.78, "caros": -0.55,
    "lento": -0.62, "lenta": -0.62, "lentas": -0.62, "roto": -0.88, "rota": -0.88,
    "fallo": -0.75, "falla": -0.72, "fallas": -0.75, "problema": -0.58,
    "problemas": -0.62, "falla": -0.72, "devolucion": -0.50, "reembolso": -0.50,
    "cancelado": -0.72, "cancelacion": -0.72, "frio": -0.42, "fea": -0.66,
    "feos": -0.66, "feo": -0.66, "altos": -0.30, "altas": -0.30, "alto": -0.30,
    "odiar": -0.92, "odio": -0.86, "detesto": -0.88,
    "awful": -0.85, "terribly": -0.85, "worst": -0.85, "worse": -0.78,
    "useless": -0.80, "hate": -0.90, "crashed": -0.70, "crash": -0.70,
    "ignored": -0.72, "rude": -0.72, "overpriced": -0.78, "delay": -0.55,
    "delayed": -0.55, "broke": -0.70, "broken": -0.78, "dead": -0.55,
    "arrepenti": -0.72, "arrepentido": -0.75, "cancelaron": -0.75, "ignorada": -0.70,
}

RAW_NEGATORS: frozenset[str] = frozenset({
    "no", "nunca", "jamás", "jamas", "nada", "ni", "sin", "tampoco", "nadie",
    "ningun", "ninguna", "not", "never", "no", "none", "without", "neither",
})

RAW_BOOSTERS: dict[str, float] = {
    "muy": 1.45, "muchisimo": 1.75, "extremadamente": 1.80, "totalmente": 1.55,
    "bastante": 1.30, "demasiado": 1.50, "superguau": 1.60, "tremendamente": 1.70,
    "absurdamente": 1.70, "increiblemente": 1.60, "very": 1.45, "extremely": 1.80,
    "totally": 1.55, "really": 1.25, "so": 1.25, "super": 1.35, "best": 1.40,
    "absolutely": 1.50,
}

RAW_DIMINISHERS: dict[str, float] = {
    "apenas": 0.45, "poco": 0.50, "algo": 0.70, "ligeramente": 0.50,
    "medianamente": 0.45, "slightly": 0.50, "kinda": 0.60, "somewhat": 0.60,
    "barely": 0.40,
}

# Marcadores de contraste adversativo. Las frases multiples se colapsan a
# un unico token en normalize.PHRASE_MAP antes de tokenizar.
RAW_CONTRAST: frozenset[str] = frozenset({
    "pero", "aunque", "embargo", "obstante", "contrario",
    "however", "although", "but", "nevertheless", CONTRAST_TOKEN,
})

# Fronteras de clausula: cualquier corte termina el alcance de un negador.
# Solo el subconjunto de contraste, ademas, invierte el foco hacia la
# clausula siguiente.
RAW_CLAUSE_BREAK: frozenset[str] = RAW_CONTRAST | {PAUSE_TOKEN, COMMA_TOKEN}


def _normalize_keys(source: dict[str, float]) -> dict[str, float]:
    return {strip_accents(k.strip().lower()): v for k, v in source.items() if k.strip()}


POSITIVE = _normalize_keys(RAW_POSITIVE)
NEGATIVE = _normalize_keys(RAW_NEGATIVE)
NEGATORS = frozenset(strip_accents(k.lower()) for k in RAW_NEGATORS)
BOOSTERS = _normalize_keys(RAW_BOOSTERS)
DIMINISHERS = _normalize_keys(RAW_DIMINISHERS)
CONTRAST = frozenset(strip_accents(k.lower()) for k in RAW_CONTRAST)
CLAUSE_BREAKS = frozenset(strip_accents(k.lower()) for k in RAW_CLAUSE_BREAK)

# Polaridad unificada
SENTIMENT: dict[str, float] = {**POSITIVE, **NEGATIVE}

# Guard de consistencia: si una palabra estructural acaba en la lista de
# stopwords, la negacion o el contraste se pierden durante la tokenizacion y
# el clasificador falla en silencio. Fallar ruidoso es mejor que fallar raro.
_LEAKED = (
    (NEGATORS | BOOSTERS.keys() | DIMINISHERS.keys() | CONTRAST)
    & normalize_module.STOPWORDS
)
if _LEAKED:
    raise RuntimeError(
        "Palabras estructurales filtradas como stopwords en normalize.py: "
        f"{sorted(_LEAKED)}"
    )


def is_negator(token: str) -> bool:
    return token in NEGATORS


def modifier(token: str) -> tuple[str, float]:
    """Devuelve ``(clase, factor)`` para un token modificador."""
    if token in NEGATORS:
        return "neg", -1.0
    if token in BOOSTERS:
        return "boost", BOOSTERS[token]
    if token in DIMINISHERS:
        return "boost", DIMINISHERS[token]
    return "", 1.0


def polarity(token: str) -> float | None:
    return SENTIMENT.get(token)


def is_contrast(token: str) -> bool:
    return token in CONTRAST


def is_clause_break(token: str) -> bool:
    return token in CLAUSE_BREAKS