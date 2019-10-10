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
mast system:

A set of tools for automating routine system-administration
tasks associated with IBM DataPower appliances.
"""
import os
import sys
import flask
import base64
import shutil
import zipfile
import commandr
from time import time, sleep
from mast.xor import xorencode
from mast.plugins.web import Plugin
from mast.logging import make_logger
from mast.timestamp import Timestamp
from mast.datapower import datapower
from pkg_resources import resource_string
from functools import partial, update_wrapper
import mast.plugin_utils.plugin_utils as util
import mast.plugin_utils.plugin_functions as pf
from mast.datapower.backups import get_normal_backup

cli = commandr.Commandr()

MAST_HOME = os.environ["MAST_HOME"]


def _pmr_create_dirs(appliances, out_dir, timestamp):
    for appliance in appliances:
        _dir = os.path.join(
            out_dir,
            appliance.hostname,
            timestamp)
        os.makedirs(_dir)


def _pmr_get_error_report_settings(appliances):
    results = {}
    for appliance in appliances:
        config = appliance.get_config("ErrorReportSettings")
        results[appliance.hostname] = config
    return results


def _pmr_conditionally_save_internal_state(appliances, ers, timestamp):
    xpath = datapower.CONFIG_XPATH + "/ErrorReportSettings/InternalState"
    for appliance in appliances:
        internal_state = ers[appliance.hostname].xml.find(xpath).text
        internal_state = True if (internal_state == "on") else False
        if not internal_state:
            appliance.SaveInternalState()


def _pmr_generate_error_reports(appliances):
    for appliance in appliances:
        appliance.ErrorReport()


def _pmr_backup_all_domains(appliances, out_dir, timestamp):
    for appliance in appliances:
        filename = os.path.join(
            out_dir,
            appliance.hostname,
            timestamp)
        filename = os.path.join(
            filename,
            '%s-%s-all-domains.zip' % (
                timestamp,
                appliance.hostname))
        with open(filename, 'wb') as fout:
            fout.write(appliance.get_normal_backup())


def _pmr_query_status_providers(appliances, out_dir, timestamp):
    global MAST_HOME
    filename = os.path.join(MAST_HOME, 'etc', 'statusProviders.txt')
    with open(filename, 'r') as fin:
        default_providers = [_.strip() for _ in fin.readlines()]
    filename = os.path.join('etc', 'statusProviders-applicationDomains.txt')
    with open(filename, 'r') as fin:
        application_providers = [_.strip() for _ in fin.readlines()]
    for appliance in appliances:
        for domain in appliance.domains:
            providers = application_providers
            if domain == 'default':
                providers = default_providers
            filename = 'pmrinfo-%s-%s-%s.xml' % (
                appliance.hostname, domain, timestamp)
            filename = os.path.join(
                out_dir,
                appliance.hostname,
                timestamp,
                filename)
            with open(filename, 'w') as fout:
                msg = "<pmrInfo-{}-{}>{}".format(
                    appliance.hostname, domain, os.linesep)
                fout.write(msg)
                for provider in providers:
                    fout.write('<{}>{}'.format(provider, os.linesep))
                    try:
                        status = appliance.get_status(
                            provider, domain=domain).pretty
                        fout.write(status)
                    except Exception:
                        fout.write("Failed to retrieve status!")
                    fout.write('</{}>{}'.format(provider, os.linesep))
                    fout.write(os.linesep)
                fout.write('</pmrInfo-{}-{}>{}'.format(
                    appliance.hostname, domain, os.linesep))


def _pmr_download_error_reports(appliances, out_dir, ers, timestamp):
    protocol_xpath = datapower.CONFIG_XPATH + "/ErrorReportSettings/Protocol"
    raid_path_xpath = datapower.CONFIG_XPATH + "/ErrorReportSettings/RaidPath"

    for appliance in appliances:
        protocol = ers[appliance.hostname].xml.find(protocol_xpath).text

        if protocol == 'temporary':
            path = 'temporary:'
            filestore = appliance.get_filestore('default', path)
            _dir = filestore.xml.find('.//location[@name="%s"]' % (path))

        elif protocol == 'raid':
            try:
                path = ers[appliance.hostname].xml.find(raid_path_xpath).text
            except AttributeError:
                path = ''
            path = "{}/{}".format(appliance.raid_directory, path)
            if path.endswith('/'):
                path = path[:-1]
            filestore = appliance.get_filestore('default', 'local:')
            _dir = filestore.xml.find('.//directory[@name="%s"]' % (path))

        else:
            appliance.log_warn(''.join(
                    ('\tThe failure notification looks like it is set for ',
                     protocol,
                     ', which we do not currently support. Failing back',
                     'to temporary:...\n')))
            path = 'temporary:'
            filestore = appliance.get_filestore('default', path)
            _dir = filestore.xml.find('.//location[@name="%s"]' % (path))

        if not _dir:
            appliance.log_warn("There were no error reports found.")
            return
        files = []
        for node in _dir.findall('.//*'):
            if node.tag == "file":
                if 'error-report' in node.get('name'):
                    files.append(node.get('name'))
        for file in files:
            fqp = '%s/%s' % (path, file)
            filename = '%s-%s' % (appliance.hostname, file)
            filename = os.path.join(
                out_dir,
                appliance.hostname,
                timestamp,
                filename)
            with open(filename, 'wb') as fout:
                fout.write(appliance.getfile('default', fqp))


def _pmr_cleanup(appliances, out_dir, timestamp):
    for appliance in appliances:
        zip_filename = '{}-{}-PMR_INFO.zip'.format(
            timestamp, appliance.hostname)
        zip_filename = os.path.join(out_dir, zip_filename)
        z = zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED)
        _zipdir(os.path.join(out_dir, appliance.hostname, timestamp), z)
        shutil.rmtree(
            os.path.abspath(
                os.path.join(out_dir, appliance.hostname, timestamp)))


def _zipdir(path, z):
    for root, dirs, files in os.walk(path):
        for file in files:
            z.write(os.path.join(root, file), os.path.basename(file))


def _verify_zip(zip_file):
    if isinstance(zip_file, str):
        try:
            zip_file = zipfile.ZipFile(zip_file, 'r')
        except zipfile.BadZipfile:
            return False
    if zip_file.testzip() is None:
        # if testzip returns None then there were no errors
        return True
    return False


@cli.command('xor', category='utilities')
def xor(string='', web=False):
    """This will xor encode and base64 encode the given string
for suitable use in passing credentials to MAST CLI commands.
This is a useful utility for scripting multiple MAST CLI commands
since your credentials will not be in plain text.

**PLEASE NOTE THAT THIS IS OBFUSCATION AT BEST, SO DON'T LEAN
TOO HEAVILY ON THIS SECURITY**

Parameters:

* `-s, --string`: The string to xor and base64 encode
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    if web:
        return xorencode(string), ""
    print(xorencode(string))


# ~#~#~#~#~#~#~#
# Caches
# ======
#
# These functions are meant to be used to flush the caches that DataPower
# maintains.
#
# Current Commands:
# ----------------
#
# FlushAAACache(PolicyName)
# FlushArpCache()
# FlushDNSCache()
# FlushDocumentCache(XMLManager)
# FlushLDAPPoolCache(XMLManager)
# FlushNDCache()
# FlushNSSCache(ZosNSSClient)
# FlushPDPCache(XACMLPDP)
# FlushRBMCache()
# FlushStylesheetCache(XMLManager)
#

