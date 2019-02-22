import os
import flask
from mast.logging import logged
from mast.plugins.web import Plugin
from mast.datapower import datapower
from pkg_resources import resource_string
from mast.xor import xordecode, xorencode


_appliances = {}


@logged("mast.datapower.ssh")
def _check_for_appliance(hostname, appliances):
    """Given that appliances is a list of DataPower objects,
    return True if hostname is the hostname of one of the
    appliances"""
    for appliance in appliances:
        if appliance.hostname == hostname:
            return True
    return False


def get_data_file(f):
    return resource_string(__name__, 'docroot/{}'.format(f))


class WebPlugin(Plugin):
    def __init__(self):
        self.route = self.ssh

    def css(self):
        return get_data_file("plugin.css")

    def js(self):
        return get_data_file("plugin.js")

    def html(self):
        return get_data_file("plugin.html")

    @logged("mast.datapower.ssh")
    def ssh(self):
        """Handle requests comming from the ssh tab in the MAST web GUI."""
        global _appliances

        # Get the unique session_id from the form (this is different
        # even across tabs in the same browser)
        session_id = flask.request.form.get("ssh_session")

        if session_id not in _appliances.keys():
            # This is the first request from session_id
            _appliances[session_id] = []

        # _appliances holds the DataPower objects which in turn
        # are holding references to the ssh session.
        appliances = _appliances[session_id]
        command = flask.request.form.get("command")
        hostnames = flask.request.form.getlist("appliances[]")
        credentials = [xordecode(_, key=xorencode(
           flask.request.cookies["9x4h/mmek/j.ahba.ckhafn"]))
           for _ in flask.request.form.getlist('credentials[]')]

        # Check for appliances the user may have added
        for index, hostname in enumerate(hostnames):
            if not _check_for_appliance(hostname, appliances):
                # User added hostname to the list of appliances at the
                # top of the Web GUI.
                appliances.append(
                    datapower.DataPower(
                        hostname,
                        credentials[index],
                        check_hostname=False))

        # Check for appliances the user may have removed
        for appliance in list(appliances):
            if appliance.hostname not in hostnames:
                # User removed hostname from the list of appliances at the
                # top of the Web GUI
                appliance.ssh_disconnect()
                appliances.remove(appliance)
        responses = {}

        # Loop through appliances, check for connectivity and issue command
        for appliance in appliances:
            if not appliance.ssh_is_connected():
                appliance.ssh_connect()
            responses[appliance.hostname] = appliance.ssh_issue_command(
                command)

        # Return JSON object containing hostnames (keys) mapped
        # to responses (values)
        return flask.jsonify(responses)
