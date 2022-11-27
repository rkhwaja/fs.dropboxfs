# fs.dropboxfs

Implementation of pyfilesystem2 file system using Dropbox

![image](https://github.com/rkhwaja/fs.dropboxfs/workflows/ci/badge.svg) [![PyPI version](https://badge.fury.io/py/fs.dropboxfs.svg)](https://badge.fury.io/py/fs.dropboxfs)

# Usage

``` python
from fs import open_fs
from fs.dropboxfs import DropboxFS

dropboxFS = DropboxFS(
  accessToken=<your access token>,
  refreshToken=<your refresh token>)

dropboxFS2 = open_fs('dropbox:///somedirectory?access_token=your_access_token&refresh_token=your_refresh_token')

# dropboxFS and dropboxFS2 are now a standard pyfilesystem2 file system
```