@cli.command('flush-aaa-cache', category='caches')
def flush_aaa_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    Domain="",
                    aaa_policy="",
                    web=False):
    """This will flush the AAA Cache for the specified AAAPolicy
in the specified Domain on the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain where the specified AAAPolicy resides
* `-A, --aaa-policy`: The AAAPolicy whose cache you would like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info(
        "Attempting to flush AAA cache on {} in {} domain.".format(
            str(env.appliances), Domain))
    kwargs = {"PolicyName": aaa_policy, 'domain': Domain}
    responses = env.perform_action('FlushAAACache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_aaa_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-arp-cache', category='caches')
def flush_arp_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    web=False):
    """This will flush the ARP cache on the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to flush ARP cache for {}".format(
        str(env.appliances)))
    responses = env.perform_action('FlushArpCache')
    logger.debug("Responses received: {}".format(str(appliances)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_arp_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-dns-cache', category='caches')
def flush_dns_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    web=False):
    """This will flush the DNS cache on the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to flush DNS cache on {}".format(
        str(env.appliances)))
    responses = env.perform_action('FlushDNSCache')
    logger.debug("Responses received: {}".format(responses))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_dns_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-document-cache', category='caches')
def flush_document_cache(appliances=[],
                         credentials=[],
                         timeout=120,
                         no_check_hostname=False,
                         Domain="",
                         xml_manager="",
                         web=False):
    """This will flush the Document cache for the specified
xml_manager in the specified domain on the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain where xml_manager resides
* `-x, --xml-manger`: The XMLManager whose document cache you would
like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to flush document cache for "
        "{} in {} domain for {} xml manager".format(
            str(env.appliances),
            Domain,
            xml_manager))
    kwargs = {"XMLManager": xml_manager, 'domain': Domain}
    responses = env.perform_action('FlushDocumentCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_document_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-ldap-pool-cache', category='caches')
def flush_ldap_pool_cache(appliances=[], credentials=[],
                          timeout=120, Domain="", xml_manager="",
                          no_check_hostname=False, web=False):
    """This will flush the LDAP Pool Cache for the specified
xml_manager in the specified domain on the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain where xml_manager resides
* `-x, --xml-manager`: The XMLManager whose LDAP Pool cache you would
like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to flush LDAP Pool Cache for "
        "{} in {} domain for {} xml manager".format(
            str(env.appliances), Domain, xml_manager))
    kwargs = {"XMLManager": xml_manager, 'domain': Domain}
    responses = env.perform_action('FlushLDAPPoolCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return (util.render_boolean_results_table(
                    responses,
                    suffix="flush_ldap_pool_cache"),
                util.render_history(env))

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-nd-cache', category='caches')
def flush_nd_cache(appliances=[],
                   credentials=[],
                   timeout=120,
                   no_check_hostname=False,
                   web=False):
    """This will flush the ND cache for the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to flush ND Cache for {}".format(
        str(env.appliances)))
    responses = env.perform_action('FlushNDCache')
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_nd_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-nss-cache', category='caches')
def flush_nss_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    Domain="",
                    zos_nss_client="",
                    web=False):
    """This will flush the NSS cache for the specified ZOSNSSClient
in the specified domain for the specified appliance.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain where zos_nss_client resides
* `-z, --zos-nss-client`: The ZOSNSSClient whose cache you would like to
flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to flush NSS Cache for {} {} {}".format(
        str(env.appliances), Domain, zos_nss_client))
    kwargs = {"ZosNSSClient": zos_nss_client, 'domain': Domain}
    responses = env.perform_action('FlushNSSCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_nss_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-pdp-cache', category='caches')
def flush_pdp_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    XACML_PDP="",
                    web=False):
    """This will flush the PDP cache for the specified XACML_PDP
for the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-X, --XACML-PDP`: The XACMLPDP object whose cache you would like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to flush PDP Cache for {} {}".format(
        str(env.appliances), XACML_PDP))
    kwargs = {"XACMLPDP": XACML_PDP}
    responses = env.perform_action('FlushPDPCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_pdp_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-rbm-cache', category='caches')
def flush_rbm_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    Domain="",
                    web=False):
    """This will flush the RBM cache in the specified domain for
the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain whose RBM cache you would like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to flush RBM cache {} {}".format(
        str(env.appliances), Domain))
    responses = env.perform_action('FlushRBMCache', **{'domain': Domain})
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="flush_rbm_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)


@cli.command('flush-stylesheet-cache', category='caches')
def flush_stylesheet_cache(appliances=[],
                           credentials=[],
                           timeout=120,
                           no_check_hostname=False,
                           Domain="",
                           xml_manager="",
                           web=False):
    """This will flush the stylesheet cache for the specified xml_manager
in the specified Domain on the specified appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain where xml_manager resides
* `-x, --xml-manager`: The XMLManager whose cache you would like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to flush Stylesheet Cache for {} {} {}".format(
        str(env.appliances),
        Domain,
        xml_manager))
    kwargs = {"XMLManager": xml_manager, 'domain': Domain}
    responses = env.perform_action('FlushStylesheetCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses,
            suffix="flush_stylesheet_cache"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)
#
# ~#~#~#~#~#~#~#

# ~#~#~#~#~#~#~#
# configuration
# =============
#
# These functions are meant to be used to affect the confiuration of the
# DataPower appliances.
#
# current commands:
# ----------------
#
# save - save the current configuration of the specified domains
#


@cli.command('save', category='configuration')
def save_config(appliances=[],
                credentials=[],
                timeout=120,
                no_check_hostname=False,
                Domain=['default'],
                web=False):
    """Saves the current running configuration in the given domain(s)

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: A list of domains to save. To spcify multiple domains,
use multiple entries of the form `[-D domain1 [-D domain2...]]`
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    if isinstance(Domain, str):
        Domain = [Domain]

    # render_save_config_results_table will handle saving the config
    if web:
        return (
            util.render_save_config_results_table(env, Domain),
            util.render_history(env)
        )

    for appliance in env.appliances:
        _domains = Domain
        if "all-domains" in _domains:
            _domains = appliance.domains
        for domain in _domains:
            logger.info("Attempting to save configuration of {} {}".format(
                appliance, domain))
            resp = appliance.SaveConfig(domain=domain)
            logger.debug("Response received: {}".format(resp))



@cli.command("quiesce-service", category="configuration")
def quiesce_service(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    type="",
                    name="",
                    Domain="",
                    quiesce_timeout="60",
                    web=False):
    """This will quiesce a service in the specified domain on the specified
appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-T, --type`: The type of service to quiesce
* `-N, --name`: The name of the service to quiesce
* `-D, --Domain`: The domain in which the service resides
* `-q, --quiesce-timeout`: This is the amount of time (in seconds)
the appliance should wait before forcing the quiesce
(**Must be at least 60**)
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname
    )
    kwargs = {
        "type": type,
        "name": name,
        "timeout": quiesce_timeout,
        "domain": Domain
    }
    logger.info("Attempting to quiesce service {} in {} on {}".format(
        name, Domain, str(env.appliances)))
    resp = env.perform_action("ServiceQuiesce", **kwargs)
    logger.debug("Responses received: {}".format(str(resp)))

    sleep(quiesce_timeout)

    if web:
        return util.render_boolean_results_table(
            resp, suffix="quiesce_service"), util.render_history(env)

    for host, xml in list(resp.items()):
        print(host, '\n', "=" * len(host))
        print('\n\n', xml)


@cli.command("unquiesce-service", category="configuration")
def unquiesce_service(appliances=[],
                      credentials=[],
                      timeout=120,
                      no_check_hostname=False,
                      Domain="",
                      type="",
                      name="",
                      quiesce_timeout=120,
                      web=False):
    """This will unquiesce a service in the specified domain on the specified
appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain in which the service resides
* `-t, --type`: The type of the service to unquiesce
* `-N, --name`: The name of the service to unquiesce
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    kwargs = {
        "type": type,
        "name": name,
        "timeout": quiesce_timeout,
        "domain": Domain}
    logger.info("Attempting to unquiesce service {} in {} on {}".format(
        name, Domain, str(env.appliances)))
    resp = env.perform_action("ServiceUnquiesce", **kwargs)
    logger.debug("Responses received: {}".format(str(resp)))

    if web:
        return util.render_boolean_results_table(
            resp, suffix="unquiesce_service"), util.render_history(env)

    for host, xml in list(resp.items()):
        print(host, '\n', "=" * len(host))
        print('\n\n', xml)

#
# ~#~#~#~#~#~#~#

# ~#~#~#~#~#~#~#
# domains
# =======
#
# These functions are meant to be used to affect the domains
# of the DataPower appliances.
#
# current commands:
# ----------------
# list-domains - Shows the domains of the specified appliances
# add-domain - adds a domain to the specified appliances
# del-domain - removes a domain from the specified appliances
# quiesce-domain - quiesce the specified domain
# unquiesce-domain - unquiesce the specified domain
# disable-domain - set the admin-state to disabled for the specified domain
# enable-domain - set the admin-state to enabled for the specified domain
#


# Tested!
@cli.command('list-domains', category='domains')
def list_domains(appliances=[],
                 credentials=[],
                 timeout=120,
                 no_check_hostname=False,
                 web=False):
    """Lists the domains on the specified appliances as well as all common
