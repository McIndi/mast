"""
mast deployment

A set of utilities which can simplify, automate and audit
your DataPower service deployments and migrations.

Copyright 2016, All Rights Reserved
McIndi Solutions LLC
"""
from deployment import *
import os

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

if __name__ == "__main__":
    cli.run()

