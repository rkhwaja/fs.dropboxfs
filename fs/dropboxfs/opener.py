__all__ = ['DropboxOpener']

from fs.opener import Opener

from .dropboxfs import DropboxFS

class DropboxOpener(Opener): # pylint: disable=too-few-public-methods
	protocols = ['dropbox']

	def open_fs(self, fs_url, parse_result, writeable, create, cwd): # pylint: disable=too-many-arguments
		_, _, directory = parse_result.resource.partition('/')
		options = {
			'access_token': parse_result.params.get('access_token'),
			'refresh_token': parse_result.params.get('refresh_token'),
			'app_key': parse_result.params.get('app_key'),
			'app_secret': parse_result.params.get('app_secret')
		}

		fs = DropboxFS(**options)

		if directory:
			return fs.opendir(directory)
		return fs
