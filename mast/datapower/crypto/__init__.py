import os
import re
import flask
import OpenSSL
import commandr
import openpyxl
from .utils import *
from time import sleep
from datetime import datetime
from mast.pprint import print_table, html_table
from mast.plugins.web import Plugin
from mast.logging import make_logger
from mast.timestamp import Timestamp
import xml.etree.cElementTree as etree
from pkg_resources import resource_string
import mast.datapower.datapower as datapower
import mast.plugin_utils.plugin_utils as util
from functools import partial, update_wrapper
from dateutil import parser, tz, relativedelta
import mast.plugin_utils.plugin_functions as pf

__version__ = "{}-0".format(os.environ["MAST_VERSION"])

cli = commandr.Commandr()


@cli.command("cert-audit", category="certificates")
def cert_audit(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               domains=[],
               out_file="tmp/cert-audit.xlsx",
               delay=0.5,
               date_time_format="%A, %B %d, %Y, %X",
               localtime=False,
               days_only=False,
               web=False):
    """Perform an audit of all CryptoCertificate objects which are
up and enabled for the specified appliances and domains.

Output:

A table and an excel spreadsheet.

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
* `-d, --domains`: The domains to audit, to audit all domains, provide
`all-domains`, to specify multiple domains use multiple entries of the
form `[-d domain1 [-d domain2...]]`.
* `-o, --out-file`: The excel spreadsheet to output, use either relative
or absolute path. The file should end in `.xlsx`
* `-D, --delay`: The amount of time in seconds to wait between auditing
each certificate. If you are experiencing intermitten `AuthenticationFailure`s,
it is a good idea to increase this parameter.
* `--date-time-format`: The format for date-timestamps. Refer to
[this document](https://docs.python.org/2/library/time.html#time.strftime)
for information on using this parameter
* `-l, --localtime`: If specified, the date-timestamps will be output in
local time instead of UTC.
* `--days-only`: If specified, only the number of days (floored) will be
reported in the `time-since-expiration` and `time-until-expiration` columns.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("cert-audit")
    if out_file is None:
        logger.error("Must specify out file")
        if not web:
            print "Must specify out_file"
        sys.exit(2)
    if not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    header_row = [
        "appliance",
        "domain",
        "certificate-object",
        "filename",
        "serial-number",
        "subject",
        "signature_algorithm",
        "not_before",
        "not_after",
        "issuer",
        "is-expired",
        "time-since-expiration",
        "time-until-expiration"]
    rows = [header_row]
    for appliance in env.appliances:
        logger.info("Checking appliance {}".format(appliance.hostname))
        if not web:
            print appliance.hostname
        _domains = domains
        if "all-domains" in domains:
            _domains = appliance.domains
        for domain in _domains:
            logger.info("In domain {}".format(domain))
            if not web:
                print "\t", domain
            config = appliance.get_config("CryptoCertificate", domain=domain)
            certs = [x for x in config.xml.findall(datapower.CONFIG_XPATH)]

            # Filter out disabled objects because the results won't change,
            # but we will perform less network traffic
            certs = filter(
                lambda x: x.find("mAdminState").text == "enabled",
                certs)

            for cert in certs:
                logger.info("Exporting cert {}".format(cert))
                filename = cert.find("Filename").text
                name = cert.get("name")
                _filename = name
                if not web:
                    print "\t\t", name
                row = [appliance.hostname, domain, name, filename]

                appliance.CryptoExport(
                    domain=domain,
                    ObjectType="cert",
                    ObjectName=name,
                    OutputFilename=_filename)
                logger.info("Finished exporting cert {}".format(cert))
                try:
                    logger.info(
                        "Retrieving file {}".format(
                            "temporary:///{}".format(_filename)))
                    cert = appliance.getfile(
                        domain,
                        "temporary:///{}".format(_filename))
                    logger.info(
                        "Finished retrieving file {}".format(
                            "temporary:///{}".format(_filename)))
                    logger.info(
                        "Attempting to delete file {}".format(
                            "temporary:///{}".format(_filename)))
                    appliance.DeleteFile(
                        domain=domain,
                        File="temporary:///{}".format(_filename))
                    logger.info(
                        "Finished deleting file {}".format(
                            "temporary:///{}".format(_filename)))
                except:
                    logger.exception("An unhandled exception has occurred")
                    rows.append(row)
                    if not web:
                        print "SKIPPING CERT"
                    continue
                cert = etree.fromstring(cert)
                _contents = insert_newlines(cert.find("certificate").text)
                certificate = \
                    "-----BEGIN CERTIFICATE-----\n" +\
                    _contents +\
                    "\n-----END CERTIFICATE-----\n"
                _cert = OpenSSL.crypto.load_certificate(
                    OpenSSL.crypto.FILETYPE_PEM,
                    certificate)
                subject = "'{}'".format(
                    ";".join(
                        ["=".join(x)
                         for x in _cert.get_subject().get_components()]))
                issuer = "'{}'".format(
                    ";".join(
                        ["=".join(x)
                         for x in _cert.get_issuer().get_components()]))
                serial_number = _cert.get_serial_number()
                try:
                    signature_algorithm = _cert.get_signature_algorithm()
                except AttributeError:
                    signature_algorithm = ""
                local_tz = tz.tzlocal()
                utc_tz = tz.tzutc()
                notBefore_utc = parser.parse(_cert.get_notBefore())
                notBefore_local = notBefore_utc.astimezone(local_tz)

                notAfter_utc = parser.parse(_cert.get_notAfter())
                notAfter_local = notAfter_utc.astimezone(local_tz)
                if localtime:
                    notAfter = notAfter_local.strftime(date_time_format)
                    notBefore = notBefore_local.strftime(date_time_format)
                else:
                    notAfter = notAfter_utc.strftime(date_time_format)
                    notBefore = notBefore_utc.strftime(date_time_format)

                if _cert.has_expired():
                    time_since_expiration = datetime.utcnow().replace(tzinfo=utc_tz) - notAfter_utc
                    if days_only:
                        time_since_expiration = time_since_expiration.days
                    else:
                        time_since_expiration = str(time_since_expiration)
                    time_until_expiration = 0
                else:
                    time_until_expiration = notAfter_utc - datetime.utcnow().replace(tzinfo=utc_tz)
                    if days_only:
                        time_until_expiration = time_until_expiration.days
                    else:
                        time_until_expiration = str(time_until_expiration)
                    time_since_expiration = 0
                row.extend(
                    [serial_number,
                     subject,
                     signature_algorithm,
                     notBefore,
                     notAfter,
                     issuer,
                     str(_cert.has_expired()),
                     time_since_expiration,
                     time_until_expiration])
                rows.append(row)
                sleep(delay)

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(out_file)
    if not web:
        print "\n\nCertificate Report (available at {}):".format(os.path.abspath(out_file))
        print_table(rows)
        print
    else:
        return (html_table(rows,
                           table_class="width-100",
                           header_row_class="results_table_header_row",
                           header_cell_class="results_table_header_column",
                           body_row_class="result_table_row",
                           body_cell_class="result_table_cell"),
                util.render_history(env))


@cli.command("cert-file-audit", category="certificates")
def cert_file_audit(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    out_file=os.path.join("tmp", "cert-file-audit.xlsx"),
                    web=False):
    """Perform an audit of all files which reside in `cert:`, `pubcert:`
