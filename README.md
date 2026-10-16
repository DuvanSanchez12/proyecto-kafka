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
  ┌────────────────────┐   JSON    ┌──────────────────────────┐
  X simulado ─► productor X ───────┐ │ Kafka (KRaft, 3 part.)   │
  Reddit sim. ─► productor Reddit ─┴►│ topic "menciones"        │
                 (Python, paralelos)  └───────────┬──────────────┘
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
                 │   Postgres      │                    │  Neo4j           │
                 │   mentions      │      recomputada   │  grafo de        │
                 │   complexity    │◄── por micro-lote ─│  co-ocurrencia   │
                 │   buckets       │   (nodos/aristas)  │  (nodos:MARCA…)  │
                 └────────┬────────┘                    └────────┬─────────┘
                          │ lee (solo lectura)                   │ lee
                          └──────────────┬────────────────────────┘
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
| `neo4j` | `neo4j:5.23-community` | grafo de co-ocurrencia (nodos/aristas) |
| `producer-x` | `python:3.11-slim` | primera fuente simulada (X) |
| `producer-reddit` | `python:3.11-slim` | segunda fuente simulada (Reddit) |
| `spark-master` / `spark-worker` | `./spark` | cluster de Spark |
| `spark-job` | `./spark` | consumidor único Spark Structured Streaming (`consumer.py`) |
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

## El grafo de co-ocurrencia (Neo4j)

El grafo **no se materializa en Postgres**: vive en **Neo4j**, un servicio más
de Docker Compose (`neo4j`, imagen `neo4j:5.23-community`). No hay que instalar
nada en la máquina anfitriona.

* **Bolt** (driver): `neo4j://neo4j:7687` dentro de la red `brandpulse`, y
  `localhost:7687` desde el host.
* **Neo4j Browser**: http://localhost:7474 (usuario `neo4j`, password `NEO4J_PASSWORD` del `.env`).

### Cómo se construye: siembra + incremental

Es una **vista derivada** de `mentions`, pero en vez de reconstruirse completa
en cada micro-lote, **crece en vivo**:

1. **Siembra (`seed_graph`)** — al arrancar el job, una sola vez, Spark agrega el
   histórico de `mentions` y reconstruye todo el grafo. Así no se pierde lo ya
   procesado aunque el `spark-job` se reinicie.
2. **Incremental (`apply_delta`)** — en cada micro-lote los executors traducen las
   menciones nuevas a contribuciones (nodos y aristas con su peso y sentimiento)
   y el driver las **suma** a Neo4j con `MERGE` + `+=`. El grafo se ve crecer
   lote a lote.

```
  mentions (Postgres)                    Neo4j
        │                                   ▲
        │  seed_graph (1 vez al arrancar)   │  MATCH (n) DETACH DELETE n
        └───────────────────────────────────┤  + MERGE de la instantánea
                                            │
   micro-lote ─► analyze_partition          │  apply_delta (idempotente)
   (executors)   calcula el delta ──────────┘  MERGE + weight += …
```

**Idempotencia.** Spark puede reintentar un micro-lote. Para no contar dos veces
el mismo lote, `apply_delta` deja un nodo marcador `(:Batch {id})`; si ya existe,
no hace nada. El marcador y los incrementos se escriben en la **misma
transacción**, así que un reintento nunca duplica pesos. `seed_graph` borra los
nodos del grafo pero conserva los marcadores de lote.

### Modelo

* **Nodos** (etiqueta nativa de Neo4j): `MARCA`, `USUARIO`, `HASHTAG`,
  `PALABRA`, `PLATAFORMA`. Propiedades: `weight`, `pos_count`, `neu_count`,
  `neg_count`, `score_sum` y `sentiment` (derivado de `score_sum / weight`).
* **Aristas**: tipo `REL` con propiedad `rel` (`MENCIONA`, `PUBLICA`,
  `ETIQUETA`, `APARECE_EN`, `USA`, `CON_HASHTAG`, `EN_PLATAFORMA`) más `weight`,
  `score_sum` y `sentiment`.
* **Marcadores internos**: `(:Batch {id})` (idempotencia). La API los filtra, no
  se ven en el dashboard.

### Qué archivos se agregaron/cambiaron

