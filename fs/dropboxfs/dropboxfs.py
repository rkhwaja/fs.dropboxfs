from contextlib import closing, contextmanager
from datetime import datetime
from io import BytesIO

from dropbox import Dropbox
from dropbox.files import DownloadError, FileMetadata, FolderMetadata, WriteMode
from dropbox.exceptions import ApiError
from fs.base import FS
from fs.errors import FileExpected, ResourceNotFound
from fs.info import Info
from fs.mode import Mode
from fs.subfs import SubFS
from fs.time import datetime_to_epoch, epoch_to_datetime

class DropboxFile(BytesIO):
	def __init__(self, dropbox, path, mode):
		self.dropbox = dropbox
		self.path = path
		self.mode = mode
		initialData = None
		self.rev = None
		try:
			metadata, response = self.dropbox.files_download(self.path)
			self.rev = metadata.rev
			with closing(response):
				# if (self.mode.reading or self.mode.appending or self.mode.updating) and not self.mode.truncate:
				if self.mode.reading and not self.mode.truncate:
					initialData = response.content
		except ApiError:
			# if the file doesn't exist, we don't need to read it's initial state
			pass
		super().__init__(initialData)
		if self.mode.appending and initialData is not None:
			# seek to the end
			self.seek(len(initialData))

	def close(self):
		if not self.mode.writing:
			return
		if self.rev is None:
			writeMode = WriteMode("add")
		else:
			writeMode = WriteMode("update", self.rev)
		metadata = self.dropbox.files_upload(self.getvalue(), self.path, mode=writeMode, autorename=False, client_modified=datetime.utcnow(), mute=False)
		# Make sure that we can't call this again
		self.path = None
		self.mode = None
		self.dropbox = None

class DropboxFS(FS):
	def __init__(self, accessToken):
		super().__init__()
		self.dropbox = Dropbox(accessToken)
		_meta = self._meta = {
			"case_insensitive": False, # I think?
			"invalid_path_chars": ":", # not sure what else
			"max_path_length": None, # don't know what the limit is
			"max_sys_path_length": None, # there's no syspath
			"network": True,
			"read_only": False,
			"supports_rename": False # since we don't have a syspath...
		}

	def __repr__(self):
		return "<DropboxDriveFS>"

	def _infoFromMetadata(self, metadata): # pylint: disable=no-self-use
		rawInfo = {
			"basic": {
				"name": metadata.name,
				"is_dir": isinstance(metadata, FolderMetadata),
			}
		}
		if isinstance(metadata, FileMetadata):
			rawInfo.update({
			"details": {
				"accessed": None, # not supported by Dropbox API
				"created": None, # not supported by Dropbox API?,
				"metadata_changed": None, # not supported by Dropbox
				"modified": datetime_to_epoch(metadata.server_modified), # API documentation says that this is reliable
				"size": metadata.size,
				"type": 0
				},
			"dropbox": {
				"content_hash": metadata.content_hash, # see https://www.dropbox.com/developers/reference/content-hash
				"rev": metadata.rev,
				"client_modified": metadata.client_modified # unverified value coming from dropbox clients
				}
			})
			if metadata.media_info is not None and metadata.media_info.is_metadata() is True:
				media_info_metadata = metadata.media_info.get_metadata()
				if media_info_metadata.time_taken is not None:
					rawInfo.update({
						"media_info": {
							"taken_date_time": datetime_to_epoch(media_info_metadata.time_taken)
						}
					})
				if media_info_metadata.location is not None:
					rawInfo.update({
						"media_info": {
							"location_latitude": media_info_metadata.location.latitude,
							"location_longitude": media_info_metadata.location.longitude
						}
					})
				# Dropbox doesn't parse some jpgs properly
				if media_info_metadata.dimensions is not None:
					rawInfo.update({
						"media_info": {
							"dimensions_height": media_info_metadata.dimensions.height,
							"dimensions_width": media_info_metadata.dimensions.width
						}
					})
		elif isinstance(metadata, FolderMetadata):
			rawInfo.update({
			"details": {
				"accessed": None, # not supported by Dropbox API
				"created": None, # not supported by Dropbox API,
				"metadata_changed": None, # not supported by Dropbox
				"modified": None, # not supported for folders
				"size": None, # not supported for folders
				"type": 1
				}})
		else:
			assert False, f"{metadata.name}, {metadata}, {type(metadata)}"
		return Info(rawInfo)

	def getinfo(self, path, namespaces=None):
		if path == "/":
			return Info({"basic": {"name": "", "is_dir": True}})
		try:
			if not path.startswith("/"):
				path = "/" + path
			metadata = self.dropbox.files_get_metadata(path, include_media_info=True)
		except ApiError as e:
			raise ResourceNotFound(path=path, exc=e)
		return self._infoFromMetadata(metadata)

	def setinfo(self, path, info): # pylint: disable=too-many-branches
		# dropbox doesn't support changing any of the metadata values
		pass

	def listdir(self, path):
		return [x.name for x in self.scandir(path)]

	def makedir(self, path, permissions=None, recreate=False):
		try:
			folderMetadata = self.dropbox.files_create_folder(path)
		except ApiError as e:
			assert isinstance(e.reason, CreateFolderError)
			# TODO - there are other possibilities
			raise DirectoryExpected(path=path)
		# don't need to close this filesystem so we return the non-closing version
		return SubFS(self, path)

	def openbin(self, path, mode="r", buffering=-1, **options):
		mode = Mode(mode)
		exists = True
		isDir = False
		try:
			isDir = self.getinfo(path).is_dir
		except ResourceNotFound:
			exists = False
		if mode.exclusive and exists:
			raise FileExists(path)
		elif mode.reading and not mode.create and not exists:
			raise ResourceNotFound(path)
		elif isDir:
			raise FileExpected(path)
		return DropboxFile(self.dropbox, path, mode)

	def remove(self, path):
		try:
			self.dropbox.files_delete(path)
		except ApiError as e:
			raise FileExpected(path=path, exc=e)

	def removedir(self, path):
		try:
			self.dropbox.files_delete(path)
		except ApiError as e:
			assert e.reason is DeleteError
			raise DirectoryExpected(path=path, exc=e)

	# non-essential method - for speeding up walk
	def scandir(self, path, namespaces=None, page=None):
		# 
		if path == "/":
			path = ""
		# get all the avaliable metadata since it's cheap
		# TODO - this call has a recursive flag so we can either use that and cache OR override walk
		result = self.dropbox.files_list_folder(path, include_media_info=True)
		allEntries = result.entries
		while result.has_more:
			result = self.dropbox.files_list_folder_continue(result.cursor)
			allEntries += result.entries
		return [self._infoFromMetadata(x) for x in allEntries]

