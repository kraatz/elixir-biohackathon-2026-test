"""Entry point: python -m spe_agent. Configuration from SPE_AGENT_CONFIG, keys from the environment."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import ConfigError, load_config, load_secrets


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per sandbox request and probe otherwise
    path = Path(os.environ.get("SPE_AGENT_CONFIG", "/etc/spe-agent/agent.yaml"))
    try:
        config = load_config(path)
        app = create_app(config, load_secrets(config, os.environ))
    except ConfigError as e:
        print(f"spe-agent: {e}", file=sys.stderr)
        return 2
    uvicorn.run(app, host=os.environ.get("SPE_AGENT_HOST", "0.0.0.0"), port=int(os.environ.get("SPE_AGENT_PORT", "8100")),
                server_header=False, proxy_headers=False, access_log=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
