"""Productor 1: flujo de menciones estilo X."""

import os

from .main import MentionProducer


def main() -> int:
    rate = float(os.getenv("PRODUCER_X_RATE", os.getenv("PRODUCER_RATE", "12")))
    return MentionProducer("x_api_simulada", ["x"], rate).run()


if __name__ == "__main__":
    raise SystemExit(main())
