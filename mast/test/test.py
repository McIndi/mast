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
_module_: `mast.test.test`

DESCRIPTION:

This module contains a Test class which can be used to
run integration tests for CLI commands.
"""
import re
import sys
import shlex
import colorama
import argparse
import subprocess
from time import time
from lxml import etree
colorama.init()


yellow = lambda x: "".join([colorama.Fore.LIGHTYELLOW_EX,
                            str(x),
                            colorama.Fore.RESET])

magenta = lambda x: "".join([colorama.Fore.LIGHTMAGENTA_EX,
                             str(x),
                             colorama.Fore.RESET])

green = lambda x: "".join([colorama.Fore.LIGHTGREEN_EX,
                             str(x),
                             colorama.Fore.RESET])

red = lambda x: "".join([colorama.Fore.LIGHTRED_EX,
                             str(x),
                             colorama.Fore.RESET])

blue = lambda x: "".join([colorama.Fore.LIGHTBLUE_EX,
                          str(x),
                          colorama.Fore.RESET])

cyan = lambda x: "".join([colorama.Fore.LIGHTCYAN_EX,
                          str(x),
                          colorama.Fore.RESET])

dim = lambda x: "".join([colorama.Style.DIM,
                         str(x),
                         colorama.Style.RESET_ALL])

bright = lambda x: "".join([colorama.Style.BRIGHT,
                         str(x),
                         colorama.Style.RESET_ALL])

test_passed = green("TEST PASSED!")

test_failed = red("TEST FAILED!")

def system_call(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False):
    """
    # system_call

    helper function to shell out commands. This should be platform
    agnostic.
    """
    stderr = subprocess.STDOUT
    pipe = subprocess.Popen(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        shell=shell)
    stdout, stderr = pipe.communicate()
    return stdout, stderr, pipe.returncode

    
class Test(object):
    """
    _class_: `mast.test.test.Test(object)`
    
    DESCRIPTION:
    
    This is a generic Test class. It is instanciated with a
    node which contains one child "command" node which contains
    the command to test. This command will be run and it's stdout,
    stderr and return code will be captured for inspection.
    
    In addition to the child "command" node the node passed in must
    have a unique "name" attribute. This attribute is used to uniquely
    identify each test.
    
    After the above requirements are satisfied, you can test the output
    of the command with the following child nodes:
    
    * `matches`: Must contain a regular expression to match against. If at
    least one match can be found in stdout or stderr, the test passes.
    * `no-matches`: Must contain a regular expression to match against. It
    there are any matches found in either stdout or stderr then the test
    will fail.
    * `contains`: Must contain a string, if this string appears in either
    stdout or stderr then the test will pass
    * `no-contains`: Must contain a string, If this string appears in either
    stdout or stderr, then the test will fail
    * `returncode`: Must contain an integer, if the return code of the command
    matches this returncode then the test will pass
    
    USAGE:
        
        :::python
        >>> node = xml.etree.ElementTree.fromstring("<test><command>echo cat<command><match>c.t</match><no-contains>dog</no-contains></test>")
        >>> t = Test(node, profile=False)
        >>> t.run_tests()
    """
    def __init__(self, node, profile):
        """
        _method_: `mast.test.test.Test.__init__(self, node, profile)`
        
        DESCRIPTION:
        
        Constructor for `Test` class.
        
        RETURNS:
        
        `None`
        
        USAGE:
        
            :::python
            >>> node = xml.etree.ElementTree.fromstring("<test><command>echo cat<command><match>c.t</match><no-contains>dog</no-contains></test>")
            >>> t = Test(node, profile=False)
            >>> t.run_tests()

        PARAMETERS:
        
        * `node`: must be an instance of either `xml.etree.ElementTree.Element`
        or `lxml.etree.ElementTree.Element` conforming to the specifications
        above.
        * `profile`: If `True`, then the run time of the command will be prepended
        to the output of each test.
        """
        self.node = node
        self.profile = profile

        self.raw_command = self.node.find("./command").text
        self.command = shlex.split(self.raw_command)
        self.name = self.node.get("name")

        self.results = []

    def run_tests(self):
        """
        _method_: `mast.test.test.Test.run_tests(self)`
        
        DESCRIPTION:
        
        Run the tests defined in the node passed into the constructor.
        
        RETURNS:
        
        `None`
        
        Usage:

            :::python
            >>> node = xml.etree.ElementTree.fromstring("<test><command>echo cat<command><match>c.t</match><no-contains>dog</no-contains></test>")
            >>> t = Test(node, profile=False)
            >>> t.run_tests()
        
        PARAMETERS:
        
        This method accepts no arguments.
        """
        if self.profile:
            start = time()

            out, err, rc = system_call(self.command, shell=True)
            end = time()
            run_time = end - start
        else:
            out, err, rc = system_call(self.command, shell=True)
        self.out = "" if out is None else out
        self.err = "" if err is None else err
        self.rc = rc
        self.run_matches()
        self.run_no_matches()
        self.run_contains()
        self.run_no_contains()
        self.run_returncode()
        if self.profile:
            self.results = [cyan(str(run_time)) + ": " + x for x in self.results]

    def run_matches(self):
        pass_tmpl = "{} test '{}' regex '{}' matched {}"
        fail_tmpl = "\n\t".join(("{0}",
                                 "test '{1}' regex '{2}' did not match stdout '{3}'",
                                 "test '{1}' regex '{2}' did not match stderr '{4}'"))
        patterns = self.node.findall("./match")
        patterns = [n.text for n in patterns]
        for pattern in patterns:
            if re.search(pattern, self.out) is not None:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          magenta(pattern),
                                          bright("stdout"))
                self.results.append(result)
            elif re.search(pattern, self.err) is not None:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          magenta(pattern),
                                          bright("stderr"))
                self.results.append(result)
            else:
                result = fail_tmpl.format(test_failed,
                                          blue(self.name),
                                          magenta(pattern),
                                          self.out,
                                          self.err)
                self.results.append(result)

    def run_no_matches(self):
        pass_tmpl = "{} test '{}' regex '{}' was not found in {}"
        fail_tmpl = "{} test '{}' regex '{}' was found in {}"
        patterns = self.node.findall("./no-match")
        patterns = [n.text for n in patterns]
        for pattern in patterns:
            if re.search(pattern, self.out) is None and re.search(pattern, self.err) is None:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          magenta(pattern),
                                          bright("stdout or stderr"))
                self.results.append(result)
            else:
                if re.search(pattern, self.out) is not None:
                    result = fail_tmpl.format(test_failed,
                                              blue(self.name),
                                              magenta(pattern),
                                              bright("stdout"))
                elif re.search(pattern, self.err) is not None:
                    result = fail_tmpl.format(test_failed,
                                              blue(self.name),
                                              magenta(pattern),
                                              bright("stderr"))
                self.results.append(result)

    def run_contains(self):
        pass_tmpl = "{} test '{}' {} contained '{}'"
        fail_tmpl = "\n\t".join(("{0}",
                                "test {1} '{2}' was not present in stdout '{3}'",
                                "test {1} '{2}' was not present in stderr '{4}'"))
        strings = self.node.findall("./contains")
        strings = [n.text for n in strings]
        for string in strings:
            if string in self.out:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          bright("stdout"),
                                          magenta(string))
                self.results.append(result)
            elif string in self.err:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          bright("stdout"),
                                          magenta(string))
                self.results.append(result)
            else:
                result = fail_tmpl.format(test_failed,
                                          blue(self.name),
                                          magenta(string),
                                          self.out,
                                          self.err)
                self.results.append(result)

    def run_no_contains(self):
        pass_tmpl = "{} test '{}' {} did not contain '{}'"
        fail_tmpl = "{} test '{}' {} contained '{}'"
        strings = self.node.findall("./no-contains")
        strings = [n.text for n in strings]
        for string in strings:
            if string not in self.out and string not in self.err:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          bright("stdout or stderr"),
                                          magenta(string))
                self.results.append(result)
            else:
                if string in self.out:
                    result = fail_tmpl.format(test_failed,
                                              blue(self.name),
                                              bright("stdout"),
                                              magenta(string))
                elif string in self.err:
                    result = fail_tmpl.format(test_failed,
                                              blue(self.name),
                                              bright("stderr"),
                                              magenta(string))
                self.results.append(result)

    def run_returncode(self):
        pass_tmpl = "{} test '{}' command '{}' exited with return code '{}'"
        fail_tmpl = "{} test '{}' command '{}' exited with return code '{}' not '{}'"
        returncodes = self.node.findall("./returncode")
        returncodes = [int(n.text) for n in returncodes]
        for returncode in returncodes:
            if self.rc == returncode:
                result = pass_tmpl.format(test_passed,
                                          blue(self.name),
                                          magenta(self.raw_command),
                                          blue(str(self.rc)))
                self.results.append(result)
            else:
                result = fail_tmpl.format(test_failed,
                                          blue(self.name),
                                          magenta(self.raw_command),
                                          blue(str(returncode)),
                                          blue(self.rc))
                self.results.append(result)

                
def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=argparse.FileType("r"))
    parser.add_argument("-p", "--profile", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    tree = etree.parse(args.file)
    nodes = tree.findall("test")
    
    num_tests = 0
    passed = 0
    failed = 0
    start = time()
    for node in nodes:
        test = Test(node, profile=args.profile)
        test.run_tests()
        num_tests += len(test.results)
        for result in test.results:
            if "TEST PASSED!" in result:
                passed += 1
            elif "TEST FAILED!" in result:
                failed += 1
            else:
                pass
            print(result)
    end = time()
    summary = "\n\n-----\nRan {} tests in {}; {} passed, {} failed"
    summary = summary.format(bright(str(num_tests)),
                             cyan(str(end-start)),
                             green(str(passed)),
                             red(str(failed)))
    print(summary)

if __name__ == "__main__":
    main()
