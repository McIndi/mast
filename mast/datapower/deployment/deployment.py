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
mast deployment

A set of utilities which can simplify, automate and audit
your DataPower service deployments and migrations.
"""
import os
import sys
import flask
import subprocess
from time import sleep
from mast.cli import Cli
from collections import OrderedDict
from mast.datapower import datapower
from mast.datapower.deployment.git_deploy import git_deploy
from mast.plugin_utils.plugin_utils import render_results_table, render_history
from mast.plugins.web import Plugin
from mast.timestamp import Timestamp
from pkg_resources import resource_string
from mast.logging import make_logger, logged
from functools import partial, update_wrapper
import mast.plugin_utils.plugin_utils as util
import mast.plugin_utils.plugin_functions as pf

cli = Cli()


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
    return stdout, stderr


@logged('mast.datapower.deployment')
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

* `-a, --appliances`: The hostname(s), ip address(es), environment name(s)
or alias(es) of the appliances you would like to affect. For details
on configuring environments please see the comments in
`environments.conf` located in `$MAST_HOME/etc/default`. For details
on configuring aliases, please see the comments in
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
* `-d, --destination`: Should be the path and filename of the file
once uploaded to the DataPower **NOTE: file_out should contain
the filename ie. local:/test.txt**
* `-D, --Domain`: The domain to which to upload the file,
* `-N, --no-overwrite`: If specified this program will exit with an
error rather than overwrite a file
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


@logged('mast.datapower.deployment')
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


@logged('mast.datapower.deployment')
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
    """Deletes a file from the specified appliances

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
* `-D, --Domain`: The domain from which to delete the file
* `-f, --filename`: The name of the file (on DataPower) you would
like to delete
* `-b, --backup`: Whether to backup the file before deleting
* `-o, --out-dir`: (NOT NEEDED IN THE WEB GUI)The directory you would like to
save the file to
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
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


