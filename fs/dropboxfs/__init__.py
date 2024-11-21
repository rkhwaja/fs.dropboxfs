from logging import getLogger, NullHandler

from .dropboxfs import * # noqa: F401, F403, RUF100
from .opener import * # noqa: F401, F403, RUF100

getLogger(__name__).addHandler(NullHandler())