and `sharedcert:` on the specified appliances.

Output:

A table and an excel spreadsheet.

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
* `-o, --out-file`: The excel spreadsheet to output, use either relative
or absolute path. The file should end in `.xlsx`
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("cert-file-audit")
    if out_file is None:
        logger.error("Must specify out file")
        if not web:
            print "Must specify out_file"
        sys.exit(2)
    if not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))
    locations = ["cert:", "pubcert:", "sharedcert:"]
    check_hostname = not no_check_hostname
    env = datapower.Environment(appliances,
                                credentials,
                                timeout,
                                check_hostname=check_hostname)

    header_row = ["appliance",
                  "domain",
                  "directory",
                  "filename",
                  "size",
                  "modified"]
    rows = [header_row]

    for appliance in env.appliances:
        if not web:
            print appliance.hostname
        domain = "default"

        for location in locations:
            if not web:
                print "\t{}".format(location)
            filestore = appliance.get_filestore(domain=domain,
                                                location=location)
            _location = filestore.xml.find(datapower.FILESTORE_XPATH)
            if _location is None:
                continue
            if _location.findall("./file") is not None:
                for _file in _location.findall("./file"):
                    dir_name = _location.get("name")
                    filename = _file.get("name")
                    if not web:
                        print "\t\t{}".format(filename)
                    size = _file.find("size").text
                    modified = _file.find("modified").text
                    rows.append([appliance.hostname,
                                 domain,
                                 dir_name,
                                 filename,
                                 size,
                                 modified])
            for directory in _location.findall(".//directory"):
                dir_name = directory.get("name")
                if not web:
                    print "\t\t{}".format(dir_name)
                for _file in directory.findall(".//file"):
                    filename = _file.get("name")
                    if not web:
                        print "\t\t\t{}".format(filename)
                    size = _file.find("size").text
                    modified = _file.find("modified").text

                    rows.append([appliance.hostname,
                                 domain,
                                 dir_name,
                                 filename,
                                 size,
                                 modified])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CertFileAudit"
    for row in rows:
        ws.append(row)
    wb.save(out_file)
    if not web:
        print_table(rows)
    else:
        return (html_table(rows,
                           table_class="width-100",
                           header_row_class="results_table_header_row",
                           header_cell_class="results_table_header_column",
                           body_row_class="result_table_row",
                           body_cell_class="result_table_cell"),
               util.render_history(env))


