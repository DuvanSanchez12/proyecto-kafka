"""Productor 2: flujo de publicaciones estilo Reddit."""

import os

from .main import MentionProducer


def main() -> int:
    rate = float(os.getenv("PRODUCER_REDDIT_RATE", os.getenv("PRODUCER_RATE", "12")))
    return MentionProducer("reddit_api_simulada", ["reddit"], rate).run()


if __name__ == "__main__":
    raise SystemExit(main())
