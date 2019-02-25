import pkg_resources  # part of setuptools
__version__ = pkg_resources.require("mast")[0].version
