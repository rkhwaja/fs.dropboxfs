# fs.dropboxfs

Implementation of [pyfilesystem2](https://docs.pyfilesystem.org/) file system using Dropbox

![image](https://github.com/rkhwaja/fs.dropboxfs/workflows/ci/badge.svg) [![PyPI version](https://badge.fury.io/py/fs.dropboxfs.svg)](https://badge.fury.io/py/fs.dropboxfs)

# Usage

``` python
from fs import open_fs
from fs.dropboxfs import DropboxFS

dropboxFS = DropboxFS(
  accessToken=<your access token>,
  refreshToken=<your refresh token>,
  app_key=<your app key>,
  app_secret=<your app secret>)

dropboxFS2 = open_fs('dropbox:///somedirectory?access_token=your_access_token&refresh_token=your_refresh_token')

# dropboxFS and dropboxFS2 are now standard pyfilesystem2 file systems
```

# Development

To run the tests, set the following environment variables:

- DROPBOX_APP_KEY - your app key (see [Dropbox Developer Console](https://www.dropbox.com/developers/apps))
- DROPBOX_APP_SECRET - your app secret (see [Dropbox Developer Console](https://www.dropbox.com/developers/apps))
- DROPBOX_CREDENTIALS_PATH - path to a json file which will contain the credentials

Then generate the credentials json file by running

``` python
./test/generate_credentials.py
```

Then run the tests by executing

```bash
  poe test
```

in the root directory
