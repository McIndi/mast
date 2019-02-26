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
import os
import flask
from mast.datapower.datapower import CONFIG_XPATH, STATUS_XPATH


def render_history(env):
    ret = []
    for appliance in env.appliances:
        ret.append(appliance.hostname)
        ret.append("=" * len(appliance.hostname))
        ret.append(appliance.history)
        ret.append(os.linesep)
    return os.linesep.join(ret)


def render_results_table(results, suffix=None):
    header_row = ("Appliance", "Result")
    rows = []
    for host, response in results.items():
        _host = host
        if suffix:
            _host = "{}-{}".format(host, suffix)
        rows.append((_host, response))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows
    )


def render_boolean_results_table(results, suffix=None):
    header_row = ("Appliance", "Result")
    rows = []
    for host, response in results.items():
        _host = host
        if suffix:
            _host = "{}-{}".format(host, suffix)
        _response = "Failed"
        if response:
            _response = "Succeeded"
        rows.append((_host, _response))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def _recurse_config(element, prefix=""):
    rows = []
    for child in element:
        if not list(child):
            _row = ["", "", ""]
            _row.append(prefix + "." + child.tag)
            _row.append(child.text)
            rows.append(_row)
        else:
            for child in list(element):
                _row = _recurse_config(child, prefix=prefix + "." + child.tag)
                rows.extend(_row)
    return rows


def _recurse_status(element, prefix=""):
    rows = []
    for child in element:
        if not list(child):
            _row = ["", ""]
            _row.append(prefix + "." + child.tag)
            _row.append(child.text)
            rows.append(_row)
        else:
            for child in list(element):
                _row = _recurse_config(child, prefix=prefix + "." + child.tag)
                rows.extend(_row)
    return rows


