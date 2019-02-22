"""
mast backups:

A set of tools for automating routine backup/checkpoint
related tasks associated with IBM DataPower appliances.

Copyright 2016, All Rights Reserved
McIndi Solutions LLC
"""
import os
import flask
import zipfile
import commandr
from time import time, sleep
from mast.plugins.web import Plugin
from mast.datapower import datapower
from mast.timestamp import Timestamp
from pkg_resources import resource_string
from mast.logging import make_logger, logged
import mast.plugin_utils.plugin_utils as util
from functools import partial, update_wrapper
import mast.plugin_utils.plugin_functions as pf


class TimeoutError(Exception):
    pass


cli = commandr.Commandr()


@logged("mast.datapower.backups")
def _verify_zip(zip_file):
    if isinstance(zip_file, basestring):
        try:
            zip_file = zipfile.ZipFile(zip_file, "r")
        except zipfile.BadZipfile:
            return False
    if zip_file.testzip() is None:
        # if testzip returns None then there were no errors
        zip_file.close()
        return True
    return False


@logged("mast.datapower.backups")
def _create_dir(base_dir, hostname, timestamp):
    directory = os.path.join(base_dir, hostname, timestamp)
    os.makedirs(directory)
    return directory


# ~#~#~#~#~#~#~#
# backups/checkpoints
# ===================
#
# These functions are meant to work with the backups and checkpoints of
# the specified appliances
#
# current commands
# ----------------
# normal-backup - Performs a normal backup of the specified domains on
#                 the specified appliances
# secure-backup - Performs a secure backup of the specified appliances
# verify-secure-backup - Verifies a secure backup based on the checksums of
#                        the files in backupmanifest.xml
# set-checkpoint - Sets a checkpoint in the given domain on the
#                  given appliances


