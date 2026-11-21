"""Punto di ingresso per PyInstaller (il modulo __main__ del pacchetto usa import relativi)."""
import sys

from meshlens.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
