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
mast accounts:

A set of tools for automating routine user/group
administration tasks associated with IBM DataPower
appliances.
"""
from mast.cli import Cli
from mast.plugins.web import Plugin
from mast.datapower import datapower
from pkg_resources import resource_string
from mast.logging import make_logger, logged
import mast.plugin_utils.plugin_utils as util
from functools import partial, update_wrapper
import mast.plugin_utils.plugin_functions as pf
from mast.pprint import pprint_xml

cli = Cli()


@logged("mast.datapower.accounts")
@cli.command('list-groups', category='users/groups')
def list_groups(appliances=[],
                credentials=[],
                timeout=120,
                no_check_hostname=False,
                web=False):
    """Display a list of all configured user groups on the specified
appliances, along with a list of the groups common to all
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
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""

    logger = make_logger("mast.accounts")

    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances, credentials, timeout, check_hostname=check_hostname)

    if web:
        return util.web_list_groups(env), util.render_history(env)

    sets = []
    for appliance in env.appliances:
        groups = appliance.groups
        logger.info(
            "Groups {} found for appliance {}".format(
                str(groups), appliance.hostname))
        sets.append(set(groups))

    for index, appliance in enumerate(env.appliances):
        print('\n', appliance.hostname)
        print('=' * len(appliance.hostname))
        for group in sets[index]:
            print('\t', group)

    common = sets[0].intersection(*sets[1:])
    logger.debug("Common Groups found {}".format(str(common)))
    print('\nCommon')
    print('======')
    for group in common:
        print('\t', group)


