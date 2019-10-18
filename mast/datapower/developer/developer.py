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
mast dev:

A set of tools for automating routine development
tasks associated with IBM DataPower appliances.
"""
import os
from mast.cli import Cli
from mast.plugins.web import Plugin
from mast.datapower import datapower
from mast.timestamp import Timestamp
from mast.pprint import pprint_xml
from pkg_resources import resource_string
from mast.logging import make_logger, logged
import mast.plugin_utils.plugin_utils as util
from functools import partial, update_wrapper
import mast.plugin_utils.plugin_functions as pf

cli = Cli()

# Caches
# ======
#
# These functions are meant to be used to flush the caches that DataPower
# maintains.
#
# Current Commands:
# ----------------
#
# FlushDocumentCache(XMLManager)
# FlushStylesheetCache(XMLManager)
#


@logged("mast.datapower.developer")
@cli.command('flush-document-cache', category='caches')
def flush_document_cache(appliances=[],
                         credentials=[],
                         timeout=120,
                         no_check_hostname=False,
                         Domain="",
                         xml_manager="",
                         web=False):
    """Flushes the Document Cache for the specified xml_manager
in the specified domain.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases please see the comments in `hosts.conf` located
in `$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
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
* `-x, --xml-manager`: The XMLManager whose cache to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.developer")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to flush document cache for {} in {} domain on {} XMLManager".format(str(env.appliances), Domain, xml_manager)
    logger.info(msg)
    if not web:
        print(msg)

    kwargs = {"XMLManager": xml_manager, 'domain': Domain}
    responses = env.perform_action('FlushDocumentCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if not web:
        for host, resp in list(responses.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        return util.render_boolean_results_table(
            responses, suffix="flush_document_cache"), util.render_history(env)


@logged("mast.datapower.developer")
@cli.command('flush-stylesheet-cache', category='caches')
def flush_stylesheet_cache(appliances=[],
                           credentials=[],
                           timeout=120,
                           no_check_hostname=False,
                           Domain="",
                           xml_manager="",
                           web=False):
    """Flushes the Stylesheet Cache for the specified xml_manager
in the specified domain.

Parameters:

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases please see the comments in `hosts.conf` located
in `$MAST_HOME/etc/default`. To pass multiple arguments to this parameter,
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
* `-x, --xml-manager`: The XMLManager whose cache to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.developer")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to flush stylesheet cache for {} in {} domain on {} XMLManager".format(str(env.appliances), Domain, xml_manager)
    logger.info(msg)
    if not web:
        print(msg)

    kwargs = {"XMLManager": xml_manager, 'domain': Domain}
    responses = env.perform_action('FlushStylesheetCache', **kwargs)
    logger.debug("Responses received: {}".format(str(responses)))

    if not web:
        for host, resp in list(responses.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        return util.render_boolean_results_table(
            responses,
            suffix="flush_stylesheet_cache"), util.render_history(env)

# services/objects
# ================
#
# These functions are meant to affect the services and objects
# on the DataPower appliances
#
# current commands
# ----------------
# import - import a service or object to the specified domain
# export - export a service or object from the specified domain


@logged("mast.datapower.developer")
@cli.command('import', category='services/objects')
def _import(appliances=[],
            credentials=[],
            timeout=120,
            no_check_hostname=False,
            Domain=[],
            file_in=None,
            deployment_policy=None,
            deployment_policy_variables=None,
            dry_run=False,
            overwrite_files=True,
            overwrite_objects=True,
            rewrite_local_ip=True,
            source_type='ZIP',
            out_dir="tmp/",
            web=False):
    """Import a service/object into the specified appliances

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
* `-D. --Domain`: The domain into which the configuration will be imported
* `-f, --file-in`: The file to import into the specified domain. This
__MUST__ match the format specified in source_type
* `-d, --deployment-policy`: The deployment policy to use for the import
(must already exist on the appliances)
* `--dry-run`: Whether to do a dry-run (nothing will be imported)
* `-N, --no-overwrite-files`: If specified, no files will be overwritten
as part of the import
* `--no-overwrite-objects`: If specified, no objects will be overwritten
as part of the import
* `--no-rewrite-local-ip`: If specified, no local ip addresses will be
rewritten as part of the import
* `-s, --source-type`: The type of file to import. Can be "XML" or "ZIP"
* `-o, --out-dir`: The directory to output artifacts generated by this
script
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.developer")
    t = Timestamp()

    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to import {} to {}".format(file_in, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    results = {}
    out_dir = os.path.join(out_dir, "import_results", t.timestamp)
    os.makedirs(out_dir)
    for appliance in env.appliances:
        if not web:
            print(appliance.hostname)
        results[appliance.hostname] = {}
        domains = Domain
        if "all-domains" in domains:
            domains = appliance.domains
        for domain in domains:
            if not web:
                print("\t", domain)
            kwargs = {
                'domain': domain,
                'zip_file': file_in,
                'deployment_policy': deployment_policy,
                'deployment_policy_variables': deployment_policy_variables,
                'dry_run': dry_run,
                'overwrite_files': overwrite_files,
                'overwrite_objects': overwrite_objects,
                'rewrite_local_ip': rewrite_local_ip,
                'source_type': source_type}

            resp = appliance.do_import(**kwargs)
            results[appliance.hostname][domain] = resp
            if not web:
                pprint_xml(resp.xml)
            logger.debug("Response received: {}".format(str(resp)))


            filename = os.path.join(
                out_dir,
                "{}-{}-import_results.xml".format(
                    appliance.hostname,
                    domain
                )
            )
            with open(filename, 'wb') as fout:
                fout.write(resp.pretty)
    if web:
        return util.render_see_download_table(
            results, suffix="import"), util.render_history(env)


@logged("mast.datapower.developer")
@cli.command('export', category='services/objects')
def export(appliances=[],
           credentials=[],
           timeout=120,
           no_check_hostname=False,
           Domain="",
           object_name=None,
           object_class=None,
           comment='',
           format='ZIP',
           persisted=True,
           all_files=True,
           referenced_files=True,
           referenced_objects=True,
           out_dir='tmp',
           web=False):
    """Exports a service or object to be used to import into another
domain or appliance

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
* `-D, --Domain`: The domain from which to export service/object
* `-o, --object-name`: The name of the object to export
* `-O, --object-class`: The class of the object to export
* `-C, --comment`: The comment to embed into the export
* `-f, --format`: the format in which to export the configuration. This
can be either "XML" or "ZIP"
* `-N, --no-persisted`: If specified, the running configuration will be
exported as opposed to the persisted configuration
* `--no-all-files`: If specified, the export will not include all files
* `--no-referenced-files`: If specified, the referenced files will not
be included in the export
* `--no-referenced-objects`: If specified, referenced objects will not
be included in the export.
* `--out-dir`: (**NOT NEEDED IN THE WEB GUI**)The directory (local)
in which to save the export
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.developer")
    t = Timestamp()
    if object_name is None or object_class is None:
        try:
            raise TypeError("Must Provide both object name and object class")
        except:
            logger.exception("Must Provide both object name and object class")
            raise
    if format == "ZIP":
        extention = "zip"
    elif format == "XML":
        extention = "xcfg"
    else:
        raise ValueError("Format must be either 'ZIP' or 'XML', got '{}'".format(format))

    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to export {} from {}".format(object_name, str(env.appliances))
    logger.info(msg)

    kwargs = {
        'domain': Domain,
        'obj': object_name,
        'object_class': object_class,
        'comment': comment,
        'format': format,
        'persisted': persisted,
        'all_files': all_files,
        'referenced_objects': referenced_objects,
        'referenced_files': referenced_files}

    results = env.perform_action(
        'export',
        **kwargs)

    for hostname, _export in list(results.items()):
        d = os.path.join(out_dir, hostname, t.timestamp)
        os.makedirs(d)
        filename = os.path.join(d, '%s-%s-%s.%s' % (
            t.timestamp,
            hostname,
            object_name,
            extention))
        msg = "Writing export of {} from {} to {}".format(object_name, hostname, filename)
        logger.debug(msg)
        if not web:
            print(msg)
        with open(filename, 'wb') as fout:
            fout.write(_export)

    if web:
        return util.render_see_download_table(
            results, suffix="export"), util.render_history(env)


@logged("mast.datapower.developer")
@cli.command('list-probes', category='services/objects')
def list_probes(appliances=[],
                credentials=[],
                timeout=120,
                no_check_hostname=False,
                Domain=[],
                web=False):
    """Lists all enabled probes in all specified domains

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
* `-D, --Domain`: One or more domains to inspect. To spcify multiple domains,
use multiple entries of the form `[-D domain1 [-D domain2...]]`
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    import urllib.request, urllib.error, urllib.parse
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout=timeout,
        check_hostname=check_hostname)
    results = {}
    for appliance in env.appliances:
        domains = Domain
        if "all-domains" in Domain:
            domains = appliance.domains
        for domain in domains:
            try:
                config = appliance.get_config(
                    _class="all-classes",
                    name="all-objects",
                    domain=domain,
                    persisted=False)
            except urllib.error.HTTPError:
                config = appliance.get_config(domain=domain, persisted=False)
            for obj in config.xml.findall(datapower.CONFIG_XPATH):
                if obj.find("DebugMode") is not None:
                    if obj.find("DebugMode").text == "on":
                        k = "{}-{}".format(appliance.hostname, domain)
                        v = "{} - {}".format(obj.tag, obj.get("name"))
                        if k in results:
                            results[k].append(v)
                        else:
                            results[k] = [v]
    if web:
        for k, v in list(results.items()):
            results[k] = "\n".join(v)
        return (
            util.render_results_table(results),
            util.render_history(env))
    else:
        for k, v in list(results.items()):
            print(k, "\n", "-" * len(k))
            for item in v:
                print("\t{}".format(item))


def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f)).decode()


class WebPlugin(Plugin):
    def __init__(self):
        self.route = partial(pf.handle, "developer")
        self.route.__name__ = "developer"
        self.html = partial(pf.html, "mast.datapower.developer")
        update_wrapper(self.html, pf.html)

    def css(self):
        return get_data_file('plugin.css')

    def js(self):
        return get_data_file('plugin.js')


if __name__ == '__main__':
    try:
        cli.run()
    except AttributeError as e:
        if "'NoneType' object has no attribute 'app'" in e:
            raise NotImplementedError(
                "HTML formatted output is not supported on the CLI")