domains.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    if web:
        return util.render_list_domains_table(
            env), util.render_history(env)

    sets = []
    for appliance in env.appliances:
        logger.info("Attempting to retrieve a list of domains for {}".format(
            str(appliance)))
        domains = appliance.domains
        logger.debug("Domains for {} found: {}".format(
            str(appliance), str(domains)))
        sets.append(set(domains))
        print('\n', appliance.hostname)
        print('=' * len(appliance.hostname))
        for domain in appliance.domains:
            print('\t', domain)

    common = list(sets[0].intersection(*sets[1:]))
    common.sort()
    logger.info("domains common to {}: {}".format(
        str(env.appliances), str(common)))
    print('\n', 'Common')
    print('======')
    for domain in common:
        print('\t', domain)


@cli.command('add-domain', category='domains')
def add_domain(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               domain_name=None,
               save_config=False,
               web=False):
    """Adds a domain to the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-d, --domain-name`: The name of the domain to add
* `-s, --save-config`: If specified the configuration on the appliances will be
saved
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to add domain {} to {}".format(
        domain_name, str(env.appliances)))
    kwargs = {'name': domain_name}
    responses = env.perform_async_action('add_domain', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        output = util.render_boolean_results_table(
            responses, suffix="add_domain")

    kwargs = {'domain': 'default'}
    if save_config:
        logger.info(
            "Attempting to save configuration of default domain on {}".format(
                str(env.appliances)))
        responses = env.perform_async_action('SaveConfig', **kwargs)
        logger.debug("Responses received: {}".format(str(responses)))
        if web:
            output += util.render_boolean_results_table(
                responses,
                suffix="save_config")
    if web:
        return output, util.render_history(env)


@cli.command('del-domain', category='domains')
def del_domain(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               Domain="",
               save_config=False,
               web=False):
    """Removes a domain from the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The name of the domain to remove
* `-s, --save-config`: If specified the configuration on the appliances will be
saved
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to remove domain {} from {}".format(
        Domain, str(env.appliances)))
    kwargs = {'name': Domain}
    responses = env.perform_async_action('del_domain', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        output = util.render_boolean_results_table(responses)

    kwargs = {'domain': 'default'}
    if save_config:
        logger.info(
            "Attempting to save configuration of default domain for {}".format(
                str(env.appliances)))
        responses = env.perform_async_action('SaveConfig', **kwargs)
        logger.debug("Responses received: {}".format(str(responses)))
        if web:
            output += util.render_boolean_results_table(
                responses, suffix="del_domain")
    if web:
        return output, util.render_history(env)


@cli.command('quiesce-domain', category='domains')
def quiesce_domain(appliances=[],
                   credentials=[],
                   timeout=120,
                   no_check_hostname=False,
                   Domain=[],
                   quiesce_timeout=60,
                   web=False):
    """Quiesces a domain on the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain to quiesce
* `-q, --quiesce-timeout`: The timeout before quiescing the domain
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to quiesce domain {} for {}".format(
        Domain, str(env.appliances)))

    responses = {}
    for appliance in env.appliances:
        domains = Domain
        if "all-domains" in domains:
            domains = appliance.domains
        for domain in domains:
            kwargs = {
                'name': domain,
                'timeout': str(quiesce_timeout),
                'domain': domain}
            responses[appliance.hostname+"-"+domain] = appliance.DomainQuiesce(**kwargs)
            logger.debug("Response received: {}".format(str(responses[appliance.hostname+"-"+domain])))
            sleep(quiesce_timeout)
    if web:
        return (
            util.render_boolean_results_table(
                responses, suffix="DomainQuiesce"), util.render_history(env))


@cli.command('unquiesce-domain', category='domains')
def unquiesce_domain(appliances=[],
                     credentials=[],
                     timeout=120,
                     no_check_hostname=False,
                     Domain=[],
                     web=False):
    """Unquiesces a domain on the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain to unquiesce
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    responses = {}
    for appliance in env.appliances:
        domains = Domain
        if "all-domains" in domains:
            domains = appliance.domains
        for domain in domains:
            logger.info("Attempting to unquiesce domain {} on {}".format(
                Domain, env.appliances))
            kwargs = {'name': domain}
            responses[appliance.hostname+"-"+domain] = appliance.DomainUnquiesce(**kwargs)
            logger.debug("Responses received: {}".format(str(responses[appliance.hostname+"-"+domain])))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="unquiesce_domain"), util.render_history(env)


@cli.command('disable-domain', category='domains')
def disable_domain(appliances=[],
                   credentials=[],
                   timeout=120,
                   no_check_hostname=False,
                   Domain=[],
                   save_config=False,
                   web=False):
    """Disables a domain on the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain to disable. To spcify multiple domains,
use multiple entries of the form `[-D domain1 [-D domain2...]]`
* `-s, --save-config`: If specified the configuration on the appliances will
be saved
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    if isinstance(Domain, str):
        Domain = Domain
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to disable domains {} on {}".format(
        str(Domain), str(env.appliances)))
    output = ""
    resp = {}
    for appliance in env.appliances:
        domains = Domain
        if "all-domains" in domains:
            domains = appliance.domains
            domains.remove("default")
        for domain in domains:
            logger.info("Attempting to disable {} on {}".format(
                domain, appliance.hostname))
            resp[appliance.hostname] = appliance.disable_domain(domain)
            logger.debug(
                "Response received: {}".format(resp[appliance.hostname]))

            if web:
                output += util.render_boolean_results_table(
                    resp, suffix="disable_domain_{}_{}".format(
                        appliance.hostname, domain))

    if save_config:
        for appliance in env.appliances:
            domains = Domain
            if "all-domains" in domains:
                domains = appliance.domains
            for domain in domains:
                logger.info(
                    "Attempting to save configuration of {} on {}".format(
                        domain, appliance))
                resp[appliance.hostname] = appliance.SaveConfig(domain=domain)
                logger.debug("Response received: {}".format(
                    resp[appliance.hostname]))

                if web:
                    output += util.render_boolean_results_table(
                        resp, suffix="save_config_{}_{}".format(
                            appliance.hostname, domain))
    if web:
        return output, util.render_history(env)


@cli.command('enable-domain', category='domains')
def enable_domain(appliances=[],
                  credentials=[],
                  timeout=120,
                  no_check_hostname=False,
                  Domain=[],
                  save_config=False,
                  web=False):
    """Enables a domain on the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The name of the domain to enable. To spcify multiple domains,
use multiple entries of the form `[-D domain1 [-D domain2...]]`
* `-s, --save-config`: If specified the configuration on the appliances
will be saved
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    if isinstance(Domain, str):
        Domain = [Domain]
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to enable domains {} on {}".format(
        str(Domain), str(env.appliances)))
    output = ""
    resp = {}
    for appliance in env.appliances:
        domains = Domain
        if "all-domains" in domains:
            domains = appliance.domains
            domains.remove("default")
        for domain in domains:
            logger.info("Attempting to enable domain {} on {}".format(
                domain, appliance.hostname))
            resp[appliance.hostname] = appliance.enable_domain(domain)
            logger.debug("Response received: {}".format(
                str(resp[appliance.hostname])))

            if web:
                output += util.render_boolean_results_table(
                    resp, suffix="enable_domain_{}_{}".format(
                        appliance.hostname, domain))

    if save_config:
        for appliance in env.appliances:
            domains = Domain
            if "all-domains" in domains:
                domains = appliance.domains
            for domain in domains:
                logger.info(
                    "Attempting to save configuration of {} on {}".format(
                        domain, appliance.hostname))
                resp[appliance.hostname] = appliance.SaveConfig(domain=domain)
                logger.debug("Response received: {}".format(
                    resp[appliance.hostname]))

                if web:
                    output += util.render_boolean_results_table(
                        resp, suffix="save_config_{}_{}".format(
                            appliance.hostname, domain))
    if web:
        return output, util.render_history(env)


