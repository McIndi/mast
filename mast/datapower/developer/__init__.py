"""
mast developer

A set of tools for automating routine development
tasks associated with IBM DataPower appliances.

Copyright 2016, All Rights Reserved
McIndi Solutions LLC
"""
import os
from developer import *
from developer import _import

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

if __name__ == "__main__":
    cli.run()

