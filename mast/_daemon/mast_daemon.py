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
import sys
import pkg_resources
import platform

try:
    import win32serviceutil
    import servicemanager
    import win32service
    import win32event
    import socket
except ImportError:
    from .daemon import Daemon
    from time import sleep

if "Windows" in platform.system():
    if "MAST_HOME" not in os.environ:
        exe_dir = os.path.dirname(sys.executable)
        if "site-packages" in exe_dir:
            mast_home = os.path.abspath(os.path.join(
                exe_dir, os.pardir, os.pardir, os.pardir, os.pardir))
        else:
            mast_home = os.path.abspath(os.path.join(exe_dir, os.pardir))
        os.environ["MAST_HOME"] = mast_home
    else:
        mast_home = os.environ["MAST_HOME"]
elif "Linux" in platform.system():
    mast_home = os.environ["MAST_HOME"]

anaconda_dir = os.path.join(mast_home, "anaconda")
scripts_dir = os.path.join(mast_home, "anaconda", "Scripts")
sys.path.insert(0, anaconda_dir)
sys.path.insert(0, scripts_dir)
os.chdir(mast_home)


# This import needs os.environ["MAST_HOME"] and os.environ["mastd"] to be set
os.environ["mastd"] = "true"
from mast.logging import make_logger, logged


@logged("mast.daemon")
def get_plugins():
    """
    _function_: `mast.daemon.get_plugins()`

    This function will use [pkg_resources.iter_entry_points](http://pythonhosted.org/setuptools/pkg_resources.html#basic-workingset-methods)
    to find `entry_points` for `mastd_plugin` and return them.
    """
    named_objects = {}
    for ep in pkg_resources.iter_entry_points(group='mastd_plugin'):
        try:
            named_objects.update({ep.name: ep.load()})
        except:
            pass
    return named_objects

PLUGINS = get_plugins()

if "Windows" in platform.system():
    class MASTd(win32serviceutil.ServiceFramework):
        """
        _class_: `mast.daemon.MASTd(win32serviceutil.ServiceFramework)`

        This is the Windows version of the MASTd class. It uses
        `win32serviceutil.ServiceFramework` to setup a Windows
        service to host mastd.
        """
        _svc_name_ = "mastd"
        _svc_display_name_ = "mastd"

        def __init__(self, args):
            """
            _method_: `mast.daemon.MASTd.__init__(self, args)`

            Initialize the service.

            Parameters:

            * `args`: These are the args being passed to
            `win32serviceutil.ServiceFramework`. These args usually
            come from the user via the command line, and should not
            need to be called directly.
            """
            logger = make_logger("mast.daemon")
            logger.debug("mastd running in {}".format(os.getcwd()))
            servicemanager.LogInfoMsg("In __init__ args: {}".format(str(args)))
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            socket.setdefaulttimeout(60)
            self.timeout = 60000
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.stop_requested = False

        def SvcStop(self):
            """
            _method_: `mast.daemon.MASTd.SvcStop(self)`

            Stop the service.
            """
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)
            self.stop_requested = True

        def SvcDoRun(self):
            """
            _method_: `mast.daemon.MASTd.SvcDoRun(self)`

            Run the service.
            """
            servicemanager.LogInfoMsg("In SvcDoRun")
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            servicemanager.LogInfoMsg("Running run")
            self.run()

        @logged("mast.daemon")
        def run(self):
            """
            _method_: `mast.daemon.MASTd.run(self)`

            This function does the brunt of the work by looping through
            the plugins and starting them. After that it enters an
            infinite loop checking the status of each plugin. If the
            plugin is found dead it will attempt to restart the plugin.
            """
            logger = make_logger("mast.daemon")
            servicemanager.LogInfoMsg("Inside run")
            global PLUGINS
            servicemanager.LogInfoMsg("Plugins: {}".format(PLUGINS))
            try:
                threads = {}
                servicemanager.LogInfoMsg("Entering main loop")
                while not self.stop_requested:
                    for key, value in list(PLUGINS.items()):
                        if key in list(threads.keys()):
                            if threads[key].isAlive():
                                continue
                            else:
                                logger.debug("Plugin {} found, but dead, attempting to restart".format(key))
                                try:
                                    threads[key] = value()
                                    threads[key].start()
                                    logger.debug(
                                        "Plugin {} started".format(key))
                                    continue
                                except:
                                    logger.exception(
                                        "An unhandled exception "
                                        "occurred during execution.")
                                    continue
                        else:
                            logger.info(
                                "Plugin "
                                "{} not found. Attempting to start.".format(
                                    key))
                            try:
                                threads[key] = value()
                                threads[key].start()
                                continue
                            except:
                                logger.exception(
                                    "An unhandled exception occurred "
                                    "during execution.")
                                continue
                            continue
                    rc = win32event.WaitForSingleObject(
                        self.hWaitStop, self.timeout)
                    # Check to see if self.hWaitStop happened
                    if rc == win32event.WAIT_OBJECT_0:
                        # Stop signal encountered
                        servicemanager.LogInfoMsg(
                            "SomeShortNameVersion - STOPPED!")
                        break
            except:
                logger.exception(
                    "An uhhandled exception occurred during execution")
                raise