@cli.command('restart-domain', category='domains')
def restart_domain(appliances=[],
                   credentials=[],
                   timeout=120,
                   no_check_hostname=False,
                   Domain=[],
                   web=False):
    """Restarts the specified domains on the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domains to restart
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    responses = {}
    for appliance in env.appliances:
        domains = Domain
        if "all-domains" in domains:
            domains = appliance.domains
        for domain in domains:
            logger.info("Attempting to restart domain {} on {}".format(
                domain, env.appliances))
            responses[appliance.hostname+"-"+domain] = appliance.RestartDomain(Domain=domain)
            logger.debug("Responses received: {}".format(str(responses[appliance.hostname+"-"+domain])))
    if web:
        return util.render_boolean_results_table(
            responses, suffix="restart_domain"), util.render_history(env)

#
# ~#~#~#~#~#~#~#

# ~#~#~#~#~#~#~#
# appliances
# ==========
#
# These functions are meant to affect the DataPower appliances
# as a whole.
#
# current commands
# ----------------
# quiesce-appliance - Quiesce the specified DataPower appliances
# unquiesce-appliance - Unquiesce the specified DataPower appliances
# reboot-appliance - Reboot the specified appliance.
# shutdown-appliance - Shutdown the specified appliance.


@cli.command('quiesce-appliance', category='appliances')
def quiesce_appliance(appliances=[],
                      credentials=[],
                      timeout=120,
                      no_check_hostname=False,
                      quiesce_timeout=60,
                      web=False):
    """Quiesce the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-q, --quiesce-timeout`: The timeout before quiescing the domain
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to quiesce appliances {}".format(
        str(env.appliances)))
    kwargs = {'timeout': str(quiesce_timeout)}
    responses = env.perform_action('QuiesceDP', **kwargs)
    sleep(quiesce_timeout)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="quiesce_dp"), util.render_history(env)

    for host, resp in list(responses.items()):
        print('\n', host, '\n', '*' * len(host), '\n')
        print(resp.pretty)


@cli.command('unquiesce-appliance', category='appliances')
def unquiesce_appliance(appliances=[],
                        credentials=[],
                        timeout=120,
                        no_check_hostname=False,
                        web=False):
    """Unquiesce the specified appliances

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info("Attempting to unquiesce {}".format(str(env.appliances)))
    responses = env.perform_action('UnquiesceDP')
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="unquiesce_dp"), util.render_history(env)

    for host, resp in list(responses.items()):
        print('\n', host, '\n', '*' * len(host), '\n')
        print(resp.pretty)


@cli.command('reboot-appliance', category='appliances')
def reboot_appliance(appliances=[],
                     credentials=[],
                     timeout=120,
                     no_check_hostname=False,
                     delay=10,
                     wait=1200,
                     web=False):
    """Reboot the specified appliances (equivalent to shutdown-reboot)

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-d, --delay`: The delay before rebooting
* `-w, --wait`: The amount of time to wait for all appliances
to come back up
* `-W, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    sleep(delay)
    start = time()
    responses = {}
    for appliance in env.appliances:
        logger.info("Attempting to reboot {}".format(appliance.hostname))
        kwargs = {"Mode": "reboot", "Delay": str(delay)}
        resp = appliance.Shutdown(**kwargs)
        responses[appliance.hostname] = resp
        logger.debug("Response received: {}".format(str(resp)))
        sleep(delay)
        start = time()
        while True:
            sleep(5)
            if appliance.is_reachable():
                logger.info("Appliance is back up, moving on")
                break
            if (time() - start) > wait:
                logger.error(
                    "{} failed to respond within the specified time".format(
                        appliance.hostname
                    )
                )
                raise RuntimeError(
                    "Appliance "
                    "{} did not respond within specified time {}".format(
                        appliance.hostname, str(wait)))
    if web:
        return util.render_boolean_results_table(
            responses, suffix="reboot_appliance"), util.render_history(env)

    for host, resp in list(responses.items()):
        print('\n', host, '\n', '*' * len(host), '\n')
        print(resp.pretty)


@cli.command('shutdown-appliance', category='appliances')
def shutdown_appliance(appliances=[],
                       credentials=[],
                       timeout=120,
                       no_check_hostname=False,
                       delay=10,
                       web=False):
    """Shutdown the specified appliances(equivalent to shutdown-halt)

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-d, --delay`: The delay before shutting down
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to shutdown {}".format(str(env.appliances)))
    kwargs = {'Mode': 'halt', 'Delay': str(delay)}
    responses = env.perform_action('Shutdown', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="shutdown-appliance"), util.render_history(env)

    for host, resp in list(responses.items()):
        print('\n', host, '\n', '*' * len(host), '\n')
        print(resp.pretty)


@cli.command('reload-appliance', category='appliances')
def reload_appliance(appliances=[],
                     credentials=[],
                     timeout=120,
                     no_check_hostname=False,
                     delay=10,
                     wait=180,
                     web=False):
    """Reload the specified appliances (equivalent to shutdown-reload)

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-d, --delay`: The delay before shutting down
* `-w, --wait`: The amount of time to wait for the appliance to come back up
* `-W, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    kwargs = {'Mode': 'reload', 'Delay': str(delay)}

    resp = {}
    for appliance in env.appliances:
        logger.info("Attempting to reload {}".format(appliance.hostname))
        resp[appliance.hostname] = appliance.Shutdown(**kwargs)
        logger.debug("Response received: {}".format(resp[appliance.hostname]))
        sleep(delay)
        start = time()
        while True:
            if appliance.is_reachable():
                logger.info("Appliance {} is back online".format(
                    appliance.hostname))
                break
            sleep(3)
            if (time() - start) > wait:
                msg = "appliance {} ".format(appliance.hostname)
                msg += "failed to come back online within the "
                msg += "specified timeout"
                logger.warn(msg)
                resp[appliance.hostname] = False
                break

    if web:
        return util.render_boolean_results_table(
            resp, suffix="reload_appliance"), util.render_history(env)

    for host, _resp in list(resp.items()):
        print('\n', host, '\n', '*' * len(host), '\n')
        if _resp is False:
            print("Appliance did not come back up")
        else:
            print(_resp.pretty)


@cli.command('firmware-upgrade', category='appliances')
def firmware_upgrade(appliances=[],
                     credentials=[],
                     timeout=1200,
                     no_check_hostname=False,
                     file_in=None,
                     accept_license=False,
                     out_dir="tmp",
                     quiesce_timeout=120,
                     reboot_delay=5,
                     reboot_wait=1200,
                     boot_delete=True,
                     no_cleanup=False,
                     no_backup=False,
                     no_save_config=False,
                     no_quiesce_appliances=False,
                     no_disable_domains=False,
                     no_reboot=False,
                     no_set_firmware=False,
                     no_enable_domains=False,
                     web=False):
    """This will attempt to upgrade the firmware of the specified
