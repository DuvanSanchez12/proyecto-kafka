"""
Corpus sintetico de menciones de marca.

Genera mensajes estilo red social con una *etiqueta de verdad*
(``expected``) conocida de antemano. Esa etiqueta es lo que despues
compara el clasificador por divide y venceras para medir su exactitud.

Los casos duros (negaciones, intensificadores, contraste adversativo y
polaridad mixta) estan incluidos a proposito: son los que separan un
clasificador plano de un clasificador que razona por tramos.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


POSITIVO = "POSITIVO"
NEUTRAL = "NEUTRAL"
NEGATIVO = "NEGATIVO"


@dataclass(frozen=True)
class Template:
    text: str
    sentiment: str
    difficulty: str = "facil"  # facil | media | dificil


SOPORTE_POSITIVO = ["increible", "impecable", "excelente", "maravilloso", "fantastico"]
SOPORTE_NEGATIVO = ["terrible", "horrible", "pesimo", "decepcionante", "frustrante"]
INTENSIFICADORES = ["muy", "extremadamente", "muchisimo", "totalmente", "bastante"]
ATENUADORES = ["apenas", "un poco", "algo", "ligeramente"]

HASHTAGS_BASE = [
    "lanzamiento", "opiniones", "review", "novedades", "tendencias",
    "compras", "calidad", "experiencia", "promo", "unboxing",
]
HASHTAGS_POS = ["meencanta", "favorito", "recomendado", "godmode"]
HASHTAGS_NEG = ["pesimo", "eviten", "estafa", "decepcion", "frufrustrante"]


# ---------------------------------------------------------------------------
# Plantillas por clase. El vocabulario coincide con el lexicon del job Spark.
# ---------------------------------------------------------------------------
TEMPLATES: list[Template] = [
    # ------------------------------- POSITIVAS -------------------------------
    Template("Acabo de comprar el {brand} nuevo y la verdad es que es {pos}", POSITIVO),
    Template("El {brand} de este ano es {pos}, sin duda", POSITIVO),
    Template("Me encanta el diseno del {brand} nuevo, se nota el trabajo", POSITIVO),
    Template("Servicio al cliente del {brand} {int} rapido y amable", POSITIVO),
    Template("Relacion precio-calidad del {brand}: {pos} en serio", POSITIVO),
    Template("Recomiendo el {brand} a todo el mundo, es {pos}", POSITIVO),
    Template("El {brand} {int} bien disenado, se nota el trabajo", POSITIVO),
    Template("Llevo tres meses con el {brand} y sigue {pos}", POSITIVO),
    Template("La garantia del {brand} me salvo, {int} {pos} la atencion", POSITIVO, "media"),
    Template("{brand} por fin saco un producto que vale la pena, {pos} de verdad", POSITIVO, "dificil"),
    Template("Compre el {brand} y quedo muy feliz con el producto", POSITIVO, "dificil"),
    Template("El nuevo {brand} es bonito y ademas {pos}", POSITIVO, "media"),
    Template("Actualizacion del {brand}: {pos} en cada detalle", POSITIVO, "media"),
    Template("My {brand} arrived fast and the quality is {pos}", POSITIVO),
    Template("The {brand} is absolutely amazing, {pos}", POSITIVO, "media"),
    Template("Dicen que el {brand} es caro pero es {pos} y durable", POSITIVO, "dificil"),

    # ------------------------------- NEUTRALES -------------------------------
    Template("Alguien sabe cuando sale la nueva version del {brand}?", NEUTRAL),
    Template("Estan buscando testers para el {brand} en mi ciudad", NEUTRAL),
    Template("El {brand} se anuncia para el proximo trimestre segun el informe", NEUTRAL),
    Template("Consulta: el {brand} tiene version para tablet?", NEUTRAL),
    Template("Hoy fui a la tienda y vi el {brand} exhibido junto a la entrada", NEUTRAL),
    Template("Pregunta para los usuarios: cuanto dura la bateria del {brand}?", NEUTRAL),
    Template("Hay una tienda {brand} cerca del parqueo del centro", NEUTRAL),
    Template("El {brand} se lanza en mi pais el proximo ano", NEUTRAL, "dificil"),
    Template("Comparando el {brand} con la competencia, alguien tiene opinion?", NEUTRAL),
    Template("Vi un documental sobre la historia de {brand} en streaming", NEUTRAL),
    Template("Did anyone else order the {brand} today?", NEUTRAL),
    Template("The {brand} store in the mall is open until 9pm", NEUTRAL),
    Template("Aqui van las especificaciones tecnicas del {brand} nuevo", NEUTRAL),
    Template("Alguien tiene el numero de seguimiento de un pedido {brand}?", NEUTRAL),
    Template("El nuevo {brand} se presenta manana en la ciudad", NEUTRAL),

    # ------------------------------- NEGATIVAS -------------------------------
    Template("El {brand} es {neg}, devuelvo el dinero", NEGATIVO),
    Template("{int} {neg} el ultimo {brand} que compre", NEGATIVO),
    Template("El {brand} llego roto y nadie responde, {neg} experiencia", NEGATIVO, "media"),
    Template("Llevo tres semanas esperando el {brand} y sigue {neg}", NEGATIVO, "media"),
    Template("Pague el doble por el {brand} y el servicio es {neg}", NEGATIVO, "media"),
    Template("Mala experiencia con {brand}, la app se cae una y otra vez", NEGATIVO),
    Template("El {brand} me ha generado un problema tras otro, todo {neg}", NEGATIVO, "media"),
    Template("Odio este modelo del {brand}, {int} {neg}", NEGATIVO),
    Template("La atencion al cliente del {brand} es {neg}, no resuelve nada", NEGATIVO, "dificil"),
    Template("After two months the {brand} battery died and support was terrible", NEGATIVO),
    Template("Requested a refund for my {brand} and they ignored me for 9 days", NEGATIVO, "media"),
    Template("The {brand} app crashed twice today, awful experience", NEGATIVO),
    Template("Cancelaron mi pedido de {brand} sin avisar, {int} {neg}", NEGATIVO, "dificil"),
    Template("Estan cobrando de mas en la tienda {brand}, {int} {neg}", NEGATIVO, "media"),
    Template("Sinceramente el {brand} de este ano es {neg}", NEGATIVO),

    # ------------------------------- CASOS DUROS ------------------------------
    # Negacion: llega una palabra positiva con negador delante -> debe salir negativa.
    Template("El {brand} no es nada {pos_word}, es una deception", NEGATIVO, "dificil"),
    Template("Nunca pense que el {brand} fuera tan {pos_word}, me arrepenti", NEGATIVO, "dificil"),
    Template("No es que el {brand} sea malo, pero si es {neg}", NEGATIVO, "dificil"),
    Template("El {brand} no es perfecto, sin embargo casi todo esta {pos}", POSITIVO, "dificil"),
    Template("El soporte del {brand} no respondio, sin embargo el producto es {pos}", POSITIVO, "dificil"),
    # Contraste adversativo: manda la clausula que sigue al conector.
    Template("El {brand} es bonito, pero el precio es {neg}", NEGATIVO, "dificil"),
    Template("El {brand} es {pos}, aunque el envio fue {neg}", NEUTRAL, "dificil"),
    Template("Me gusta el {brand}, pero el soporte es {neg}", NEGATIVO, "dificil"),
    Template("El packaging del {brand} es {pos}, no obstante la app es {neg}", NEGATIVO, "dificil"),
    Template("Gran diseno del {brand}, aunque la calidad de materiales es {neg}", NEGATIVO, "dificil"),
    # Intensificadores y atenuadores.
    Template("El {brand} es {at} bueno, solo cumple", NEUTRAL, "media"),
    Template("El {brand} es {int} {pos}, es lo mejor que he probado", POSITIVO),
    Template("El {brand} es {at} {neg}, solo eso", NEGATIVO, "media"),
    Template("La app del {brand} funciona {at} bien", NEUTRAL, "media"),
    # Varias clausulas a la vez.
    Template("Mi opinion del {brand}: calidad {pos} y atencion {neg}", NEUTRAL, "dificil"),
    Template("El {brand} es rapido pero caro y el envoltorio es {neg}", NEUTRAL, "dificil"),
    Template("Servicio del {brand} {pos}, precios altos", POSITIVO, "media"),
    Template("Diseno {pos}, colores feos", NEUTRAL, "dificil"),
    Template("Mi pedido de {brand} llego tarde y el soporte fue {pos}, gracias", POSITIVO, "dificil"),
    Template("No compro mas {brand}, lo mio fue {neg}", NEGATIVO),
]


_PLACEHOLDERS = {
    "{pos}": lambda: random.choice(SOPORTE_POSITIVO),
    "{pos_word}": lambda: random.choice(SOPORTE_POSITIVO),
    "{neg}": lambda: random.choice(SOPORTE_NEGATIVO),
    "{int}": lambda: random.choice(INTENSIFICADORES),
    "{at}": lambda: random.choice(ATENUADORES),
}

DIFFICULTY_WEIGHTS = {"facil": 3.0, "media": 1.4, "dificil": 1.2}


def _render(template: str, brand: str) -> str:
    text = template.replace("{brand}", brand)
    for token, factory in _PLACEHOLDERS.items():
        text = text.replace(token, factory())
    return " ".join(text.split())


def pick_template() -> Template:
    return random.choices(
        TEMPLATES,
        weights=[DIFFICULTY_WEIGHTS[t.difficulty] for t in TEMPLATES],
        k=1,
    )[0]


def pick_hashtags(sentiment: str) -> list[str]:
    tags = [random.choice(HASHTAGS_BASE)]
    roll = random.random()
    if sentiment == POSITIVO and roll < 0.45:
        tags.append(random.choice(HASHTAGS_POS))
    elif sentiment == NEGATIVO and roll < 0.45:
        tags.append(random.choice(HASHTAGS_NEG))
    if random.random() < 0.2:
        tags.append(random.choice(HASHTAGS_BASE))
    seen: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return seen


def make_mention(brand: str, author_pool: list[str], platform: str) -> dict:
    template = pick_template()
    followers = int(abs(random.gauss(1200, 9000))) + 15
    sentiment = template.sentiment
    return {
        "text": _render(template.text, brand),
        "expected": sentiment,
        "author": random.choice(author_pool),
        "platform": platform,
        "lang": "en" if random.random() < 0.18 else "es",
        "hashtags": pick_hashtags(sentiment),
        "author_followers": followers,
        "likes": max(0, int(abs(random.gauss(45, 180)))),
        "shares": max(0, int(abs(random.gauss(6, 22)))),
    }