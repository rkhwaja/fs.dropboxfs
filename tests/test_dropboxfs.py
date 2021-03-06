from contextlib import contextmanager
from os import environ

from fs.dropboxfs import DropboxFS

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