@contextmanager
def setup_test():
	from os import environ
	from uuid import uuid4
	token = environ["DROPBOX_ACCESS_TOKEN"]
	fs = DropboxFS(token)
	testDir = "/tests/dropboxfs-test-" + uuid4().hex
	try:
		assert fs.exists(testDir) is False
		fs.makedir(testDir)
		yield (fs, testDir)
	finally:
		fs.removedir(testDir)
		fs.close()
	return fs, testDir

def test():
	from contextlib import suppress
	from fs.path import join
	
	with setup_test() as testSetup:
		fs, testDir = testSetup

		textPath = join(testDir, "test.txt")
		assert not fs.exists(textPath), "Bad starting state"
		with fs.open(textPath, "w") as f:
			f.write("Testing")
		assert fs.exists(textPath)
		with fs.open(textPath, "r") as f:
			assert f.read() == "Testing"
		fs.remove(textPath)
		assert not fs.exists(textPath)

		binaryPath = join(testDir, "binary.txt")
		assert not fs.exists(binaryPath), "Bad starting state"
		with fs.open(binaryPath, "wb") as f:
			f.write(b"binary")
		assert fs.exists(binaryPath)
		with fs.open(binaryPath, "rb") as f:
			assert f.read() == b"binary"
		fs.remove(binaryPath)
		assert not fs.exists(binaryPath)

		dirPath = join(testDir, "somedir")
		assert not fs.exists(dirPath), "Bad starting state"
		fs.makedir(dirPath)
		assert fs.exists(dirPath)
		fs.removedir(dirPath)
		assert not fs.exists(dirPath)

		with fs.open(binaryPath, "wb") as f:
			f.write(b"binary")
		assert fs.listdir(testDir) == ["binary.txt"]
		fs.remove(binaryPath)
		assert not fs.exists(binaryPath)

def assert_contents(fs, path, expectedContents):
	with fs.open(path, "r") as f:
		contents = f.read()
		assert contents == expectedContents, f"'{contents}'"

def test_versions():
	from contextlib import suppress
	from fs.path import join

	with setup_test() as testSetup:
		fs, testDir = testSetup

		path = join(testDir, "versions.txt")

		with suppress(ResourceNotFound, FileExpected):
			fs.remove(path)

		with fs.open(path, "wb") as f:
			f.write(b"v1")

		with fs.open(path, "wb") as f:
			f.write(b"v2")

		with suppress(ResourceNotFound, FileExpected):
			fs.remove(path)

def test_open_modes():
	from contextlib import suppress
	from io import SEEK_END
	from fs.path import join

	with setup_test() as testSetup:
		fs, testDir = testSetup

		path = join(testDir, "test.txt")
		with suppress(ResourceNotFound, FileExpected):
			fs.remove(path)
		with fs.open(path, "w") as f:
			f.write("AAA")
		assert_contents(fs, path, "AAA")
		with fs.open(path, "ra") as f:
			f.write("BBB")
		assert_contents(fs, path, "AAABBB")
		with fs.open(path, "r+") as f:
			f.seek(1)
			f.write("X")
		assert_contents(fs, path, "AXABBB")
		fs.remove(path)
		assert not fs.exists(path)

def test_speed():
	from time import perf_counter
	from fs.path import join

	with setup_test() as testSetup:
		fs, testDir = testSetup

		startTime = perf_counter()
		for directory in ["a", "b", "c", "d"]:
			thisDirFS = fs.makedir(join(testDir, directory))
			for filename in ["A", "B", "C", "D"]:
				with thisDirFS.open(filename, "w") as f:
					f.write(filename)
		print(f"Time for makedir/openbin {perf_counter() - startTime}")

		testDirFS = fs.opendir(testDir)
		startTime = perf_counter()
		for path, info_ in testDirFS.walk.info(namespaces=["basic", "details"]):
			pass
		print(f"Time for walk {perf_counter() - startTime}")

def test_opener():
	from os import environ
	from fs import open_fs
	from fs.path import join
	with setup_test() as testSetup:
		fs, testDir = testSetup
		testPath = join(testDir, "testfile")
		fs2 = open_fs(f"dropbox://{testDir}?access_token={environ['DROPBOX_ACCESS_TOKEN']}")
		with fs2.open("testfile", "w") as f:
			f.write("test")
		assert fs.exists(testPath)
