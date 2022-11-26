# Make the tests a module so that pytest will pick up the source code of the fs module for testing

from os.path import join, realpath

import fs

# Add the local code directory to the `fs` module path
# Can only rely on fs.__path__ being an iterable - on windows it's not a list, at least with pytest
newPath = list(fs.__path__)
newPath.insert(0, realpath(join(__file__, '..', '..', 'fs')))
fs.__path__ = newPath
