# This file is part of McIndi's Automated Solutions Tool (MAST).
#
# MAST is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3
# as published by the Free Software Foundation.
#
# MAST is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MAST.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright 2015-2019, McIndi Solutions, All rights reserved.
from deployment import cli

# Fix issue with __main__.py messing up command line help
import sys
sys.argv[0] = "mast-deployment"

try:
    cli.Run()
except AttributeError, e:
    if "'NoneType' object has no attribute 'app'" in e:
        raise NotImplementedError(
            "HTML formatted output is not supported on the CLI")
    raise
except ImportError, e:
    if "No module named backups" in e:
        raise NotImplementedError(
            "HTML formatted output is not supported on the CLI")
    raise
