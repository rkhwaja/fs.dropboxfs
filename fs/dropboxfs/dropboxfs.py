from contextlib import closing
from datetime import datetime
from io import BytesIO

from dropbox import Dropbox
from dropbox.exceptions import ApiError
from fs.base import FS
from fs.mode import Mode

class DropboxFile(BytesIO):
	def __init__(self, dropbox, path):
		self.dropbox = dropbox
		self.path = path
		try:
			metadata, response = self.dropbox.files_download(self.path)
			with closing(response):
				initialData = response.read()
			self.rev = metadata.rev
		except DownloadError:
			initialData = None
			self.rev = None
		super().__init__(self, initialData)

	def close(self):
		if self.rev is None:
			writeMode = WriteMode("add")
		else:
			writeMode = WriteMode("update", self.rev)
		self.metadata = self.dropbox.files_upload(self.data, self.path, mode=writeMode, autorename=False, client_modified=datetime.now(), mute=False)

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
			"read_only": True, # at least until openbin is fully implemented
			"supports_rename": False # since we don't have a syspath...
		}

	def __repr__(self):
		return f"<DropboxDriveFS>"

	def _itemInfo(self, metadata): # pylint: disable=no-self-use
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
				rawInfo.update({"media_info":
					{
						"taken_date_time": datetime_to_epoch(media_info_metadata.time_taken),
						"location_latitude": media_info_metadata.location.latitude,
						"location_longitude": media_info_metadata.location.longitude,
						"dimensions_height": media_info_metadata.dimensions.height,
						"dimensions_width": media_info_metadata.dimensions.width
					}})
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
		return Info(rawInfo)

	def getinfo(self, path, namespaces=None):
		try:
			metadata = self.dropbox.files_get_metadata(path, include_media_info=True)
		except ApiError as e:
			raise ResourceNotFound(path=path, exc=e)
		return self._itemInfo(metadata)

	def setinfo(self, path, info): # pylint: disable=too-many-branches
		# dropbox doesn't support changing any of the metadata values
		pass

	def listdir(self, path):
		# get all the avaliable metadata since it's cheap
		# TODO - this call has a recursive flag so we can either use that and cache OR override walk
		result = self.dropbox.files_list_folder(path, include_media_info=True)
		allEntries = result.entries
		while result.has_more:
			result = self.dropbox.files_list_folder_continue(result.cursor)
			allEntries += result.entries
		return [x.name for x in allEntries]

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
		if mode.exclusive and self.exists(path):
			raise FileExists(path=path)
		if self.exists(path) and not self.isfile(path):
			raise FileExpected(path=path)
		return DropboxFile(self.dropbox, path)

	def remove(self, path):
		try:
			self.dropbox.files_delete(path)
		except ApiError as e:
			assert e.reason is DeleteError
			raise FileExpected(path=path, exc=e)

	def removedir(self, path):
		try:
			self.dropbox.files_delete(path)
		except ApiError as e:
			assert e.reason is DeleteError
			raise DirectoryExpected(path=path, exc=e)

def test():
	from os import environ
	token = environ["DROPBOX_ACCESS_TOKEN"]
	fs = DropboxFS(token)
	with fs.open("/temp/test/test.txt", "w") as f:
		f.write("Testing")
