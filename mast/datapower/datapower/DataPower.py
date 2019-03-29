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
_module_: `mast.datapower.datapower.DataPower`

A library which provides various utilities for interacting with IBM
DataPower appliances. The most important of which is the DataPower
class which provides many convenient wrappers around the SOMA XML
Management Interface as well as some methods to interact with the CLI
Management Interface (ssh).
"""
from dpSOMALib import SomaRequest as Request
import xml.etree.cElementTree as etree
from functools import partial, wraps
from mast.timestamp import Timestamp
from mast.config import get_config
from mast.hashes import get_sha1
from mast.logging import make_logger, logged
from datetime import datetime
from time import time, sleep
from StringIO import StringIO
import zipfile
import logging
import random
import base64
import os
import re


class AuthenticationFailure(Exception):
    """
    _class_: `mast.datapower.datapower.AuthenticationFailure(Exception)`

    Description:

    Raised when the appliance responds with a 200 status code,
    but includes `Authentication Failure` in the response body
    """
    pass


class FailedToRetrieveBackup(Exception):
    """
    _class_: `mast.datapower.datapower.FailedToRetrieveBackup(Exception)`

    Description:

    Raised when the appliance sends back a response containing an
    empty file node when asked for a normal backup. This usually
    means an intermediate failure or too little space in
    `temporary:///` to store the export. This can usually be fixed
    by cleaning up the filesystem or trying again.
    """
    pass


class SSHTimeoutError(Exception):
    """
    _class_: `mast.datapower.datapower.SSHTimeoutError(Exception)`

    Description:

    Raised when the appliance takes longer to respond to a cli
    command than the specified timeout.
    """
    pass


try:
    import Crypto.Cipher.AES
    orig_new = Crypto.Cipher.AES.new

    def fixed_AES_new(key, *ls):
        """
        _function_: `mast.datapower.datapower.fixed_AES_new(key, *ls)`

        Description:

        __Internal Use__

        This is a workaround to
        [this bug](https://github.com/dlitz/pycrypto/issues/149)
        """
        if Crypto.Cipher.AES.MODE_CTR == ls[0]:
            ls = list(ls)
            ls[1] = ''
        return orig_new(key, *ls)

    Crypto.Cipher.AES.new = fixed_AES_new
    # END HACK
    import paramiko
    paramiko_is_present = True
    make_logger('paramiko')
except ImportError:
    paramiko_is_present = False


def _escape(string):
    """
    _function_: `mast.datapower.datapower._escape(string)`

    Description:

    __Internal Use__

    This function removes newlines and escapes single and double
    quotations

    Returns:

    A Python `str` object

    Usage:

        :::python
        >>> _escape("\"'\r\n'\"")
        &quot;&apos;&apos;&quot;

    Parameters:

    * `string`: A python `str` object which you would like escaped.
    """
    return string.replace(
        "\n", "").replace(
        "\r", "").replace(
        "'", "&apos;").replace(
        '"', "&quot;")


def correlate(func):
    """
    _decorator_: `mast.datapower.datapower.correlate(func)`

    Description:

    Decorator which changes self.correlation_id before executing
    a function and changes it back to it's previous value after
    execution

    Returns:

    A Python `function`

    Parameters:

    * `func`: A callable which you would like executed with a different
    `correlation_id`.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        old_correlation_id = self.correlation_id
        self.correlation_id = random.randint(1000000, 9999999)
        ret = func(self, *args, **kwargs)
        self.correlation_id = old_correlation_id
        return ret
    return wrapper


BASE_XPATH = '{http://schemas.xmlsoap.org/soap/envelope/}Body/'
BASE_XPATH += '{http://www.datapower.com/schemas/management}response/'

ACTION_XPATH = BASE_XPATH
ACTION_XPATH += '{http://www.datapower.com/schemas/management}result/'

CONFIG_XPATH = BASE_XPATH
CONFIG_XPATH += '{http://www.datapower.com/schemas/management}config/'

STATUS_XPATH = BASE_XPATH
STATUS_XPATH += '{http://www.datapower.com/schemas/management}status/'

FILESTORE_XPATH = BASE_XPATH
FILESTORE_XPATH += '{http://www.datapower.com/schemas/management}filestore/'


def pretty_print(elem, level=0):
    """
    _function_: `mast.datapower.datapower.pretty_print(elem, level=0)`

    Description:

    Given an xml.etree.ElementTree.Element, insert whitespace
    so that when xml.etree.ElementTree.tostring is called on
    it, it will be pretty-printed.

    Usage:

        :::python
        pretty_print(elem)

    Parameters:

    * `elem` - Should be an instance of xml.etree.ElementTree.Element
    * `level` - Used by function itself for recursive calls should not
    be passed in by user
    """
    i = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            pretty_print(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


class DPResponse(object):
    """
    _class_: `mast.datapower.datapower.DPResponse(object)`

    Description:

    This is a generic class used to wrap an XML response received
    from a DataPower appliance from the SOMA XML management interface.
    """

    def __init__(self, response):
        """
        _method_: `mast.datapower.DPResponse(object)`

        Description:

        This is a generic response object.

        Returns:

        `None`

        Usage:

            :::python
            dp = DataPower('hostname', 'user:password')
            resp = dp.get_config('EthernetInterface')
            # resp is now an instance of DPResponse
            print resp.text
            print resp.xml
            print resp.pretty
            str(resp)
            repr(resp)

        Parameters:

        * `response`: The XML response from a DataPower appliance
        as a Python `str`
        """
        self.text = response.replace(
            '\r', '').replace('\n', '').replace('  ', ' ')

    @property
    def xml(self):
        """
        _property_: `mast.datapower.datapower.DPResponse.xml`

        Description:

        Returns an xml.etree.cElementTree object created by parsing
        the response. This is cached after the first call.

        Returns:

        `xml.etree.cElementTree`

        Usage:

            :::python
            >>> resp = DPResponse(dp_xml_response)
            >>> resp.xml
            <object 'xml.etree.cElementTree'>

        Parameters:

        This method accepts no arguments
        """
        if not hasattr(self, '_xml'):
            if hasattr(etree, 'register_namespace'):
                etree.register_namespace(
                    'dp',
                    'http://www.datapower.com/schemas/management')
                etree.register_namespace(
                    'env',
                    'http://schemas.xmlsoap.org/soap/envelope/')
            else:
                pass
            self._xml = etree.fromstring(self.text)
        return self._xml

    @property
    def pretty(self):
        """
        _property_: `mast.datapower.datapower.pretty`

        Description:

        Returns a pretty-printed string of the response XML.
        This is cached after the first call.

        Returns:

        `str`

        Usage:

            :::python
            >>> resp = DPResponse(dp_xml_response)
            >>> resp.pretty
            ...Pretty-printed xml as str...

        Parameters:

        This method accepts no arguments
        """
        if not hasattr(self, '_pretty'):
            pretty_print(self.xml)
            self._pretty = etree.tostring(self.xml)
        return self._pretty

    def __str__(self):
        """
        _method_: `mast.datapower.datapower.DPResponse.__str__`

        Description:

        Pretty-print the response XML and return as `str`.
        This is cached after the first call.

        Same as DPResponse.pretty

        Returns:

        `str`

        Usage:

            :::python
            >>> resp = DPResponse(dp_xml_response)
            >>> resp.__str__
            ...Pretty-printed xml as str...

        Parameters:

        This method accepts no arguments
        """
        return self.pretty

    def __repr__(self):
        """
        _method_: `mast.datapower.datapower.DPResponse.__repr__`

        Description:

        Remove newlines and colapse whitespace of the response and return
        as `str`.

        Same as DPResponse.text

        Returns:

        `str`

        Usage:

            :::python
            >>> resp = DPResponse(dp_xml_response)
            >>> resp.pretty
            ...xml with unnecessary whitespace removed...

        Parameters:

        This method accepts no parameters
        """
        return self.text


class BooleanResponse(DPResponse):
    """
    _class_: `mast.datapower.datapower.BooleanResponse(DPResponse)`

    Description:

    This is a DPResponse object with one additional property
    it will attempt to convey the success of the action through
    the __nonzero__ magic method, so a test like:

        :::python
        if resp:
            success
        else:
            failure

    will work.

    This is automatically used instead of DPResponse automatically
    when a DataPower Method involving a do-action is called as well
    as a few other methods which are known to return 'OK' surrounded
    by copious amounts of whitespace.
    """
    def __nonzero__(self):
        """
        _method_: `mast.datapower.datapower.BooleanResponse.__nonzero__(self)`

        Description:

        Tests for the existance of the string " OK " to be in the
        response XML.

        Returns:

        `boolean`

        Usage:

            :::python
            >>> resp = BooleanResponse("<xml> OK </xml>")
            >>> print resp.__nonzero__
            True
            >>> resp = BooleanResponse("<xml></xml>")
            >>> print resp.__nonzero__
            False

        Parameters:

        This method accepts no arguments
        """
        if 'OK' in self.text:
            return True
        return False


class AMPBooleanResponse(DPResponse):
    """
    _class_: `mast.datapower.datapower.AMPBooleanResponse(DPResponse)`

    Description:

    Returned when an AMP request is issued, this is currently
    only used on DataPower.firmware_upgrade()

    This is a DPResponse object with one additional property
    it will attempt to convey the success of the action through
    the __bool__ magic method, so a test like:

        :::python
        if resp:
            success
        else:
            failure

    will work.

    This is automatically used instead of DPResponse automatically
    when a DataPower Method involving a do-action is called as well
    as a few other methods which are known to return 'OK' surrounded
    by copious amounts of whitespace.

    """
    def __nonzero__(self):
        """
        _method_: `mast.datapower.datapower.AMPBooleanResponse.__nonzero__(self)`

        Description:

        Tests for the existance of the string ">ok<" to be in the
        response XML.

        Returns:

        `boolean`

        Usage:

            :::python
            >>> resp = BooleanResponse("<xml>ok</xml>")
            >>> print resp.__nonzero__
            True
            >>> resp = BooleanResponse("<xml></xml>")
            >>> print resp.__nonzero__
            False

        Parameters:

        This method accepts no arguments
        """
        if '>ok<' in self.text:
            return True
        return False


class StatusResponse(DPResponse):
    """
    _class_: `mast.datapower.datapower.StatusResponse(DPResponse)`

    Description:

    __WARNING__: This implementation is currently broken, but will
    be fixed soon.

    This is a DPResponse object with one additional property
    dictionary which returns the response as a python dict.

    This is automatically used instead of DPResponse automatically
    when DataPower.get_status() is called.
    """
    @property
    def dictionary(self):
        """
        BROKEN IMPLEMENTATION!
        """
        if not hasattr(self, "_dict"):
            self._dict = {}
            nodes = self.xml.findall(STATUS_XPATH)
            for index, node in enumerate(nodes):
                name = '{}_{}'.format(node.tag, index)
                self._dict[name] = {}
                for n in node.findall('.//'):
                    self._dict[name][n.tag] = n.text
        return self._dict


class ConfigResponse(DPResponse):
    """
    _class_: `mast.datapower.datapower.ConfigResponse(DPResponse)`

    __WARNING__: This implementation is currently broken, but will
    be fixed soon.

    This is a DPResponse object with one additional property
    dictionary which returns the response as a python dict

    This is automatically used instead of DPResponse automatically
    when DataPower.get_config() is called.
    """
    @property
    def dictionary(self):
        """
        BROKEN IMPLEMENTATION!
        """
        if not hasattr(self, "_dict"):
            self._dict = {}
            nodes = self.xml.findall(CONFIG_XPATH)
            for node in nodes:
                name = node.get("name")
                self._dict[name] = {}
                for n in node.findall('.//'):
                    self._dict[name][n.tag] = n.text
        return self._dict

logger = logging.getLogger("DataPower")
logger.addHandler(logging.NullHandler())

global_config = get_config("appliances.conf")

class DataPower(object):
    """
    _class_: `mast.datapower.datapower.DataPower(object)`

    Description:

    This class represents an IBM DataPower appliance. It contains
    numerous convenience methods which are available for use in
    your scripts.

    Everything is lazy in this class. Instanciation will not prompt
    any information to be sent to or from the appliance being
    represented.

    Usage:

        :::python
        >>> dp = DataPower("localhost", "user:pass")
        >>> print dp.hostname
        >>> print dp.domains
    """

    def __init__(self,
                 hostname,
                 credentials,
                 domain='default',
                 scheme=global_config.get("global", "soma_scheme"),
                 port=global_config.getint("global", "soma_port"),
                 uri=global_config.get("global", "soma_uri"),
                 test_case=global_config.get("global", "soma_spec_file"),
                 web_port=global_config.getint("global", "web_port"),
                 ssh_port=global_config.getint("global", "ssh_port"),
                 environment=None,
                 check_hostname=True,
                 retry_interval=global_config.getint("global", "retry_interval")):
        """
        _method_: `mast.datapower.datapower.DataPower.__init__(self, hostname, credentials, domain='default', scheme='https', port='5550', uri='/service/mgmt/current', test_case='etc/v7000-xi52.xml', web_port='9090', ssh_port=22, environment=None, check_hostname=True)`

        Description:

        This method instanciates an instance of a DataPower object.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")

        Parameters:

        * `hostname`: Can be a hostname, IP Address, or an alias configured in
        $MAST_HOME/etc/local/hosts.conf
        * `credentials`: should be a string that is a username and password
        seperated by a colon (ie. "user:pass")
        * `domain`: The initial domain to start in.
        * `scheme`: either "http" or "https" defaults to "https"
        * `port`: The port for the xml management interface defaults
        to 5550 (should be a string not an int)
        * `uri`: The URI of the SOMA XML Management Interface defaults
        to "/service/mgmt/current"
        * `test_case`: The XML Test Case file (These are provided by McIndi)
        they are based on your model and firmware see the documentation as
        to which one to use
        * `web_port`: the port of the Web Management Interface defaults to
        "9090"
        * `ssh_port`: the port (as an int) of the CLI Management Interface (SSH)
        * `environment`: The environment you want this instance to be associated
        with in the logs.
        * `check_hostname`: If `False` hostname verification will be disabled
        for TLS. Defaults to `True`
        """
        hosts_config = get_config("hosts.conf")
        self.session_id = random.randint(1000000, 9999999)
        self.correlation_id = None
        self.check_hostname = check_hostname
        self._history = []
        self.hostname = hostname
        if hosts_config.has_option("hosts", hostname):
            self._hostname = hosts_config.get("hosts", hostname)
        else:
            self._hostname = hostname

        self.credentials = credentials
        self.scheme = scheme
        self.port = port
        self.web_port = web_port
        self.ssh_port = ssh_port
        self.uri = uri
        self.test_case = test_case
        self.retry_interval = retry_interval

        self.domain = domain
        self._environment = environment

        logger = logging.getLogger("DataPower.{}".format(hostname))
        logger.addHandler(logging.NullHandler())
        self.paramiko_is_present = paramiko_is_present
        if not self.paramiko_is_present:
            self.log_warn(
                "Paramiko Library is not present "
                "any ssh related functionality will "
                "not work.")

        config = get_config("appliances.conf")
        if config.has_section(self.hostname):

            if config.has_option(self.hostname, 'soma_port'):
                self.port = config.getint(self.hostname, 'soma_port')

            if config.has_option(self.hostname, 'web_port'):
                self.web_port = config.getint(self.hostname, 'web_port')

            if config.has_option(self.hostname, 'ssh_port'):
                self.ssh_port = config.getint(self.hostname, 'ssh_port')

            if config.has_option(self.hostname, 'soma_scheme'):
                self.scheme = config.get(self.hostname, 'soma_scheme')

            if config.has_option(self.hostname, 'soma_uri'):
                self.uri = config.get(self.hostname, 'soma_uri')

            if config.has_option(self.hostname, 'soma_spec_file'):
                self.test_case = config.get(self.hostname, 'soma_spec_file')

            if config.has_option(self.hostname, 'retry_interval'):
                self.retry_interval = config.getint(self.hostname, 'retry_interval')

        self.request = Request(self.scheme,
                               self._hostname,
                               self.port,
                               self.uri,
                               self.credentials,
                               self.test_case)
        self._add_dynamic_methods()

        # Compatability
        self.list_dir = self.get_filestore

    def __str__(self):
        """
        _method_: `mast.datapower.datapower.DataPower.__str__(self)`

        Description:

        Returns the `str`ing representation of the appliance, which is
        the hostname surrounded by single quotes (')

        Returns:

        `str`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> str(dp)
            'localhost'

        Parameters:

        This method accepts no arguments
        """
        return "'{}'".format(self.hostname)

    def __repr__(self):
        """
        _method_: `mast.datapower.datapower.DataPower.__repr__(self)`

        Description:

        Returns the `str`ing representation of the appliance, which is
        the hostname surrounded by single quotes (')

        Returns:

        `str`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> repr(dp)
            'localhost'

        Parameters:

        This method accepts no arguments
        """
        return "'{}'".format(self.hostname)

    def get_logger(self):
        """
        _method_: `mast.datapower.datapower.get_logger(self)`

        Description:

        Instanciate and return a `logging.Logger` instance associated
        with this appliance. The logger will be configured according
        to logging.conf in the section "appliance".

        Returns:

        `logging.Logger`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> logger = dp.get_logger()
            >>> logger.info("Informational message")
            >>> logger.debug("Debug message")

        Parameters:

        This method accepts no arguments
        """
        return make_logger("DataPower.{}".format(self.hostname))

    @correlate
    @logged("audit")
    def ssh_connect(self, domain='default', port=22, timeout=120):
        """
        _method_: `mast.datapower.datapower.DataPower.ssh_connect(self, domain='default', port=22, timeout=120)`

        Descritpion:

        This will attempt to connect to the DataPower appliance over SSH.
        Once connected you can issue commands with DataPower.ssh_issue_command.

        Don't forget to disconnect by calling `DataPower.ssh_disconnect`.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.ssh_connect()
            >>> dp.ssh_issue_command("show mem")
            ...Memory Usage Output...
            >>> dp.ssh_disconnect()

        Parameters:

        * `domain`: The domain to log in to, defaults to `default`
        * `port`: The ssh port to connect to. Expects an `int`, defaults
        to 22
        * `timeout`: The amount of time (in seconds) to wait for the
        connection to become active. If the timeout is exceeded, a
        `SSHTimeoutError` is raised
        """
        try:
            self.log_info("Attempting SSH connection")
            self.domain = domain
            if not self.paramiko_is_present:
                self.log_warn("Paramiko library not installed. Exiting")
                raise NotImplementedError
            self._ssh = paramiko.SSHClient()
            username, password = self.credentials.split(':', 1)

            ssh_config = get_config("ssh.conf")
            if ssh_config.getboolean("ssh", "auto_add_keys"):
                self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self.log_debug("Attempting to initialize SSH subsystem")
                self._ssh.connect(
                    self._hostname,
                    port=self.ssh_port,
                    username=username,
                    password=password,
                    timeout=timeout)
                transport = self._ssh.get_transport()
                transport.set_keepalive(5)
                self._ssh_conn = self._ssh.invoke_shell()
                self.log_debug("Successfully initialized SSH subsystem")
            except Exception, e:
                self.log_error(
                    "Exception occurred initializing"
                    "SSH subsystem: {}".format(str(e)))
                raise
            while not self._ssh_conn.recv_ready():
                sleep(0.25)
            resp = ""
            while self._ssh_conn.recv_ready():
                resp += self._ssh_conn.recv(1024)
            resp += self.ssh_issue_command("{}\n".format(username))
            resp += self.ssh_issue_command("{}\n".format(password))
            if resp.strip().lower().endswith("login:"):
                raise AuthenticationFailure(
                    "Invalid credentials provided, please ensure "
                    "that account is not locked")
            resp += self.ssh_issue_command("{}\n".format(domain))

            self.log_info("SSH session now active")
        except paramiko.SSHException, e:
            self.log_error('SSH connection failed: %s' % (e))
            raise
        return resp

    @correlate
    @logged("audit")
    def ssh_is_connected(self):
        """
        _method_: `mast.datapower.datapower.DataPower.ssh_is_connected(self)`

        Description:

        Determines if we are currently connected to the appliance via
        SSH

        Returns:

        `boolean`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.ssh_is_connected()
            False
            >>> dp.ssh_connect()
            >>> dp.ssh_is_connected()
            True
            >>> dp.ssh_disconnect()

        Parameters:

        This method accepts no arguments
        """
        if not hasattr(self, '_ssh'):
            self.log_warn(
                'SSH Connectivity check performed '
                'before SSH system initialized.')
            return False
        self.log_info("Checking SSH connectivity...")
        transport = self._ssh.get_transport() if self._ssh else None
        resp = transport and transport.is_active()
        if resp:
            self.log_info("SSH Connectivity verified.")
            return True
        self.log_warn("SSH Connectivity lost.")
        return False

    @correlate
    @logged("audit")
    def ssh_disconnect(self):
        """
        _method_: `mast.datapower.datapower.DataPower.ssh_disconnect(self)`

        Description:

        Disconnects the current SSH session as initiated through
        DataPower.ssh_connect.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.ssh_is_connected()
            False
            >>> dp.ssh_connect()
            >>> dp.ssh_is_connected()
            True
            >>> dp.ssh_disconnect()
            >>> dp.ssh_is_connected()
            False

        Parameters:

        This method accepts no arguments
        """
        if self.ssh_is_connected():
            try:
                self.log_info("Attempting to disconnect SSH session...")
                self._ssh.close()
                self.log_info("Successfully disconnected SSH session")
                return True
            except Exception, e:
                self.log_error(
                    "An exception occurred trying"
                    "to close ssh session: {}".format(str(e)))
                raise
        else:
            self.log_warn("Attempted to close an inactive SSH session")
            return False
        return True

    def ssh_issue_command(self, command, timeout=120):
        """
        _method_: `mast.datapower.datapower.DataPower(self, command, timeout=120)`

        Description:

        Issues a command through the SSH session as initiated through
        DataPower.ssh_connect and return the response.

        Returns:

        `str`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.ssh_connect()
            >>> dp.ssh_issue_command("show mem")
            ...Memory Usage Output...
            >>> dp.ssh_disconnect()

        Parameters:

        * `command`: The command to send to the appliance.
        * `timeout`: The amount of time (in seconds) to wait for a
        response. Defaults to 120.
        """
        username, password = self.credentials.split(":", 1)
        # need to manually log in order to obfuscate credentials
        logger = make_logger("audit")
        logger.info(
            "Attempting to execute ssh_issue_command('{}', '{}')".format(
                str(self), command.replace(password, "********").strip()
            ))
        if not self.ssh_is_connected():
            self.log_error(
                'attempted command on a non-existant '
                'ssh connection: {}'.format(command.replace(password,
                                                            "********")))
            return None
        # I need resp.splitlines() to succeed
        resp = '\n'

        # The command needs to be suffixed with a newline in order for
        # the server to relize that it is a command.
        command = command + '\n' if not command.endswith('\n') else command

        self.log_info(
            "Attempting to send SSH command: "
            "{}".format(command.strip().replace(password, "********")))
        self._ssh_conn.sendall(command)

        # Wait for a response, but check for timeouts
        start = time()
        self.log_debug("Waiting for response...")
        while not self._ssh_conn.recv_ready():
            sleep(0.25)
            if (time() - start) >= timeout:
                # Timeout occurred
                self.log_error(
                    'Timeout occurred while attempting: {}'.format(command))
                raise SSHTimeoutError(
                    'Timeout occurred while attempting: {}'.format(command))

        # Make sure we get everything
        self.log_debug("Retrieving response...")
        while not self.ssh_finished_command(resp):
            resp += self._ssh_conn.recv(1024)
            if (time() - start) >= timeout:
                # Timeout occurred
                self.log_error(
                    'Timeout occurred while attempting: {}'.format(command))
                raise SSHTimeoutError(
                    'Timeout occurred while attempting: {}'.format(command))
        self.log_info(
            "Response received: {}".format(
                resp.replace('\n', '').replace('\r', '')))
        resp = resp.strip()
        resp = resp.replace('\r', '')
        if not resp.startswith(command):
            resp = ' {}\n{}'.format(command.replace(password, "********"), resp)
        logger.info(
            "Finished execution of ssh_issue_command('{}', '{}'). Result: {}".format(
                str(self), command.replace(password, "********").strip(), resp
            ))
        return resp

    @correlate
    @logged("debug")
    def ssh_finished_command(self, resp):
        """
        _method_: `mast.datapower.datapower.DataPower.ssh_finished_command(self, resp)`

        Description:

        _FOR INTERNAL USE_

        What we do here is check various conditions (all known responses
        that DataPower could give for any command) to see if
        the appliance has sent back a valid response.

        First we check a regular expression to see if the prompt of the
        DataPower CLI (ie. 'xi52#' or 'xi52(config)#') is present on the
        last line of the response.

        Second we check if 'Goodbye' is in the response. This handles the
        case when you type exit for the last time to end a session.

        Third we match a regular expression to see if the string '[y/n]'
        is present on the end of the line. This handles the case when
        DataPower is asking you to say yes or no.

        Finally we check to see if "login:, "Password:" or
        "domain (? for all)" is in the response to handle
        the case when you provided invalid credentials

        Returns:

        True if the appliance has finished executing the last command
        and we received all of the output, False otherwise.

        Parameters:

        * `resp`: The response from the appliance to be checked for
        completeness.
        """
        import re
        if self._ssh_conn.recv_ready():
            return False
        if re.match('.*?#$', resp.splitlines()[-1].strip()):
            return True
        elif 'Goodbye' in resp:
            self.ssh_disconnect()
            return True
        elif 'nter new password:' in resp:
            return True
        elif re.match('.*?\[y/n\]', resp.splitlines()[-1]):
            return True
        elif resp.strip().lower().endswith('login:'):
            return True
        elif resp.strip().lower().endswith('password:'):
            return True
        elif resp.strip().lower().endswith("domain (? for all):"):
            return True
        return False

    @logged("debug")
    def send_request(self, status=False, config=False, boolean=False):
        """
        _method_: `mast.datapower.datapower.DataPower.send_request(self, status=False, config=False, boolean=False)`

        Description:

        This method attempts to send the objects current request
        to the appliance. Use this instead of DataPower.request.send()
        because this will ensure that each action is logged and the
        response type is set correctly.

        Special classes are available for use when expecting a response
        of a specific type. You can enable the use of these special classes
        simply by providing one of the expected kwargs
        (status, config, boolean) These typically map pretty well
        to "get-status", "get-config" and "do-action" requests.

        Returns:

        `DPResponse`, `StatusResponse`, `ConfigResponse` or `BooleanResponse`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print type(dp.send_request(status=True))
            <class 'mast.datapower.datapower.StatusResponse'>
            >>> print type(dp.send_request(config=True))
            <class 'mast.datapower.datapower.ConfigResponse'>
            >>> print type(dp.send_request(boolean=True))
            <class 'mast.datapower.datapower.BooleanResponse'>

        Parameters:

        _IMPORTANT_: the parameters `status`, `config` and boolean are
        mutually exclusive, only one can be `True`.

        * `status`: If True, It will be returned as a StatusResponse
        which is a subclass of `DPResponse`
        * `config`: If True, It will be returned as a ConfigResponse
        which is a subclass of `DPResponse`
        * `boolean`: If True, It will be returned as a BooleanResponse
        which is a subclass of `DPResponse`
        """
        # Gather request and response and put in in self.history
        _hist = {"request": repr(self.request)}
        self.log_debug("Request built: {}".format(_escape(repr(self.request))))
        self.log_debug("Sending the request to the appliance.")
        try:
            self.last_response = self.request.send(secure=self.check_hostname)
            if "Authentication failure" in self.last_response:
                raise AuthenticationFailure(self.last_response)
        except Exception, e:
            _hist["response"] = str(e).replace("\n", "").replace("\r", "")
            if hasattr(e, "read"):
                _hist["response"] = e.read().replace(
                        "\n", "").replace("\r", "")
            self._history.append(_hist)
            self.log_error(
                "An error occurred trying to send request to "
                "appliance: {}".format(_escape(str(e))))
            if self.retry_interval > 0:
                try:
                    self.log_info("Retrying in {} seconds".format(self.retry_interval))
                    sleep(self.retry_interval)
                    self.last_response = self.request.send(secure=self.check_hostname)
                    if "Authentication failure" in self.last_response:
                        raise AuthenticationFailure(self.last_response)
                except:
                    _hist["response"] = str(e).replace("\n", "").replace("\r", "")
                    if hasattr(e, "read"):
                        _hist["response"] = e.read().replace(
                                "\n", "").replace("\r", "")
                    self._history.append(_hist)
                    self.log_error(
                        "An error occurred trying to send request to "
                        "appliance: {}".format(_escape(str(e))))
                    raise
            else:
                raise
        self.log_debug(
            "Recieved response from appliance: "
            "{}".format(_escape(self.last_response)))
        # TODO: Replace this with an xpath
        _hist["response"] = re.sub(
            r"<dp:file(.*?)>.*?</dp:file>",
            r"<dp:file\1>base 64 encoded file removed from log</dp:file>",
            str(self.last_response).replace("\r", "").replace("\n", ""))

        self._history.append(_hist)

        if status:
            obj = StatusResponse
        elif boolean:
            obj = BooleanResponse
        elif config:
            obj = ConfigResponse
        else:
            obj = DPResponse
        return obj(self.last_response)

    def log_debug(self, message):
        """
        _method_: `mast.datapower.datapower.DataPower.log_debug(self, message)`

        Description:

        Log a debug level message through the appliances logger.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.log_debug("Debug Message")

        Parameters:

        * `message`: The message to log
        """
        logger = self.get_logger()
        msg = []
        for k, v in self.extra.items():
            msg.append('"{0}": "{1}", '.format(k, v))
        msg.append('"message": "{}"'.format(message))
        msg = ''.join(msg)
        username, password = self.credentials.split(':', 1)
        msg = msg.replace(password, "********")
        logger.debug(msg)

    def log_info(self, message):
        """
        _method_: `mast.datapower.datapower.DataPower.log_info(self, message)`

        Log a informational level message through the appliances logger.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.log_info("Informational Message")

        Parameters:

        * `message`: The message to log
        """
        logger = self.get_logger()
        msg = []
        for k, v in self.extra.items():
            msg.append('"{0}": "{1}", '.format(k, v))
        msg.append('"message": "{}"'.format(message))
        msg = ''.join(msg)
        username, password = self.credentials.split(':', 1)
        msg = msg.replace(password, "********")
        logger.debug(msg)

    def log_warn(self, message):
        """
        _method_: `mast.datapower.datapower.DataPower.log_warn(self, message)`

        Log a warning level message through the appliances logger.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.log_warn("Warning Message")

        Parameters:

        * `message`: The message to log
        """
        logger = self.get_logger()
        msg = []
        for k, v in self.extra.items():
            msg.append('"{0}": "{1}", '.format(k, v))
        msg.append('"message": "{}"'.format(message))
        msg = ''.join(msg)
        username, password = self.credentials.split(':', 1)
        msg = msg.replace(password, "********")
        logger.info(msg)

    def log_error(self, message, get_logs=False):
        """
        _method_: `mast.datapower.datapower.DataPower.log_error(self, message)`

        Log an error level message through the appliances logger.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.log_error("Error Message")

        Parameters:

        * `message`: The message to log
        * `get_logs`: If True, it will be attempted to download all available
        logs from the appliance into `$MAST_HOME/tmp`
        """
        logger = self.get_logger()
        msg = []
        for k, v in self.extra.items():
            msg.append('"{0}": "{1}", '.format(k, v))
        msg.append('"message": "{}"'.format(message))
        msg = ''.join(msg)
        username, password = self.credentials.split(':', 1)
        msg = msg.replace(password, "********")
        logger.error(msg)

        self.log_debug("Request/Response History: {}".format(self.history))

        if get_logs:
            self.get_all_logs()

    def log_critical(self, msg, get_logs=False):
        """
        _method_: `mast.datapower.datapower.DataPower.log_critical(self, message)`

        Log a critical level message through the appliances logger.

        Returns:

        `None`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.log_critical("Critical Message")

        Parameters:

        * `message`: The message to log
        * `get_logs`: If True, it will be attempted to download all available
        logs from the appliance into `$MAST_HOME/tmp`
        """
        logger = self.get_logger()
        _msg = []
        for k, v in self.extra.items():
            _msg.append('"{0}": "{1}", '.format(k, v))
        _msg.append('"message": "{}"'.format(msg))
        msg = ''.join(msg)
        username, password = self.credentials.split(':', 1)
        msg = msg.replace(password, "********")
        logger.critical(msg)
        self.log_debug("Request/Response History: {}".format(self.history))
        if get_logs:
            self.get_all_logs()

    @correlate
    @logged("debug")
    def is_reachable(self):
        """
        _method_: `mast.datapower.datapower.DataPower.is_reachable(self)`

        Description:

        Determines if the appliance is reachable over the SOMA XML
        management interface

        __Implementation Note__:

        This method atttempts to query Version from the appliance
        then it attemps to parse it as xml, and it verifies that
        "datapower" appears in the response (which it should in the dp
        namespace declaration).

        Returns:

        `boolean`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.is_reachable()
            True
            >>> dp = DataPower("does_not_exist", "user:pass")
            >>> print dp.is_reachable()
            False

        Parameters:

        This method accepts no arguments
        """
        self.request.clear()

        try:
            resp = self.get_status("Version")
            # Because of lazy-loading we must explicitly prompt xml parsing
            tree = resp.xml
            return 'datapower' in resp.text
        except:
            return False

    @correlate
    @logged("debug")
    def check_xml_mgmt(self):
        """
        _method_: `mast.datapower.datapower.DataPower.check_xml_mgmt(self)`

        Description:

        Determines if the appliance is reachable over the SOMA XML
        management interface

        Returns:

        `boolean`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.check_xml_mgmt()
            True
            >>> dp = DataPower("does_not_exist", "user:pass")
            >>> print dp.check_xml_mgmt()
            False

        Parameters:

        This method accepts no arguments
        """
        try:
            return self.is_reachable()
        except:
            return False

    @correlate
    @logged("debug")
    def check_web_mgmt(self):
        """
        _method_: `mast.datapower.datapower.DataPower.check_web_mgmt(self)`

        Description:

        Determine if the Web GUI is accessable.

        This uses the information passed into the constructor as well as
        settings configured in $MAST_HOME/etc/local/appliances.conf

        Returns:

        `boolean`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.check_web_mgmt()
            True
            >>> dp = DataPower("does_not_exist", "user:pass")
            >>> print dp.check_web_mgmt()
            False

        Parameters:

        This method accepts no arguments
        """
        import urllib2
        import ssl
        context = ssl.create_default_context()
        if not self.check_hostname:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        url = 'https://' + self._hostname + ':' + str(self.web_port)
        try:
            test = urllib2.urlopen(url, context=context)
        except urllib2.URLError, e:
            self.log_error(
                "An error occurred while attempting to "
                "connect to appliance. Error: {}".format(str(e)))
            return False
        return 'DataPower' in test.read()

    @correlate
    @logged("debug")
    def check_cli_mgmt(self):
        """
        _method_: `mast.datapower.datapower.DataPower.check_cli_mgmt(self)`

        Description:

        Determine if the SSH management interface is reachable

        This uses information passed to the constructor
        as well as settings configured in $MAST_HOME/etc/local/appliances.conf

        Returns:

        `boolean`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.check_cli_mgmt()
            True
            >>> dp = DataPower("does_not_exist", "user:pass")
            >>> print dp.check_cli_mgmt()
            False

        Parameters:

        This method accepts no arguments.
        """
        try:
            resp = self.ssh_connect(port=self.ssh_port)
            self.ssh_disconnect()
            return 'DataPower' in resp
        except:
            return False

    @logged("audit")
    def _add_dynamic_methods(self):
        """
        _method_: `mast.datapower.datapower.DataPower._add_dynamic_methods(self)`

        Description:

        __Internal Use__

        This method dynamically builds and adds methods
        to the DataPower object based on the do-action functions provided
        by the SOMA.

        Returns:

        `None`

        Parameters:

        This method accepts no arguments
        """
        xp = '{http://schemas.xmlsoap.org/soap/envelope/}Body/'
        xp += '{http://www.datapower.com/schemas/management}request/'
        xp += '{http://www.datapower.com/schemas/management}do-action'
        do_action = self.request._test_case.find(xp)
        for node in list(do_action):
            if not hasattr(self, node.tag):
                setattr(self, node.tag, partial(self.do_action, node.tag))

    @correlate
    @logged("audit")
    def do_action(self, action, **kwargs):
        """
        _method_: `mast.datapower.datapower.DataPower.do_action(self, action, **kwargs)`

        Description:

        __Internal Use__

        This is a generic function meant to implement the dynamic
        methods created by _add_dynamic_methods.

        Returns:

        `BooleanResponse`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.do_action("SaveConfig", domain="default")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> print "OK" in resp.text
            True
            >>> print bool(resp)
            True

        Parameters:

        * `action`: The do-action command (ie `"SaveConfig"`) to be executed
        by the appliance
        * `**kwargs`: The keyword-arguments to pass to the do-action command
        """
        if 'domain' in kwargs:
            self.domain = kwargs.get('domain')
            self.log_debug("Setting domain to {}".format(kwargs.get('domain')))
        self.request.clear()
        act = self.request.request(domain=self.domain).do_action[action]
        for key in act.valid_children():
            if key in kwargs:
                act[key](str(kwargs[key]))
            elif key.replace('-', '_') in kwargs:
                # Handles the python rule of not using dashes in variable names
                act[key](str(kwargs[key.replace('-', '_')]))
        resp = self.send_request(boolean=True)
        return resp

    @property
    def environment(self):
        '''
        _property_: `mast.datapower.datapower.DataPower.environment`

        Description:

        The environment this appliance belongs to. Returns "-" if
        this appliance does not belong to an environment otherwise
        it returns a string of environments seperated by commas.

        Returns:

        `str`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.environment
            -
            >>> dp._environment = "prod, dev, qa"
            >>> print dp.environment
            prod, dev, qa

        Parameters:

        This method accepts no arguments
        '''
        if self._environment:
            return self._environment

        config = get_config('environments.conf')
        environments = {}
        for section in config.sections():
            environments[section] = config.get(section, 'appliances').split()

        _in = []
        for env in environments:  # lint:ok
            if self.hostname in environments[env]:  # lint:ok
                _in.append(env)
        if not _in:
            return "-"
        return ", ".join(_in)

    @property
    def extra(self):
        """
        _property_: `mast.datapower.datapower.DataPower.extra`

        Description:

        __Internal Use__

        A dictionary to be used with log formatting, but
        there could be other uses for this function, because it
        returns the appliance hostname, the current domain, the
        current user and the environment which the appliance
        belongs to.

        Returns:

        `dict`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print "domain" in dp.extra
            True
            >>> print "hostname" in dp.extra
            True
            >>> print "session_id" in dp.extra
            True
            >>> print "environment" in dp.extra
            True
            >>> print "correlation_id" in dp.extra
            True
            >>> print "user" in dp.extra
            True
            >>> print "foo" in dp.extra
            False

        Parameters:

        This method accepts no arguments
        """
        user = self.credentials.split(':', 1)[0]
        return {'hostname': self.hostname,
                'domain': self.domain,
                'user': user,
                'session_id': self.session_id,
                'correlation_id': self.correlation_id,
                'environment': self.environment}

    @property
    @logged("debug")
    def domains(self):
        """
        _property_: `mast.datapower.datapower.DataPower.domains`

        Description:

        A (per-session) cached list of all domains on this DataPower.

        Returns:

        `list`

        Usage:

            :::python
            >>> dp = DataPower('localhost', 'user:pass')
            >>> print dp.domains
            ['default', 'test1', 'test2', 'test3']

        Parameters:

        This method accepts no parameters
        """
        if not hasattr(self, "_domains"):
            self.request.clear()
            resp = self.get_status('DomainStatus')

            self._domains = [x.text for x in resp.xml.findall('.//*/Domain')]
        return self._domains

    @property
    @logged("debug")
    def users(self):
        """
        _property_: `mast.datapower.datapower.DataPower.users`

        Description:

        A current list of all users on this DataPower.

        Returns:

        `list`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.users
            ['testuser1', 'testuser2', 'testuser3', 'testuser4']

        Parameters:

        This method accepts no arguments
        """
        self.request.clear()
        resp = self.get_config('User', persisted=False)

        users = resp.xml.findall('.//User')
        users = [x.get('name') for x in users]
        return users

    @property
    @logged("debug")
    def groups(self):
        """
        _property_: `mast.datapower.datapower.DataPower.groups`

        Description:

        A current list of user groups on the appliance
        (running configuration).

        Returns:

        `list`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.groups
            ['testgroup1', 'testgroup2', 'testgroup3']

        Parameters:

        This method accepts no arguments
        """
        self.request.clear()
        resp = self.get_config('UserGroup', persisted=False)

        groups = resp.xml.findall('.//UserGroup')
        groups = [x.get('name') for x in groups]
        return groups

    @property
    @logged("debug")
    def raid_directory(self):
        """
        _property_: `mast.datapower.datapower.DataPower.raid_directory`

        Description:

        The directory at which the raid volume is mounted.
        This is cached as soon as requested.

        Returns:

        `list`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.raid_directory
            local:/raid0

        Parameters:

        This method accepts no arguments
        """
        if not hasattr(self, '_raid_directory'):
            resp = self.get_config(_class='RaidVolume', persisted=False)
            _dir = resp.xml.find(CONFIG_XPATH + 'RaidVolume/Directory').text
            # TODO: Is local:/ really always the correct location?
            self._raid_directory = 'local:/{}'.format(_dir)
        return self._raid_directory

    @property
    @logged("debug")
    def fallback_users(self):
        """
        _property_: `mast.datapower.datapower.DataPower.fallback_users`

        Description:

        A list of users configured as RBM fallback users.

        Returns:

        `list`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.fallback_users
            ['testuser1', 'testuser2']

        Parameters:

        This method accepts no arguments
        """
        resp = self.get_config('RBMSettings', persisted=False)
        xpath = CONFIG_XPATH + "RBMSettings"
        config = resp.xml.find(xpath)
        fallback_users = config.findall("FallbackUser")
        return [fallback_user.text for fallback_user in fallback_users]

    @property
    @logged("debug")
    def history(self):
        """
        _property_: `mast.datapower.datapower.DataPower.history`

        Returns a string containing the complete history of request/response
        to/from the appliance. Each line is prefixed with either "request: "
        or "response: ". They are in chronological order.

        __Note__: This property is derived from DataPower._history which is a
        list of dictionaries. Each dictionary has two keys
        "request" and "response" corresponding to a request sent to the
        appliance and the response received from the appliance.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp._history
            []
            >>> resp = dp.do_action("SaveConfig", domain="default")
            >>> print len(dp._history)
            1
            >>> print dp._history[0].keys()
            ['request', 'response']
            >>> print len(dp.history.splitlines())
            2
            >>> print dp.history.splitlines()[0].startswith("request: ")
            True
            >>> print dp.history.splitlines()[1].startswith("response: ")
            True
        """
        _hist = ""
        for entry in self._history:
            _hist += "request: {}{}".format(entry["request"], os.linesep)
            _hist += "response: {}{}".format(entry["response"], os.linesep)
        return _hist

    @correlate
    @logged("audit")
    def add_user(
            self,
            username,
            password,
            supress_force_password_change=False,
            privileged=False,
            user_group=None
        ):
        """
        _method_: `mast.datapower.datapower.DataPower.add_user(self, username, password, privileged=False, user_group=None)`

        Adds a user to this appliance with the specified username,
        password, access-level or user-group.

        __NOTE__:

        If privileged is set to True then user_group
        doesn't need to be provided. Also if user_group is specified
        then privileged must be False (The user will inherit it's
        access-level from the user-group)

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.users
            ['testuser1', 'testuser2', 'testuser3', 'testuser4']
            >>> resp = dp.add_user("testuser5", "password", privileged=True)
            >>> print dp.users
            ['testuser1', 'testuser2', 'testuser3', 'testuser4', 'testuser5']

        Parameters:

        * `username`: The name of the user to add
        * `password`: The initial password to set for the user
        * `privileged`: If privileged is `True` the user will have
        an access level of privileged
        * `user_group`: The user group to add the user to
        """
        self.request.clear()
        if privileged and user_group:
            # Can't specify both access_level and user_group
            self.log_error(
                "user group provided for privileged user. Aborting.")
            return False
        if not privileged and not user_group:
            # Must specify one of: access_level or user_group
            self.log_error(
                "Neither access level or user group provided. Aborting.")
            return False
        user = self.request.request(
            domain='default').set_config.User(name=username)
        user.Password(password)

        if privileged:
            self.log_debug("User {} will be created as privileged".format(
                username))
            user.AccessLevel('privileged')
        else:
            self.log_debug("User {} will be added to group {}.".format(
                username, user_group))
            user.AccessLevel('group-defined')
            groupname = user.GroupName
            groupname.set('class', 'UserGroup')
            groupname(user_group)
        if supress_force_password_change:
            user.SuppressPasswordChange("on")
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def change_password(self, username, password):
        """
        _method_: `mast.datapower.datapower.DataPower.change_password(self, username, password)`

        changes a user's password to password.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.change_password("testuser1", "new_password")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>

        Parameters:

        * `username`: The name of the user whos password you'd like to
        change
        * `password`: The new password for the user
        """
        self.request.clear()
        self.request.request.modify_config.User(
            name=username).Password(password)
        resp = self.send_request(boolean=True)
        if username == self.credentials.split(':', 1)[0]:
            # Handles the case of changing the password of the user which
            # we are using to authenticate to DataPower
            self.credentials = '{}:{}'.format(username, password)
            self.request._credentials = base64.encodestring(
                self.credentials).strip()
        return resp

    @correlate
    @logged("audit")
    def remove_user(self, username):
        """
        _method_: `mast.datapower.datapower.DataPower.remove_user(self, username)`

        Removes a local user from this appliance.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.users
            ['testuser1', 'testuser2', 'testuser3', 'testuser4']
            >>> resp = dp.remove_user("testuser4")
            >>> print dp.users
            ['testuser1', 'testuser2', 'testuser3']

        Parameters:

        * `username`: The name of the user to remove
        """
        self.request.clear()
        self.request.request(domain='default').del_config.User(name=username)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def ssh_del_rbm_fallback(self, usernames):
        """
        _method_: `mast.datapower.datapower.DataPower.ssh_del_rbm_fallback(self, usernames)`

        Removes a user or a list of users from RBM fallback. This
        function uses SSH to accomplish the task eliminating the need
        for for complex and fragile "vector-add" functions.

        Returns: The text transcript of the ssh session

        Parameters:

        * `usernames`: A list of usernames to remove as rbm fallback users
        """
        if isinstance(usernames, str):
            usernames = [usernames]
        self.ssh_connect()
        session = ''
        session += self.ssh_issue_command("co")
        session += self.ssh_issue_command("rbm")
        for username in usernames:
            session += self.ssh_issue_command(
                "no fallback-user {}".format(username))
        session += self.ssh_issue_command("exit")
        session += self.ssh_issue_command("write mem")
        session += self.ssh_issue_command("y")
        session += self.ssh_issue_command("exit")
        session += self.ssh_issue_command("exit")
        self.ssh_disconnect()
        return session

    @correlate
    @logged("audit")
    def ssh_add_rbm_fallback(self, usernames):
        """
        _method_: `mast.datapower.datapower.DataPower.ssh_add_rbm_fallback(self, usernames)`

        Adds a user or a list of users to RBM fallback. This function
        uses SSH to accomplish the task eliminating the need for
        for complex and fragile "vector-add" functions.

        Returns: The text transcript of the ssh session

        Parameters:

        * `usernames`: A list of users to add as rbm fallback users
        """
        if isinstance(usernames, str):
            usernames = [usernames]
        self.ssh_connect()
        session = ''
        session += self.ssh_issue_command("co")
        session += self.ssh_issue_command("rbm")
        for username in usernames:
            session += self.ssh_issue_command(
                "fallback-user {}".format(username))
        session += self.ssh_issue_command("exit")
        session += self.ssh_issue_command("write mem")
        session += self.ssh_issue_command("y")
        session += self.ssh_issue_command("exit")
        session += self.ssh_issue_command("exit")
        self.ssh_disconnect()
        return session

    @correlate
    @logged("audit")
    def del_rbm_fallback(self, username):
        '''
        _method_: `mast.datapower.datapower.DataPower.del_rbm_fallback(self, username)`

        Removes a fallback user from rbm configuration.
        Returns a BooleanResponse object created with the
        DataPower response.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.del_rbm_fallback("testuser1")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> # This should go through 2 request/response cycles
            >>> print len(dp._history)
            2

        Returns: A `BooleanResponse` object containing the xml response
        from the appliance

        Parameters:

        * `username`: The name of the user to remove from the appliance's
        list of rbm fallback users
        '''
        self.request.clear()
        xpath = CONFIG_XPATH + 'RBMSettings[@name="RBM-Settings"]'
        resp = self.get_config('RBMSettings', persisted=False)

        existing_config = resp.xml.find(xpath)

        # Start building the request to add the fallback user.
        self.request.clear()
        new_config = self.request.request.set_config.RBMSettings(
            name='RBM-Settings')

        # loop through all valid children for new_config
        for child in new_config.valid_children():
            # If this valid child is present in existing_config:
            # append it to new_config
            if existing_config.find(child) is not None:
                if child in 'FallbackUser':
                    for node in existing_config.findall(child):
                        if node.text == username:
                            pass
                        else:
                            new_config.append(node)
                else:
                    for node in existing_config.findall(child):
                        new_config.append(node)

        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def add_rbm_fallback(self, user):
        '''
        _method_: `mast.datapower.datapower.DataPower.add_rbm_fallback(self, user)`

        Adds a fallback user to specified rbm configuration.
        Returns a BooleanResponse object created with the
        DataPower response.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.add_rbm_fallback("testuser1")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> # This should go through 3 request/response cycles
            >>> print len(dp._history)
            3

        __Implementation Detail__

        Because of the way SOMA works, if we try and just add a fallback
        user it will remove the rest of that fallback user's
        configuration. To remedy this we first grab
        the existing configuration and append it to the request to
        add the fallback user effectively rewriting it's entire
        configuration...Seems inefficient, but otherwise we're
        stuck doing this step manually

        Returns: a `BooleanResponse` object containing the XML response
        from the appliance.

        Parameters:

        * `user`: The name of the user to add to the appliance's list of
        rbm fallback users
        '''
        if user not in self.users:
            self.log_error("User {} does not exist. Exiting...".format(user))
            raise KeyError("User {} does not exist on appliance".format(user))
        self.request.clear()
        xpath = CONFIG_XPATH + 'RBMSettings[@name="RBM-Settings"]'
        resp = self.get_config('RBMSettings', persisted=False)

        existing_config = resp.xml.find(xpath)

        # Start building the request to add the fallback user.
        self.request.clear()
        new_config = self.request.request.set_config.RBMSettings(
            name='RBM-Settings')

        # I hate using flag, but otherwise it would add the fallback user once
        # for each existing fallback user
        flag = False
        # loop through all valid children for new_config
        for child in new_config.valid_children():
            # If this valid child is present in existing_config:
            # append it to new_config
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    new_config.append(node)
            # We are looking for FallbackUser Here we found one...
            if child in 'FallbackUser' and flag is False:
                # add FallbackUser to the new_config
                new_config.FallbackUser(user)
                # Set the flag to True so we don't do this more than once
                flag = True
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def add_group(self,
                  name,
                  access_policies=None,
                  admin_state="enabled",
                  local=True):
        """
        _method_: `mast.datapower.datapower.DataPower.add_group(self, name, access_policies=None, admin_state="enabled", local=True)`

        Adds a user-group to this appliance. access_policies should be a
        list of strings containing access-policies to be applied to this
        user-group.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.groups
            ['testgroup1', 'testgroup2', 'testgroup3']
            >>> resp = dp.add_group("testgroup4")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> print dp.groups
            ['testgroup1', 'testgroup2', 'testgroup3', 'testgroup4']

        Returns: A `BooleanResponse` object containing the appliance's
        XML response

        Parameters:

        * `name`: The name of the group to add
        * `access_policies`: A list of access policies to apply to the
        group
        * `admin_state`: The admin-state to apply to the UserGroup object
        Either `"enabled"` or `"disabled"`
        * `local`: Whether to make the group a local group.

        """
        local = "true" if local else "false"
        self.request.clear()
        ug = self.request.request(
            domain='default').set_config.UserGroup(name=name, local=local)
        ug.mAdminState(admin_state)
        if access_policies:
            for access_policy in access_policies:
                ug.AccessPolicies(access_policy)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def del_group(self, group):
        """
        _method_: `mast.datapower.datapower.DataPower.del_group(self, group)`

        Removes a group from the appliance.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.groups
            ['testgroup1', 'testgroup2', 'testgroup3']
            >>> resp = dp.del_group("testgroup3")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> print dp.groups
            ['testgroup1', 'testgroup2']


        Returns: A `BooleanResponse` object containing the XML response
        from the appliance.

        Parameters:

        * `group`: The name of the `UserGroup` to remove
        """
        self.request.clear()
        self.request.request(domain='default').del_config.UserGroup(name=group)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def getfile(self, domain, filename):
        """
        _method_: `mast.datapower.datapower.DataPower.getfile(self, domain, filename)`

        Retrieves a file from this appliance.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> # Our stub server will return "Test Succeeded" base64 encoded
            >>> print dp.getfile("default", "config:/autoconfig.cfg")
            Test Succeeded
            >>> # The following is a regression test to ensure that
            >>> # empty files are handled properly (returns a null string)
            >>> # This allows you to write an exact copy of the empty file
            >>> # with no considerations
            >>> print dp.getfile("default", "config:/empty.txt")
            <BLANKLINE>

        Returns: the contents base64 decoded and ready for writing to a file.

        Parameters:

        * `domain`: The domain from which to retrieve the file
        * `filename`: The path and filename of the file to retrieve
        """
        self.domain = domain
        self.request.clear()
        self.request.request(domain=domain).get_file(name=filename)
        resp = self.send_request()
        try:
            xpath = "".join((
                BASE_XPATH,
                "{http://www.datapower.com/schemas/management}file"))
            _file = resp.xml.find(xpath).text or ""
        except:
            self.log_error(
                "An error occurred while trying to retrieve "
                "file {} from {} domain".format(
                    filename,
                    domain))
            raise
        return base64.decodestring(_file)

    @correlate
    @logged("audit")
    def _set_file(self, contents, filename, domain, overwrite=True):
        """
        _method_: `mast.datapower.datapower.DataPower._set_file(self, contents, filename, domain, overwrite=True)`

        Uploads a file to DataPower.

        Usage:

            :::python
            >>> import base64
            >>> dp = DataPower("localhost", "user:pass")
            >>> contents = base64.encodestring("Test Succeeded")
            >>> resp = dp._set_file(contents, "local:/test.txt", "default")
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> print dp.getfile("default", "local:/test.txt")
            Test Succeeded

        Parameters:

        * contents - the base64 encoded file contents to upload
        * filename - the path and filename of the file as you want it to
        appear on the appliance
        * domain - The domain to which to upload the file
        * overwrite - Whether to overwrite the file if it exists
        """
        if not overwrite:
            if self.file_exists(filename, domain):
                _hist = {
                    "request": "Attempted set-file with "
                               "overwrite set to False",
                    "response": "File exists, aborting..."}
                self._history.append(_hist)
                self.log_error(
                    "Attempted to overwrite file with overwrite set to False")
                return False
        self.domain = domain
        self.request.clear()
        self.request.request(domain=domain).set_file(contents, name=filename)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def set_file(self, file_in, file_out, domain, overwrite=True, filestore=None):
        '''
        _method_: `mast.datapower.datapower.DataPower.set_file(self, file_in, file_out, domain, overwrite=True)`

        To upload a file to a specific domain and location on this
        DataPower.

        Usage

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.set_file(
            ...     file_in="README.md",
            ...     file_out="local:/README.md",
            ...     domain="default",
            ...     overwrite=True)
            >>> print type(resp)
            <class 'mast.datapower.datapower.BooleanResponse'>
            >>> print len(dp._history)
            3
            >>> resp = dp.set_file(
            ...     file_in="README.md",
            ...     file_out="local:/foo/foo.xml",
            ...     domain="default",
            ...     overwrite=False)
            >>> print resp
            False
            >>> print len(dp._history)
            4

        Parameters:

        * file_in: Should be a string containing the path and
        filename of the file to upload
        * file_out: If a location or directory is provided filename will be
        as it appears on the local machine, if a path and filename is provided
        filename will be as provided
        * domain: The domain to which to upload the file
        * `filestore`: if provided, it should be a DPResponse from a
        get-filestore request. This is used to avoid repeated requests
        to the appliance
        '''
        if not overwrite:
            if self.file_exists(file_out, domain, filestore):
                self.log_error(
                    "Attempted to overwrite file with overwrite set to False")
                return False
        if self.directory_exists(file_out, domain, filestore) or \
                self.location_exists(file_out, domain, filestore):
            file_out = "{}/{}".format(file_out, os.path.basename(file_in))
            file_out = file_out.replace("//", "/")
        # Fix for leading and trailing whitespace in the filename
        file_out_fname = file_out.split("/")[-1]
        file_out = file_out.replace(file_out_fname, file_out_fname.strip())
        self.domain = domain
        file_in = self._get_local_file(file_in)
        self.request.clear()
        self.request.request(domain=domain).set_file(file_in, name=file_out)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("audit")
    def del_file(self, domain, filename, backup=False, local_dir="tmp"):
        """
        _method_: `mast.datapower.datapower.DataPower.del_file(self, domain, filename, backup=False, local_dir="tmp")`

        Removes a file from the DataPower in the specified domain. If backup
        is True it will copy the file into local_dir.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.del_file(
            ...     domain="default",
            ...     filename="local:/foo/foo.xml",
            ...     backup=False,
            ...     local_dir="tmp")
            >>> print resp
            <env:Envelope \
                xmlns:dp="http://www.datapower.com/schemas/management" \
                xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
              <env:Body>
                <dp:response>
                  <dp:timestamp>2015-01-12T17:20:26-05:00</dp:timestamp>
                  <dp:result>      OK     </dp:result>
                </dp:response>
              </env:Body>
            </env:Envelope>

        Returns: A `BooleanResponse` object containing the appliance's
        XML response

        Parameters:

        * `domain`: The domain from which to delete the file
        * `filename`: The path and filename of the file to delete
        * `backup`: If `True`, the file will be backed up locally before
        removing from the appliance
        * `local_dir`: The local directory to save the backed up file to
        """
        if backup:
            contents = self.getfile(domain, filename)
            file_out = os.path.join(local_dir, filename.split("/")[-1])
            with open(file_out, "w") as fout:
                fout.write(contents)
        resp = self.DeleteFile(domain=domain, File=filename)
        return resp

    @logged("debug")
    def _get_local_file(self, file_in):
        """
        _method_: `mast.datapower.datapower.DataPower._get_local_file(self, file_in)`

        This function will get a file on the local computer,
        base64 encode it so it is ready to be put into a set_file
        call.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp._get_local_file("README.md")
            <base64 encoded contents of the file>

        Returns: The base64 encoded string representing the file contents

        Parameters:

        * `file_in`: The path and filename of  the file to base64 encode
        and return
        """
        with open(file_in, 'rb') as f:
            fin = base64.encodestring(f.read())
            fin = fin.replace("\n", "").replace("\r", "")
        return fin

    @correlate
    @logged("debug")
    def get_filestore(self, domain, location='local:'):
        '''
        _method_: `mast.datapower.datapower.DataPower.get_filestore(self, domain, location='local:')`

        Retrieve the filestore listing of location from appliance in domain.

        Returns: A `DPResponse` object containing the XML response of
        the appliance

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.get_filestore(
            ...     domain="default",
            ...     location="local:")
            >>> print type(resp)
            <class 'mast.datapower.datapower.DPResponse'>

        Parameters:

        * `domain`: The domain from which to retrieve the filestore
        * `location`: The location for which to retrieve the filestore
        '''
        self.domain = domain
        self.request.clear()
        self.request.request(domain=domain).get_filestore(location=location)
        filestore = self.send_request()
        return filestore

    @correlate
    @logged("debug")
    def get_temporary_filesystem(self):
        """
        _method_: `mast.datapower.datapower.DataPower.get_temporary_filesystem(self)`

        Get a directory listing for the entire temporary filesystem.

        Returns: A `DPResponse` object which contains the XML response from
        the appliance

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.get_temporary_filesystem()
            >>> print type(resp)
            <class 'mast.datapower.datapower.DPResponse'>

        Parameters:

        This method accepts no arguments
        """
        locations = ["temporary:", "logtemp:", "image:"]
        doc = etree.Element("filesystem")
        doc.set('name', 'temporary')
        for location in locations:
            _filestore = self.get_filestore(
                domain="default", location=location)
            doc.append(_filestore.xml.find(FILESTORE_XPATH))
        return DPResponse(etree.tostring(doc))

    @correlate
    @logged("debug")
    def get_encrypted_filesystem(self):
        """
        _method_: `mast.datapower.datapower.DataPower.get_encrypted_filesystem(self)`

        Get a directory listing of  the entire encrypted filesystem.

        Returns: A `DPResponse` object which contains the XML response
        from the appliance

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.get_encrypted_filesystem()
            >>> print type(resp)
            <class 'mast.datapower.datapower.DPResponse'>

        Parameters:

        This method accepts no arguments
        """
        locations = ["local:", "store:",
                     "logstore:", "cert:",
                     "pubcert:", "sharedcert:",
                     "chkpoints:", "config:",
                     "tasktemplates:"]
        doc = etree.Element("filesystem")
        doc.set('name', 'encrypted')
        for location in locations:
            _filestore = self.get_filestore(
                domain="default", location=location)
            doc.append(_filestore.xml.find(FILESTORE_XPATH))
        return DPResponse(etree.tostring(doc))

    @correlate
    @logged("debug")
    def directory_exists(self, directory, domain, filestore=None):
        """
        _method_: `mast.datapower.datapower.DataPower.directory_exists(self, directory, domain)`

        Determine whether directory exists in `domain` on the appliance.

        Returns: `True` if `directory` is a directory in domain,
        `False` otherwise.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.directory_exists(
            ...     directory="local:/foo",
            ...     domain="default")
            True
            >>> print dp.directory_exists(
            ...     directory="local:/foobar",
            ...     domain="default")
            False

        Parameters:

        * `directory`: The name of the directory which you would like to
        verifiy the existance of
        * `domain`: The name of the domain in which to look for `directory`
        * `filestore`: if provided, it should be a DPResponse from a
        get-filestore request. This is used to avoid repeated requests
        to the appliance
        """
        self.domain = domain
        location = directory.split(':')[0] + ':'
        directory = directory.replace('///', '/')
        directory = directory.rstrip("/")
        xpath = FILESTORE_XPATH + '/directory[@name="{}"]'.format(directory)
        if filestore is None:
            filestore = self.get_filestore(domain, location)
        return filestore.xml.find(xpath) is not None

    @correlate
    @logged("debug")
    def location_exists(self, location, domain, filestore=None):
        """
        _method_: `mast.datapower.datapower.DataPower.location_exists(self, location, domain)`

        Determine if `location` is a location in the specified domain on
        the appliance.

        Returns: `True` if `location` is a location in the specified
        domain `False` otherwise.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.location_exists("local:", "default")
            True
            >>> print dp.location_exists("foo:", "default")
            False

        Parameters:

        * `location`: The name of the location you would like to
        verify exists
        * `domain`: The name of the domain in which to look for
        `location`
        * `filestore`: if provided, it should be a DPResponse from a
        get-filestore request. This is used to avoid repeated requests
        to the appliance
        """
        self.domain = domain
        location = location.rstrip("/")
        if not location.endswith(":"):
            location = "{}:".format(location)
        try:
            if filestore is None:
                filestore = self.get_filestore(self.domain, location)
            node = filestore.xml.find(
                './/location[@name="{}"]'.format(location))
            return node is not None
        except:
            return False

    @correlate
    @logged("debug")
    def file_exists(self, filename, domain, filestore=None):
        """
        _method_: `mast.datapower.datapower.DataPower.file_exists(self, filename, domain)`

        Determine whether file exists in the specified domain on the
        appliance

        Returns: `True` if `filename` exists in domain, otherwise
        `False`

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.file_exists("local:/foo/foo.xml", "default")
            True
            >>> print dp.file_exists("local:/foo/foobar.xml", "default")
            False
            >>> print dp.file_exists("local:/bar/bar.xml", "default")
            True
            >>> print dp.file_exists("local:/foobar/foo.xml", "default")
            False

        Parameters:

        * `filename`: The path and filename of the file who's existance
        you would like to verify
        * `domain`: The name of the domain in which to look for `filename`
        * `filestore`: if provided, it should be a DPResponse from a
        get-filestore request. This is used to avoid repeated requests
        to the appliance
        """
        self.domain = domain
        location = '{}:'.format(filename.split(':')[0])
        path = filename.replace('///', '/')
        filename = path.split('/')[-1]
        path = '/'.join(path.split('/')[:-1])
        if len(path.split('/')) < 2:
            xpath = '{}/location[@name="{}"]/file[@name="{}"]'.format(
                FILESTORE_XPATH,
                path,
                filename)
        else:
            xpath = '{}/directory[@name="{}"]/file[@name="{}"]'.format(
                FILESTORE_XPATH,
                path,
                filename)
        if filestore is None:
            filestore = self.get_filestore(domain, location)
        return filestore.xml.find(xpath) is not None

    @correlate
    @logged("debug")
    def copy_directory(self, dp_path,
                       local_path, domain='default',
                       recursive=True, filestore=None):
        """
        _method_: `mast.datapower.datapower.DataPower.copy_directory(self, dp_path, local_path, domain='default', recursive=True, filestore=None)`

        This will copy the contents of dp_path to local_path.

        Returns: None

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> dp.copy_directory("local:", "/tmp", "default", True)

        Parameters:

        * `dp_path`: The directory/location on the appliance, you would
        like to copy locally
        * `local_path`: The base directory to copy the files to
        * `domain`: The domain from which to copy the files
        * `recursive`: Whether or not to recurse into sub-directories
        * `filestore`: The filestore of the location in which `dp_path`
        resides. If this is not passed in, the filestore will be
        retrieved from the appliance. This is to help when acting
        recursively so the filestore is retrieved only once
        """
        dp_path = dp_path.replace("///", "/")
        if dp_path.endswith("/"):
            dp_path = dp_path[:-1]

        _path = dp_path.replace(":", "").strip("/")
        _path = _path.replace("/", os.path.sep)
        if _path not in local_path:
            local_path = os.path.join(local_path, _path)
        try:
            os.makedirs(local_path)
        except:
            pass

        if filestore is None:
            location = '{}:'.format(dp_path.split(':')[0])
            try:
                filestore = self.get_filestore(
                    domain=domain, location=location)
            except TypeError:
                self.log_error(
                    "Error reading directory"
                    ": %s, request: %s, response: %s" % (
                        dir, self.request, self.last_response.read()))
                return None

        files = self.ls(
            dp_path,
            domain=domain,
            include_directories=recursive,
            filestore=filestore)

        for file in files:
            self.log_info("Getting file {}".format(file))
            if file.endswith("/"):
                _local_path = os.path.join(
                    local_path, file[:-1].split("/")[-1])
                try:
                    os.makedirs(_local_path)
                except:
                    pass
                self.copy_directory(
                    file,
                    _local_path,
                    domain=domain,
                    filestore=filestore)
                continue
            filename = os.path.join(local_path, file.split('/')[-1])
            with open(filename, 'wb') as fout:
                fname = '{}/{}'.format(dp_path, file)
                fout.write(self.getfile(domain=domain, filename=fname))

    @correlate
    @logged("debug")
    def ls(self, dir, domain='default', include_directories=True,
           filestore=None):
        """
        _method_: `mast.datapower.datapower.DataPower.ls(self, dir, domain='default', include_directories=True, filestore=None)`

        Retrieve a directory listing of `dir` in `domain` on the appliance.

        Returns: A python `list` files will have just the filename, but
        directories will have the location and the path in the
        standard notation.

        Usage:

            :::python
            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.ls("local:/foo", "default", True)
            ['foo.xml', 'bar.xml', 'baz.xml', 'local:/foo/level1/']
            >>> print dp.ls("local:", "default", True)
            ['local:/foo/', 'local:/bar/', 'local:/baz/']
            >>> print dp.ls("local:", "default", False)
            []

        Parameters:

        * `dir`: The directory to list
        * `domain`: The domain to look in for `dir`
        * `include_directories`: Whether to include directories in the
        listing
        * `filestore`: The filestore of the location in which `dir`
        resides. If this is not passed in, the filestore will be
        retrieved from the appliance. This is to help when acting
        recursively so the filestore is retrieved only once
        """
        # dir won't match if it ends in a "/"
        dir = dir.rstrip("/")
        self.domain = domain
        self.log_info("Attempting to list directory: %s" % (dir))
        location = '{}:'.format(dir.split(':')[0])
        if filestore is None:
            try:
                filestore = self.get_filestore(
                    domain=domain, location=location)
            except TypeError:
                self.log_error(
                    "Error reading directory: "
                    "%s, request: %s, response: %s" % (
                        dir, self.request, self.last_response.read()))
                return None
        fs = filestore.xml.find(FILESTORE_XPATH)
        directory = fs.find('.//directory[@name="{}"]'.format(dir))
        if directory is None:
            directory = filestore.xml.find(
                './/location[@name="{}"]'.format(dir.replace('/', '')))

        files = []
        if include_directories:
            for child in list(directory):
                if child.get("name") is not None:
                    if child.tag == "directory":
                        files.append(child.get("name") + "/")
                    else:
                        files.append(child.get("name"))
        else:
            for child in list(directory):
                if child.tag == 'file':
                    if child.get("name") is not None:
                        files.append(child.get("name"))
        self.log_info("Successfully retrieved directory listing: %s" % (dir))
        return files

    @correlate
    @logged("debug")
    def do_import(self,
                  domain,
                  zip_file,
                  deployment_policy=None,
                  deployment_policy_variables=None,
                  dry_run=False,
                  overwrite_files=True,
                  overwrite_objects=True,
                  rewrite_local_ip=True,
                  source_type='ZIP'):
        '''
        This function will import a zip file type configuration to the
        specified domain.
        '''
        self.domain = domain
        # Get zip file and base64 encode it to prepare it for travel.
        with open(zip_file, 'rb') as fin:
            contents = base64.encodestring(fin.read())

        # SOMA requires boolean values to be 'true' or 'false'.
        dry_run = str(dry_run).lower()
        overwrite_files = str(overwrite_files).lower()
        overwrite_objects = str(overwrite_objects).lower()
        rewrite_local_ip = str(rewrite_local_ip).lower()

        self.request.clear()
        do_import = self.request.request(domain=domain).do_import
        if deployment_policy is not None:
            do_import.set('deployment-policy', deployment_policy)
        if deployment_policy_variables is not None:
            do_import.set('deployment-policy-variables', deployment_policy_variables)
        do_import.set('rewrite-local-ip', rewrite_local_ip)
        do_import.set('overwrite-objects', overwrite_objects)
        do_import.set('overwrite-files', overwrite_files)
        do_import.set('dry-run', dry_run)
        do_import.set('source-type', source_type)
        do_import.input_file(contents)
        return self.send_request()

    @correlate
    @logged("debug")
    def add_static_route(self, ethernet_interface,
                         destination, gateway, metric):
        '''
        adds a static route to the specified ethernet_interface.
        Returns a BooleanResponse object

        * ethernet_interface: The ethernet interface to which to add the
        static route
        * destination: The destination IP address
        * gateway: The IP address of the gateway
        * metric: more or less priority...the lower the number the higer
        priority
        '''
        # We must retrieve the existing configuration first.
        # (see comments in add_secondary_address)
        self.domain = "default"

        xpath = CONFIG_XPATH + 'EthernetInterface[@name="%s"]' % (
            ethernet_interface)
        self.request.clear()
        resp = self.get_config('EthernetInterface', persisted=False)
        existing_config = resp.xml.find(xpath)
        if existing_config is None:
            self.log_error(
                "Tried to add static route to ethernet "
                "interface {} which doesn't appear to exist. Aborting".format(
                    ethernet_interface))
            return None
        # Begin building the request to add the static route
        self.request.clear()
        new_config = self.request.request(domain="default").modify_config\
            .EthernetInterface(name=ethernet_interface)

        flag = False
        for child in new_config.valid_children():
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    if node.tag == 'Authentication':
                        continue
                    new_config.append(node)
            if child in "StaticRoutes" and flag is False:
                sr = new_config.StaticRoutes
                sr.Destination(destination)
                sr.Gateway(gateway)
                sr.Metric(metric)
                flag = True
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def del_static_route(self, ethernet_interface, destination):
        '''
        adds a static route to the specified ethernet_interface.
        Returns a BooleanResponse object

        * ethernet_interface: The ethernet interface to which to add the
        static route
        * destination: The destination IP address
        '''
        # We must retrieve the existing configuration first.
        # (see comments in add_secondary_address)
        self.domain = "default"

        xpath = CONFIG_XPATH + 'EthernetInterface[@name="%s"]' % (
            ethernet_interface)
        self.request.clear()
        resp = self.get_config('EthernetInterface', persisted=False)
        existing_config = resp.xml.find(xpath)
        if existing_config is None:
            self.log_error(
                "Tried to remove static route to ethernet interface "
                "{} which doesn't appear to exist. Aborting".format(
                    ethernet_interface))
            return None
        # Begin building the request to add the static route
        self.request.clear()
        new_config = self.request.request(domain="default").set_config\
            .EthernetInterface(name=ethernet_interface)

        for child in new_config.valid_children():
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    if node.tag == 'StaticRoutes':
                        if node.find('Destination').text == destination:
                            continue
                    if node.tag == 'Authentication':
                        continue
                    new_config.append(node)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def add_secondary_address(self, ethernet_interface, secondary_address):
        '''
        Adds a secondary ip address to specified ethernet interface.
        Returns a BooleanResponse object

        * ethernet_interface: The ethernet interface to which to add the
        secondary IP
        * secondary_address: The address to add to the above interface

        Because of the way SOMA works, if we try and just add a secondary
        interface it will remove the rest of that ethernet interface's
        configuration. To remedy this we first grab the existing
        configuration and append it to the request to add the
        secondary ip effectively rewriting it's entire configuration...
        Seems inefficient, but otherwise we're stuck doing this
        step manually
        '''
        self.domain = "default"
        self.request.clear()
        xpath = CONFIG_XPATH + 'EthernetInterface[@name="%s"]' % (
            ethernet_interface)

        resp = self.get_config('EthernetInterface', persisted=False)
        existing_config = resp.xml.find(xpath)

        # If CIDR mask is not provided, we will retrieve it from the existing
        # configuration.
        if '/' not in secondary_address:
            # Allow for DHCP
            if existing_config.find('IPAddress') is not None:
                cidr = existing_config.find('IPAddress').text.split('/')[-1]
                secondary_address = '%s/%s' % (secondary_address, cidr)

        # Start building the request to add the secondary ip.
        self.request.clear()
        new_config = self.request.request.modify_config.EthernetInterface(
            name=ethernet_interface)

        # I hate using flag, but otherwise it would add the secondary ip once
        # foreach existing secondary ip
        flag = False
        # loop through all valid children for new_config
        for child in new_config.valid_children():
            # If this valid child is present in existing_config:
            # append it to new_config
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    if node.tag == 'Authentication':
                        continue
                    new_config.append(node)
            # We are looking for SecondaryAddress Here we found one...
            if child in 'SecondaryAddress' and flag is False:
                # add SecondaryAddress to the new_config
                new_config.SecondaryAddress(secondary_address)
                # Set the flag to True so we don't do this more than once
                flag = True
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def del_secondary_address(self, ethernet_interface, secondary_address):
        """
        Removes a secondary address from the specified ethernet
        interface

        * ethernet_interface - The name of the ethernet interface
        (ie eth0)
        * secondary_address - The secondary address to remove
        """
        self.domain = "default"
        self.request.clear()
        xpath = CONFIG_XPATH + 'EthernetInterface[@name="%s"]' % (
            ethernet_interface)

        resp = self.get_config('EthernetInterface', persisted=False)
        existing_config = resp.xml.find(xpath)

        # If CIDR mask is not provided, we will retrieve it from the existing
        # configuration.
        if '/' not in secondary_address:
            # Allow  for DHCP
            if existing_config.find('IPAddress') is not None:
                cidr = existing_config.find('IPAddress').text.split('/')[-1]
                secondary_address = '{}/{}'.format(secondary_address, cidr)

        # Start building the request to add the secondary ip.
        self.request.clear()
        new_config = self.request.request.set_config.EthernetInterface(
            name=ethernet_interface)

        # loop through all valid children for new_config
        for child in new_config.valid_children():
            # If this valid child is present in existing_config:
            # append it to new_config
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    if node.tag == 'Authentication':
                        continue
                    if node.text:
                        if secondary_address in node.text:
                            # unless it's the secondary_address we are removing
                            continue
                    new_config.append(node)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def add_static_host(self, hostname, ip):
        '''
        adds a static host DNS entry to the DataPower.
        Returns a BooleanResponse object

        * hostname: the hostname of the static host
        * ip: the IP address of the static host
        '''
        # Again we need to grab the existing config before we add the static
        # host.
        # See the comments in add_secondary_address
        self.domain = "default"
        xpath = CONFIG_XPATH + 'DNSNameService'
        self.request.clear()
        resp = self.get_config('DNSNameService', persisted=False)
        existing_config = resp.xml.find(xpath)

        self.request.clear()
        new_config = self.request.request.modify_config.DNSNameService(
            name=existing_config.get('name'))
        flag = False
        for child in new_config.valid_children():
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    if node.find('Flags') is not None:
                        node.remove(node.find('Flags'))
                    new_config.append(node)
            if child == 'StaticHosts' and flag is False:
                SH = new_config.StaticHosts
                SH.Hostname(hostname)
                SH.IPAddress(ip)
                flag = True
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def del_static_host(self, hostname):
        '''
        removes a static host DNS entry to the DataPower.
        Returns a BooleanResponse object

        * hostname: the hostname of the static host
        '''
        # Again we need to grab the existing config before we add the static
        # host.
        # See the comments in add_secondary_address
        self.domain = "default"
        xpath = CONFIG_XPATH + 'DNSNameService'
        self.request.clear()
        resp = self.get_config('DNSNameService', persisted=False)
        existing_config = resp.xml.find(xpath)

        self.request.clear()
        new_config = self.request.request.set_config.DNSNameService(
            name=existing_config.get('name'))
        for child in new_config.valid_children():
            if existing_config.find(child) is not None:
                for node in existing_config.findall(child):
                    if node.find('Flags') is not None:
                        node.remove(node.find('Flags'))
                    if node.tag == 'StaticHosts':
                        if node.find('Hostname').text == hostname:
                            continue
                    new_config.append(node)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def add_host_alias(self, name, ip, admin_state='enabled'):
        '''
        adds a host alias to the DataPower.

        Returns a BooleanResponse object

        * name - The name of the host alias
        * ip - the IP address of the host alias
        * admin_state - either "enabled" or "disabled" the admin state
        to apply to the host alias
        '''
        assert admin_state in ('enabled', 'disabled')
        self.domain = "default"
        self.request.clear()

        HA = self.request.request(domain='default').set_config.\
            HostAlias(name=name)
        HA.mAdminState(admin_state)
        HA.IPAddress(ip)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def del_host_alias(self, name):
        '''
        removes a host alias to the DataPower.

        Returns a BooleanResponse object

        * name: The name of the host alias
        '''
        self.domain = "default"
        self.request.clear()

        self.request.request(domain='default').del_config.\
            HostAlias(name=name)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def export(self, domain, obj, object_class,
               comment='', format='ZIP', persisted=True, all_files=True,
               referenced_files=True, referenced_objects=True):
        """
        Exports an object/service from the appliance. Returns
        the base64 decoded string ready for writing to a file.
        """
        re1 = r'<\?xml.*?\n.*?file>'
        re2 = r'</dp:file.*Envelope>'
        self.domain = domain
        all_files = str(all_files).lower()
        referenced_files = str(referenced_files).lower()
        referenced_objects = str(referenced_objects).lower()
        persisted = str(persisted).lower()
        self.request.clear()
        export = self.request.request(
            domain=domain).do_export(format=format, persisted=persisted)
        export.set('all-files', all_files)
        obj = export.object(name=obj)
        obj.set('class', object_class)
        obj.set('ref-files', referenced_files)
        obj.set('ref-objects', referenced_objects)
        self.send_request()
        try:
            response = re.sub(re1, '', self.last_response)
            response = re.sub(re2, '', response)
        except:
            self.log_error(
                "Regular expression failed! Usually This is a connectivity"
                " error or an invalid request")
            raise
        return base64.decodestring(response)


    @correlate
    @logged("debug")
    def get_normal_backup(self,
                          domains=None,
                          format='ZIP',
                          comment=""):
        '''
        This function builds the request for a Normal Backup, sends it out,
        extracts the base64 encoded file, base64 decodes the file and returns
        the result.

            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.get_normal_backup(
            ...     domain="default",
            ...     format="ZIP",
            ...     comment="TESTING")
            >>> with open("tmp/out.zip", "wb") as fout:
            ...     fout.write(resp)
            >>> import zipfile
            >>> zip = zipfile.ZipFile("tmp/out.zip")
            >>> print zip.testzip()
            None
            >>> # Don't leave traces behind
            >>> zip.close()
            >>> import os; os.remove("tmp/out.zip")
        '''
        if domains is None:
            domains = ["all-domains"]
        if isinstance(domains, basestring):
            domains = [domains]
        self.request.clear()
        dobackup = self.request.request.do_backup(format=format)
        if comment:
            dobackup.user_comment(comment)
        for domain in domains:
            dobackup.domain(name=domain)
        resp = self.send_request()
        try:
            xpath = "".join((
                BASE_XPATH,
                "{http://www.datapower.com/schemas/management}file"))
            _file = resp.xml.find(xpath).text
        except AttributeError:
            raise FailedToRetrieveBackup(
                "DataPower did not send a valid backup when requested."
                "This can sometimes be fixed by cleaning up the filesystem"
                "and retrying.")
        except:
            self.log_error(
                "There was an error retrieving a backup from {} {}".format(
                    self.hostname, domain))
            raise
        _file = base64.decodestring(_file)
        if format == "ZIP":
            stringio = StringIO(_file)
            zip_file = zipfile.ZipFile(stringio)
            if zip_file.testzip() is not None:
                raise FailedToRetrieveBackup(
                    "We received a corrupted backup when attempting to "
                    "backup {} {} ".format(self.hostname, domains)
                )
        return _file

    @correlate
    @logged("debug")
    def restore_normal_backup(self, file_in, domain,
                              source_type="ZIP", overwrite_files=True,
                              overwrite_objects=True, rewrite_local_ip=True,
                              deployment_policy=None, import_domain=True,
                              reset_domain=True, dry_run=False):
        """
        Restores a normal backup to the appliance.
        """

        file_in = self._get_local_file(file_in)
        self.request.clear()
        do_restore = self.request.request.do_restore
        do_restore.set('source-type', source_type)
        do_restore.set('dry-run', str(dry_run).lower())
        do_restore.set('overwrite-files', str(overwrite_files).lower())
        do_restore.set('overwrite-objects', str(overwrite_objects).lower())
        do_restore.set('rewrite-local-ip', str(rewrite_local_ip).lower())
        if deployment_policy is not None:
            do_restore.set('deployment-policy', deployment_policy)
        do_restore.input_file(file_in)
        dmn = do_restore.domain
        dmn.set('name', domain)
        dmn.set('import-domain', str(import_domain).lower())
        dmn.set('reset-domain', str(reset_domain).lower())
        return self.send_request()

    @correlate
    @logged("debug")
    def get_existing_checkpoints(self, domain):
        '''
        This function returns a dictionary
        describing the existing checkpoints in the
        given domain.

        checkpoints = {'chkpoint1': {'date': ['2014', '01', '01']
                                     'time': ['23', '59', '59']}
                       ...}
        '''
        self.domain = domain
        self.log_info("Attempting to get existing checkpoints")
        xpath = STATUS_XPATH + 'DomainCheckpointStatus'
        self.request.clear()
        resp = self.get_status('DomainCheckpointStatus', domain=domain)

        checkpoints = resp.xml.findall(xpath)
        rtn_dict = {}
        for checkpoint in checkpoints:
            name = checkpoint.find('ChkName').text
            date = checkpoint.find('Date').text.split('-')
            time = checkpoint.find('Time').text.split()[0].split(':')
            rtn_dict.setdefault(name, {'date': date,
                                       'time': time})
        return rtn_dict

    @correlate
    @logged("debug")
    def remove_oldest_checkpoint(self, domain):
        """
        This will remove the oldest checkpoint in domain.
        """
        self.domain = domain
        checkpoints = self.get_existing_checkpoints(domain)
        timestamps = []
        names = []
        for checkpoint in checkpoints:
            names.append(checkpoint)
            timestamp = checkpoints[checkpoint]['date']
            timestamp.extend(checkpoints[checkpoint]['time'])
            timestamp = map(int, timestamp)
            timestamps.append(datetime(*timestamp))

        oldest_index = timestamps.index(min(timestamps))
        checkpoint_name = names[oldest_index]
        self.request.clear()

        resp = self.RemoveCheckpoint(ChkName=checkpoint_name, domain=domain)
        return resp

    @correlate
    @logged("debug")
    def rollback_checkpoint(self, domain, checkpoint_name):
        """
        Rolls given domain back to given checkpoint. To see which
        checkpoints are available please use
        DataPower.get_existing_checkpoints
        """
        self.domain = domain
        self.RollbackCheckpoint(domain=domain, ChkName=checkpoint_name)

    @correlate
    @logged("debug")
    def max_checkpoints(self, domain):
        """
        Returns an int representing the configured maximum number of
        checkpoints for a given domain.
        """
        xpath = CONFIG_XPATH + "Domain[@name='{}']/MaxChkpoints".format(domain)
        config = self.get_config("Domain", domain)
        return int(config.xml.find(xpath).text)

    @correlate
    @logged("debug")
    def get_xml_managers(self, domain):
        """
        Returns a list of XML Managers in domain.
        """
        xpath = CONFIG_XPATH + 'XMLManager'
        self.request.clear()
        resp = self.get_config('XMLManager', domain=domain)
        mgrs = [x.get("name") for x in resp.xml.findall(xpath)]
        return mgrs

    @correlate
    @logged("debug")
    def get_AAA_policies(self, domain):
        """
        Returns a list of AAA policies in domain.
        """
        xpath = CONFIG_XPATH + 'AAAPolicy'
        self.request.clear()
        resp = self.get_config('AAAPolicy', domain=domain)
        policies = [x.get('name') for x in resp.xml.findall(xpath)]
        return policies

    @correlate
    @logged("debug")
    def get_XACMLPDPs(self, domain):
        """
        Returns a list of XACMLPDPs in domain.
        """
        xpath = CONFIG_XPATH + 'XACMLPDP'
        self.request.clear()
        resp = self.get_config('XACMLPDP', domain=domain)
        xacmlpdps = [x.get("name") for x in resp.xml.findall(xpath)]
        return xacmlpdps

    @correlate
    @logged("debug")
    def get_ZosNSSClients(self, domain):
        """
        Returns a list of ZosNSSClients in domain.
        """
        xpath = CONFIG_XPATH + 'ZosNSSClient'
        self.request.clear()
        resp = self.get_config('ZosNSSClient', domain=domain)
        ZosNSSClients = [x.get("name") for x in resp.xml.findall(xpath)]
        return ZosNSSClients

    @correlate
    @logged("debug")
    def get_secondary_addresses(self, interface):
        """
        Returns a list of Secondary Addresses for interface.
        """
        xpath = "{}EthernetInterface[@name='{}']/SecondaryAddress".format(
            CONFIG_XPATH, interface)
        int_config = self.get_config('EthernetInterface', persisted=False)
        return [x.text for x in int_config.xml.findall(xpath)]

    @correlate
    @logged("debug")
    def get_static_hosts(self):
        """
        Returns a list of Static Hosts.
        """
        config = self.get_config('DNSNameService', persisted=False)
        static_hosts = config.xml.findall(CONFIG_XPATH + '/StaticHosts')

        return [
            (x.find('Hostname').text, x.find('IPAddress').text)
            for x in static_hosts]

    @correlate
    @logged("debug")
    def get_static_routes(self, interface):
        """
        Returns a list of Static Routes for interface.
        """
        xpath = "{}EthernetInterface[@name='{}']/StaticRoutes".format(
            CONFIG_XPATH, interface)
        config = self.get_config('EthernetInterface', persisted=False)
        return [(
            x.find('Destination').text,
            x.find('Gateway').text,
            x.find('Metric').text)
            for x in config.xml.findall(xpath)]

    @correlate
    @logged("debug")
    def get_host_aliases(self):
        """
        Returns a list of Host Aliases for the appliances
        """
        xpath = "{}HostAlias".format(CONFIG_XPATH)
        config = self.get_config("HostAlias")
        return [(
            x.get("name"),
            x.find('IPAddress').text,
            x.find("mAdminState").text)
            for x in config.xml.findall(xpath)]

    @logged("debug")
    def verify_local_backup(self, dir):
        """
        Given dir, this method attempts to find a file called
        backupmanifest.xml, then parses that file and checks the
        checksum of each file in the backupmanifest.xml against
        what is in dir.

        Returns True if all files match their Hash, and False if
        any file doesn't.
        """
        tree = etree.parse(os.path.join(dir, 'backupmanifest.xml'))
        file_node = tree.find('backupmanifest/files')
        flag = False
        for file in file_node.findall('./file'):
            if file.find('./checksum') is not None:
                name = file.find('./filename').text
                self.log_debug("Checking file: {}".format(name))
                checksum = file.find('./checksum').text
                sha = get_sha1(os.path.join(dir, name))
                if checksum == sha:
                    self.log_info("File {} is verified".format(name))
                else:
                    self.log_error(
                        "File {} does not match sha1 hash!".format(name))
                    flag = True
        if flag is True:
            self.log_error("Verification Failed! Please try your backup again")
            return False
        self.log_info("Verification succeeded. All files match their hash.")
        return True

    @correlate
    @logged("debug")
    def object_audit(self, domain='all-domains'):
        """
        This method will get the difference between the running and
        the persisted configuration. Returns a DPResponse object.

        TODO: Allow a blacklist param to skip domains when all-domains
        is specified.
        """
        if isinstance(domain, basestring):
            domain = [domain]
        if "all-domains" in domain:
            domain = self.domains
        resp = etree.Element("diff")
        for _domain in domain:
            self.request.clear()
            obj = self.request.request(domain=_domain).get_diff.object
            obj.set('class', 'all-classes')
            obj.set('name', 'all-objects')
            obj.set('recursive', 'true')
            obj.set('from-persisted', 'true')
            _resp = self.send_request()
            el = _resp.xml.find(
                "{}{}".format(
                    BASE_XPATH,
                    "{http://www.datapower.com/schemas/management}diff"))
            el.set("domain", _domain)
            resp.append(el)
        pretty_print(resp)
        return etree.tostring(resp)

    @correlate
    @logged("debug")
    def get_status(self, provider, domain="default"):
        """
        Returns a StatusResponse object representing the status of the
        requested provider.

            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.get_status("CPUUsage")
            >>> print type(resp)
            <class 'mast.datapower.datapower.StatusResponse'>
            >>> print resp.xml.find(".//CPUUsage") # doctest: +ELLIPSIS
            <Element 'CPUUsage' at ...>
        """
        self.domain = domain
        self.request.clear()
        gs = self.request.request(domain=domain).get_status
        gs.set('class', provider)
        resp = self.send_request(status=True)
        return resp

    @correlate
    @logged("debug")
    def del_config(self, _class, name, domain="default"):
        """
        Deletes an object from the appliance's configuration.

            >>> dp = DataPower("localhost", "user:pass")
            >>> print dp.users
            ['testuser1', 'testuser2', 'testuser3', 'testuser4']
            >>> resp = dp.del_config("User", "testuser1")
            >>> print dp.users
            ['testuser2', 'testuser3', 'testuser4']
        """
        self.request.clear()
        self.request.request(domain=domain).del_config[_class](name=name)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def get_config(self,
                   _class=None,
                   name=None,
                   recursive=False,
                   persisted=True,
                   domain='default'):
        """
        Returns a ConfigResponse object representing the configuration of
        the requested object.

            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.get_config("EthernetInterface")
            >>> print resp.xml.find(".//EthernetInterface") is not None
            True
        """
        self.domain = domain
        self.request.clear()
        gc = self.request.request(domain=domain).get_config
        if _class:
            gc.set('class', _class)
        if name:
            gc(name=name)
        gc(recursive=str(recursive).lower(), persisted=str(persisted).lower())
        resp = self.send_request(config=True)
        return resp

    @correlate
    @logged("debug")
    def get_all_logs(self, dir="logtemp:", log_dir=None):
        """
        Attempts to retrieve all log files from this appliance.
        """
        timestamp = Timestamp()
        self.log_info("Attempting to retrieve all current DataPower logs")

        if not log_dir:
            # Guess at a good log directory
            config = get_config("logging.conf")
            log_dir = config.get("from_appliance", "log_dir")
        if os.path.sep not in dir:
            new_dir = "{}-{}-log-dump".format(
                timestamp.timestamp, self.hostname)
            log_dir = os.path.join(log_dir, new_dir)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # get a list of files
        files = self.ls(dir, include_directories=True)
        for file in files:
            if ":/" in file:
                # directory recurse
                new_dir = file.split('/')[-1]
                new_log_dir = os.path.join(log_dir, new_dir)
                self.get_all_logs(file, log_dir=new_log_dir)
            else:
                if "log" in file:
                    filename = "{}/{}".format(dir, file)
                    local_filename = os.path.join(log_dir, file)
                    content = self.getfile("default", filename)
                    with open(local_filename, 'wb') as fout:
                        fout.write(content)

    # PICK UP WRITING TESTS HERE
    @correlate
    @logged("debug")
    def disable_domain(self, domain):
        """
        Sets the admin state of the given domain to disabled
        """
        self.domain = domain
        self.request.clear()
        self.request.request.modify_config.Domain(
            name=domain).mAdminState('disabled')
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def enable_domain(self, domain):
        """
        Sets the admin state of the given domain to enabled.
        """
        self.domain = domain
        self.request.clear()
        self.request.request.modify_config.Domain(
            name=domain).mAdminState('enabled')
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def add_domain(self, name):
        """
        Adds a domain to the appliance.
        """
        self.request.clear()
        self.request.request(domain='default').set_config.Domain(name=name)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def del_domain(self, name):
        """
        Removes domain with name of name from the appliance
        """
        self.request.clear()
        self.request.request(domain="default").del_config.Domain(name=name)
        resp = self.send_request(boolean=True)
        return resp

    @correlate
    @logged("debug")
    def set_firmware(self, image_file, AcceptLicense=False, timeout=1200):
        """
        Uses AMP to set a firmware image file and attempt to
        reload the appliance to apply the up/down-graded firmware.

            >>> dp = DataPower("localhost", "user:pass")
            >>> resp = dp.set_firmware("tmp/EMPTY_DO_NOT_REMOVE.txt")
            >>> print bool(resp)
            True
        """
        import urllib2
        tpl = """<soapenv:Envelope
xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:dp="http://www.datapower.com/schemas/appliance/management/3.0">
   <soapenv:Header/>
   <soapenv:Body>
      <dp:SetFirmwareRequest>
         %AcceptLicense%
         <dp:Firmware>%image_file%</dp:Firmware>
      </dp:SetFirmwareRequest>
   </soapenv:Body>
</soapenv:Envelope>"""
        import ssl
        context = ssl.create_default_context()
        if not self.check_hostname:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        if AcceptLicense:
            self.log_info("AcceptLicense is set to True")
            tpl = tpl.replace("%AcceptLicense%", "<dp:AcceptLicense />")
        else:
            self.log_warn("AcceptLicense is set to False. This will fail.")
            tpl = tpl.replace("%AcceptLicense%", "")
        tpl = tpl.replace("%image_file%", self._get_local_file(image_file))
        url = "https://{}:{}/service/mgmt/amp/3.0".format(
            self._hostname, self.port)
        creds = self.request._credentials.strip()
        req = urllib2.Request(
            url=url,
            data=tpl,
            headers={
                'Content-Type': 'text/xml',
                'Authorization': 'Basic {}'.format(creds)})
        response_xml = urllib2.urlopen(req, timeout=timeout, context=context)
        response_xml = response_xml.read()
        return AMPBooleanResponse(response_xml)


if __name__ == '__main__':
    pass
