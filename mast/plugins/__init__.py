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
import web

__version__ = "{}-0".format(os.environ["MAST_VERSION"])