@logged('mast.datapower.deployment')
@cli.command('clean-up', category='maintenance')
def clean_up(appliances=[],
             credentials=[],
             timeout=120,
             no_check_hostname=False,
             Domain='default',
             checkpoints=False,
             export=False,
             error_reports=False,
             recursive=False,
             logtemp=False,
             logstore=False,
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
* `-D, --Domain`: The domain who's filesystem you would like to clean up
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
        if error_reports:
            _clean_error_reports(
                appliance, Domain,
                backup_files, t.timestamp,
                out_dir)
            rows.append(("", "ErrorReports", "Cleaned"))
    return flask.render_template(
        "results_table.html",
        header_row=["Appliance", "Location", "Action"],
        rows=rows), util.render_history(env)


@logged('mast.datapower.deployment')
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
                file,
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


@logged('mast.datapower.deployment')
def _clean_error_reports(appliance, domain, backup, timestamp, out_dir):
    if backup:
        local_dir = os.path.join(
            out_dir,
            appliance.hostname,
            timestamp,
            domain,
            'temporary')
        os.makedirs(local_dir)
    files = appliance.ls(
        'temporary:/',
        domain=domain,
        include_directories=False)
    files = [f for f in files if 'error-report' in f]
    for _file in files:
        filename = 'temporary:/{}'.format(_file)
        if backup:
            fout = open(os.path.join(local_dir, _file), 'wb')
            contents = appliance.getfile(domain, filename)
            fout.write(contents)
            fout.close
        appliance.DeleteFile(domain=domain, File=filename)


@logged('mast.datapower.deployment')
@cli.command('predeploy', category='deployment')
def predeploy(
        appliances=[],
        credentials=[],
        timeout=120,
        no_check_hostname=False,
        out_dir="tmp",
        Domain="",
        comment="",
        predeploy_command=None,
        CryptoCertificate="",
        secure_backup_destination="local:/raid0",
        backup_default=True,
        backup_all=True,
        do_secure_backup=False,
        do_normal_backup=True,
        set_checkpoints=True,
        include_iscsi=False,
        include_raid=False,
        remove_secure_backup=True,
        default_checkpoint=True,
        remove_oldest_checkpoint=True,
        allow_shell=False,
        web=False):
    """Perform routine pre-deployment actions. Everything is optional, but if
you wish to perform an action, you must provide the necessary arguments.

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
* `-o, --out-dir`: (Not needed in web GUI) The directory (local)
where you would like to store the artifacts generated by this
script
* `-D, --Domain`: This is the app domain to backup and the app domain
in which to set a checkpoint
* `-C, --comment`: This is shared among other actions. The comment is
used to build the name of the checkpoint.
* `-p, --predeploy-command`: This command will be "shelled out"
to the machine running MAST after performing the backups and checkpoints.
Use this parameter to pull from version control or similar
operations.
* `--CryptoCertificate`: The CryptoCertificate with which to
encrypt the secure backup
* `-s, --secure-backup-destination`: The destination (on the DataPower)
where the secure backup will be stored
* `-N, --no-backup-default`: Whether to also backup the default domain
* `--no-backup-all`: Whether to also backup all-domains
* `-d, --do-secure-backup`: Whether to retrieve a secure backup
* `--no-do-normal-backup`: Whether to retrieve normal backups
* `--no-set-checkpoints`: Whether to set checkpoints
* `-i, --include-iscsi`: Whether to include the iscsi volume in the
secure backup
* `-I, --include-raid`: Whether to include the raid volume in the
secure backup
* `--no-remove-secure-backup`: Whether to remove the secure backup
from the appliance after verifying your local copy.
* `--no-default-checkpoint`: Whether to create a checkpoint in the
default domain
* `--no-remove-oldest-checkpoint`: Whether to remove the oldest
checkpoint from the domain IF AND ONLY IF the maximum number
of checkpoints has been reached.
* `-A, --allow-shell`: Whether to allocate a shell for the execution of
the predeploy-command
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__

Here is what is possible (will be done in this order):

1. Secure Backup
    * The following parameters apply:
        * `-d, --do-secure-backup`
        * `-o, --out-dir`
        * `--CryptoCertificate`
        * `-s, --secure-backup-destination`
        * `-i, --include-iscsi`
        * `-I, --include-raid`
        * `--no-remove-secure-backup`
2. Normal Backups
    * The following parameters apply:
        * `--no-do-normal-backup`
        * `-o, --out-dir`
        * `-D, --Domain`
        * `-N, --no-backup-default`
        * `--no-backup-all`
        * `-C, --comment`
3. Checkpoints
    * The following parameters apply:
        * `--no-set-checkpoints`
        * `-D, --Domain`
        * `-C, --comment`
        * `--no-default-checkpoint`
        * `--no-remove-oldest-checkpoint`"""
    from mast.datapower.backups import set_checkpoint
    from mast.datapower.backups import get_normal_backup, get_secure_backup

    logger = make_logger('mast.datapower.deployment')
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    if web:
        output = ""
        history = ""

    # Loop through appliances so we will only affect one appliance at a time
    for appliance in env.appliances:

        # Secure Backup
        if do_secure_backup:
            if not CryptoCertificate:
                # Fail if CryptoCertificate is not given
                logger.error(
                    "Cert must be specified in order "
                    "to perform a secure backup!")
                sys.exit(-1)

            logger.info("Starting Secure Backup for {}".format(
                appliance.hostname))

            _out = get_secure_backup(
                appliances=appliance.hostname,
                credentials=appliance.credentials,
                timeout=timeout,
                out_dir=out_dir,
                CryptoCertificate=CryptoCertificate,
                destination=secure_backup_destination,
                include_iscsi=include_iscsi,
                include_raid=include_raid,
                remove=remove_secure_backup,
                quiesce_before=False,
                unquiesce_after=False,
                no_check_hostname=no_check_hostname,
                web=web)

            if web:
                output += _out[0]
                history += _out[1]

            logger.info("Finished Secure Backup for {}".format(
                appliance.hostname))

        # Normal backups
        if do_normal_backup:
            logger.info(
                "Pre-Deployment backups started at {}".format(
                    str(Timestamp())))

            domains = [Domain]
            if backup_default:
                domains.append("default")
            if backup_all:
                domains.append("all-domains")

            _out = get_normal_backup(
                appliances=[appliance.hostname],
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=domains,
                comment=comment,
                out_dir=out_dir,
                web=web)

            logger.info(
                "Pre-Deployment backups finished at {}".format(
                    str(Timestamp())))

            if web:
                output += _out[0]
                history += _out[1]

        # Checkpoints
        if set_checkpoints:
            logger.info(
                "Pre-Deployment checkpoints started at {}".format(
                    str(Timestamp())))

            domains = [Domain]
            if default_checkpoint:
                domains.append("default")

            _out = set_checkpoint(
                appliances=[appliance.hostname],
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=domains,
                comment=comment,
                remove_oldest=remove_oldest_checkpoint,
                web=web)

            logger.info(
                "Pre-Deployment checkpoints finished at {}".format(
                    str(Timestamp())))

            if web:
                output += _out[0]
                history += _out[1]

    if predeploy_command:
        logger.info(
            "Pre-Deployment command '{}' found. Executing at {}".format(
                predeploy_command, str(Timestamp())))

        out, err = system_call(command=predeploy_command, shell=allow_shell)
        out = str(out)
        err = str(err)

        logger.info(
            "finished executing Pre-Deployment command '{}' at {}., output: {}".format(
                predeploy_command, str(Timestamp()), ";".join([out, err])))
        if web:
            from mast.plugin_utils.plugin_utils import render_results_table
            results = {"predeploy command": "{}\n\nout: {}\n\nerr: {}".format(predeploy_command, out, err)}
            output += render_results_table(results)
        else:
            print("Finished running pre-deploy command. output: {}".format(
                ";".join([out, err])))

    if web:
        return output, history


@logged('mast.datapower.deployment')
@cli.command('deploy', category='deployment')
def deploy(
        appliances=[],
        credentials=[],
        timeout=180,
        no_check_hostname=False,
        Domain=[],
        file_in=None,
        deployment_policy="",
        dry_run=False,
        overwrite_files=True,
        overwrite_objects=True,
        rewrite_local_ip=True,
        object_audit=True,
        out_dir='tmp',
        format='ZIP',
        quiesce_domain=True,
        quiesce_appliance=False,
        quiesce_timeout=120,
        web=False):

    """Perform a deployment/migration of a service/object to an IBM DataPower
appliance. This script will try to perform the deployment/migration in a
manner consistent with best practices.

__WARNING__: There is an inherent security risk involved in this script,
in order to allow the most flexible integration with various
Version Control Systems possible, we allow a pre-deployment
hook and a post-deployment hook which will be "shelled out"
to your operating system. For this reason PLEASE be sure to
run this script (and the MAST Web GUI server) as a user with
appropriate permissions.

DO NOT RUN AS ROOT!!!

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
* `-D, --Domain`: The domain to import the configuration into, also the
domain to quiesce if `--no-quiesce-domain` is not specified.
* `-f, --file-in`: This is the configuration file that you are
importing. It must be in the format specified by the format
parameter.
* `-d, --deployment-policy`: The deployment policy to apply to the
import, must already exist on the appliance
* `--dry-run`: If specified, a dry-run will be performed instead of
an actual import
* `-N, --no-overwrite-files`: If specified, no files will be over-
written during the import
* `--no-overwrite-objects`: If specified, no objects will be over-
written during import
* `--no-rewrite-local-ip`: If specified local ip addresses will not
be rewritten on import
* `--no-object-audit`: If specified, an object audit will not be
performed. An object audit is  a diff between the running and
persisted configuration
* `-o, --out-dir`: This is where to place the artifacts generated
by this script
* `-F, --format`: The format of the configuration file, must be
either "ZIP" or "XML".
* `--no-quiesce-domain`: If specified, the domain will not be quiesced
prior to the deployment.
* `-q, --quiesce-appliance`: If specified, the appliance will be
quiesced prior to the deployment
* `-Q, --quiesce-timeout`: This is the amount of time for the appliance
to wait before beginning the quiescence procedure.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    import mast.datapower.system as system
    from mast.datapower.developer import _import

    logger = make_logger('mast.datapower.deployment')
    if web:
        output = ""
        history = ""

    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    for appliance in env.appliances:
        appliance.log_info("Deployment started on {}".format(
            appliance.hostname))

        # Quiesce Domain
        if quiesce_domain:
            logger.info(
                "Quiescing domain {} before deployment at {}".format(
                    Domain, str(Timestamp())))

            _out = system.quiesce_domain(
                appliances=[appliance.hostname],
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=Domain,
                quiesce_timeout=quiesce_timeout,
                web=web)

            logger.info(
                "Finished quiescing domain {} before deployment at {}".format(
                    Domain, str(Timestamp())))

            sleep(quiesce_timeout)

            if web:
                output += _out[0]
                history += _out[1]

        # Quiesce Appliance
        if quiesce_appliance:
            logger.info(
                "Quiescing appliances before deployment at {}".format(
                    str(Timestamp())))

            _out = system.quiesce_appliance(
                appliances=appliance.hostname,
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                quiesce_timeout=quiesce_timeout,
                web=web)

            logger.info(
                "Finished quiescing appliances before deployment at {}".format(
                    str(Timestamp())))

            sleep(quiesce_timeout)

            if web:
                output += _out[0]
                history += _out[1]

        appliance.log_info("Attempting to import configuration at '{}'".format(
            str(Timestamp())))

        file_out = os.path.join(
            out_dir, '{}-deployment_results.txt'.format(appliance.hostname))

        # import configuration
        _out = _import(
            appliances=[appliance.hostname],
            credentials=credentials,
            timeout=timeout,
            no_check_hostname=no_check_hostname,
            Domain=Domain,
            file_in=file_in,
            deployment_policy=deployment_policy,
            dry_run=dry_run,
            overwrite_files=overwrite_files,
            overwrite_objects=overwrite_objects,
            rewrite_local_ip=rewrite_local_ip,
            source_type=format,
            out_dir=out_dir,
            web=web)


        if web:
            output += _out[0]
            history += _out[1]

        appliance.log_info("Finished importing configuration at {}".format(
            str(Timestamp())))

        # unquiesce domain
        if quiesce_domain:
            appliance.log_info("Attempting to unquiesce domain")

            _out = system.unquiesce_domain(
                appliances=[appliance.hostname],
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=Domain,
                web=web)

            appliance.log_info("Finished unquiescing domain")

            if web:
                output += _out[0]
                history += _out[1]

        # unquiesce appliance
        if quiesce_appliance:
            logger.info(
                "Quiescing appliances before deployment at {}".format(
                    str(Timestamp())))

            _out = system.unquiesce_appliance(
                appliances=[appliance.hostname],
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                web=web)

            logger.info(
                "Finished quiescing appliances before deployment at {}".format(
                    str(Timestamp())))

            if web:
                output += _out[0]
                history += _out[1]

        if object_audit:
            appliance.log_info(
                "Post-Deployment Object audit started at {}".format(
                    str(Timestamp())))

            _out = system.objects_audit(
                appliances=[appliance.hostname],
                credentials=credentials,
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                out_dir=out_dir,
                web=web)

            appliance.log_info(
                "Post-Deployment Object audit finished at {}".format(
                    str(Timestamp())))

            if web:
                output += _out[0]
                history += _out[1]

    if web:
        return output, history


@logged('mast.datapower.deployment')
@cli.command('postdeploy', category='deployment')
def postdeploy(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               Domain="",
               unquiesce_domain=True,
               unquiesce_appliance=False,
               postdeploy_command=None,
               save_config=True,
               web=False):
    """This is a simple script which will allow you to unquiesce
your domain or appliances after you quiesce them for a deployment.
Also this will allow you to save the config.

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
* `-D, --Domain`: The domain which will be unquiesced and persisted.
* `-N, --no-unquiesce-domain`: If specified, this script will not attempt
to unquiesce the domain
* `-u, --unquiesce-appliance`: If specified, this script will attempt to
unquiesce the appliance
* `-p, --postdeploy-command`: This command will be "shelled out"
to the machine running MAST after unquiescing and saving the configuration,
use this parameter to clean up VCS artifacts and/or perform check-outs
of your deployed services or similar operations
* `--no-save-config`: If specified, the configuration will not be saved in
the application domain
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    import mast.datapower.system as system
    check_hostname = not no_check_hostname
    logger = make_logger('mast.datapower.deployment')

    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    if web:
        output = ""
        history = ""
    for appliance in env.appliances:
        if unquiesce_appliance:
            appliance.log_info("Attempting to unquiesce appliance")

            _out = system.unquiesce_appliance(
                appliances=[appliance.hostname],
                credentials=[appliance.credentials],
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                web=web)
            appliance.log_info(
                "Finished Unquiescing appliance")

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("Finished unquiescing appliance")

        if unquiesce_domain:
            appliance.log_info("Attempting to unquiesce domain")

            _out = system.unquiesce_domain(
                appliances=[appliance.hostname],
                credentials=[appliance.credentials],
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=Domain,
                web=web)
            appliance.log_info(
                "Finished Unquiescing domain")

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("Finished unquiescing domain")

        if save_config:
            appliance.log_info(
                "Attempting to save configuration after deployment")

            _out = system.save_config(
                appliances=[appliance.hostname],
                credentials=[appliance.credentials],
                timeout=timeout,
                no_check_hostname=no_check_hostname,
                Domain=Domain,
                web=web)

            appliance.log_info(
                "Finished saving configuration after deployment")

            if web:
                output += _out[0]
                history += _out[1]
            else:
                print("Finished saving the configuration")

    if postdeploy_command:
        logger.info(
            "Post-Deployment command '{}' found. Executing at {}".format(
                postdeploy_command, str(Timestamp())))

        out, err = system_call(command=postdeploy_command)
        out = str(out)
        err = str(err)

        logger.info(
            "finished executing Post-Deployment command '{}' at {}., output: {}".format(
                postdeploy_command, str(Timestamp()), ";".join([out, err])))
        if web:
            results = {"postdeploy command": "{}\n\nout: {}\n\nerr: {}".format(postdeploy_command, out, err)}
            output += render_results_table(results)
        else:
            print("Finished running post-deploy command. output: {}".format(
                ";".join([out, err])))

    if web:
        return output, history

def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f)).decode()


