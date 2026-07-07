from __future__ import annotations

import argparse
import json
import logging

from .commands import require_tools
from .config import Config
from .service import Service


def main() -> None:
    parser = argparse.ArgumentParser(description="MoLive NAS incremental Live Photo converter")
    parser.add_argument("command", choices=["scan", "daemon", "status"])
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    service = Service(Config())
    if args.command == "status":
        print(json.dumps(service.db.stats(), ensure_ascii=False, indent=2))
    elif args.command == "scan":
        require_tools()
        service.process_once()
    else:
        service.daemon()


if __name__ == "__main__":
    main()
