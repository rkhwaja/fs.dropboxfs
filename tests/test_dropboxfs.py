from json import load, loads
from logging import info
from os import environ
from time import perf_counter
from unittest import TestCase
from uuid import uuid4

from fs.opener import open_fs, registry
from fs.subfs import SubFS
from fs.test import FSTestCases

from fs.dropboxfs import DropboxFS, DropboxOpener

def LoadCredentials():
	if 'DROPBOX_CREDENTIALS_FOR_CI' in environ:
		return loads(environ['DROPBOX_CREDENTIALS_FOR_CI'])

	with open(environ['DROPBOX_CREDENTIALS_PATH'], encoding='utf-8') as f:
		return load(f)

def FullFS():
	credentials = LoadCredentials()
	return DropboxFS(refresh_token=credentials.get('refresh_token'), app_key=credentials.get('app_key'), app_secret=credentials.get('app_secret'))

def test_list_root():
	fs = FullFS()
	assert fs.listdir('/') == fs.listdir('')

class PyFsCompatLayer:
    """PyFilesystem2 Python 3.12 compatibility layer.

    Adds a workaround for PyFilesystem2#568:
    https://github.com/PyFilesystem/pyfilesystem2/issues/568
    """

    assertRaisesRegexp = TestCase.assertRaisesRegex

class TestDropboxFS(FSTestCases, TestCase, PyFsCompatLayer):
	def make_fs(self):
		self.fullFS = FullFS()
		self.testSubdir = f'/tests/dropboxfs-test-{uuid4()}'
		return self.fullFS.makedirs(self.testSubdir)

	def destroy_fs(self, _):
		self.fullFS.removetree(self.testSubdir)

	def test_speed(self):
		startTime = perf_counter()
		for directory in ('a', 'b', 'c', 'd'):
			thisDirFS = self.fs.makedir(directory)
			for filename in ('A', 'B', 'C', 'D'):
				with thisDirFS.open(filename, 'w') as f:
					f.write(filename)
		info(f'Time for makedir/openbin {perf_counter() - startTime}')

		startTime = perf_counter()
		for path, info_ in self.fs.walk.info(namespaces=['basic', 'details']): # noqa: B007
			pass
		info(f'Time for walk {perf_counter() - startTime}')

	def test_upload_large_file(self):
		self.fs.writebytes('large_file.bin', b'x' * (150 * 1024 * 1024 * 2))

	def test_opener(self):
		registry.install(DropboxOpener())

		credentials = LoadCredentials()

		fs = open_fs(f"dropbox://{self.testSubdir}?refresh_token={credentials['refresh_token']}&app_key={credentials['app_key']}&app_secret={credentials['app_secret']}")

		# we're just testing that we can open a filesystem with a url
		assert isinstance(fs, SubFS), str(fs)
