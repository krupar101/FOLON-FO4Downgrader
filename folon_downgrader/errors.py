from dataclasses import dataclass
from enum import Enum

STEAM_RECOVERY = ('The downgrade may be incomplete. Verify integrity of game files or reinstall Fallout 4 '
                  'through Steam to restore the Steam version, then rerun the downgrade if wanted. '
                  'Steam may not restore third-party mods or custom files.')


class Stage(str, Enum):
    PREFLIGHT = 'preflight'
    BOOTSTRAP = 'bootstrap_steamcmd'
    DOWNLOAD = 'download'
    VERIFY_DOWNLOAD = 'verify_download'
    PREPARE = 'prepare_deployment'
    DEPLOY = 'deploy'
    VERIFY_TARGET = 'verify_target'
    COMPLETE = 'complete'
    CLEANUP = 'cleanup_downloads'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


@dataclass
class DowngradeError(Exception):
    code: str
    message: str

    def __str__(self):
        return f'{self.code}: {self.message}'


def fail(code, message):
    raise DowngradeError(code, message)
