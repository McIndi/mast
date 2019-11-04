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
import os
import sys
import platform


if "Windows" in platform.system():
    import win32serviceutil

    def main():
        exe_dir = os.path.dirname(sys.executable)
        if "site-packages" in exe_dir:
            mast_home = os.path.abspath(os.path.join(
                exe_dir, os.pardir, os.pardir, os.pardir, os.pardir))
        else:
            mast_home = os.path.abspath(os.path.join(exe_dir, os.pardir))
        anaconda_dir = os.path.join(mast_home, "anaconda")
        scripts_dir = os.path.join(mast_home, "anaconda", "Scripts")
        sys.path.insert(0, anaconda_dir)
        sys.path.insert(0, scripts_dir)
        os.environ["MAST_HOME"] = mast_home
        os.chdir(mast_home)

        from .mast_daemon import MASTd

        win32serviceutil.HandleCommandLine(MASTd)

elif "Linux" in platform.system():

    def main():
        from .mast_daemon import MASTd

        mast_home = os.environ["MAST_HOME"]
        pid_file = os.path.join(
            mast_home,
            "var",
            "run",
            "mastd.pid")
        mastd = MASTd(pid_file)

        if len(sys.argv) != 2:
            print("USAGE: python -m mastd.daemon { start | stop | restart | status }")
            sys.exit(1)

        if "start" in sys.argv[1]:
            mastd.start()
        elif "stop" in sys.argv[1]:
            mastd.stop()
        elif "restart" in sys.argv[1]:
            mastd.restart()
        elif "status" in sys.argv[1]:
            print(mastd.status())
        else:
            print("USAGE: python -m mast.daemon { start | stop | restart | status }")
            sys.exit(1)

        sys.exit(0)

if __name__ == "__main__":
    print("Calling main")
    main()
    print("main returned")
