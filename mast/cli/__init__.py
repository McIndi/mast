# -*- coding: utf-8 -*-
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
_module_: `mast.cli`

Provide an easy way to convert a function to a Command Line Program.

There are two main methods in the one class provided (Cli):

* `command`: A decorator which converts a function to a CLI based
on function signature
* `run`: A method which parses the command line arguments and
executes the appropriate function
"""
import os
import sys
import inspect
import argparse
from mast import __version__

class Cli(object):
    """
    _class_: `mast.cli.Cli()`: see `mast.cli.Cli.__init__` for arguments
    to the constructor.

    This is a class which can be used to dynamically generate a
    command line interface for a function based on the function's
    signature.

    To define an argument to the command line program, you must set
    a default value for the function's parameter. The supported types
    of default arguments are:

    * `str` - When the default argument is a string, a string will be
    expected from the command line
    * `list` - When the default argument is a list, multiple values
    will be accepted from the command line
    * `int` - When the default argument is an integer, an integer
    will be expected from the command line
    * `float` - When the default argument is a float, a float will
    be expected from the command line
    * `bool` - When the default argument is a boolean value, the option
    will be a flag, which when present will provide the oposite value
    as the default argument

    There are two main ways to use this library:

    Many functions as sub-commands:

        :::python
        from mast.cli import Cli

        cli = Cli()

        @cli.command
        def subcommand_one(arg_1="", arg_2=10):
            do_something(arg_1, arg_2)

        @cli.command
        def subcommand_two(arg_1=20, flag_1=False):
            do_something_else(arg_1, flag_1)

        if __name__ == "__main__":
            try:
                cli.run()
            except:
                log_something()
                raise

    One `main` function as the program:

        :::python
        from mast.cli import Cli

        def main(arg_1=[], arg_2=2.0, flag_1=True):
            do_something()

        if __name__ == "__main__":
            cli = Cli(main=main)
            try:
                cli.run()
            except:
                log_something()
                raise
    """
    def __init__(self, description="", main=None, optionals=None):
        """
        _method_: `mast.cli.Cli.__init__(self, description="", main=None, optionals=None)`

        This is the constructor for this class. A few options are
        available which allows defining how the program will appear
        to the user.

        Parameters:

        * `description`: This is the description which will be
        displayed (along with details on the available parameters) to
        the user when they provide a `-h` or `--help` on the command
        line
        * `main`: If you provide an argument to this parameter,
        it should be a function, and this function will be treated
        as the main function and it will be executed when your program
        is called from the command line. __NOTE__ that if `main` is
        provided, you cannot create sub-commands using the `command`
        decorator.
        * `optionals`: If provided, `optionals` should be a `dict`
        containing the name and value of optional arguments. Any parameter
        not in this `dict` will be considered required by your program.
        """
        self.main = main
        self.optionals = optionals
        self.functions = {}
        self.parser = argparse.ArgumentParser(
            description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter)
        if self.main is None:
            self.subparsers = self.parser.add_subparsers()
        else:
            self.create_subparser(self.main)

    def create_subparser(self, fn, name=None, category=None):
        """
        _method_: `mast.cli.Cli.create_subparser(self, fn)`

        __Internal use only__

        collects information about decorated function, builds a
        subparser then returns the function unchanged.

        Parameters:

        * `fn`: The function to create a sub-command for.
        """
        if not name:
            name = fn.__name__
        self.functions[name] = fn

        desc = fn.__doc__
        args, _, __, defaults = inspect.getargspec(fn)

        args = [] if not args else args
        defaults = [] if not defaults else defaults

        if self.main is None:
            _parser = self.subparsers.add_parser(
                name.replace("_", "-"),
                description=desc,
                formatter_class=argparse.RawDescriptionHelpFormatter)
            _parser.set_defaults(func=self.functions[name])
        else:
            _parser = self.parser
            _parser.set_defaults(func=self.main)

        positionals = args[:len(args) - len(defaults)]
        keywords = [x for x in zip(args[len(args) - len(defaults):], defaults)]

        for arg in positionals:
            if arg in self.optionals:
                _parser.add_argument(
                    arg, nargs='?', default=self.optionals[arg])
            else:
                _parser.add_argument(arg)

        for arg, default in keywords:
            _arg = arg.replace("_", "-")
            # Try the lower case first letter for the short option first
            params = _parser._option_string_actions
            if '-{}'.format(arg[0]) not in params:
                flag = ('-{}'.format(arg[0]), '--{}'.format(_arg))
            # Then the upper-case first letter for the short option
            elif '-{}'.format(arg[0]).upper() not in params:
                flag = ('-{}'.format(arg[0]).upper(), '--{}'.format(_arg))
            # otherwise no short option
            else:
                flag = ('--{}'.format(_arg), )
            if isinstance(default, (str, type(None))):
                _parser.add_argument(*flag, type=str, default=default)
            elif isinstance(default, list):
                _parser.add_argument(*flag, action='append')
            elif isinstance(default, bool):
                if default:
                    _parser.add_argument(
                        *flag, action='store_false', default=default)
                else:
                    _parser.add_argument(
                        *flag, action='store_true', default=default)
            elif isinstance(default, int):
                _parser.add_argument(*flag, type=int, default=default)
            elif isinstance(default, float):
                _parser.add_argument(*flag, type=float, default=default)

    def command(self, name=None, category=None):
        """
        _method_: `mast.cli.Cli.command(self)`

        This decorator allows you to decorate many functions which
        will then be available to the user as sub-commands. Default
        arguments to all parameters will be required. Please see above
        for how default arguments are mapped to types.

        Parameters:

        This method accepts no arguments.

        Usage

            :::python
            from mast.cli import Cli

            cli = Cli()

            @cli.command
            def function_1(param=""):
                do_something()

            @cli.command
            def function_2(param=""):
                do_something()

            if __name__ == "__main__":
                try:
                    cli.run()
                except:
                    logger.exception()
                    raise
        """
        def inner(fn):
            if self.main is not None:
                print("The Cli decorator cannot be used when main is specified")
                sys.exit(-1)
            self.create_subparser(fn)
            return fn
        return inner

    def run(self):
        """
        _method_: `mast.cli.Cli.run(self)`

        This method will attempt to parse the provided arguments and
        execute the required function.

        Parameters:

        This method accepts no arguments.
        """
        args = self.parser.parse_args()
        func = args.func
        _args, _, __, defaults = inspect.getargspec(func)
        kwargs = {}
        for arg in _args:
            kwargs[arg] = getattr(args, arg)
        func(**kwargs)
