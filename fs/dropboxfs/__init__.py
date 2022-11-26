from logging import getLogger, NullHandler

from .dropboxfs import DropboxFS
from .opener import DropboxOpener

getLogger(__name__).addHandler(NullHandler())
