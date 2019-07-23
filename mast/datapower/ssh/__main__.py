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
from mast.datapower.datapower import Environment
from getpass import getpass
from mast.cli import Cli
import sys
import os

# Fix issue with __main__.py messing up command line help
sys.argv[0] = "mast-ssh"

try:
    import readline
except ImportError as e:
    import pyreadline as readline  # lint:ok
import atexit

histfile = os.path.join(os.path.expanduser("~"), '.mast_ssh_history')
try:
    readline.read_history_file(histfile)
except IOError:
    pass
atexit.register(readline.write_history_file, histfile)

PASSWORD_CHANGE_PROMPTS = [
    "Please enter new password: ",
    "Please re-enter new password to confirm: ",
]
PASSWORD_PROMPTS = ["Password: "] + PASSWORD_CHANGE_PROMPTS

class Input(object):
    """This is a class representing the ssh command prompt. This is a
    very simple CLI. It has a queue (python list) named commands which
    can be added to. If next() is called and this list is empty then
    the user is prompted for the next command"""
    def __init__(self, prompt):
        """Initialization method"""
        self.commands = []
        self.prompt = prompt

    def send(self, command):
        """Adds a command to the queue (the python list) commands"""
        self.commands.append(command)

    def next(self):
        """This is provided so that this object can function as
        an iterator."""
        if self.prompt in PASSWORD_CHANGE_PROMPTS:
            return getpass(self.prompt)

        try:
            return self.commands.pop(0)
        except IndexError:
            if self.prompt in PASSWORD_PROMPTS:
                return getpass(self.prompt)
            return raw_input(self.prompt)

    def __iter__(self):
        """return self as an iterator"""
        return self


def initialize_appliances(env, domain='default', timeout=120):
    """This initiates an ssh session, extracts the prompt and
    displays the initial output."""
    responses = []
    for appliance in env.appliances:
        _resp = appliance.ssh_connect(domain=domain, timeout=timeout)
        # Sanitize password from output
        password = appliance.credentials.split(":", 1)[1]
        _resp = _resp.replace(password, "*"*8)
        responses.append(_resp)
    output = format_output(responses, env)
    prompt = output.splitlines()[-1:][0] + ' '
    output = '\n'.join(output.splitlines()[:-1]) + '\n'
    display_output(output)
    return prompt


def issue_command(command, env, timeout=60):
    """This method issues a command to the DataPower's CLI."""
    responses = []
    for appliance in env.appliances:
        resp = appliance.ssh_issue_command(command)
        responses.append(resp)
    return responses


def compare(array):
    """Return True if all responses from the DataPowers are the same,
    False otherwise."""
    return array.count(array[0]) == len(array)


def format_output(array, env):
    """Format the output based on the output of compare(array). If all of
    the appliances responded with the same output, then it will be printed
    only once (This is to make it appear as if you are speaking to one
    appliance). Otherwise, if any of the output is different then every
    response is printed individually prepended wiht the appliance's name/ip."""
    seperator = '\n\n{}\n----\n\n'
    if compare(array):
        return array[0]
    response = ''
    for index, appliance in enumerate(env.appliances):
        response += seperator.format(appliance.hostname) + array[index]
    return response + '\n\n> '


def display_output(string):
    """This outputs string to stdout and immediately flushes stdout. This is
    used to prevent the print statment from printing a newline each time it
    is invoked."""
    sys.stdout.write(string)
    sys.stdout.flush()


def main(appliances=[],
         credentials=[],
         domain="default",
         input_file="",
         timeout=120):
    """A multi-box ssh client, designed specifically for IBM DataPower
appliances.

__IMPORTANT__: This will not work for other types of machines, this is
because since the DataPower doesn't follow the SSH spec exactly,
special care was taken so we would properly handle their implementation.
The steps which were taken to achieve this handling prevent it from
being reliably used for other machine types

Parameters:

* `-a, --appliances`: The hostname(s), ip addresse(s), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases please see the comments in `hosts.conf` located
in `$MAST_HOME/etc/default`.
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password` and should be provided in a space-seperated list
if multiple are provided. If you would prefer to not use plain-text
passwords, you can use the output of `$ mast-system xor <username:password>`.
* `-d, --domain`: The domain to log into
* `-i, --input-file`: If provided, it should point to a text file which
contains cli commands (one-per-line) which will be executed in order on
each appliance
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
"""
    env = Environment(appliances, credentials)
    prompt = initialize_appliances(env, domain, timeout=timeout)
    global _input
    _input = Input(prompt)
    if input_file:
        if not os.path.exists(input_file) and os.path.isfile(input_file):
            print "input_file must be a file containing cli commands to issue"
            sys.exit(-1)
        with open(input_file, "r") as fin:
            for command in fin:
                output = issue_command(command, env, timeout=timeout)
                output = format_output(output, env)
                prompt = output.splitlines()[-1:][0] + ' '
                _input.prompt = prompt
                # output = '\n'.join(output.splitlines()[:-1]) + '\n'
                display_output(output)
                if ('Goodbye' in prompt) or ('Goodbye' in output):
                    print('Goodbye')
                    sys.exit(0)
    for command in _input:
        output = issue_command(command, env, timeout=timeout)
        output = format_output(output, env)
        prompt = output.splitlines()[-1:][0] + ' '
        _input.prompt = prompt
        output = '\n'.join(output.splitlines()[:-1]) + '\n'
        display_output(output)
        if ('Goodbye' in prompt) or ('Goodbye' in output):
            print('Goodbye')
            break
    raise SystemExit


if __name__ == '__main__':
    try:
        cli = Cli(main=main, description=main.__doc__)
        cli.run()
    except Exception, e:
        # generic try...except just for future use
        raise
