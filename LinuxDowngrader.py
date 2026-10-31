"""Compatibility entry point; all downgrade behavior lives in the shared engine."""
from folon_downgrader.cli import main


def Linux(Path='', **kwargs):
    if kwargs:
        raise ValueError('Credentials are no longer accepted as Python arguments. Use interactive --download.')
    return main(['--game-path', str(Path)] if Path else [])


if __name__ == '__main__':
    raise SystemExit(main())