@logged("mast.datapower.backups")
@cli.command('restore-normal-backup', category='backups')
def restore_normal_backup(appliances=[],
                          credentials=[],
                          timeout=120,
                          no_check_hostname=False,
                          file_in=None,
                          Domain="",
                          source_type="ZIP",
                          overwrite_files=True,
                          overwrite_objects=True,
                          rewrite_local_ip=True,
                          deployment_policy=None,
                          import_domain=True,
                          reset_domain=True,
                          dry_run=False,
                          out_dir="tmp",
                          web=False):
    """Restores a normal backup to the specified appliances and Domains.

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
* `-f, --file-in`: The backup file which will be restored. This must be in the
format specified in source_type
* `-D, --Domain`: The domain to which to restore the backup
* `-s, --source-type`: The type of backup, must be either "ZIP" or "XML"
* `-N, --no-overwrite-files`: Whether to overwrite files when restoring
the backup
* `--no-overwrite-objects`: Whether to overwrite objects when restoring
the backup
* `--no-rewrite-local-ip`: Whether to rewrite the local IP Addresses
* `-d, --deployment-policy`: The deployment policy to apply when restoring
the backup
* `--no-import-domain`: Whether we are importing a domain
* `--no-reset-domain`: Whether to reset the domain
* `--dry-run`: Whether this should be a dry-run
* `-o, --out_dir`: (NOT NEEDED IN WEB GUI) The directory (local) where you would
want all of the files generated by the restore to be placed
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to restore normal backup on {} in {} domain".format(
            str(env.appliances), Domain))

    kwargs = {
        "file_in": file_in,
        "source_type": source_type,
        "domain": Domain,
        "overwrite_files": overwrite_files,
        "overwrite_objects": overwrite_objects,
        "rewrite_local_ip": rewrite_local_ip,
        "deployment_policy": deployment_policy,
        "import_domain": import_domain,
        "reset_domain": reset_domain,
        "dry_run": dry_run}

    resp = env.perform_action("restore_normal_backup", **kwargs)
    logger.debug("Responses received {}".format(str(resp)))

    out_dir = os.path.join(out_dir, "restore_normal_backup", t.timestamp)
    os.makedirs(out_dir)

    for host, r in resp.items():
        filename = os.path.join(out_dir, "{}-{}-{}-results.xml".format(
            t.timestamp,
            host,
            Domain))
        with open(filename, 'wb') as fout:
            fout.write(r.pretty)
    if web:
        return util.render_see_download_table(resp), util.render_history(env)


@logged("mast.datapower.backups")
@cli.command('normal-backup', category='backups')
def get_normal_backup(appliances=[],
                      credentials=[],
                      timeout=120,
                      no_check_hostname=False,
                      Domain=[],
                      comment="",
                      out_dir='tmp',
                      individual=False,
                      web=False):
    """Performs a normal backup of the specified domain.

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
* `-D, --Domain`: The domains to backup (all-domains will backup all domains)
To spcify multiple domains,
use multiple entries of the form `[-D domain1 [-D domain2...]]`
* `-C, --comment`: The comment to add to the backup
* `-o, --out-dir`: (NOT NEEDED IN WEB GUI) The directory (local) where you
would like to store the backup
* `-I, --individual`: If specified and all-domains is specified as --Domain
then backup each domain individually instead of "all-domains"
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    t = Timestamp()
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    if not Domain:
        raise ValueError("Must provide one or more domains including 'all-domains'")

    if isinstance(Domain, basestring):
        Domain = [Domain]
    # Fixes duplicate domains issue
    Domain = list(set(Domain))

    results = {}
    if not individual:
        logger.info(
            "Attempting to retrieve normal backup from "
            "{} in {} domain".format(str(env.appliances), Domain))
        kwargs = {'domains': Domain, 'comment': comment}
        _results = env.perform_async_action('get_normal_backup', **kwargs)
        logger.debug("backups retrieved, check file for contents")

        for hostname, backup in _results.items():
            directory = os.path.join(
                out_dir,
                hostname,
                "NormalBackup",
                t.timestamp)
            os.makedirs(directory)
            filename = os.path.join(
                directory,
                '%s-%s-%s.zip' % (
                    t.timestamp,
                    hostname,
                    "_".join(Domain)))

            logger.debug(
                "Writing backup for {} to {}".format(
                    hostname, filename))
            with open(filename, 'wb') as fout:
                fout.write(backup)

            if _verify_zip(filename):
                logger.info(
                    "backup for {} in {} domain verified".format(
                        hostname, str(Domain)))
                results[hostname + "-" + "_".join(Domain) + "-normalBackup"] = "Verified"
            else:
                logger.info(
                    "backup for {} in {} domain corrupt".format(
                        hostname, str(Domain)))
                results[hostname + "-" + "_".join(Domain) + "-normalBackup"] = "Corrupt"
    else:
        for domain in Domain:
            logger.info(
                "Attempting to retrieve normal backup from "
                "{} in {} domain".format(str(env.appliances), domain))
            kwargs = {'domains': domain, 'comment': comment}
            _results = env.perform_async_action('get_normal_backup', **kwargs)
            logger.debug("backups retrieved, check file for contents")

            for hostname, backup in _results.items():
                directory = os.path.join(
                    out_dir,
                    hostname,
                    "NormalBackup",
                    t.timestamp)
                if not os.path.exists(directory):
                    os.makedirs(directory)
                filename = os.path.join(
                    directory,
                    '%s-%s-%s.zip' % (
                        t.timestamp,
                        hostname,
                        domain))

                logger.debug(
                    "Writing backup for {} to {}".format(
                        hostname, filename))
                with open(filename, 'wb') as fout:
                    fout.write(backup)

                if _verify_zip(filename):
                    logger.info(
                        "backup for {} in {} domain verified".format(
                            hostname, domain))
                    results[hostname + "-" + domain + "-normalBackup"] = "Verified"
                else:
                    logger.info(
                        "backup for {} in {} domain corrupt".format(
                            hostname, domain))
                    results[hostname + "-" + domain + "-normalBackup"] = "Corrupt"

    if web:
        return util.render_results_table(results), util.render_history(env)

    for k, v in results.items():
        print
        print k
        print '=' * len(k)
        print v
        print