elif "Linux" in platform.system():
    class MASTd(Daemon):
        """
        _class_: `mast.daemon.MASTd(daemon)`

        This class is the Linux version of MASTd, It acts like a
        well-behaved Linux daemon. It will write a pid file to
        `$MAST_HOME/var/run/mastd.pid` and it will fork into the
        background twice causing it to become a child of init.

        After that initilization, it will find `mastd_plugins` and
        attempt to start them. After all the plugins are started,
        mastd will check every minute each of the plugins, restarting
        them if they are not alive.
        """
        def get_plugins(self):
            """
            _method_: `mast.daemon.MASTd.get_plugins(self)`

            This method uses `pkg_resources.iter_entry_points` to locate
            all `mastd_plugin`s and return them.
            """
            logger = make_logger("mast.daemon")
            self.named_objects = {}
            for ep in pkg_resources.iter_entry_points(group='mastd_plugin'):
                try:
                    self.named_objects.update({ep.name: ep.load()})
                except:
                    logger.exception(
                        "An unhandled exception occurred during execution.")
                    pass
            logger.info(
                "Collected plugins {}".format(
                    str(list(self.named_objects.keys()))))

        @logged("mast.daemon")
        def run(self):
            """
            _method_: `mast.daemon.MASTd.run(self)`

            This method will be called when mastd has successfully been
            spawned and forked. This is where most of the logic happens.

            If the plugin's thread is found to be dead, it will be restarted.
            """
            logger = make_logger("mast.daemon")
            os.chdir(mast_home)
            try:
                if not hasattr(self, "named_objects"):
                    self.get_plugins()
                threads = {}

                while True:
                    for key, value in list(self.named_objects.items()):
                        if key in list(threads.keys()):
                            if threads[key].isAlive():
                                continue
                            else:
                                logger.debug("Plugin {} found, but dead, attempting to restart".format(key))
                                try:
                                    threads[key] = value()
                                    threads[key].start()
                                    continue
                                except:
                                    logger.exception(
                                        "An unhandled exception occurred "
                                        "during execution.")
                                    continue
                        else:
                            logger.info(
                                "Plugin "
                                "{} not found. Attempting to start.".format(
                                    key))
                            try:
                                threads[key] = value()
                                threads[key].start()
                                continue
                            except:
                                logger.exception(
                                    "An unhandled exception occurred "
                                    "during execution.")
                                continue
                            continue
                    sleep(60)
            except:
                logger.exception(
                    "An uhhandled exception occurred during execution")
                raise

        @logged("mast.daemon")
        def status(self):
            """
            _method_: `mast.daemon.MASTd.status(self)`

            Not implemented yet.
            """
            raise NotImplementedError
