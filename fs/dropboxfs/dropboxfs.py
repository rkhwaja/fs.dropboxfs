from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from logging import getLogger

from dropbox import Dropbox
from dropbox.files import CreateFolderError, DeleteError, FileMetadata, FolderMetadata, ListFolderContinueError, ListFolderError, WriteMode
from dropbox.exceptions import ApiError
from fs.base import FS
from fs.enums import ResourceType
from fs.errors import DirectoryExists, DirectoryExpected, DirectoryNotEmpty, FileExists, FileExpected, FSError, OperationFailed, RemoveRootError, ResourceNotFound
from fs.info import Info
from fs.mode import Mode
from fs.path import dirname, join
from fs.subfs import SubFS
from fs.time import datetime_to_epoch

_logger = getLogger(__name__)

def _infoFromMetadata(metadata):
	rawInfo = {
		'basic': {
			'name': metadata.name,
			'is_dir': isinstance(metadata, FolderMetadata),
		}
	}
	if isinstance(metadata, FileMetadata):
		rawInfo.update({
		'details': {
			'accessed': None, # not supported by Dropbox API
			'created': None, # not supported by Dropbox API?,
			'metadata_changed': None, # not supported by Dropbox
			'modified': datetime_to_epoch(metadata.server_modified), # API documentation says that this is reliable
			'size': metadata.size,
			'type': ResourceType.file if metadata.symlink_info is None else ResourceType.symlink
			},
		'dropbox': {
			'content_hash': metadata.content_hash, # see https://www.dropbox.com/developers/reference/content-hash
			'rev': metadata.rev,
			'client_modified': datetime_to_epoch(metadata.client_modified) # unverified value coming from dropbox clients
			}
		})
		if metadata.media_info is not None and metadata.media_info.is_metadata() is True:
			media_info_metadata = metadata.media_info.get_metadata()
			if media_info_metadata.time_taken is not None:
				rawInfo.update({
					'media_info': {
						'taken_date_time': datetime_to_epoch(media_info_metadata.time_taken)
					}
				})
			if media_info_metadata.location is not None:
				rawInfo.update({
					'media_info': {
						'location_latitude': media_info_metadata.location.latitude,
						'location_longitude': media_info_metadata.location.longitude
					}
				})
			# Dropbox doesn't parse some jpgs properly
			if media_info_metadata.dimensions is not None:
				rawInfo.update({
					'media_info': {
						'dimensions_height': media_info_metadata.dimensions.height,
						'dimensions_width': media_info_metadata.dimensions.width
					}
				})
	elif isinstance(metadata, FolderMetadata):
		rawInfo.update({
		'details': {
			'accessed': None, # not supported by Dropbox API
			'created': None, # not supported by Dropbox API,
			'metadata_changed': None, # not supported by Dropbox
			'modified': None, # not supported for folders
			'size': None, # not supported for folders
			'type': ResourceType.directory
			}})
	else:
		assert False, f'{metadata.name}, {metadata}, {type(metadata)}'
	return Info(rawInfo)

