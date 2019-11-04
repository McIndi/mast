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
"""
_module_: `mast.daemon`

This module implements a daemon on Linux platforms or a
Service on Windows platforms. It checks for any modules
which have a registered [setuptools entrypoint](http://pythonhosted.org/setuptools/pkg_resources.html#entry-points)
called `mastd_plugin` which should be a subclass of `threading.Thread`.

When `mastd` is started, it will search for and find `mastd_plugin`s and
attempt to start them. After one minute and each minute after that,
each thread will be checked. If it is alive, it will be left alone, but
if it is dead, it will be restarted. This process will continue until
`mastd` is stopped.
"""
import os
from mast import __version__

# This environment variable needs to be set for other imports to work
os.environ["MAST_VERSION"] = __version__

from .mast_daemon import *
