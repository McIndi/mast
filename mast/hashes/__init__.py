"""
_module_: `mast.hashes`

This module provides a number of functions which are wrappers
around Python's [hashlib](https://docs.python.org/2/library/hashlib.html)
library.

While your version of OpenSSL may allow for more hashing algorithms,
the algorithms supported by this module should always be present.

The following algorithms are supported:

* md5 - `mast.hashes.get_md5`
* sha1 - `mast.hashes.get_sha1`
* sha224 - `mast.hashes.get_sha224`
* sha256 - `mast.hashes.get_sha256`
* sha384 - `mast.hashes.get_sha384`
* sha512 - `mast.hashes.get_sha512`

When one of these functions are called, it expects the path and filename
of a file and will return the hexadecimal representation of the
requested hash as a Python `str`.
"""
import hashlib
import os

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

def _get_file_hash(filename, cls):
    """
    _function_: `mast.hashes._get_file_hash(filename, cls)`

    Given filename, returns the hash of the file as a string containing
    only hexadecimal digits. The algorithm used depends on the value passed
    to `cls`, which should be a  constructor for a hash algorithm available
    through hashlib. Convenience functions for the constructors which are
    always present are provided and listed here:

    * `get_md5`
    * `get_sha1`
    * `get sha224`
    * `get_sha256`
    * `get_sha384`
    * `get_sha512`

    More may be available depending on your version of OpenSSL, but these are
    always present.

    Parameters:

    * `filename`: The file for which to calculate the hash.
    * `cls`: The class constructor to use to build the hash. It is
    expected to behave like a class from `hashlib`.
    """
    _hash = cls()
    with open(filename, 'rb') as fin:
        _buffer = fin.read(65536)
        while len(_buffer) > 0:
            _hash.update(_buffer)
            _buffer = fin.read(65536)
    return _hash.hexdigest()


def get_md5(filename):
    """
    _function_: `mast.hashes.get_md5(filename)`

    Return the md5 hash of filename

    Parameters:

    * `filename`: The file for which to calculate the hash.

    Usage:

        :::python
        from mast.hashes import get_md5

        hash = get_md5("/path/to/file")
    """
    return _get_file_hash(filename, hashlib.md5)


def get_sha1(filename):
    """
    _function_: `mast.hashes.get_sha1(filename)`

    Return the sha1 hash of filename

    Parameters:

    * `filename`: The file for which to calculate the hash.

    Usage:

        :::python
        from mast.hashes import get_sha1

        hash = get_sha1("/path/to/file")
    """
    return _get_file_hash(filename, hashlib.sha1)


def get_sha224(filename):
    """
    _function_: `mast.hashes.get_sha224(filename)`

    Return the sha224 hash of filename

    Parameters:

    * `filename`: The file for which to calculate the hash.

    Usage:

        :::python
        from mast.hashes import get_sha224

        hash = get_sha224("/path/to/file")
    """
    return _get_file_hash(filename, hashlib.sha224)


def get_sha256(filename):
    """
    _function_: `mast.hashes.get_sha256(filename)`

    Return the sha256 hash of filename

    Parameters:

    * `filename`: The file for which to calculate the hash.

    Usage:

        :::python
        from mast.hashes import get_sha256

        hash = get_sha256("/path/to/file")
    """
    return _get_file_hash(filename, hashlib.sha256)


def get_sha384(filename):
    """
    _function_: `mast.hashes.get_sha384(filename)`

    Return the sha384 hash of filename

    Parameters:

    * `filename`: The file for which to calculate the hash.

    Usage:

        :::python
        from mast.hashes import get_sha384

        hash = get_sha384("/path/to/file")
    """
    return _get_file_hash(filename, hashlib.sha384)


def get_sha512(filename):
    """
    _function_: `mast.hashes.get_sha512(filename)`

    Return the sha512 hash of filename

    Parameters:

    * `filename`: The file for which to calculate the hash.

    Usage:

        :::python
        from mast.hashes import get_sha512

        hash = get_sha512("/path/to/file")
    """
    return _get_file_hash(filename, hashlib.sha512)
