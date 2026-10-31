from dataclasses import dataclass
from enum import Enum


class Stage(str, Enum):
    PREFLIGHT = 'preflight'
    BOOTSTRAP = 'bootstrap_steamcmd'
    DOWNLOAD = 'download'
    VERIFY_DOWNLOAD = 'verify_download'
    PREPARE = 'prepare_deployment'
    DEPLOY = 'deploy'
    VERIFY_TARGET = 'verify_target'
    COMPLETE = 'complete'
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
