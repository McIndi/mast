"""
_module_: `mast.xor`

This module provides two functions which help with the obfuscation
of credentials. __NOTE__ that this is only obfuscation as it will
default to using a key of a single `_` (underscore), so it will be
pretty easy to get at the plain-text. This is merely meant to prevent
accidental glances at the credentials. The two functions are:

1. `xorencode(string, key="_")`: Returns a base64 encoded and xored
string with key
2. `xordecode(string, key="_")`: Returns a base64 decoded and un-xored
string with key

Although, from a purely theoretical point of view, this can be used to
implement a "Mathematically Secure" encryption method as long it is used
with a [one-time pad](https://en.wikipedia.org/wiki/One-time_pad), but
in reality it is very difficult to use a one-time pad for computer
security.
"""
import os
import base64
from itertools import cycle, izip

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

def xorencode(string, key="_"):
    """
    _function_: `mast.xor.xorencode(string, key="_")`

    Return the base64 encoded XORed version of string. This is XORed with
    key which defaults to a single underscore.

    Usage:

        :::python
        >>> from mast.xor import xorencode, xordecode
        >>> s = "test_string"
        >>> enc = xorencode(s)
        >>> print s, enc
        test_string KzosKwAsKy02MTg=
        >>> dec = xordecode(enc)
        >>> print s, dec
        test_string test_string
    """
    return base64.encodestring(
        ''.join(
            chr(ord(c) ^ ord(k)) for c, k in izip(string, cycle(key)))).strip()


def xordecode(string, key="_"):
    """
    _function_: `mast.xor.xordecode(string, key="_")`

    Returns the base64 decoded, XORed version of string. This is XORed with
    key, which defaults to a single underscore

    Usage:

        :::python
        >>> from mast.xor import xorencode, xordecode
        >>> s = "test_string"
        >>> enc = xorencode(s)
        >>> print s, enc
        test_string KzosKwAsKy02MTg=
        >>> dec = xordecode(enc)
        >>> print s, dec
        test_string test_string
    """
    string = base64.decodestring(string)
    return ''.join(
        chr(ord(c) ^ ord(k)) for c, k in izip(string, cycle(key))).strip()