@logged("mast.datapower.backups")
@cli.command('secure-backup', category='backups')
def get_secure_backup(appliances=[],
                      credentials=[],
                      timeout=1200,
                      no_check_hostname=False,
                      out_dir='tmp',
                      CryptoCertificate="",
                      destination='local:/raid0',
                      include_iscsi=False,
                      include_raid=False,
                      remove=True,
                      quiesce_before=True,
                      unquiesce_after=True,
                      quiesce_timeout=60,
                      web=False):
    """Performs a secure backup of the specified domain.

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
* `-o, --out-dir`: (NOT NEEDED IN WEB GUI) The directory (local) to store
the backup
* `-C, --CryptoCertificate`: The CryptoCertificate object to use to encrypt
the backup
* `-d, --destination`: The base location (on the appliance) to store
the backup
* `-i, --include-iscsi`: Whether to include the iscsi filesystem
* `-I, --include-raid`: Whether to include the RAID filesystem
* `-N, --no-remove`: If specified the backup will NOT be removed from
the DataPower
* `--no-quiesce-before`: If specified, the appliance will not be
quiesced before performing the secure backup
* `--no-unquiesce-after`: If specified, the appliance will not be
unquiesced after performing the secure backup
* `-q, --quiesce-timeout`: The timeout to wait before the appliance
attempts to quiesce
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    output = ""

    if quiesce_before:
        resp = {}
        for appliance in env.appliances:
            logger.info(
                "Quiescing {} in preparation of Secure Backup".format(
                    appliance.hostname))
            resp[appliance.hostname] = appliance.QuiesceDP(
                timeout=quiesce_timeout)
            logger.debug(
                "Response received {}".format(resp[appliance.hostname]))
            if web:
                output += util.render_boolean_results_table(
                    resp, suffix="Quiesce_appliance")
        sleep(quiesce_timeout)

    t = Timestamp()
    if destination.endswith("/"):
        destination = destination.rstrip("/")
    destination = '%s/%s' % (destination, t.timestamp)

    kwargs = {'Dir': destination, 'domain': 'default'}

    logger.info(
        "Creating directory {} on {} to store Secure Backup".format(
            destination, str(env.appliances)))
    resp = env.perform_async_action('CreateDir', **kwargs)
    logger.debug("Responses received {}".format(str(resp)))

    if web:
        output += util.render_boolean_results_table(resp, suffix="CreateDir")

    include_raid = 'on' if include_raid else 'off'
    include_iscsi = 'on' if include_iscsi else 'off'

    kwargs = {
        'cert': CryptoCertificate,
        'destination': destination,
        'include_iscsi': include_iscsi,
        'include_raid': include_raid}
    logger.info(
        "Attempting to perform a Secure Backup on {}".format(
            str(env.appliances)))
    resp = env.perform_async_action('SecureBackup', **kwargs)
    logger.debug("Responses received: {}".format(str(resp)))

    if web:
        output += util.render_boolean_results_table(
            resp, suffix="SecureBackup")

    if web:
        results = {}
        remove_results = {}
    for appliance in env.appliances:
        directory = os.path.join(
            out_dir,
            appliance.hostname,
            "SecureBackup",
            t.timestamp)

        start = time()
        while not appliance.file_exists(
                '{}/backupmanifest.xml'.format(
                    destination),
                'default'):
                sleep(5)
                if time() - start > timeout:
                    raise TimeoutError

        logger.info(
            "Attempting to retrieve Secure Backup from {}".format(
                appliance.hostname))
        appliance.copy_directory(
            destination,
            directory)

        _directory = os.path.join(
            directory, destination.replace(":", "").replace("///", "/"))

        try:
            logger.info(
                "Attempting to verify Secure Backup for {}".format(
                    appliance.hostname))
            if appliance.verify_local_backup(_directory):
                logger.info(
                    "Secure Backup integrity verified for {}".format(
                        appliance.hostname))
                if web:
                    results[appliance.hostname] = "Succeeded"
                else:
                    print '\t', appliance.hostname, " - ", "Succeeded"
                if remove:
                    logger.info(
                        "Attempting to remove Secure Backup from appliance "
                        "{}".format(
                            appliance.hostname))
                    _resp = appliance.RemoveDir(
                        Dir=destination, domain='default')
                    logger.debug("Response received: {}".format(_resp))
                    if web:
                        remove_results[appliance.hostname] = _resp
            else:
                logger.warn(
                    "Secure Backup for {} Corrupt!".format(
                        appliance.hostname))
                if web:
                    results[appliance.hostname] = "Failed"
                else:
                    print '\t', appliance.hostname, " - ", "Failed"
                appliance.log_error(
                    'Verification of backup in %s failed' % (_directory))
        except:
            if web:
                results[appliance.hostname] = "Failed"
            logger.exception(
                "An unhandled exception occurred during execution.")
    if web:
        output += util.render_results_table(
            results, suffix="verify-SecureBackup")
        output += util.render_boolean_results_table(
            remove_results, suffix="RemoveDir")

    if unquiesce_after:
        resp = {}
        for appliance in env.appliances:
            logger.info(
                "Attempting to unquiesce {}".format(
                    str(appliance.hostname)))
            resp[appliance.hostname] = appliance.UnquiesceDP()
            logger.debug(
                "Response received: {}".format(
                    resp[appliance.hostname]))
            if web:
                output += util.render_boolean_results_table(
                    resp, suffix="Unquiesce_appliance")

    if web:
        return output, util.render_history(env)


@logged("mast.datapower.backups")
@cli.command('restore-secure-backup', category='backups')
def restore_secure_backup(appliances=[],
                          credentials=[],
                          timeout=1200,
                          no_check_hostname=False,
                          CryptoCertificate="",
                          location="",
                          validate_only=False,
                          web=False):
    """Restores a secure backup to the specified appliances.

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
* `-C, --CryptoCertificate`: The CryptoCertificate object with which
the secure backup was encrypted
* `-l, --location`: The location on the appliances where the SecureBackup
resides (This means that you will have to upload the secure backup
if you got it from MAST, external to the appliance)
* `-v, --validate-only`: If specified then the appliances will only attemp to
validate the backup instead of actually restoring it
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to restore Secure Backup on {}".format(
            str(env.appliances)))

    validate = "on" if validate_only else "off"

    kwargs = {"cred": CryptoCertificate,
              "source": location,
              "validate": validate}
    resp = env.perform_action("SecureRestore", **kwargs)
    logger.debug("Responses received: {}".format(str(resp)))

    if web:
        return (util.render_boolean_results_table(resp),
                util.render_history(env))

    for host, msg in resp.items():
        print host, '\n', "=" * len(host)
        print msg
        print


