from __future__ import annotations

import argparse

from src.interfaces.web.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inicia o frontend web da suite de automacao do Consignado."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host para publicar o servidor web. Padrao: 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Porta para publicar o servidor web. Padrao: 8765",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

