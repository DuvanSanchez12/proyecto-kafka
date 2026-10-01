# BrandPulse

Análisis de sentimiento de marca **en tiempo real** sobre un stream de redes
sociales, con Kafka + Spark Structured Streaming + Postgres y un dashboard
React con grafo de co-ocurrencia estilo Neo4j.

El núcleo del proyecto es un **clasificador de sentimiento por divide y
vencerás** (no un `if` sobre palabras): la mención se parte por la mitad, cada
mitad se resuelve por recursión y los resultados se **combinan con una
operación `Merge(A, B)`** con semántica de lenguaje (negación con alcance hacia
adelante y contraste adversativo). El árbol de recursión hace, por diseño, el
mismo trabajo que un merge sort, y su complejidad se **mide**, no se enuncia.

---

## Arquitectura

```
                 ┌─────────────┐   JSON    ┌──────────────────────────┐
  API social  →  │  productor  │ ────────► │  Kafka (KRaft, 3 part.)  │
  (sintética)    │  Python     │  topic    └───────────┬──────────────┘
                 └─────────────┘  "menciones"          │
                                                       ▼
                              ┌────────────────────────────────────────┐
                              │  Spark Structured Streaming            │
                              │  foreachBatch → mapPartitions          │
                              │  ┌──────────────────────────────────┐  │
                              │  │ divide y vencerás  +  merge sort │  │
                              │  └──────────────────────────────────┘  │
                              └───────────────┬────────────────────────┘
                                              │ escribe
                          ┌───────────────────┴───────────────────┐
                          ▼                                       ▼
                 ┌─────────────────┐                    ┌──────────────────┐
                 │   Postgres      │  ◄── instantánea ──│  grafo de        │
                 │   mentions      │      recomputada   │  co-ocurrencia   │
                 │   complexity    │      por micro-lote│  (nodes/edges)   │
                 └────────┬────────┘                    └──────────────────┘
                          │ lee (solo lectura)
                          ▼
                 ┌─────────────────┐        ┌───────────────────────────┐
                 │  API FastAPI    │ ◄────► │  Dashboard React (nginx)  │
                 └─────────────────┘  /api  │  KPIs · tendencia · grafo │
                                            └───────────────────────────┘
```

Servicios (Docker Compose, red `brandpulse`):

| Servicio | Imagen | Rol |
|---|---|---|
| `kafka` | `apache/kafka:3.9.0` | broker en modo KRaft (sin ZooKeeper) |
| `postgres` | `postgres:16-alpine` | warehouse de sentimiento |
| `producer` | `python:3.11-slim` | genera y publica menciones sintéticas |
| `spark-master` / `spark-worker` | `./spark` | cluster de Spark |
| `spark-job` | `./spark` | job de Structured Streaming |
| `api` | `./api` | REST de solo lectura |
| `frontend` | `./frontend` | dashboard estático + proxy `/api` |

---

## El algoritmo

### Divide y vencerás con estado de cláusula

```
D&C(tokens, lo, hi)
    caso base  : |tramo| <= BASE       → escaneo lineal; deja (negado, factor) al cierre
    división   : mid = lo + |tramo| // 2
    conquista  : (L, R) = (D&C(lo, mid), D&C(mid, hi))
    combinación: Merge(L, R) + traspaso del estado de L a la cláusula abierta de R
```

La sutileza que hace que el resultado **no dependa de dónde se corta** la
recursión (propiedad verificada en los tests) es separar dos cosas que viajan
distinto por el árbol:

* **magnitud** (polaridad × intensificadores) → se **multiplica** y se propaga
  hacia la derecha;
* **negación** → es un **booleano por cláusula**, se propaga hacia la derecha y
  es **idempotente** (`"no ... nada increíble"` refuerza, no cancela).

Porque la negación en español tiene alcance hacia adelante, un modificador de la
mitad derecha nunca alcanza a la mitad izquierda: esa asimetría es lo que hace
que el árbol completo sea consistente.