class _DropboxFile(BytesIO):
	def __init__(self, dropbox, path, mode):
		self.dropbox = dropbox
		self.path = path
		self._mode = mode
		initialData = None
		self.rev = None
		try:
			metadata, response = self.dropbox.files_download(self.path)
			self.rev = metadata.rev
			with closing(response):
				if (self._mode.reading or self._mode.appending) and not self._mode.truncate:
					initialData = response.content
		except ApiError:
			# if the file doesn't exist, we don't need to read it's initial state
			pass
		super().__init__(initialData)
		if self._mode.appending and initialData is not None:
			# seek to the end
			self.seek(len(initialData))
		self._closed = False

	def truncate(self, size=None):
		# BytesIO.truncate works as needed except if truncating to longer than the existing size
		originalSize = len(self.getvalue())
		super().truncate(size)
		if size is None: # Bytes.truncate works fine for this case
			return len(self.getvalue())
		if size <= originalSize: # BytesIO.truncate works fine for this case
			return len(self.getvalue())
		# this is the behavior of native files and is specified by pyfilesystem2
		self.write(b'\0' * (size - originalSize))
		self.seek(originalSize)
		return len(self.getvalue())

	def read(self, size=-1):
		if self._mode.reading is False:
			raise OSError('This file object is not readable')
		return super().read(size)

	def write(self, data):
		if self._mode.writing is False:
			raise OSError('This file object is not writable')
		return super().write(data)

	def readable(self):
		return self._mode.reading

	def writable(self):
		return self._mode.writing

	@property
	def closed(self):
		return self._closed

	@property
	def mode(self):
		return self._mode.to_platform_bin()

	def close(self):
		if not self._mode.writing and not self._mode.appending:
			self._closed = True
			return
		writeMode = WriteMode('add') if self.rev is None else WriteMode('update', self.rev)
		try:
			metadata = self.dropbox.files_upload(self.getvalue(), self.path, mode=writeMode, autorename=False, client_modified=datetime.now(timezone.utc).replace(tzinfo=None), mute=False) # noqa: F841
		except ApiError as e:
			raise OperationFailed(self.path) from e
		# Make sure that we can't call this again
		self.path = None
		self._mode = None
		self.dropbox = None
		self._closed = True