appliances.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-f, --file_in`: The patch (upgrade script usually `*.scrypt4`, `*.scrypt3 etc...`)
* `-A, --accept-license`: Whether to accept the license of the new firmware
(You **MUST** Leave this checked or the upgrade will not work)
* `-r, --REBOOT_DELAY`: The delay before rebooting
* `-R, --REBOOT_WAIT`: The amount of time to wait for all appliances to come back up
* `-n, --no-boot-delete`:Whether to perform a `boot delete` prior to
upgrading the firmware
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    cleanup = not no_cleanup
    backup = not no_backup
    save = not no_save_config
    quiesce_appliances = not no_quiesce_appliances
    disable_domains = not no_disable_domains
    set_firmware = not no_set_firmware
    enable_domains = not no_enable_domains
    reboot = not no_reboot
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to upgrade the firmware of {}".format(
        str(env.appliances)))
    if web:
        output = ""
        history = ""

    for appliance in env.appliances:

        if not web:
            print(appliance.hostname)

        if cleanup:
            logger.info("Cleaning up the filesystem of {}".format(
                appliance.hostname))

            if not web:
                print("\tCleaning Filesystem")
            _out = clean_up(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain="default",
                checkpoints=True,
                export=True,
                logtemp=True,
                logstore=True,
                error_reports=True,
                recursive=True,
                backup_files=True,
                out_dir=out_dir,
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone.")

        if boot_delete:
            logger.info("Attempting to perform boot delete on {}".format(
                appliance.hostname))
            if not web:
                print("\tAttempting to performing boot delete")
            appliance.ssh_connect()
            r = appliance.ssh_issue_command("co")
            r += appliance.ssh_issue_command("flash")
            r += appliance.ssh_issue_command("boot delete")
            r += appliance.ssh_issue_command("exit")
            r += appliance.ssh_issue_command("exit")
            r += appliance.ssh_issue_command("exit")
            if not web:
                print(r)
            logger.debug("Responses received: {}".format(str(r)))

        if backup:
            logger.info("Attempting to perform all-domains backup on {}".format(
                appliance.hostname))
            if not web:
                print("\tGetting an all-domains backup")
            _out = get_normal_backup(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain="all-domains",
                comment="pre-firmware_upgrade_backup",
                out_dir=out_dir,
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone.")

        if cleanup:
            logger.info("Cleaning up the filesystem of {}".format(
                appliance.hostname))
            if not web:
                print("\tCleaning filesystem")
            _out = clean_up(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain="default",
                checkpoints=True,
                export=True,
                logtemp=True,
                logstore=True,
                error_reports=True,
                recursive=True,
                backup_files=True,
                out_dir=out_dir,
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone")

        if save:
            logger.info(
                "Attempting to save the configuration of all-domains on {}".format(
                    appliance.hostname))
            if not web:
                print("\tSaving configuration")
            _out = save_config(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=["all-domains"],
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone.")

        if quiesce_appliances:
            logger.info("Attempting to quiesce appliance {}".format(
                appliance.hostname))
            if not web:
                print("\tQuiescing Appliance")
            _out = quiesce_appliance(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                quiesce_timeout=quiesce_timeout,
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone.")

            sleep(quiesce_timeout)

        if disable_domains:
            for domain in appliance.domains:
                if domain not in "default":
                    logger.info("Attempting to disable domain {} on {}".format(
                        domain, appliance.hostname))
                    if not web:
                        print("\tdisabling domain {}".format(domain))
                    _out = disable_domain(
                        appliances=appliance.hostname,
                        credentials=appliance.credentials,
                        timeout=timeout,
                        no_check_hostname=no_check_hostname,
                        Domain=[domain],
                        save_config=False,
                        web=web)

                    if web:
                        output += _out[0]
                        history += _out[1]
                    else:
                        print("\t\tDone.")

        if save:
            logger.info(
                "Attempting to save configuration of all-domains on {}".format(
                    appliance.hostname))
            if not web:
                print("\tSaving configuration")
            _out = save_config(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=["all-domains"],
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone")

        if reboot:
            logger.info("Attempting to reboot {}".format(appliance.hostname))
            if not web:
                print("\tRebooting appliance")
            _out = reboot_appliance(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                delay=reboot_delay,
                wait=reboot_wait,
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone.")

        if set_firmware:
            logger.info("Attempting to set firmware on {}".format(
                appliance.hostname))

            if not web:
                print("\tAttempting to update firmware")
            _out = appliance.set_firmware(
                file_in,
                accept_license,
                timeout)

            if web:
                resp = util.render_boolean_results_table(
                    {appliance.hostname: _out})
                output += resp
            else:
                print("\t\tDone.")

        sleep(60)

        logger.debug("Waiting for {} to come back online".format(
            appliance.hostname))
        start = time()
        while True:
            if appliance.is_reachable():
                logger.info("Appliance is back up.")
                break
            if time() - start > timeout:
                logger.error(
                    "Appliance did not come back up within specified time"
                    "Aborting the remaining firmware upgrades!")

        # TODO: verify version
        # Not implemented yet

        if enable_domains:
            for domain in appliance.domains:
                if domain not in "default":
                    logger.info("Attempting to enable domain {} on {}".format(
                        domain, appliance.hostname))
                    if not web:
                        print("\tenabling domain {}".format(domain))
                    _out = enable_domain(
                        appliances=appliance.hostname,
                        credentials=appliance.credentials,
                        timeout=timeout,
                        no_check_hostname=no_check_hostname,
                        Domain=[domain],
                        save_config=False,
                        web=web)

                    if web:
                        output += _out[0]
                        history += _out[1]
                    else:
                        print("\t\tDone.")
        if save:
            logger.info(
                "Attempting to save configuration of all-domains on {}".format(
                    appliance.hostname))
            if not web:
                print("\tSaving configuration")
            _out = save_config(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=["all-domains"],
                web=web)

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("\t\tDone")

    if web:
        return output, history
#
# ~#~#~#~#~#~#~#

# ~#~#~#~#~#~#~#
# file management
# ===============
#
# These functions are meant to facilitate common filesystem related tasks
# such as setting a file, removing a file, fetching a file or getting a file
# to/from the specified appliances
#


@cli.command('get-encrypted-filesystem', category='file management')
def get_encrypted_filesystem(appliances=[],
                             credentials=[],
                             timeout=120,
                             no_check_hostname=False,
                             out_dir="tmp",
                             web=False):
    """This will get a directory listing of all locations within the
encrypted filesystem. The output will be in the form of xml files saved
into `-o, --out-dir`.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-o, --out-dir`: The directory in which to output the results of
the filesystem audit
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to get a listing of encrypted filesystem")
    resp = env.perform_action("get_encrypted_filesystem")
    logger.info("Response received: {}".format(resp))

    out_dir = os.path.join(out_dir, t.timestamp)
    os.makedirs(out_dir)

    for host, r in list(resp.items()):
        filename = os.path.join(
            out_dir, "{}-encrypted-filesystem.xml".format(host))
        logger.info("Writing directory listing to {}".format(filename))
        with open(filename, 'wb') as fout:
            fout.write(r.pretty)

    if web:
        return util.render_see_download_table(
            resp, suffix="get_encrypted_filesystem"), util.render_history(env)


@cli.command('get-temporary-filesystem', category='file management')
def get_temporary_filesystem(appliances=[],
                             credentials=[],
                             timeout=120,
                             no_check_hostname=False,
                             out_dir="tmp",
                             web=False):
    """This will get a directory listing of all locations within the
temporary filesystem. The output will be in the form of xml files saved
into `-o, --out-dir`.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-o, --out-dir`: The directory in which to output the results of
the filesystem audit
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""

    logger = make_logger("mast.system")
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info(
        "Attempting to get a listing of temporary filesystem of {}".format(
            str(env.appliances)))
    resp = env.perform_action("get_temporary_filesystem")
    logger.debug("response received: {}".format(resp))

    out_dir = os.path.join(out_dir, t.timestamp)
    os.makedirs(out_dir)

    for host, r in list(resp.items()):
        filename = os.path.join(
            out_dir, "{}-temporary-filesystem.xml".format(host))
        logger.info("Writing listing of temporary filesystem to {}".format(
            filename))
        with open(filename, 'wb') as fout:
            fout.write(r.pretty)

    if web:
        return util.render_see_download_table(
            resp, suffix="get_temporary_filesystem"), util.render_history(env)


@cli.command('get-filestore', category='file management')
def get_filestore(appliances=[],
                  credentials=[],
                  timeout=120,
                  no_check_hostname=False,
                  Domain="",
                  location="local:",
                  out_dir="tmp",
                  web=False):
    """This will get the directory listing of the specified location.
