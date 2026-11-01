import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .engine import Engine, Request
from .errors import DowngradeError
from .platforms import data_root, discover


def manifest_path():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'manifests/fo4-1.10.163.0-en.json'


def parser():
    p = argparse.ArgumentParser(description='Downgrader 2.0 by FOLON Team — Steam Fallout 4 for Windows and Linux.')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--game-path', '--path', '-p', type=Path)
    p.add_argument('--staging-root', type=Path)
    p.add_argument('--steamcmd-root', type=Path)
    p.add_argument('--state-root', type=Path)
    p.add_argument('--check-inventory', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--content-root', type=Path, help='Existing app_377160 directory to verify/deploy')
    p.add_argument('--manifest', type=Path, default=manifest_path(), help='Trusted release-owned inventory; do not use untrusted manifests')
    p.add_argument('--json', action='store_true', help='Print structured result (not available for interactive download)')
    p.add_argument('--yes', action='store_true', help='Confirm deployment to the explicitly selected game path')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--linux', '-l', '-L', action='store_true', help=argparse.SUPPRESS)
    group = p.add_mutually_exclusive_group()
    for action in ('discover', 'preflight', 'dry-run', 'setup-steamcmd', 'download', 'verify-download', 'verify-only', 'deploy', 'resume', 'repair'):
        group.add_argument('--' + action, dest='action', action='store_const', const=action)
    p.set_defaults(action='preflight')
    return p


def make_request(args):
    base = data_root()
    game = args.game_path
    if game is None:
        found = discover()
        if len(found) != 1:
            raise DowngradeError('GAME_SELECTION_REQUIRED', 'Use --discover, then select one installation with --game-path.')
        game = found[0]
    return Request(game.resolve(), (args.staging_root or base / 'staging').absolute(),
                   (args.steamcmd_root or base / 'steamcmd').absolute(),
                   (args.state_root or base / 'transactions').absolute(), args.manifest.absolute(),
                   args.content_root.absolute() if args.content_root else None)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(argv)
    if not argv or (not args.linux and args.action == 'preflight' and '--preflight' not in argv and not args.json):
        args.gui = True
    try:
        if args.check_inventory:
            from .manifest import Manifest
            manifest = Manifest(args.manifest)
            manifest.require_inventory()
            print(json.dumps({'version': __version__, 'files': len(manifest.selected_files()), 'inventory_complete': True}))
            return 0
        if args.gui:
            from .qt import launch
            return launch(args)
        if args.action == 'discover':
            result = {'ok': True, 'installations': [str(p) for p in discover()]}
        else:
            if args.action == 'download' and (args.json or not sys.stdin.isatty()):
                raise DowngradeError('TERMINAL_REQUIRED', 'Interactive SteamCMD authentication requires a terminal without --json.')
            request = make_request(args)
            if args.action in ('deploy', 'resume', 'repair') and args.yes and args.game_path is None:
                raise DowngradeError('GAME_SELECTION_REQUIRED', '--yes requires an explicit --game-path.')
            confirmed = args.yes
            if args.action in ('deploy', 'resume', 'repair') and not confirmed and sys.stdin.isatty() and not args.json:
                print(f'Game: {request.game}')
                confirmed = input('Type YES to modify this game installation: ') == 'YES'
            result = Engine(request, emit=lambda e: None if args.json else print(e.get('message', e['stage']))).run(args.action, confirmed)
    except DowngradeError as error:
        result = {'ok': False, 'error_code': error.code, 'message': error.message, 'game_modified': False}
    except (OSError, ImportError):
        result = {'ok': False, 'error_code': 'STARTUP_FAILED', 'message': 'Check the selected paths and install the pinned dependencies.', 'game_modified': False}
    except KeyboardInterrupt:
        return 130
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else (130 if result.get('error_code') == 'CANCELLED' else 1)


if __name__ == '__main__':
    raise SystemExit(main())