@logged("mast.datapower.accounts")
@cli.command('add-group', category='users/groups')
def add_group(appliances=[],
              credentials=[],
              timeout=120,
              no_check_hostname=False,
              save_config=False,
              name=None,
              access_policies=[],
              web=False):
    """Adds a user group to the specified appliances.

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
* `-s, --save-config`: If specified the configuration on the appliances
will be saved
* `-N, --name`: The name of the group to add
* `-A, --access-policies`: The access policies which will be associated
with this group
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    kwargs = {'name': name, 'access_policies': access_policies}
    msg = "Adding group {} to {}".format(name, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)
    resp = env.perform_async_action('add_group', **kwargs)
    logger.debug("responses received {}".format(str(resp)))
    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(resp, suffix="add_group")

    if save_config:
        kwargs = {'domain': 'default'}
        msg = "Saving configuration in the default domain of {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **kwargs)
        logger.debug("Responses received {}".format(str(resp)))
        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('del-group', category='users/groups')
def del_group(appliances=[],
              credentials=[],
              timeout=120,
              no_check_hostname=False,
              save_config=False,
              UserGroup="",
              web=False):
    """Removes a user group from the specified appliances.

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
* `-s, --save-config`: If specified the configuration on the
appliances will be saved
* `-U, --UserGroup`: The name of the group to remove
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    kwargs = {'group': UserGroup}
    msg = "Removing user group {} from {}".format(UserGroup, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)
    resp = env.perform_async_action('del_group', **kwargs)
    logger.debug("Responses received: {}".format(str(resp)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(resp, suffix="del_group")

    if save_config:
        logger.info(
            "Saving configuration of default domain for {}".format(
                str(env.appliances)))
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received: {}".format(str(resp)))

        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('list-users', category='users/groups')
def list_users(appliances=[],
               credentials=[],
               timeout=120,
               no_check_hostname=False,
               web=False):
    """Lists the users on the specified appliances as well as a list
of users common to all appliances.

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
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)

    logger.info("Attempting to list users for {}".format(str(env.appliances)))
    if web:
        return util.web_list_users(env), util.render_history(env)

    sets = []
    for appliance in env.appliances:
        users = appliance.users
        logger.debug(
            "Found users for {}: {}".format(
                appliance.hostname, str(users)))
        sets.append(set(users))
        print('\n', appliance.hostname)
        print('=' * len(appliance.hostname))
        for user in users:
            print('\t', user)
    common = sets[0].intersection(*sets)
    logger.debug(
        "Users common to {}: {}".format(
            str(env.appliances), str(common)))
    print('\nCommon')
    print('======')
    for user in common:
        print('\t', user)


@logged("mast.datapower.accounts")
@cli.command('add-user', category='users/groups')
def add_user(appliances=[],
             credentials=[],
             timeout=120,
             no_check_hostname=False,
             save_config=False,
             username=None,
             password="",
             supress_force_password_change=False,
             privileged=False,
             group=None,
             web=False):
    """Adds a user to the specified appliances.

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
* `-s, --save-config`: If specified the configuration on the appliances
will be saved
* `-u, --username`: The name of the user to add
* `-p, --password`: The initial password for the user
* `-P, --privileged`: Whether the user will be a privileged user
* `-g, --group`: The group to which to add the user
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__

**NOTE**: You cannot specify both privileged and a group.
It will fail to add the group"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to add user {} to {}".format(username, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)
    kwargs = {
        'username': username,
        'password': password,
        'privileged': privileged,
        'user_group': group,
        'supress_force_password_change': supress_force_password_change,
    }
    resp = env.perform_async_action('add_user', **kwargs)
    logger.debug("Responses received {}".format(str(resp)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(resp, suffix="add_user")

    if save_config:
        msg = "Attempting to save config of default domain on {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received {}".format(str(resp)))
        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('del-user', category='users/groups')
def del_user(appliances=[],
             credentials=[],
             timeout=120,
             no_check_hostname=False,
             save_config=False,
             User="",
             web=False):
    """Removes a user from the specified appliances.

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
you can use the output of`$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-s, --save-config`: If specified the configuration on the
appliances will be saved
* `-U, --User`: The name of the user to remove
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to delete user {} from {}".format(User, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    resp = env.perform_async_action('remove_user', **{'username': User})
    logger.debug("Responses received {}".format(str(resp)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(resp, suffix="remove_user")

    if save_config:
        msg = "Attempting to save config of default domain on {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received {}".format(str(resp)))

        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('change-password', category='users/groups')
def change_password(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    save_config=False,
                    User="",
                    password="",
                    web=False):
    """Changes the specified user's password to the specified password.

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
If you would prefer to not use plain-textpasswords,
you can use the output of `$ mast-system xor <username:password>`.
* `-t, --timeout`: The timeout in seconds to wait for a response from
an appliance for any single request. __NOTE__ Program execution may
halt if a timeout is reached.
* `-n, --no-check-hostname`: If specified SSL verification will be turned
off when sending commands to the appliances.
* `-s, --save-config`: If specified the configuration on the appliances will
be saved
* `-U, --User`: The name of the user whose password you are changing
* `-p, --password`: The new password for the specified user. NOTE: You may need to
place quotations around the argument passed if using special characters as these
might be incorrectly interpreted by your shell.
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to change password for {} on {}".format(User, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    kwargs = {'username': User, 'password': password}
    resp = env.perform_async_action('change_password', **kwargs)
    logger.debug("Responses received {}".format(str(resp)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(
            resp, suffix="change_password")

    if save_config:
        msg = "Attempting to save config of default domain on {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received {}".format(str(resp)))
        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('force-change-password', category='users/groups')
def force_change_password(appliances=[],
                          credentials=[],
                          timeout=120,
                          no_check_hostname=False,
                          save_config=False,
                          User="",
                          web=False):
    """Forces a user to change their password on their next login.

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
* `-s, --save-config`: If specified the configuration on the
appliances will be saved
* `-U, --User`: The name of the user to force a password change
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to force {} to change password on {}".format(User, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    resp = env.perform_async_action(
        'UserForcePasswordChange',
        **{'User': User})
    logger.debug("Responses received {}".format(str(resp)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(
            resp,
            suffix="force_password_change")

    if save_config:
        msg = "Attempting to save config of default domain on {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received {}".format(str(resp)))
        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('list-rbm-fallback', category='users/groups')
def list_rbm_fallback_users(appliances=[],
                            credentials=[],
                            timeout=120,
                            no_check_hostname=False,
                            web=False):
    """Lists the current RBM Fallback Users for the specified appliances,
as well as the fallback users which are common to all appliances.

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
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    if web:
        return util.web_list_rbm_fallback(env), util.render_history(env)

    sets = []
    for appliance in env.appliances:
        logger.info(
            "Attempting to list RBM Fallback users on {}".format(
                appliance.hostname))
        users = appliance.fallback_users
        logger.debug(
            "RBM Fallback users for {}: {}".format(
                appliance.hostname, str(users)))
        sets.append(set(users))
        print('\n', appliance.hostname)
        print('=' * len(appliance.hostname))
        for user in users:
            print('\t', user)
    common = sets[0].intersection(*sets)
    logger.debug(
        "RBM Fallback usesrs common to {}: {}".format(
            str(env.appliances), str(common)))
    print('\nCommon')
    print('======')
    for user in common:
        print('\t', user)


@logged("mast.datapower.accounts")
@cli.command('add-rbm-fallback', category='users/groups')
def add_rbm_fallback(appliances=[],
                     credentials=[],
                     timeout=120,
                     no_check_hostname=False,
                     save_config=False,
                     User="",
                     web=False):
    """Adds a user to the the RBM Fallback users.

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
* `-s, --save-config`: If specified the configuration on the
appliances will be saved
* `-U, --User`: The name of the user to add to RBM Fallback
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to add {} as an RBM Fallback user to {}".format(User, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    resp = env.perform_async_action('add_rbm_fallback', **{'user': User})
    logger.debug("Responses received {}".format(str(env.appliances)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(
            resp, suffix="add_rbm_fallback")

    if save_config:
        msg = "Attempting to save config of default domain on {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received {}".format(str(resp)))
        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('del-rbm-fallback', category='users/groups')
def del_rbm_fallback(appliances=[],
                     credentials=[],
                     timeout=120,
                     no_check_hostname=False,
                     save_config=False,
                     User="",
                     web=False):
    """Removes a user from the the RBM Fallback users.

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
* `-s, --save-config`: If specified the configuration on the
appliances will be saved
* `-U, --User`: The name of the user to remove from RBM Fallback
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to remove {} from RBM Fallback users on {}".format(User, str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    resp = env.perform_async_action('del_rbm_fallback', **{'username': User})
    logger.debug("Responses received {}".format(str(resp)))

    if not web:
        for host, resp in list(resp.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        output = util.render_boolean_results_table(
            resp, suffix="del_rbm_fallback")

    if save_config:
        msg = "Attempting to save config of default domain on {}".format(str(env.appliances))
        logger.info(msg)
        if not web:
            print(msg)
        resp = env.perform_async_action('SaveConfig', **{'domain': 'default'})
        logger.debug("Responses received {}".format(str(resp)))
        if not web:
            for host, resp in list(resp.items()):
                print("{}\n{}".format(host, "="*len(host)))
                pprint_xml(resp.xml)
        else:
            output += util.render_boolean_results_table(
                resp, suffix="save_config")
    if web:
        return output, util.render_history(env)

#
# ~#~#~#~#~#~#~#

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
# FlushLDAPPoolCache(XMLManager)
# FlushRBMCache()


@logged("mast.datapower.accounts")
@cli.command('flush-aaa-cache', category='caches')
def flush_aaa_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    Domain="",
                    aaa_policy="",
                    web=False):
    """Flushes the AAA Cache of the specified aaa_policy in the
specified Domain.

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
* `-D, --Domain`: The domain where the aaa_policy resides
* `-A, --aaa-policy`: the AAAPolicy who's cache you would like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to flush AAA cache on {}".format(str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    kwargs = {"PolicyName": aaa_policy, 'domain': Domain}
    responses = env.perform_action('FlushAAACache', **kwargs)
    logger.debug("Responses received {}".format(str(responses)))

    if not web:
        for host, resp in list(responses.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        return util.render_boolean_results_table(
            responses, suffix="flush_aaa_cache"), util.render_history(env)


@logged("mast.datapower.accounts")
@cli.command('flush-ldap-pool-cache', category='caches')
def flush_ldap_pool_cache(appliances=[],
                          credentials=[],
                          timeout=120,
                          no_check_hostname=False,
                          Domain="",
                          xml_manager="",
                          web=False):
    """Flushes the LDAP Pool Cache for the specified xml_manager
in the specified domain.

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
* `-D, --Domain`: The domain which has the xml_manager who's cache
you would like to flush.
* `-x, --xml-manager`: The XMLManager who's cache you would like to flush
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to flush LDAP Pool cache on {}".format(str(env.appliances))
    logger.info(msg)

    kwargs = {"XMLManager": xml_manager, 'domain': Domain}
    responses = env.perform_action('FlushLDAPPoolCache', **kwargs)
    logger.debug("Responses received {}".format(str(responses)))

    if not web:
        for host, resp in list(responses.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        return (util.render_boolean_results_table(
                    responses,
                    suffix="flush_ldap_pool_cache"),
                util.render_history(env))


@logged("mast.datapower.accounts")
@cli.command('flush-rbm-cache', category='caches')
def flush_rbm_cache(appliances=[],
                    credentials=[],
                    timeout=120,
                    no_check_hostname=False,
                    Domain="",
                    web=False):
    """Flush the RBM Cache in the specified Domain

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
* `-D, --Domain`: The domain for which to flush the RBM Cache
* `-w, --web`: __For Internel Use Only, will be removed in future versions.
DO NOT USE.__"""
    logger = make_logger("mast.accounts")
    check_hostname = not no_check_hostname
    env = datapower.Environment(
        appliances,
        credentials,
        timeout,
        check_hostname=check_hostname)
    msg = "Attempting to flush RBM cache on {}".format(str(env.appliances))
    logger.info(msg)
    if not web:
        print(msg)

    responses = env.perform_action('FlushRBMCache', **{'domain': Domain})
    logger.debug("Responses received {}".format(str(responses)))

    if not web:
        for host, resp in list(responses.items()):
            print("{}\n{}".format(host, "="*len(host)))
            pprint_xml(resp.xml)
    else:
        return util.render_boolean_results_table(
            responses, suffix="flush_rbm_cache"), util.render_history(env)

#
# ~#~#~#~#~#~#~#


def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f)).decode()


class WebPlugin(Plugin):
    def __init__(self):
        self.route = partial(pf.handle, "accounts")
        self.route.__name__ = "accounts"
        self.html = partial(pf.html, "mast.datapower.accounts")
        update_wrapper(self.html, pf.html)

    def css(self):
        return get_data_file("plugin.css")

    def js(self):
        return get_data_file("plugin.js")


if __name__ == '__main__':
    try:
        cli.run()
    except AttributeError as e:
        if "'NoneType' object has no attribute 'app'" in e:
            raise NotImplementedError(
                "HTML formatted output is not supported on the CLI")
        raise