| Archivo | Rol |
|---|---|
| `docker-compose.yml` | servicio `neo4j`, volumen `neo4j-data` y variables `NEO4J_*` |
| `spark/jobs/graph/neo4j_sink.py` | `seed_graph` y `apply_delta` (Cypher) |
| `spark/jobs/sinks/postgres.py` | `GraphDelta`/`PartitionState` y armado del delta en `analyze_partition` |
| `spark/jobs/sentiment_stream.py` | siembra al arrancar + `apply_graph` por micro-lote |
| `spark/jobs/config.py` | `Neo4jConfig` (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`) |
| `api/app/neo4j_client.py` | lee el grafo desde Neo4j para `/api/graph` |
| `db/init/01_schema.sql` | se quitaron las tablas `graph_nodes`/`graph_edges` |

### Inspeccionarlo a mano

En Neo4j Browser (http://localhost:7474):

```cypher
MATCH (n) WHERE NOT n:Batch RETURN n LIMIT 100;                 // nodos
MATCH (m:MARCA)-[r:REL]-(x) RETURN m, r, x LIMIT 100;           // vecinos de la marca
MATCH (n) WHERE NOT n:Batch RETURN labels(n), count(*);         // cuántos por tipo
MATCH (b:Batch) RETURN count(b);                                // lotes aplicados
```

El frontend lo dibuja con **Cytoscape + layout cose-bilkent** (force-directed),
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
* Neo4j Browser: http://localhost:7474 (usuario `neo4j`, password definida en `.env`)
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

Los dos productores arrancan en paralelo y publican en el mismo topic Kafka.
Cada mensaje lleva `source` (`x_api_simulada` o `reddit_api_simulada`) para
identificar su origen. El consumidor `consumer.py` lee ambas fuentes; Spark
cierra un micro-lote cada `SPARK_TRIGGER` segundos (10 por defecto), analiza
las menciones y las inserta en PostgreSQL en grupos de `DB_BATCH_SIZE` filas
(500 por defecto). El destino es la base relacional PostgreSQL, no archivos.

Para ejecutar o revisar cada productor por separado:

```bash
docker compose up -d producer-x producer-reddit spark-job
docker compose logs -f producer-x producer-reddit spark-job
```

El `DB_BATCH_SIZE` se configura en `.env`. La clase `DatabaseConfig` construye
la configuración de PostgreSQL desde las variables `POSTGRES_*`; la clase
`BatchedPostgresWriter` recibe esa configuración en su constructor, abre la
conexión y ejecuta las inserciones SQL por lotes. Para verificar que llegan
datos de los dos orígenes:

```sql
SELECT source, platform, COUNT(*) AS menciones
FROM mentions
GROUP BY source, platform
ORDER BY source;
```

Si ya se había iniciado PostgreSQL antes de esta actualización, aplica una vez
la migración de la columna `source` al volumen existente:

```bash
docker compose exec -T postgres psql -U marketing -d brandpulse \
  -c "ALTER TABLE mentions ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'desconocida';"
```

### Compartir el dashboard con dos personas

Los dos usuarios abren **la misma URL del dashboard**; ambos ven el mismo
backend, los mismos eventos y las mismas filas de PostgreSQL del equipo que
ejecuta Docker. No se debe iniciar una copia local del proyecto en cada equipo.

1. En el escritorio anfitrión, inicia el proyecto con `docker compose up --build -d`.
2. En VS Code conectado al entorno que ejecuta Docker, abre **Ports** y elige
   **Forward a Port**. Escribe el puerto `5173` (o el valor de `WEB_PORT`).
3. Cambia la visibilidad del puerto reenviado a **Public** y copia la URL HTTPS
   que muestra VS Code. Esa es la URL que se comparte con la segunda persona.
4. La segunda persona abre esa misma URL en su navegador. Mantén Docker y el
   entorno anfitrión encendidos mientras se conectan.

La dirección pública la asigna VS Code al crear el reenvío en el equipo o
entorno remoto que ejecuta el proyecto. No existe hasta que se inicia el
servicio y se reenvía el puerto. Si se usa VS Code local sin un entorno remoto
con reenvío público, se necesita un túnel público configurado en ese equipo;
una dirección `localhost` solo funciona en el mismo equipo.

Para escalar el volumen:

```bash
PRODUCER_X_RATE=100 PRODUCER_REDDIT_RATE=100 docker compose up -d --force-recreate producer-x producer-reddit
```

También se pueden cambiar ambos valores en `.env` y recrear los servicios.
En PowerShell, edita `.env` en vez de anteponer variables con sintaxis Bash.

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
├── producer/app/                  # productor base + fuentes X y Reddit
│   ├── producer_x.py              # productor 1
│   ├── producer_reddit.py         # productor 2
├── spark/
│   ├── Dockerfile                 # venv + conectores Kafka en $SPARK_HOME/jars
│   └── jobs/
│       ├── consumer.py            # consumidor único de Spark
│       ├── sentiment_stream.py    # lógica Structured Streaming (foreachBatch)
│       ├── config.py
│       ├── algorithms/            # merge_sort, complexity, sentiment_dnc
│       ├── text/                  # normalización y lexicones
│       ├── graph/builder.py       # SQL de la serie por minuto (buckets)
│       ├── graph/neo4j_sink.py    # reconstruye el grafo en Neo4j (Cypher)
│       └── sinks/postgres.py      # escritura SQL por lotes + telemetría
├── api/app/                       # FastAPI (solo lectura)
└── frontend/src/                  # React + Vite + Cytoscape + Recharts
```
