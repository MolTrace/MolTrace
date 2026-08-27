"""PyInstaller entry point for the packaged local science service.

A script rather than `python -m nmrcheck.local_service_main`, because PyInstaller
freezes a script. It does nothing but call the same `main()` the module entry
calls, so the two cannot drift into different startup behaviour.
"""

from nmrcheck.local_service_main import main

if __name__ == "__main__":
    raise SystemExit(main())