The output will be in the form of xml files saved into `-o, --out-dir`.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain from which to get the filestore
* `-l, --Location`: Within the DataPower filesystem (certs, local, etc.)
* `-o, --out-dir`: The directory in which to output the results of
the filesystem audit
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""

    logger = make_logger("mast.system")
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to retrieve directory listing of {} in {}".format(
        str(env.appliances), location))
    resp = env.perform_action(
        "get_filestore",
        domain=Domain,
        location=location)
    logger.debug("Response received: {}".format(resp))

    out_dir = os.path.join(out_dir, t.timestamp)
    os.makedirs(out_dir)

    for host, r in list(resp.items()):
        filename = os.path.join(
            out_dir, "{}-get-filestore.xml".format(host))
        logger.info("Writing directory listing of {} to {}".format(
            str(env.appliances), filename))
        with open(filename, 'wb') as fout:
            fout.write(r.pretty)

    if web:
        return util.render_see_download_table(
            resp, suffix="get_filestore"), util.render_history(env)


@cli.command('copy-file', category='file management')
def copy_file(appliances=[],
              credentials=[],
              timeout=120,
              no_check_hostname=False,
              Domain="",
              src="",
              dst="",
              overwrite=True,
              web=False):
    """Copies a file from src to dst (both src and dst are on the appliance)
optionally overwriting dst.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain for both src and dst
* `-s, --src`: The path to the source file (on the appliance(s))
* `-d, --dst`: The destination of the copied file (on the appliance(s))
* `-N, --no-overwrite`:  If specified dst will not be overwritten if it
already exists
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.system")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    resp = {}
    for appliance in env.appliances:
        logger.info("Attempting to copy file on {} from {} to {}".format(
            appliance.hostname,
            src,
            dst))
        fin = appliance.getfile(domain=Domain, filename=src)
        fout = base64.encodestring(fin)
        resp[appliance.hostname] = appliance._set_file(
            fout, dst, Domain, overwrite)
        logger.debug("Response received: {}".format(resp[appliance.hostname]))
    if web:
        return (
            util.render_boolean_results_table(resp),
            util.render_history(env))
    for host, r in list(resp.items()):
        print(host)
        print("=" * len(host))
        if r:
            print("Success")
        else:
            print("Failed")


@cli.command('set-file', category='file management')
def set_file(appliances=[],
             credentials=[],
             timeout=120,
             no_check_hostname=False,
             file_in=None,
             destination=None,
             Domain='default',
             overwrite=True,
             web=False):
    """Uploads a file to the specified appliances

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-f, --file-in`: The path and filename of the file to upload
* `-d, --destination`: If a location or directory is provided filename will be
as it appears on the local machine, if a path and filename is provided
filename will be as provided
* `-D, --Domain`: The domain to which to upload the file
* `-N, --no-overwrite`: Whether to overwrite the destination if it exists
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    kwargs = {
        'file_in': file_in,
        'file_out': destination,
        'domain': Domain,
        'overwrite': overwrite}
    resp = env.perform_async_action('set_file', **kwargs)

    if web:
        return util.render_boolean_results_table(
            resp, suffix="set_file"), util.render_history(env)


@cli.command('get-file', category='file management')
def get_file(appliances=[],
             credentials=[],
             timeout=120,
             no_check_hostname=False,
             location=None,
             Domain='default',
             out_dir='tmp',
             web=False):
    """Retrieves a file from the specified appliances

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-l, --location`: The location of the file (on DataPower) you would
like to get
* `-D, --Domain`: The domain from which to get the file
* `-o, --out-dir`: (NOT NEEDED IN THE WEB GUI)The directory you would like to
save the file to
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    kwargs = {'domain': Domain, 'filename': location}
    responses = env.perform_async_action('getfile', **kwargs)

    if not os.path.exists(out_dir) or not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    for hostname, fin in list(responses.items()):
        filename = location.split('/')[-1]
        filename = os.path.join(
            out_dir,
            '%s-%s-%s' % (hostname, t.timestamp, filename))
        with open(filename, 'wb') as fout:
            fout.write(fin)
    if web:
        return util.render_see_download_table(
            responses, suffix="get_file"), util.render_history(env)


@cli.command('del-file', category="file management")
def delete_file(appliances=[],
                credentials=[],
                timeout=120,
                no_check_hostname=False,
                Domain="",
                filename="",
                backup=False,
                out_dir="tmp",
                web=False):
    """Deletes a file from the specified appliance(s) optionally backing
up the file locally.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain from which to delete the file
* `-f, --filename`: The filename of the file to delete **Must include
the full path**
* `-b, --backup`: If specified, the file will be backed up to
the directory specified as `-o, --out-dir`
* `-o, --out-dir`: If `-b, --backup` is specified, this is where to
save the backup of the file to.
"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    if backup:
        resp = {}
        for appliance in env.appliances:
            _out_dir = os.path.join(out_dir, appliance.hostname)
            if not os.path.exists(_out_dir):
                os.makedirs(_out_dir)
            resp[appliance.hostname] = appliance.del_file(
                filename=filename, domain=Domain,
                backup=True, local_dir=_out_dir)
    else:
        resp = env.perform_action("del_file", filename=filename, domain=Domain)
    if web:
        return (
            util.render_boolean_results_table(resp),
            util.render_history(env))
    for host, response in list(resp.items()):
        print(host)
        print("=" * len(host))
        if response:
            print("Success")
        else:
            print("Error")
        print()

@cli.command('generate-error-report', category='error-reports')
def generate_error_report(appliances=[],
                          credentials=[],
                          timeout=120,
                          no_check_hostname=False,
                          web=False):
    """This will attempt to retireve any error reports from the
currently configured location on the specified appliance(s).

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(appliances,
                                credentials,
                                timeout=timeout,
                                check_hostname=check_hostname)
    responses = {}
    for appliance in env.appliances:
        msg = "Generating Error report on {}".format(appliance.hostname)
        if not web:
            print(msg)
        appliance.log_info(msg)
        resp = appliance.ErrorReport()
        responses[appliance.hostname] = resp
        if resp:
            msg = "Successfully generated error report on {}".format(
                appliance.hostname)
            if not web:
                print("\t", msg)
            appliance.log_info(msg)
        else:
            msg = "An error occurred generating error report on {}: \n{}".format(
                appliance.hostname, resp)
            if not web:
                print("\t", msg)
            appliance.log_error(msg)
    if web:
        return (util.render_boolean_results_table(responses),
               util.render_history(env))


@cli.command('get-error-reports', category='error-reports')
def get_error_reports(appliances=[],
                      credentials=[],
                      timeout=120,
                      no_check_hostname=False,
                      out_dir="tmp",
                      decompress=False,
                      web=False):
    """This will attempt to retireve any error reports from the
currently configured location on the specified appliance(s).

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-o, --out-dir`: The directory to save the error reports in
* `-d, --decompress`: If specified, the error reports will be decompressed
from the ".gz" encoding
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    t = Timestamp()
    for appliance in env.appliances:
        _dir = os.path.join(
            out_dir,
            appliance.hostname)
        if not os.path.exists(_dir):
            os.makedirs(_dir)
    ers = _pmr_get_error_report_settings(env.appliances)
    _pmr_download_error_reports(env.appliances, out_dir, ers, "")
    if decompress:
        import gzip
        dirs = os.listdir(out_dir)
        files = []
        for _dir in dirs:
             files.extend([os.path.join(out_dir, _dir, x) for x in os.listdir(os.path.join(out_dir, _dir))])
        files = [x for x in files if x.endswith(".gz")]
        for filename in files:
            new_filename = filename.replace(".gz", "")
            print("Decompress: {} -> {}".format(filename, new_filename))
            with gzip.open(filename, "rb") as fin, open(new_filename, "wb") as fout:
                fout.writelines(fin.readlines())
            os.remove(os.path.abspath(filename))
            print("\tDone")

    # Quick hack to let render_see_download_table() to get the appliance names
    _ = {}
    for appliance in env.appliances:
        _[appliance.hostname] = None
    if web:
        return util.render_see_download_table(
            _, suffix="get_error_reports"), util.render_history(env)


@cli.command('copy-directory', category='file management')
def copy_directory(appliances=[],
                   credentials=[],
                   timeout=120,
                   no_check_hostname=False,
                   location="",
                   out_dir="tmp",
                   Domain="",
                   recursive=False,
                   web=False):
    """This will get all of the files from a directory on the appliances