class DropboxFS(FS):
	def __init__(self, access_token=None, refresh_token=None, app_key=None, app_secret=None):
		"""Provide one of:
		1) accessToken (if you have a long-lived access token or won't need a refresh)
		2) refreshToken and appKey (if you don't need an app secret to refresh)
		3) refreshToken, appKey and appSecret (if you do need an app secret to refresh)"""
		super().__init__()
		self.dropbox = Dropbox(oauth2_access_token=access_token, oauth2_refresh_token=refresh_token, app_key=app_key, app_secret=app_secret)
		_meta = self._meta = {
			'case_insensitive': True, # I think?
			'invalid_path_chars': ':\0\\', # not sure what else
			'max_path_length': None, # don't know what the limit is
			'max_sys_path_length': None, # there's no syspath
			'network': True,
			'read_only': False,
			'supports_rename': False, # since we don't have a syspath...
			'thread_safe': True
		}

	def __repr__(self):
		return 'DropboxFS()'

	def getinfo(self, path, namespaces=None):
		_logger.info(f'getinfo({path}, {namespaces})')
		path = self.validatepath(path)
		if path == '/':
			return Info({'basic': {'name': '', 'is_dir': True}})
		with self._lock:
			try:
				metadata = self.dropbox.files_get_metadata(path, include_media_info=(namespaces is not None and 'media_info' in namespaces))
			except ApiError as e:
				raise ResourceNotFound(path=path) from e
			return _infoFromMetadata(metadata)

	def setinfo(self, path, info):
		_logger.info(f'setinfo({path}, {info})')
		# dropbox doesn't support changing any of the metadata values
		path = self.validatepath(path)
		with self._lock:
			if self.exists(path) is False:
				raise ResourceNotFound(path)

	def listdir(self, path):
		_logger.info(f'listdir({path})')
		path = self.validatepath(path)
		with self._lock:
			return [x.name for x in self.scandir(path)]

	def makedir(self, path, permissions=None, recreate=False):
		_logger.info(f'makedir({path}, {permissions}, {recreate})')
		path = self.validatepath(path)
		with self._lock:
			try:
				info_ = self.getinfo(path)
				if info_.is_dir:
					if recreate is False:
						raise DirectoryExists(path=path)
					return SubFS(self, path)
				raise DirectoryExists(path)
			except ResourceNotFound:
				pass

			# check that the parent directory exists
			parentDir = dirname(path)
			if not self.exists(parentDir):
				raise ResourceNotFound(path=path)

			try:
				folderMetadata = self.dropbox.files_create_folder_v2(path) # noqa: F841
			except ApiError as e:
				assert isinstance(e.error, CreateFolderError)
				# TODO - there are other possibilities
				raise DirectoryExpected(path=path) from e
			# don't need to close this filesystem so we return the non-closing version
			return SubFS(self, path)

	def openbin(self, path, mode='r', buffering=-1, **options):
		_logger.info(f'openbin({path}, {mode}, {buffering}, {options})')
		if 't' in mode:
			raise ValueError('Text mode is not allowed in openbin')
		path = self.validatepath(path)
		mode = Mode(mode)
		exists = True
		isDir = False
		with self._lock:
			try:
				isDir = self.getinfo(path).is_dir
			except ResourceNotFound:
				exists = False
			if mode.exclusive and exists:
				raise FileExists(path)
			if mode.reading and not mode.create and not exists:
				raise ResourceNotFound(path)
			if isDir:
				raise FileExpected(path)
			if mode.writing: # make sure that the parent directory exists
				parentDir = dirname(path)
				# throws ResourceNotFound if the parent dir doesn't exist
				_ = self.getinfo(parentDir)
			return _DropboxFile(self.dropbox, path, mode)

	def remove(self, path):
		_logger.info(f'remove({path})')
		path = self.validatepath(path)
		with self._lock:
			# correctly throws ResourceNotFound if path doesn't exist
			info_ = self.getinfo(path)
			if info_.is_dir:
				raise FileExpected(path=path)
			try:
				# this deletes both files and folders so we need to precheck
				self.dropbox.files_delete_v2(path)
			except ApiError as e:
				raise FileExpected(path=path) from e

	def removedir(self, path):
		_logger.info(f'removedir({path})')
		path = self.validatepath(path)
		if path == '/':
			raise RemoveRootError(path=path)
		with self._lock:
			# correctly throws ResourceNotFound if path doesn't exist
			info_ = self.getinfo(path)
			if info_.is_dir is False:
				raise DirectoryExpected(path=path)
			if next(self.scandir(path), None) is not None:
				raise DirectoryNotEmpty(path=path)
			try:
				# this deletes both files and folders so we need to precheck
				self.dropbox.files_delete_v2(path)
			except ApiError as e:
				assert isinstance(e.error, DeleteError)
				raise DirectoryExpected(path=path) from e

	# non-essential method - for speeding up walk
	def scandir(self, path, namespaces=None, page=None):
		_logger.info(f'scandir({path}, {namespaces}, {page})')
		path = self.validatepath(path)
		with self._lock:
			# get all the avaliable metadata since it's cheap
			# TODO - this call has a recursive flag so we can either use that and cache OR override walk
			try:
				effective_path = path
				if path == '/':
					# Error in call to API function "files/list_folder": request body: path: Specify the root folder as an empty string rather than as "/"
					effective_path = ''
				result = self.dropbox.files_list_folder(effective_path)
			except ApiError as e:
				assert isinstance(e.error, ListFolderError), 'Unexpected Dropbox error thrown'
				if e.error.is_path() is False:
					raise FSError from e
				lookupError = e.error.get_path()
				if lookupError.is_not_found():
					raise ResourceNotFound(path=path) from e
				if lookupError.is_not_folder():
					raise DirectoryExpected(path=path) from e
			allEntries = result.entries

			try:
				while result.has_more and (page is None or len(allEntries) < page[1]):
					result = self.dropbox.files_list_folder_continue(result.cursor)
					allEntries += result.entries
			except ApiError as e:
				assert isinstance(e.error, ListFolderContinueError)
				raise FSError from e
			if page is not None:
				allEntries = allEntries[page[0]: page[1]]
			# Dropbox doesn't return media_info items during list since Dec 2, 2019
			if namespaces is not None and 'media_info' in namespaces:
				return (self.getinfo(join(path, x['name'])) for x in allEntries)
			return (_infoFromMetadata(x) for x in allEntries)
