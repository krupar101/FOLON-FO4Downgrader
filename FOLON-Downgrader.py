"""Shared Windows/Linux entry point. Use --gui for the optional Qt frontend."""
from folon_downgrader.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
