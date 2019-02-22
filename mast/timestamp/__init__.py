"""
_module_: `mast.timestamp`

This module provides one class `Timestamp` which provides several
convenience methods for getting at various representations of
the current timestamp.
"""
from time import time
from datetime import datetime
import os

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

class Timestamp(object):
    """
    _class_: `mast.timestamp.Timestamp`

    Timestamp an object which represents a given moment in time. An instance
    of Timestamp takes the time at initialization and captures the moment in
    epoch format using time.time(), after initialization, a number of
    convenience methods allow access to different formats of representing that
    time.

    Usage:

        :::python
        >>> from mast.timestamp import Timestamp
        >>> t = Timestamp()
        >>> print t.epoch
        1451323059
        >>> print t.friendly
        Monday December 28, 12:17:39
        >>> print t.timestamp
        20151228121739
        >>> print t.short
        12-28-2015 12:17:39
        >>> print str(t)
        Monday December 28, 12:17:39
        >>> print int(t)
        1451323059

    """
    def __init__(self):
        """
        _method_: `mast.timestamp.Timestamp.__init__(self)`

        Initialization function, catpture the current time in epoch format
        then create a timestamp object from datetime.fromtimestamp().

        Returns: None

        Parameters:

        This method takes no arguments.
        """
        self._epoch = time()
        self._timestamp = datetime.fromtimestamp(self._epoch)

    @property
    def epoch(self):
        """
        _property_: `mast.timestamp.Timestamp.epoch`

        Returns: The timestamp in epoch format
        """
        return int(self)

    @property
    def friendly(self):
        """
        _property_: `mast.timestamp.Timestamp.friendly`

        Returns the timestamp in a friendly, human-readable format.
        For January 1, 1970 at Midnight, this would return:
        `Thursday, January 1, 1970, 00:00:00`

        This the same as `strftime('%A %B %d, %X')`
        """
        return self._timestamp.strftime('%A, %B %d, %Y, %X')

    @property
    def timestamp(self):
        """
        _property_: `mast.timestamp.Timestamp.timestamp`

        Returns the timestamp in a special format which for jan 1, 1970 at
        midnight would look like this "19700101000000" which is year, month,
        day, hour, minute and second. This is very useful for timestamped
        filenames, where, you don't want commas and spaces, but would like
        something a human can read.

        This is the same as `strftime('%Y%m%d%H%M%S')`
        """
        return self._timestamp.strftime('%Y%m%d%H%M%S')

    @property
    def short(self):
        """
        _property_: `mast.timestamp.Timestamp.short`

        Returns the short representation of the timestamp, which for Jan 1,
        1970 at midnight would look like this "01-01-1970 00:00:00"

        This is the same as `strftime('%m-%d-%Y %H:%M:%S')`
        """
        return self._timestamp.strftime('%m-%d-%Y %H:%M:%S')

    def strftime(self, _format):
        """
        _method_: `mast.timestamp.Timestamp.strftime(self, _format)`

        Returns: the timestamp in a format specified by the _format param.
        This should be a string following the rules
        [here](https://docs.python.org/2/library/datetime.html#strftime-and-strptime-behavior)

        Parameters:

        * `_format`: This is the format of the timestamp as you would like
        it returned.
        """
        return self._timestamp.strftime(_format)

    def __str__(self):
        """
        _method_: `mast.timestamp.Timestamp.__str__`

        This ensures that when doing something like:

            :::python
            print Timestamp()

        you get a human-readable version. This is the same as
        `Timestamp.friendly`.
        """
        return self.friendly

    def __int__(self):
        """
        _method_: `mast.timestamp.Timestamp.__int__`

        This ensures that this will work:

            :::python
            import timestamp
            t1 = timestamp.Timestamp()

            do_something()

            t2 = timestamp.Timestamp()
            print "The operation took {} seconds to complete".format(t1 - t2)

        This is the same as `Timestamp.epoch`.
        """
        return int(self._epoch)

if __name__ == '__main__':
    ts = Timestamp()
    print ts.timestamp
    print ts.friendly
    print ts.epoch