in the specified domain.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-l, --location`: The filesystem and/or directory name to copy.
* `-o, --out-dir`: The local directory into which to copy the files
from the appliance(s)
* `-D, --Domain`: The domain from which to copy the files
* `-r, --recursive`: If specified, files will be copied recursively
from the directory specified by `-l, --location`
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    for appliance in env.appliances:
        _out_dir = os.path.join(out_dir, t.timestamp, appliance.hostname)
        if not os.path.exists(_out_dir) or not os.path.isdir(_out_dir):
            os.makedirs(_out_dir)
        appliance.copy_directory(
            location, _out_dir, Domain, recursive=recursive)

    # Quick hack to let render_see_download_table() to get the appliance names
    _ = {}
    for appliance in env.appliances:
        _[appliance.hostname] = None
    if web:
        return util.render_see_download_table(
            _, suffix="copy_directory"), util.render_history(env)


@cli.command("create-dir", category="file management")
def create_dir(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               Domain="default",
               directory="",
               web=False):
    """Creates a directory in the specified domain. **NOTE** the
parent directory does not need to exist it will act like `mkdir -p`.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain in which to create the directory
* `-d, --directory`: The directory to create. While the location needs
to exists, parent directories do not, will act like `mkdir -p`
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.datapower.system")

    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout=timeout,
        check_hostname=check_hostname)
    kwargs = {'domain': Domain, 'Dir': directory}
    responses = env.perform_action('CreateDir', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if web:
        return util.render_boolean_results_table(
            responses, suffix="create-directory"), util.render_history(env)

    for host, response in list(responses.items()):
        if response:
            print()
            print(host)
            print('=' * len(host))
            if response:
                print('OK')
            else:
                print("FAILURE")
                print(response)
#
# ~#~#~#~#~#~#~#

# ~#~#~#~#~#~#~#
# auditing
# ========
#
# These functions are meant to help with accountability. They invlove
# log files as well as object auditing and gathering information necessary
# in order to submit a PMR
#
# current commands
# ----------------
# fetch-logs - Retrieves a copy of all log files on the appliance
# get-pmr-info - Retrieves the information necessary to submit a PMR
# object-audit - Retrieves a diff of the running and persisted configurations


@cli.command('fetch-logs', category='auditing')
def fetch_logs(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               out_dir='tmp',
               web=False):
    """Fetch all log files from the specified appliance(s) storing them in
out-dir.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-o, --out-dir`: The local directory to save the logs to
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    kwargs = {'log_dir': out_dir}
    resp = env.perform_async_action('get_all_logs', **kwargs)

    if web:
        return util.render_see_download_table(
            resp, suffix="fetch_logs"), util.render_history(env)


@cli.command('get-pmr-info', category='auditing')
def get_pmr_info(appliances=[],
                 credentials=[],
                 timeout=120,
                 no_check_hostname=False,
                 out_dir='tmp',
                 web=False):
    """Get all posible troubleshooting information from the
specified appliances.

Implementation:

This script will perform the following actions in this order:

1. Create a directory structure on the local machine under `-o, --out-dir`
to store the artifacts
2. Retrieve the appliance(s) ErrorReportSettings
3. If the appliance(s) are not configured to save internal state on error
report generation, the internal state will be saved
4. An error report will be generated
5. A backup of all domains will be taken
6. A number of StatusProviders will be queried in both the default
domain and each application domain. See `$MAST_HOME/etc/statusProviders.txt`
and `$MAST_HOME/etc/statusProviders-applicationDomains.txt` to see which
providers will be queried.
7. All error reports present on the appliance(s) will be copied
8. A zipfile will be created per appliance containing all the artifacts
generated by this script and the files will be cleaned up (locally).

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-o, --out-dir`: The directory to save the artifacts generated by
this script in
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    t = Timestamp()
    _pmr_create_dirs(env.appliances, out_dir, t.timestamp)
    ers = _pmr_get_error_report_settings(env.appliances)
    _pmr_conditionally_save_internal_state(env.appliances, ers, t.timestamp)
    _pmr_generate_error_reports(env.appliances)
    _pmr_backup_all_domains(env.appliances, out_dir, t.timestamp)
    _pmr_query_status_providers(env.appliances, out_dir, t.timestamp)
    _pmr_download_error_reports(env.appliances, out_dir, ers, t.timestamp)
    _pmr_cleanup(env.appliances, out_dir, t.timestamp)

    # Quick hack to let render_see_download_table() to get the appliance names
    resp = {}
    for appliance in env.appliances:
        resp[appliance.hostname] = None
    if web:
        return util.render_see_download_table(
            resp, suffix="get_pmr_info"), util.render_history(env)


@cli.command('object-audit', category='auditing')
def objects_audit(appliances=[],
                  credentials=[],
                  timeout=120,
                  no_check_hostname=False,
                  out_dir='tmp',
                  web=False):
    """Get a "diff" of the current and persisted configuration
from all-domains.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-o, --out-dir`: The directory to store the artifacts generated by this
script.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    results = env.perform_async_action('object_audit')

    for hostname, audit in list(results.items()):
        filename = os.path.join(out_dir, hostname, 'object_audit', t.timestamp)
        os.makedirs(filename)
        filename = os.path.join(filename, 'object-audit.xml')
        with open(filename, 'w') as fout:
            fout.write(audit)
    if web:
        return util.render_see_download_table(
            results, suffix="object_audit"), util.render_history(env)


@cli.command('get-status', category='auditing')
def get_status(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               StatusProvider=[],
               Domain='default',
               out_file=None,
               machine=False,
               web=False):
    """This will query the status of the specified appliances in
in the specified Domain for the specified StatusProviders.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-S, --StatusProvider`: Status providers to query. To pass multiple arguments
to this parameter, use multiple entries of the form `[-S StatusProvider1  [-S StatusProvider2...]]`
* `-D, --Domain`: The domain from which to query the status providers
* `-o, --out-file`: The file to write the results to, this will default
to stdout
* `-m, --machine`: If specified, the xml will be written with whitespace
collapsed and newlines removed
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    if not web:
        if out_file is not None:
            out_file = open(out_file, 'w')
        else:
            out_file = sys.stdout

    if web:
        output = ""

    for provider in StatusProvider:
        t = Timestamp()

        kwargs = {'provider': provider, 'domain': Domain}
        results = env.perform_async_action('get_status', **kwargs)
        if web:
            output += util.render_status_results_table(
                results, suffix="get_status")

        for hostname, response in list(results.items()):
            if machine:
                status = repr(response)
            else:
                status = str(response)
            header = '\n\n%s - %s - %s\n\n' % (hostname, provider, t.timestamp)
            if not web:
                out_file.write(header + status + '\n')

    if web:
        return output, util.render_history(env)
    if out_file != sys.stdout:
        out_file.close()


