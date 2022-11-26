__all__ = ['DropboxOpener']

from fs.opener import Opener

from .dropboxfs import DropboxFS

class DropboxOpener(Opener): # pylint: disable=too-few-public-methods
	protocols = ['dropbox']

	def open_fs(self, fs_url, parse_result, writeable, create, cwd): # pylint: disable=too-many-arguments
		_, _, directory = parse_result.resource.partition('/')
		fs = DropboxFS(accessToken=parse_result.params['access_token'], refreshToken=parse_result.params['refresh_token'])

		if directory:
			return fs.opendir(directory)
		return fs