@logged("mast.datapower.backups")
@cli.command('list-checkpoints', category='checkpoints')
def list_checkpoints(appliances=[],
                     credentials=[],
                     timeout=120,
                     no_check_hostname=False,
                     Domain="",
                     web=False):
    """Lists the checkpoints which are currently in the
    specified domain

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
* `-D, --Domain`: The domain to list the checkpoints for
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to list checkpoints for {} in {} domain".format(
            str(env.appliances), Domain))

    resp = env.perform_action("get_existing_checkpoints", domain=Domain)
    logger.debug("Responses received: {}".format(str(resp)))
    if web:
        return (util.web_list_checkpoints(resp, Domain),
                util.render_history(env))

    for host, d in resp.items():
        print host, '\n', '=' * len(host)
        for key, value in d.items():
            print key, "-".join(value["date"]), ":".join(value["time"])
        print


@logged("mast.datapower.backups")
@cli.command('remove-checkpoint', category='checkpoints')
def remove_checkpoint(appliances=[],
                      credentials=[],
                      timeout=120,
                      no_check_hostname=False,
                      Domain="",
                      checkpoint_name="",
                      web=False):
    """Deletes a checkpoint from the specified domain

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
* `-D, --Domain`: The domain from which to delete the checkpoint
* `-C, --checkpoint-name`: The name of the checkpoint to remove
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to remove checkpoint {} from {} in {} domain".format(
            checkpoint_name,
            str(env.appliances),
            Domain))

    resp = env.perform_action(
        "RemoveCheckpoint", ChkName=checkpoint_name, domain=Domain)
    logger.debug("Responses received: {}".format(str(resp)))

    if web:
        return (util.render_boolean_results_table(resp),
                util.render_history(env))