@cli.command('get-config', category='auditing')
def get_config(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               ObjectClass="",
               obj_name=None,
               recursive=False,
               persisted=False,
               Domain='default',
               out_file=None,
               machine=False,
               web=False):
    """This will get the config of obj_name from the specified
domain on the specified appliances.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-O, --ObjectClass`: The class of the object whose config you wish to get
* `-o, --obj-name`: If given, the configuration will be gotten for that object,
otherwise, all objects of class ObjectClass will be provided
* `-r, --recursive`: If specified, the configuration will be retrieved
recursively
* `-p, --persisted`: If specified, the persisted configuration will
be retrieved as opposed to the running configuration
otherwise the running configuration will be provided
* `-D, --Domain`: The domain from which to get the configuration
* `-o, --out-file`: The file to write the results to, this will default
to stdout
* `-m, --machine`: If specified, the xml will be written with whitespace
collapsed and newlines removed
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    t = Timestamp()

    if out_file is not None:
        out_file = open(out_file, 'w')
    else:
        out_file = sys.stdout

    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    kwargs = {
        '_class': ObjectClass,
        'name': obj_name,
        'recursive': recursive,
        'persisted': persisted,
        'domain': Domain}
    results = env.perform_async_action('get_config', **kwargs)

    if web:
        return util.render_config_results_table(
            results, suffix="get_config"), util.render_history(env)

    for hostname, response in list(results.items()):
        if machine:
            resp = repr(response)
        else:
            resp = str(response)
        header = '\n\n%s - %s - %s\n\n' % (hostname, ObjectClass, t.timestamp)
        out_file.write(header + resp + '\n')

    if out_file != sys.stdout:
        out_file.close()
#
# ~#~#~#~#~#~#~#

# ~#~#~#~#~#~#~#
# maintenance
# ===========
#
# These functions are meant to perform routine maintenance on the specified
# appliances
#
# current commands
# ----------------
# clean-up - Cleans the filesystem.


@cli.command('clean-up', category='maintenance')
def clean_up(appliances=[],
             credentials=[],
             timeout=120,
             no_check_hostname=False,
             Domain='default',
             checkpoints=False,
             export=False,
             logtemp=False,
             logstore=False,
             error_reports=False,
             recursive=False,
             backup_files=True,
             out_dir='tmp',
             web=False):
    """This will clean up the specified appliances filesystem optionally
(defaults to True) taking copies of the files as backups.

Parameters:

* `-a, --appliances` - The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in `hosts.conf` located in
`$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
use multiple entries of the form `[-a appliance1 [-a appliance2...]]`
* `-c, --credentials`: The credentials to use for authenticating to the
appliances. Should be either one set to use for all appliances
or one set for each appliance. Credentials should be in the form
`username:password`. To pass multiple credentials to this parameter, use
multiple entries of the form `[-c credential1 [-c credential2...]]`.
When referencing multiple appliances with multiple credentials,
there must be a one-to-one correspondence of credentials to appliances:
`[-a appliance1 [-a appliance2...]] [-c credential1 [-c credential2...]]`
If you would prefer to not use plain-text passwords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-D, --Domain`: The domain whose filesystem you would like to clean up
* `-C, --checkpoints`: If specified, all checkpoints will be removed
from the domain
* `-e, --export`: If specified all exports will be removed from the domain
* `-l, --logtemp`: If specified, all files in `logtemp:` will be removed
from the domain
* `-L, --logstore`: If specified, all files in `logstore:` will be
removed
* `-E, --error-reports`: If specified, all error reports will be removed
from the appliance(s)
* `-r, --recursive`: If specified, directories will be cleaned recursively
* `--no-backup-files`: If specified, files will not be backed up before
deleting
* `-o, --out-dir`: The directory to save backed up files
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    t = Timestamp()
    dirs = []
    if checkpoints:
        dirs.append('chkpoints:/')
    if export:
        dirs.append('export:/')
    if logtemp:
        dirs.append('logtemp:/')
    if logstore:
        dirs.append('logstore:/')

    if web:
        rows = []
    for appliance in env.appliances:
        if web:
            rows.append((appliance.hostname, ))
        for _dir in dirs:
            _clean_dir(
                appliance,
                _dir,
                Domain,
                recursive,
                backup_files,
                t.timestamp,
                out_dir)
            if web:
                rows.append(("", _dir, "Cleaned"))
            else:
                print('\t', appliance.hostname, "-", _dir, "-", " Cleaned")
        if error_reports:
            _clean_error_reports(
                appliance, Domain,
                backup_files, t.timestamp,
                out_dir)
            if web:
                rows.append(("", "ErrorReports", "Cleaned"))
            else:
                print('\t', appliance.hostname, "-", "ErrorReports - Cleaned")
    if web:
        return flask.render_template(
            "results_table.html",
            header_row=["Appliance", "Location", "Action"],
            rows=rows), util.render_history(env)


def _clean_dir(appliance, _dir, domain, recursive, backup, timestamp, out_dir):
    if backup:
        local_dir = os.path.sep.join(
            os.path.sep.join(_dir.split(':/')).split('/'))
        local_dir = os.path.join(
            out_dir,
            appliance.hostname,
            timestamp,
            domain,
            local_dir)
        os.makedirs(local_dir)
    # if not recursive don't include_directories
    files = appliance.ls(_dir, domain=domain, include_directories=recursive)
    for file in files:
        if "diag-log" in file and "." not in file:
            continue
        if ':/' in file:
            _clean_dir(
                appliance,
                file.rstrip("/"),
                domain,
                recursive,
                backup,
                timestamp,
                out_dir)
        else:
            filename = '{}/{}'.format(_dir, file)
            if backup:
                fout = open(os.path.join(local_dir, file), 'wb')
                contents = appliance.getfile(domain, filename)
                fout.write(contents)
                fout.close
            appliance.DeleteFile(domain=domain, File=filename)


def _clean_error_reports(appliance, domain, backup, timestamp, out_dir):
    protocol_xpath = datapower.CONFIG_XPATH + "/ErrorReportSettings/Protocol"
    raid_path_xpath = datapower.CONFIG_XPATH + "/ErrorReportSettings/RaidPath"

    if backup:
        local_dir = os.path.join(
            out_dir,
            appliance.hostname,
            timestamp,
            domain,
            'temporary')
        os.makedirs(local_dir)
    ers = appliance.get_config("ErrorReportSettings")
    protocol = ers.xml.find(protocol_xpath).text

    if protocol == 'temporary':
        path = 'temporary:'
        filestore = appliance.get_filestore('default', path)
        _dir = filestore.xml.find('.//location[@name="%s"]' % (path))

    elif protocol == 'raid':
        try:
            path = ers.xml.find(raid_path_xpath).text
        except AttributeError:
            path = ''
        path = "{}/{}".format(appliance.raid_directory, path)
        path = path.rstrip("/")

        filestore = appliance.get_filestore('default', 'local:')
        _dir = filestore.xml.find('.//directory[@name="%s"]' % (path))

    else:
        appliance.log_warn(''.join(
                ('\tThe failure notification looks like it is set for ',
                 protocol,
                 ', which we do not currently support. Failing back',
                 'to temporary:...\n')))
        path = 'temporary:'
        filestore = appliance.get_filestore('default', path)
        _dir = filestore.xml.find('.//location[@name="%s"]' % (path))

    if not _dir:
        appliance.log_warn("There were no error reports found.")
        return

    files = []
    for node in _dir.findall('.//*'):
        if node.tag == "file" and 'error-report' in node.get('name'):
            files.append(node.get('name'))

    for f in files:
        fqp = '%s/%s' % (path, f)
        filename = '%s-%s' % (appliance.hostname, f)
        if backup:
            local_dir = os.path.join(
                out_dir,
                appliance.hostname,
                timestamp,
                domain,
                path.replace(":", "").replace("/", os.path.sep))
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            filename = os.path.join(local_dir, filename)
            with open(filename, 'wb') as fout:
                fout.write(appliance.getfile('default', fqp))
        appliance.DeleteFile(domain="default", File=fqp)


def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f))


class WebPlugin(Plugin):
    def __init__(self):
        self.route = partial(pf.handle, "system")
        self.route.__name__ = "system"
        self.html = partial(pf.html, "mast.datapower.system")
        update_wrapper(self.html, pf.html)

    def css(self):
        return get_data_file('plugin.css')

    def js(self):
        return get_data_file('plugin.js')
#
# ~#~#~#~#~#~#~#

if __name__ == '__main__':
    try:
        cli.Run()
    except AttributeError as e:
        if "'NoneType' object has no attribute 'app'" in e:
            raise NotImplementedError(
                "HTML formatted output is not supported on the CLI")
        else:
            raise
