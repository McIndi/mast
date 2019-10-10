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
_module_: `mast.plugins`

This module implements base classes to be used for mast plugins.

Currently, there is only one class `mast.plugins.web.Plugin` which
doesn't actually implement any functionality, but provides a class
with the following `no-op` methods which should be implemented by
subclasses:

* `html(self)`: Should return the html for the plugin's tab in the
web gui
* `css(self)`: Should return the css for the plugin
* `js(self)`: Should return any required javascript needed by the plugin
* `route(self)`: request handler, will recieve all requests which
reach the endpoint, you must handle HTTP verbs yourself.

In the future, this module will provide a base class to help in the
creation of `mastd_plugin`s, but for now, you can just subclass
`threading.Thread`.
"""
import os
from . import web
from mast import __version__