@logged("mast.datapower.backups")
@cli.command('rollback-checkpoint', category='checkpoints')
def rollback_checkpoint(appliances=[],
                        credentials=[],
                        timeout=120,
                        no_check_hostname=False,
                        Domain="",
                        checkpoint_name="",
                        web=False):
    """Roll back the specified domain to the named checkpoint.

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
* `-D, --Domain`: The domain which to roll back
* `-C, --checkpoint_name`: The name of the checkpoint to roll back to
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to rollback checkpoint {} on {} in {} domain".format(
            checkpoint_name,
            str(env.appliances),
            Domain))

    resp = env.perform_action(
        "RollbackCheckpoint", ChkName=checkpoint_name, domain=Domain)
    logger.debug("Responses received: {}".format(str(resp)))

    if web:
        return (util.render_boolean_results_table(resp),
                util.render_history(env))


@logged("mast.datapower.backups")
@cli.command('set-checkpoint', category='checkpoints')
def set_checkpoint(appliances=[],
                   credentials=[],
                   timeout=120,
                   no_check_hostname=False,
                   Domain=['default'],
                   comment='',
                   remove_oldest=True,
                   web=False):
    """Sets a checkpoint in the given domains on the specified appliances

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
* `-D, --Domain`: Domains to set checkpoints in. To spcify multiple domains,
use multiple entries of the form `[-D domain1 [-D domain2...]]`
* `-C, --comment`: The comment to use for the checkpoint (will also be used to
build the checkpoint name)
* `-N, --no-remove-oldest`: If specified this script will attempt to
remove the oldest checkpoint __IF__ the maximum number of checkpoints exist
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.backups")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    logger.info(
        "Attempting to set checkpoint on {} in {} domain(s)".format(
            str(env.appliances),
            str(Domain)))

    t = Timestamp()

    if web:
        header_row = ("Appliance", "Result")
        rows = []

    for appliance in env.appliances:
        if not web:
            print appliance.hostname
        _domains = Domain
        print Domain
        print _domains
        if "all-domains" in _domains:
            _domains = appliance.domains
        print _domains
        for domain in _domains:
            print domain
            if not web:
                print "\t", domain
            name = '{0}-{1}-{2}'.format(comment, domain, t.timestamp)
            logger.debug(
                "Attempting to set checkpoint {} on {} in {} domain".format(
                    name,
                    appliance,
                    domain))
            if remove_oldest:
                _max = appliance.max_checkpoints(domain)
                if len(appliance.get_existing_checkpoints(domain)) >= _max:
                    logger.info(
                        "Maximum number of checkpoints for domain "
                        "{} on {} reached. Removing oldest checkpoint.".format(
                            domain, appliance.hostname))
                    _resp = appliance.remove_oldest_checkpoint(domain)
                    logger.debug("Response received: {}".format(_resp))
            kwargs = {'domain': domain, 'ChkName': name}
            resp = appliance.SaveCheckpoint(**kwargs)
            logger.debug("Response received: {}".format(resp))
            if not web:
                if resp:
                    print "\t\tSuccessful"
                else:
                    print "\t\tFailed"
            if web:
                if resp:
                    rows.append((
                        "{}-{}-set_checkpoint".format(
                            appliance.hostname, domain),
                        "Succeeded"))
                else:
                    rows.append((
                        "{}-{}-set_checkpoint".format(
                            appliance.hostname, domain),
                        "Failed"))
    if web:
        return flask.render_template(
            "results_table.html",
            header_row=header_row,
            rows=rows), util.render_history(env)
#
# ~#~#~#~#~#~#~#


def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f))


class WebPlugin(Plugin):
    def __init__(self):
        self.route = partial(pf.handle, "backups")
        self.route.__name__ = "backups"
        self.html = partial(pf.html, "mast.datapower.backups")
        update_wrapper(self.html, pf.html)

    def css(self):
        return get_data_file('plugin.css')

    def js(self):
        return get_data_file('plugin.js')


if __name__ == '__main__':
    try:
        cli.Run()
    except AttributeError, e:
        if "'NoneType' object has no attribute 'app'" in e:
            raise NotImplementedError(
                "HTML formatted output is not supported on the CLI")
