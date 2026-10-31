"""Compatibility entry point for the shared Qt frontend."""
from folon_downgrader.cli import main


def Windows(steampath=None):
    return main(['--gui'] + (['--game-path', str(steampath)] if steampath else []))


if __name__ == '__main__':
    raise SystemExit(main(['--gui']))
