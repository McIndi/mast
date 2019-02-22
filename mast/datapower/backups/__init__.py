"""
mast backups:

A set of tools for automating routine backup/checkpoint
related tasks associated with IBM DataPower appliances.

Copyright 2016, All Rights Reserved
McIndi Solutions LLC
"""
from backups import *
import os

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

if __name__ == "__main__":
    cli.run()