def render_config_results_table(resp, suffix=""):
    header_row = ["Appliance", "ObjectClass", "ObjectName", "Key", "Value"]
    rows = []
    xpath = CONFIG_XPATH
    for host, response in resp.items():
        _host = host
        if suffix:
            _host = "{}-{}".format(host, suffix)
        results = response.xml.findall(xpath)
        for child in results:
            _row = [_host, child.tag, child.get("name")]
            rows.append(_row)
            for grandchild in child:
                if not list(grandchild):
                    _row = ["", "", ""]
                    _row.append(grandchild.tag)
                    _row.append(grandchild.text)
                    rows.append(_row)
                else:
                    rows.extend(_recurse_config(
                        grandchild, prefix=grandchild.tag))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_status_results_table(resp, suffix=""):
    header_row = ["Appliance", "Provider", "Key", "Value"]
    rows = []
    xpath = STATUS_XPATH
    for host, response in resp.items():
        _host = host
        if suffix:
            _host = "{}-{}".format(host, suffix)
        results = response.xml.findall(xpath)
        for child in results:
            _row = [_host, child.tag]
            rows.append(_row)
            for grandchild in child:
                if not list(grandchild):
                    _row = ["", ""]
                    _row.append(grandchild.tag)
                    _row.append(grandchild.text)
                    rows.append(_row)
                else:
                    rows.extend(_recurse_status(
                        grandchild, prefix=grandchild.tag))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_save_config_results_table(env, domains):
    header_row = ["Appliance", "Result"]
    rows = []
    for appliance in env.appliances:
        if "all-domains" in domains:
            domains = appliance.domains
        for domain in domains:
            appl_domain = "{}-{}-save_config".format(
                appliance.hostname, domain)
            resp = appliance.SaveConfig(domain=domain)
            _row = [appl_domain, "Failed"]
            if resp:
                _row = [appl_domain, "Succeeded"]
            rows.append(_row)
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_list_domains_table(env):
    header_row = ("Appliance", "Domains")
    sets = []
    rows = []
    for appliance in env.appliances:
        domains = appliance.domains
        domains.sort()
        rows.append((appliance.hostname, flask.Markup("<br />".join(domains))))
        sets.append(set(domains))
    common = list(sets[0].intersection(*sets[1:]))
    common.sort()
    rows.append(("All", flask.Markup("<br />".join(common))))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_see_download_table(resp, suffix=""):
    header_row = ("Appliance", "Result")
    rows = []
    for host, r in resp.items():
        _host = host
        if suffix:
            _host = "{}-{}".format(host, suffix)
        rows.append((_host, "See Download"))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_connectivity_table(env):
    header_row = ("Appliance", "XML", "Web", "CLI")
    rows = []
    for appliance in env.appliances:
        _row = []
        _row.append(appliance.hostname)
        _row.append(appliance.check_xml_mgmt())
        _row.append(appliance.check_web_mgmt())
        _row.append(appliance.check_cli_mgmt())
        rows.append(_row)
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_tcp_connection_test_table(env, remote_hosts, remote_ports):
    header_row = ("Appliance", "Remote Host", "Remote Port", "Success")
    rows = []
    for appliance in env.appliances:
        for host in remote_hosts:
            for port in remote_ports:
                _row = [appliance.hostname, host, port]
                resp = appliance.TCPConnectionTest(
                    RemoteHost=host,
                    RemotePort=port)
                success = bool(resp)
                _row.append(str(success))
                rows.append(_row)
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_ethernet_interface_results_table(resp):
    header_row = ["Appliance", "EthernetInterface", "Key", "Value"]
    rows = []
    xpath = CONFIG_XPATH
    for host, response in resp.items():
        results = response.xml.find(xpath)
        for index, child in enumerate(results):
            _row = ["", ""]
            if not index:
                rows.append([host, results.get("name"), "", ""])

            if not list(child):
                _row.append(child.tag)
                _row.append(child.text)
            else:
                for node in child:
                    header = "{}.{}".format(child.tag, node.tag)
                    __row = list(_row)
                    __row.append(header)
                    __row.append(node.text)
                    rows.append(__row)
                continue
            rows.append(_row)
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_host_alias_table(resp):
    header_row = ("Appliance", "Host Alias", "IPAddress", "AdminState")
    rows = []
    sets = []
    for host, results in resp.items():
        sets.append(set(results))
        for item in results:
            _row = [host]
            _row.extend(item)
            rows.append(_row)
    common = sets[0].intersection(*sets[1:])
    for item in common:
        _row = ["common"]
        _row.extend(item)
        rows.append(_row)
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_static_hosts_table(resp):
    header_row = ("Appliance", "Hostname", "IP Address")
    rows = []
    for host, l in resp.items():
        for item in l:
            rows.append((host, item[0], item[1]))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_static_routes_table(resp):
    header_row = ("Appliance", "Destination", "Gateway", "Metric")
    rows = []
    for host, l in resp.items():
        for item in l:
            rows.append((host, item[0], item[1], item[2]))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def render_secondary_address_table(resp):
    header_row = ("Appliance", "Secondary Address")
    rows = []
    for host, response in resp.items():
        for item in response:
            rows.append((host, item))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def web_list_checkpoints(resp, domain):
    header_row = ("Appliance", "Checkpoints")
    rows = []
    for host, d in resp.items():
        _host = "{}-{}".format(host, domain)
        _results = []
        for k, v in d.items():
            _results.append(
                " ".join((
                    k,
                    "-".join(v["date"]),
                    ":".join(v["time"]))))
        rows.append((_host, flask.Markup("<br />".join(_results))))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def web_list_groups(env):
    """Returns an html table with all of the groups defined on the appliances
    within env."""
    header_row = ("Appliance", "Groups")
    sets = []
    rows = []
    for appliance in env.appliances:
        groups = appliance.groups
        rows.append((appliance.hostname, flask.Markup("<br />".join(groups))))
        sets.append(set(groups))
    common = sets[0].intersection(*sets[1:])
    rows.append(("All", flask.Markup("<br />".join(common))))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def web_list_users(env):
    """Returns an html table with all of the users defined on the appliances
    within env."""
    header_row = ("Appliance", "Users")
    sets = []
    rows = []
    for appliance in env.appliances:
        users = appliance.users
        rows.append((appliance.hostname, flask.Markup("<br />".join(users))))
        sets.append(set(users))
    common = sets[0].intersection(*sets[1:])
    rows.append(("All", flask.Markup("<br />".join(common))))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)


def web_list_rbm_fallback(env):
    """Returns an html table with all of the RBM fallback users defined on the
    appliances within env."""
    header_row = ("Appliance", "RBM Fallback Users")
    sets = []
    rows = []
    for appliance in env.appliances:
        users = appliance.fallback_users
        rows.append((appliance.hostname, flask.Markup("<br />".join(users))))
        sets.append(set(users))
    common = sets[0].intersection(*sets[1:])
    rows.append(("All", flask.Markup("<br />".join(common))))
    return flask.render_template(
        "results_table.html",
        header_row=header_row,
        rows=rows)
