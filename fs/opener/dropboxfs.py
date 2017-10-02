from .base import Opener

class DropboxOpener(Opener):
	protocols = ["dropbox"]

	@staticmethod
	def open_fs(fs_url, parse_result, writeable, create, cwd):
		from ..dropboxfs import DropboxFS
		_, _, directory = parse_result.resource.partition('/')
		fs = DropboxFS(accessToken=parse_result.params["access_token"])

		if directory:
			return fs.opendir(directory)
		else:
			return fs