cli.command('git-deploy', category='deployment')(git_deploy)

@logged('mast.datapower.deployment')
@cli.command('add-password-map-alias', category='password map aliases')
def add_password_map_alias(
    appliances=[],
    credentials=[],
    timeout=120,
    no_check_hostname=False,
    Domain="",
    alias_name="",
    password="",
    save_config=True,
    web=False,
    ):
    """create a password map alias on the specified appliances

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
* `-A, --alias-name`: The name to use for the password map alias
* `-P, --Password`: The password to use for the password map alias
* `-N, --no-save-config`: If specified, the configuration of the domain will be
persisted
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    logger = make_logger('mast.datapower.deployment')

    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname
    )

    if web:
        output = OrderedDict()
    for appliance in env.appliances:
        if not web:
            print((appliance.hostname))
            print("\tAttempting to add Password Map Alias")
        response = appliance.AddPasswordMap(
            domain=Domain,
            AliasName=alias_name,
            Password=password,
        )
        logger.info(repr(response))
        if web:
            output["{}-{}".format(appliance.hostname, "AddPasswordMapAlias")] = "\n".join(
                response.xml.find(
                    ".//{http://www.datapower.com/schemas/management}result"
                ).itertext()
            )
        else:
            print((
                "\t\t{}".format(
                    "\n\t\t".join(
                        response.xml.find(
                            ".//{http://www.datapower.com/schemas/management}result"
                        ).itertext()
                    ).strip()
                )
            ))
        if save_config and response:
            if not web:
                print("\tSaving Configuration")
            response = appliance.SaveConfig(domain=Domain)
            logger.info(repr(response))
            if web:
                output["{}-{}".format(appliance.hostname, "SaveConfig")] = "\n".join(
                    response.xml.find(
                        ".//{http://www.datapower.com/schemas/management}result"
                    ).itertext()
                )
            else:
                print((
                    "\t\t{}".format(
                        "\n\t\t".join(
                            response.xml.find(
                                ".//{http://www.datapower.com/schemas/management}result"
                            ).itertext()
                        ).strip()
                    )
                ))
    if web:
        return (
            render_results_table(output),
            render_history(env),
        )

@logged('mast.datapower.deployment')
@cli.command('del-password-map-alias', category='password map aliases')
def del_password_map_alias(
    appliances=[],
    credentials=[],
    timeout=120,
    no_check_hostname=False,
    Domain="",
    alias_name="",
    save_config=True,
    web=False,
    ):
    """delete a password map alias on the specified appliances

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
* `-A, --alias-name`: The name of the password map alias to delete
* `-N, --no-save-config`: If specified, the configuration of the domain will be
persisted
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    check_hostname = not no_check_hostname
    logger = make_logger('mast.datapower.deployment')

    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname
    )

    if web:
        output = OrderedDict()
    for appliance in env.appliances:
        if not web:
            print((appliance.hostname))
            print("\tAttempting to remove Password Map Alias")
        response = appliance.DeletePasswordMap(
            domain=Domain,
            AliasName=alias_name,
        )
        logger.info(repr(response))
        if web:
            output["{}-{}".format(appliance.hostname, "DeletePasswordMapAlias")] = "\n".join(
                response.xml.find(
                    ".//{http://www.datapower.com/schemas/management}result"
                ).itertext()
            )
        else:
            print((
                "\t\t{}".format(
                    "\n\t\t".join(
                        response.xml.find(
                            ".//{http://www.datapower.com/schemas/management}result"
                        ).itertext()
                    ).strip()
                )
            ))
        if save_config and response:
            if not web:
                print("\tSaving Configuration")
            response = appliance.SaveConfig(domain=Domain)
            logger.info(repr(response))
            if web:
                output["{}-{}".format(appliance.hostname, "SaveConfig")] = "\n".join(
                    response.xml.find(
                        ".//{http://www.datapower.com/schemas/management}result"
                    ).itertext()
                )
            else:
                print((
                    "\t\t{}".format(
                        "\n\t\t".join(
                            response.xml.find(
                                ".//{http://www.datapower.com/schemas/management}result"
                            ).itertext()
                        ).strip()
                    )
                ))
    if web:
        return (
            render_results_table(output),
            render_history(env),
        )

class WebPlugin(Plugin):
    def __init__(self):
        self.route = partial(pf.handle, "deployment")
        self.route.__name__ = "deployment"
        self.html = partial(pf.html, "mast.datapower.deployment")
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
    except ImportError as e:
        if "No module named backups" in e:
            raise NotImplementedError(
                "HTML formatted output is not supported on the CLI")
