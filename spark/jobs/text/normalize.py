"""Normalizacion y tokenizacion de texto social (es/en)."""

from __future__ import annotations

import re
import unicodedata

URL_RE = re.compile(r"https?://\S+|www\.\S+")
USER_RE = re.compile(r"[@#](\w[\w_.-]*)")
RT_RE = re.compile(r"\bRT\b")
MENTION_RE = re.compile(r"@\w+")
NON_WORD_RE = re.compile(r"[^a-z0-9áéíóúüñ#']+")
SPACE_RE = re.compile(r"\s+")

# Marcador unico al que se colapsan las locuciones adversativas, para que
# "sin embargo" no se lea como negador + relleno.
CONTRAST_TOKEN = "contrastomarcador"

# La puntuacion no se descarta: se convierte en centinelas que marcan fin de
# clausula. El alcance de una negacion en espanol termina en el punto o la
# coma, asi que el clasificador necesita verlos.
PAUSE_TOKEN = "__pausa__"     # . ! ? ; :
COMMA_TOKEN = "__coma__"      # ,
PUNCT_TOKENS = frozenset({PAUSE_TOKEN, COMMA_TOKEN})

PHRASE_MAP: dict[str, str] = {
    "sin embargo": f" {CONTRAST_TOKEN} ",
    "no obstante": f" {CONTRAST_TOKEN} ",
    "that said": f" {CONTRAST_TOKEN} ",
    "dicho esto": f" {CONTRAST_TOKEN} ",
    "en resumen": f" {CONTRAST_TOKEN} ",
}

STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque
    bien cada casi como con contra cual cuando de del desde donde dos el ella
    ellas ello ellos en entre era erais eran eres es esa esas ese eso esos esta
    estan estas este esto estos estoy fue fueron ha habia han hasta hay la las
    le les lo los mas me mi mientras mio mis mucho muy nada ni no nos nuestra
    nuestro o os otra otro para pero poco por porque que quien quienes se sea
    ser si sido siendo sin sobre solo son su sus tan te tiene tienen toda todas
    todo todos tras un una uno unos y ya yo del al
    the a an and or but if then else of to in on at for with from by is are was
    were be been being this that these those it its i you he she we they my your
    do does did not no so very just about into over after before up out
    """.split()
)

# Palabras ESTRUCTURALES: negadores, intensificadores, atenuadores y
# conectores adversativos. Aunque gramaticalmente sean "palabras vacias", el
# clasificador necesita verlas: son las que definen el ALCANCE del
# sentimiento sobre el resto de la oracion. Nunca deben filtrarse como
# stopwords, o la negacion y el contraste se pierden antes de tiempo.
STRUCTURAL = frozenset(
    {
        # negadores
        "no", "nunca", "jamas", "nada", "ni", "sin", "tampoco", "nadie",
        "ningun", "ninguna", "not", "never", "none", "without", "neither",
        # intensificadores
        "muy", "muchisimo", "extremadamente", "totalmente", "bastante",
        "demasiado", "superguau", "tremendamente", "absurdamente",
        "increiblemente", "very", "extremely", "totally", "really", "so",
        "super", "best", "absolutely", "mas",
        # atenuadores
        "apenas", "poco", "algo", "ligeramente", "medianamente", "slightly",
        "kinda", "somewhat", "barely",
        # conectores adversativos
        "pero", "aunque", "embargo", "obstante", "contrario", "however",
        "although", "but", "nevertheless", "still", CONTRAST_TOKEN,
    }
)

STOPWORDS -= STRUCTURAL



def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Minusculas, sin acentos, sin URLs ni usuarios; conserva los cortes."""
    text = strip_accents(text.lower())
    text = URL_RE.sub(" ", text)
    text = RT_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    text = re.sub(r"\.\.\.|[.!?;:]+", f" {PAUSE_TOKEN} ", text)
    text = re.sub(r"[,]+", f" {COMMA_TOKEN} ", text)
    text = re.sub(r"[^a-z0-9#'_ ]+", " ", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    """
    Devuelve tokens significativos, en orden y con repeticiones.

    Los centinelas de puntuacion sobreviven al filtro de stopwords porque el
    clasificador los usa como frontera de clausula.
    """
    normalized = normalize(text)
    for phrase, marker in PHRASE_MAP.items():
        normalized = normalized.replace(phrase, marker)
    tokens = []
    for token in normalized.split(" "):
        if not token or len(token) <= 1:
            continue
        if token not in PUNCT_TOKENS and token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def extract_hashtags(text: str) -> list[str]:
    seen: list[str] = []
    for tag in USER_RE.findall(text.lower()):
        cleaned = re.sub(r"[^a-z0-9_#]", "", tag)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen