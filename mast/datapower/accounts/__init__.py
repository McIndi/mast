"""
mast accounts:

A set of tools for automating routine user/group
administration tasks associated with IBM DataPower
appliances.

Copyright 2016, All Rights Reserved
McIndi Solutions LLC
"""
from accounts import *
import os

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

if __name__ == "__main__":
    cli.run()

