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
import struct


if sys.platform == 'win32':
    def get_terminal_size(defaultx=80, defaulty=25):
        """Return size of current terminal console.
        This function try to determine actual size of current working
        console window and return tuple (sizex, sizey) if success,
        or default size (defaultx, defaulty) otherwise.
        Dependencies: ctypes should be installed.
        Author: Alexander Belchenko (e-mail: bialix AT ukr.net)
        """
        try:
            import ctypes
        except ImportError:
            return defaultx, defaulty

        h = ctypes.windll.kernel32.GetStdHandle(-11)
        csbi = ctypes.create_string_buffer(22)
        res = ctypes.windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)

        if res:
            (bufx, bufy, curx, cury, wattr,
             left, top, right, bottom, maxx, maxy) = struct.unpack(
                "hhhhHhhhhhh", csbi.raw)
            sizex = right - left + 1
            sizey = bottom - top + 1
            return (sizex, sizey)
        else:
            return (defaultx, defaulty)

    def get_keypress():
        import msvcrt
        return msvcrt.getch()
else:
    def get_terminal_size(fd=1, defaultx=80, defaulty=25):
        """
        Returns height and width of current terminal. First tries to get
        size via termios.TIOCGWINSZ, then from environment. Defaults to 25
        lines x 80 columns if both methods fail.

        :param fd: file descriptor (default: 1=stdout)
        :defaultx: The value to return for x if unable to determine
        (default: 80)
        :param fd: The value to return for y if unable to determine
        (default: 80)
        """
        try:
            import fcntl, termios, struct
            hw = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
            wh = (hw[1], hw[0])
        except:
            try:
                wh = (os.environ['COLUMNS'], os.environ['LINES'])
            except:
                wh = (80, 25)
        return wh

    def get_keypress():
        import termios, fcntl, sys, os
        fd = sys.stdin.fileno()

        oldterm = termios.tcgetattr(fd)
        newattr = termios.tcgetattr(fd)
        newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, newattr)

        oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)

        try:
            while 1:
                try:
                    c = sys.stdin.read(1)
                    break
                except IOError: pass
        finally:
            termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
            fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
        return c

def page(text):
    if not sys.stdout.isatty():
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    height = get_terminal_size()[1]
    current_line = 0
    for line in text.splitlines():
        if current_line >= height - 2:
            sys.stdout.write("        \r{}".format(line))
            sys.stdout.flush()
            sys.stdout.write("\n--more--\r")
            sys.stdout.flush()
            key = get_keypress()
            if key == " ":
                sys.stdout.write("        \r")
                sys.stdout.flush()
                current_line = 0
            elif key == "q":
                sys.stdout.write("        ")
                sys.stdout.flush()
                break
            elif key == '\x03':
                sys.stdout.write("        \r")
                sys.stdout.flush()
                break
        else:
            print line
        current_line += 1