@cli.command("export-certs", category="certificates")
def export_certs(appliances=[],
                 credentials=[],
                 timeout=120,
                 no_check_hostname=False,
                 domains=[],
                 out_dir="tmp",
                 delay=0.5,
                 web=False):
    """Export all CryptoCertificate objects which are up and enabled
from the specified domains on the specified appliances in PEM format
and download them to `out-dir`

Output:

Downloaded files

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
* `-d, --domains`: The domains to audit, to audit all domains, provide
`all-domains`, to specify multiple domains use multiple entries of the
form `[-d domain1 [-d domain2...]]`.
* `-o, --out-dir`: The directory to which to download the certificates.
* `-D, --delay`: The amount of time in seconds to wait between exporting each
certificate. If you are experiencing intermitten `AuthenticationFailure`s,
it is a good idea to increase this parameter.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("export-certs")
    check_hostname = not no_check_hostname
    env = datapower.Environment(appliances,
                                credentials,
                                timeout,
                                check_hostname=check_hostname)

    for appliance in env.appliances:
        logger.info("Checking appliance {}".format(appliance.hostname))
        if not web:
            print appliance.hostname

        _domains = domains
        if "all-domains" in domains:
            _domains = appliance.domains

        for domain in _domains:
            logger.info("In domain {}".format(domain))
            if not web:
                print "\t", domain

            # Get a list of all certificates in this domain
            config = appliance.get_config("CryptoCertificate", domain=domain)
            certs = [x for x in config.xml.findall(datapower.CONFIG_XPATH)]

            # Filter out disabled objects because the results won't change,
            # but we will perform less network traffic
            certs = filter(
                lambda x: x.find("mAdminState").text == "enabled",
                certs)
            if not certs:
                continue

            # Create a directory structure $out_dir/hostname/domain
            dir_name = os.path.join(out_dir, appliance.hostname, domain)
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)

            for cert in certs:
                logger.info("Exporting cert {}".format(cert))

                # Get filename as it will appear locally
                filename = cert.find("Filename").text
                out_file = re.sub(r":[/]*", "/", filename)
                out_file = out_file.split("/")
                out_file = os.path.join(dir_name, *out_file)

                # extract directory name as it will appear locally
                _out_dir = out_file.split(os.path.sep)[:-1]
                _out_dir = os.path.join(*_out_dir)
                # Create the directory if it doesn't exist
                if not os.path.exists(_out_dir):
                    os.makedirs(_out_dir)

                name = cert.get("name")
                if not web:
                    print "\t\t", name
                export = appliance.CryptoExport(domain=domain,
                                                ObjectType="cert",
                                                ObjectName=name,
                                                OutputFilename=name)
                # TODO: Test export and handle failure
                logger.info("Finished exporting cert {}".format(cert))
                try:
                    logger.info(
                        "Retrieving file temporary:///{}".format(name))
                    cert = appliance.getfile(domain,
                                             "temporary:///{}".format(name))
                    logger.info(
                        "Finished retrieving file temporary:///{}".format(
                            name))
                    logger.info(
                        "Attempting to delete file temporary:///{}".format(
                            name))
                    appliance.DeleteFile(domain=domain,
                                         File="temporary:///{}".format(name))
                    logger.info(
                        "Finished deleting file temporary:///{}".format(name))
                except:
                    logger.exception("An unhandled exception has occurred")
                    if not web:
                        print "SKIPPING CERT"
                    continue
                cert = etree.fromstring(cert)
                with open(out_file, "w") as fout:
                    _contents = insert_newlines(cert.find("certificate").text)
                    contents = "{}\n{}\n{}\n".format(
                        "-----BEGIN CERTIFICATE-----",
                        _contents,
                        "-----END CERTIFICATE-----")
                    fout.write(contents)
    if web:
        return (util.render_see_download_table({k.hostname: "" for k in env.appliances},
                                              "export-certs"),
               util.render_history(env))


def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f))


class WebPlugin(Plugin):
    def __init__(self):
        self.route = partial(pf.handle, "crypto")
        self.route.__name__ = "crypto"
        self.html = partial(pf.html, "mast.datapower.crypto")
        update_wrapper(self.html, pf.html)

    def css(self):
        return get_data_file('plugin.css')

    def js(self):
        return get_data_file('plugin.js')

if __name__ == "__main__":
    try:
        cli.Run()
    except AttributeError, e:
        if "'NoneType' object has no attribute 'app'" in e:
            raise NotImplementedError(
                "HTML formatted output is not supported on the CLI")
