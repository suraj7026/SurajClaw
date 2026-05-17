"""``python -m clawcli`` shim — dispatches to :func:`clawcli.main.main`."""
from __future__ import annotations

from clawcli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