Casos que resuelve correctamente (ver `spark/tests/test_algorithms.py`):

| Texto | Esperado | Por qué |
|---|---|---|
| `es increíble` | positivo | polaridad directa |
| `no es nada increíble` | negativo | negación con alcance de cláusula |
| `es increíble, pero es terrible` | negativo | el contraste adversativo pesa la última cláusula |
| `es bonito aunque el envío fue mal` | negativo | igual: domina la cláusula posterior al conector |

### Complejidad (medida, no solo citada)

```
T(n) = 2·T(n/2) + Θ(m)      m = items de opinión del tramo
     = Θ(n log n)           (m ≤ n, y Θ(n) en el peor caso)
```

* la profundidad del árbol es `⌈log₂(n / BASE)⌉`;
* el número de mezclas es `2^d − 1`, **igual en el mejor y el peor caso**
  (no hay pivote): Θ(n log n) garantizado;
* la cota de comparaciones del merge sort es `n·log₂(n) − n + 1`.

Cada micro-lote persiste en `complexity_stats` las comparaciones **reales**
(contadas en ejecución) junto a la **cota teórica**, y el dashboard las grafica
juntas. Lo esperado es que `real ≤ cota` siempre.

### Merge sort

`merge_sort` bottom-up instrumentado, `merge(A, B)` estable con contador de
comparaciones, `k_way_merge` con heap (`O(N log k)`) y
`distributed_merge_sort` sobre RDD. Se usa para ordenar los items de opinión por
peso antes de la reducción final.

---

## El grafo de co-ocurrencia

Es una **vista derivada** de `mentions`: en cada micro-lote se recalcula completo
y se reemplaza dentro de una transacción (`DELETE` + `INSERT`). Eso lo hace
**idempotente** (un reintento de Spark no duplica aristas) y siempre consistente
con los hechos.

* **Nodos**: `MARCA`, `USUARIO`, `HASHTAG`, `PALABRA`, `PLATAFORMA`, con peso
  (`COUNT`), desglose pos/neu/neg y sentimiento promedio.
* **Aristas**: `MENCIONA`, `PUBLICA`, `ETIQUETA`, `APARECE_EN`, `USA`.
* El frontend lo dibuja con **Cytoscape + layout cose-bilkent** (force-directed),
  coloreando nodos por tipo y bordeando por sentimiento promedio.

---

## Puesta en marcha

