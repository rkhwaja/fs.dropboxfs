from logging import getLogger, NullHandler

from .dropboxfs import DropboxFS # noqa: F401
from .opener import DropboxOpener # noqa: F401

getLogger(__name__).addHandler(NullHandler())
