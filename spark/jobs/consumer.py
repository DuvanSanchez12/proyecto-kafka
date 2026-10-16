"""Consumidor unico: Kafka -> Spark por micro-lotes -> PostgreSQL."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sentiment_stream import main


if __name__ == "__main__":
    raise SystemExit(main())