Requisitos: Docker con Compose.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps          # esperar a que kafka/postgres/spark estén healthy
```

* Dashboard: http://localhost:5173
* API: http://localhost:8000/api/health
* Spark UI: http://localhost:8080
* Kafka (desde el host): `localhost:9094`

### En Windows

Todo corre dentro de contenedores, así que el proyecto funciona igual. Las
diferencias son de entorno, no de código.

**Requisitos**

1. **Docker Desktop con WSL2** (obligatorio). En *Settings → General* activá
   *Use the WSL 2 based engine*. Es lo que hace que los bind mounts y el
   networking funcionen bien.
2. **Memoria**: la imagen de Spark necesita RAM. En *Settings → Resources* subí
   a **6 GB** (mínimo 4). Con los valores por defecto de Windows el build o el
   job se pueden morir por falta de memoria.
3. **Disco**: activá *Virtual disk limit* en un espacio razonable si querés
   evitar que crezca sin control; el build de la imagen de Spark baja unos
   cientos de MB.

**Clonar y arrancar** (PowerShell o CMD)

```powershell
git clone https://github.com/DuvanSanchez12/proyecto-kafka.git
cd proyecto-kafka
copy .env.example .env
docker compose up --build -d
docker compose ps
```

Dos diferencias concretas respecto a macOS/Linux:

- **Finales de línea.** El repo trae un `.gitattributes` que fuerza LF, así que
  Git en Windows no convierte los `.yml`, `Dockerfile`, `.sh` ni `.sql` a CRLF.
  Sin eso, los scripts que corren *dentro* de los contenedores fallarían con
  errores raros tipo `\r: command not found`. Si clonás un fork viejo, borrá la
  carpeta y volvé a clonar para que aplique.
- **Rutas montadas.** Solo hay un bind mount, `./db/init`, y Compose lo traduce
  solo. No hace falta tocar rutas ni usar `C:\...`.

**Comandos útiles en PowerShell**

```powershell
docker compose logs -f spark-job     # micro-lotes en vivo
docker compose ps                     # estado de los servicios
docker compose down                   # parar (conserva los datos)
docker compose down -v                # parar y borrar los datos
```

Si PowerShell se queja de que no reconoce `docker`, reiniciá la terminal tras
instalar Docker Desktop: el PATH se agrega al final de la instalación.

**Si tenés WSL2 y preferís trabajar desde la distro**, el flujo es idéntico al
de Linux: `cp .env.example .env && docker compose up --build -d`. Es la opción
más cómoda si ya usás la terminal de Ubuntu.

El productor empieza a publicar apenas Kafka está disponible y Spark cierra un
micro-lote cada `SPARK_TRIGGER` segundos (10 por defecto). En ~1 minuto ya hay
KPIs, tendencia y grafo.

Para escalar el volumen:

```bash
PRODUCER_RATE=200 docker compose up -d producer
docker compose up -d --scale spark-worker=2   # (ajustar cores/memoria)
```

O más simple y multiplataforma: cambiá `PRODUCER_RATE` en `.env` y recreá el
servicio. En Windows con PowerShell, `PRODUCER_RATE=200 docker compose up -d`
**no** funciona (esa sintaxis es de bash); usá el `.env`.

---

## Endpoints de la API

| Ruta | Devuelve |
|---|---|
| `GET /api/health` | estado del pipeline, marca, último lote |
| `GET /api/kpis` | totales, exactitud, promedios, distribución |
| `GET /api/trend?minutes=30` | serie por minuto por sentimiento |
| `GET /api/graph?limit=140` | nodos y aristas del grafo |
| `GET /api/messages?limit=30` | últimas menciones con su clasificación |
| `GET /api/accuracy` | matriz real × predicho y exactitud por clase |
| `GET /api/complexity?limit=40` | complejidad medida vs. cota teórica por lote |

---

## Verificación

Pruebas del núcleo algorítmico (sin Spark ni red):

```bash
pip install pytest
python -m pytest spark/tests -q
```

Cubren tres propiedades:

1. `merge_sort` ordena y respeta la cota `n log₂(n)`.
2. El clasificador acierta los casos lingüísticos duros (negación, doble
   negación, contraste, intensificadores).
3. El resultado **no depende del tamaño del caso base**: el árbol produce la
   misma clasificación que escanear la mención completa de un tirón (prueba
   empírica de que la combinación es asociativa).

Sobre el corpus sintético (~66 plantillas) la exactitud observada es del orden
del **94 %**, y el arquitecto de la prueba de invariancia reporta **0
discrepancias** entre distintos tamaños de caso base.

---

## Estructura del repositorio

```
proyecto-kafka/
├── docker-compose.yml
├── .env.example                   # plantilla (copiar a .env)
├── .gitattributes                 # fuerza LF: necesario en Windows/WSL2
├── db/init/01_schema.sql          # tablas, vistas, índices
├── producer/app/                  # corpus sintético + publisher Kafka
├── spark/
│   ├── Dockerfile                 # venv + conectores Kafka en $SPARK_HOME/jars
│   └── jobs/
│       ├── sentiment_stream.py    # Structured Streaming (foreachBatch)
│       ├── config.py
│       ├── algorithms/            # merge_sort, complexity, sentiment_dnc
│       ├── text/                  # normalización y lexicones
│       ├── graph/builder.py       # SQL de la instantánea del grafo
│       └── sinks/postgres.py      # escritura distribuida + telemetría
├── api/app/                       # FastAPI (solo lectura)
└── frontend/src/                  # React + Vite + Cytoscape + Recharts
```
