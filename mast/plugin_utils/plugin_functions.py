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
This module is meant to consolidate the functionality of the following
plugins:

    1_system
    2_accounts
    3_backups
    4_developer
    5_network

This is possible since, even though the functionality between these plugins
is completely different, the structure is identical. In essence these plugins
dynamically create forms based on the function signatures of the functions
within the corresponding bin scripts.

The point of this is to recreate the functionality of the MAST CLI in the MAST
web GUI. So, I was able to consolidate all of the functionality of these
plugins into this single module.

- TODO: move hard-coded HTML into flask (jinja 2) templates
TODO: Documentation
TODO: Test cases (unit testing)
"""
import re
import os
import sys
import flask
import inspect
import zipfile
import markdown
import htmlentitydefs
from textwrap import dedent
from mast.config import get_config
from mast.datapower.datapower import Environment
from mast.xor import xordecode, xorencode
from mast.timestamp import Timestamp
from mast.logging import make_logger, logged

OBJECT_STATUS_ARGS = ['AAAPolicy', 'AS1PollerSourceProtocolHandler',
    'AS2ProxySourceProtocolHandler', 'AS2SourceProtocolHandler',
    'AS3SourceProtocolHandler', 'AccessControlList', 'AppSecurityPolicy',
    'AuditLog', 'B2BCPA', 'B2BCPACollaboration', 'B2BCPAReceiverSetting',
    'B2BCPASenderSetting', 'B2BGateway', 'B2BPersistence', 'B2BProfile',
    'B2BProfileGroup', 'B2BXPathRoutingPolicy', 'CRLFetch', 'CertMonitor',
    'CloudConnectorService', 'CloudGatewayService', 'CompactFlash',
    'CompileOptionsPolicy', 'ConfigDeploymentPolicy', 'ConformancePolicy',
    'CookieAttributePolicy', 'CountMonitor', 'CryptoCertificate',
    'CryptoFWCred', 'CryptoIdentCred', 'CryptoKerberosKDC',
    'CryptoKerberosKeytab', 'CryptoKey', 'CryptoProfile', 'CryptoSSKey',
    'CryptoValCred', 'DNSNameService', 'DeploymentPolicyParametersBinding',
    'DocumentCryptoMap', 'Domain', 'DomainAvailability', 'DurationMonitor',
    'EBMS2SourceProtocolHandler', 'ErrorReportSettings', 'EthernetInterface',
    'FTPFilePollerSourceProtocolHandler', 'FTPQuoteCommands',
    'FTPServerSourceProtocolHandler', 'FilterAction', 'FormsLoginPolicy',
    'GeneratedPolicy', 'HTTPInputConversionMap', 'HTTPSSourceProtocolHandler',
    'HTTPService', 'HTTPSourceProtocolHandler', 'HTTPUserAgent', 'HostAlias',
    'ILMTAgent', 'IMSCalloutSourceProtocolHandler', 'IMSConnect',
    'IMSConnectSourceProtocolHandler', 'IPMILanChannel', 'IPMIUser',
    'IPMulticast', 'ISAMReverseProxy', 'ISAMReverseProxyJunction',
    'ISAMRuntime', 'IScsiChapConfig', 'IScsiHBAConfig', 'IScsiInitiatorConfig',
    'IScsiTargetConfig', 'IScsiVolumeConfig', 'ImportPackage', 'IncludeConfig',
    'InteropService', 'JSONSettings', 'LDAPConnectionPool',
    'LDAPSearchParameters', 'Language', 'LinkAggregation', 'LoadBalancerGroup',
    'LogLabel', 'LogTarget', 'MCFCustomRule', 'MCFHttpHeader', 'MCFHttpMethod',
    'MCFHttpURL', 'MCFXPath', 'MPGWErrorAction', 'MPGWErrorHandlingPolicy',
    'MQFTESourceProtocolHandler', 'MQGW', 'MQQM', 'MQQMGroup',
    'MQSourceProtocolHandler', 'MQhost', 'MQproxy', 'MTOMPolicy', 'Matching',
    'MessageContentFilters', 'MessageMatching', 'MessageType', 'MgmtInterface',
    'MultiProtocolGateway', 'NFSClientSettings', 'NFSDynamicMounts',
    'NFSFilePollerSourceProtocolHandler', 'NFSStaticMount', 'NTPService',
    'NameValueProfile', 'NetworkSettings', 'OAuthSupportedClient',
    'OAuthSupportedClientGroup', 'ODR', 'ODRConnectorGroup',
    'POPPollerSourceProtocolHandler', 'PasswordMap', 'Pattern', 'PeerGroup',
    'PolicyAttachments', 'PolicyParameters', 'ProcessingMetadata',
    'RADIUSSettings', 'RBMSettings', 'RaidVolume', 'RestMgmtInterface',
    'SAMLAttributes', 'SFTPFilePollerSourceProtocolHandler', 'SLMAction',
    'SLMCredClass', 'SLMPolicy', 'SLMRsrcClass', 'SLMSchedule',
    'SMTPServerConnection', 'SNMPSettings', 'SOAPHeaderDisposition',
    'SQLDataSource', 'SQLRuntimeSettings', 'SSHClientProfile',
    'SSHServerSourceProtocolHandler', 'SSHService', 'SSLProxyProfile',
    'SSLProxyService', 'SchemaExceptionMap', 'SecureCloudConnector',
    'ShellAlias', 'SimpleCountMonitor', 'StatelessTCPSourceProtocolHandler',
    'Statistics', 'StylePolicy', 'StylePolicyAction', 'StylePolicyRule',
    'SystemSettings', 'TAM', 'TCPProxyService', 'TFIMEndpoint',
    'TelnetService', 'Throttler', 'TibcoEMSServer',
    'TibcoEMSSourceProtocolHandler', 'TimeSettings', 'UDDIRegistry',
    'UDDISubscription', 'URLMap', 'URLRefreshPolicy', 'URLRewritePolicy',
    'User', 'UserGroup', 'VLANInterface', 'WCCService',
    'WSEndpointRewritePolicy', 'WSGateway', 'WSRRSavedSearchSubscription',
    'WSRRServer', 'WSRRSubscription', 'WSStylePolicy', 'WSStylePolicyRule',
    'WebAppErrorHandlingPolicy', 'WebAppFW', 'WebAppRequest', 'WebAppResponse',
    'WebAppSessionPolicy', 'WebB2BViewer', 'WebGUI', 'WebServiceMonitor',
    'WebServicesAgent', 'WebSphereJMSServer',
    'WebSphereJMSSourceProtocolHandler', 'WebTokenService', 'XACMLPDP',
    'XC10Grid', 'XMLFirewallService', 'XMLManager', 'xmltrace',
    'XPathRoutingMap', 'XSLCoprocService', 'XSLProxyService',
    'XTCProtocolHandler', 'ZHybridTargetControlService', 'ZosNSSClient']

STATUS_PROVIDERS = ["ActiveUsers", "ARPStatus",
    "AS1PollerSourceProtocolHandlerSummary", "AS2SourceProtocolHandlerSummary",
    "AS3SourceProtocolHandlerSummary", "B2BGatewaySummary",
    "B2BHighAvailabilityStatus", "B2BMessageArchiveStatus", "B2BTransactionLog",
    "Battery", "ChangeGroupRetryQueue", "ChangeGroups",
    "CloudConnectorServiceSummary", "CloudGatewayServiceSummary",
    "ConnectionsAccepted", "CPUUsage", "CryptoEngineStatus",
    "CryptoEngineStatus2", "CryptoHwDisableStatus", "CryptoModeStatus",
    "CurrentSensors", "DateTimeStatus", "DebugActionStatus",
    "DNSCacheHostStatus", "DNSCacheHostStatus2", "DNSCacheHostStatus3",
    "DNSNameServerStatus", "DNSNameServerStatus2", "DNSSearchDomainStatus",
    "DNSStaticHostStatus", "DocumentCachingSummary", "DocumentStatus",
    "DocumentStatusSimpleIndex", "DomainCheckpointStatus",
    "DomainsMemoryStatus", "DomainsMemoryStatus2", "DomainStatus",
    "DomainSummary", "DynamicQueueManager", "DynamicTibcoEMSStatus",
    "EBMS2SourceProtocolHandlerSummary", "EnvironmentalFanSensors",
    "EnvironmentalSensors", "EthernetCountersStatus",
    "EthernetInterfaceStatus", "EthernetMAUStatus",
    "EthernetMIIRegisterStatus", "FailureNotificationStatus",
    "FailureNotificationStatus2", "FilePollerStatus",
    "FilesystemStatus", "FirmwareStatus", "FirmwareVersion",
    "FirmwareVersion2", "FTPFilePollerSourceProtocolHandlerSummary",
    "FTPServerSourceProtocolHandlerSummary", "GatewayTransactions",
    "HSMKeyStatus", "HTTPConnections", "HTTPConnectionsCreated",
    "HTTPConnectionsDestroyed", "HTTPConnectionsOffered",
    "HTTPConnectionsRequested", "HTTPConnectionsReturned",
    "HTTPConnectionsReused", "HTTPMeanTransactionTime",
    "HTTPMeanTransactionTime2", "HTTPServiceSummary",
    "HTTPSourceProtocolHandlerSummary", "HTTPSSourceProtocolHandlerSummary",
    "HTTPTransactions", "HTTPTransactions2", "Hypervisor", "IGMPStatus",
    "IMSConnectSourceProtocolHandlerSummary", "IMSConnectstatus",
    "IPAddressStatus", "IPMISelEvents", "IPMulticastStatus",
    "IScsiHBAStatus", "IScsiInitiatorStatus", "IScsiTargetStatus",
    "IScsiVolumeStatus", "KerberosTickets", "KerberosTickets2",
    "LDAPPoolEntries", "LDAPPoolSummary", "LibraryVersion", "LicenseStatus",
    "LinkAggregationMemberStatus", "LinkAggregationStatus", "LinkStatus",
    "LoadBalancerStatus", "LoadBalancerStatus2", "LogTargetStatus",
    "MemoryStatus", "MessageCountFilters", "MessageCounts",
    "MessageDurationFilters", "MessageDurations", "MessageSources",
    "MQConnStatus", "MQFTESourceProtocolHandlerSummary",
    "MQQMstatus", "MQSourceProtocolHandlerSummary",
    "MQStatus", "MultiProtocolGatewaySummary",
    "NDCacheStatus", "NDCacheStatus2", "NetworkInterfaceStatus",
    "NetworkReceiveDataThroughput", "NetworkReceivePacketThroughput",
    "NetworkTransmitDataThroughput", "NetworkTransmitPacketThroughput",
    "NFSFilePollerSourceProtocolHandlerSummary", "NFSMountStatus",
    "NTPRefreshStatus", "OAuthCachesStatus", "ObjectStatus",
    "ODRConnectorGroupStatus", "ODRConnectorGroupStatus2",
    "ODRLoadBalancerStatus", "OtherSensors", "PCIBus", "PolicyDomainStatus",
    "POPPollerSourceProtocolHandlerSummary", "PortStatus", "PowerSensors",
    "RaidArrayStatus", "RaidBatteryBackUpStatus", "RaidBatteryModuleStatus",
    "RaidLogicalDriveStatus", "RaidPartitionStatus", "RaidPhysDiskStatus",
    "RaidPhysDiskStatus2", "RaidPhysicalDriveStatus", "RaidVolumeStatus",
    "RaidVolumeStatus2", "ReceiveKbpsThroughput", "ReceivePacketThroughput",
    "RoutingStatus", "RoutingStatus2", "RoutingStatus3",
    "SecureCloudConnectorConnectionsStatus", "SelfBalancedStatus",
    "SelfBalancedStatus2", "SelfBalancedTable", "ServicesMemoryStatus",
    "ServicesMemoryStatus2", "ServicesStatus", "ServicesStatusPlus",
    "ServiceVersionStatus", "SFTPFilePollerSourceProtocolHandlerSummary",
    "SLMPeeringStatus", "SLMSummaryStatus", "SNMPStatus",
    "SQLConnectionPoolStatus", "SQLRuntimeStatus", "SQLStatus",
    "SSHKnownHostFileStatus", "SSHKnownHostFileStatus2", "SSHKnownHostStatus",
    "SSHServerSourceProtocolHandlerSummary", "SSHTrustedHostStatus",
    "SSLProxyServiceSummary", "StandbyStatus", "StandbyStatus2",
    "StatelessTCPSourceProtocolHandlerSummary", "StylesheetCachingSummary",
    "StylesheetExecutions", "StylesheetExecutionsSimpleIndex",
    "StylesheetMeanExecutionTime", "StylesheetMeanExecutionTimeSimpleIndex",
    "StylesheetProfiles", "StylesheetProfilesSimpleIndex", "StylesheetStatus",
    "StylesheetStatusSimpleIndex", "SystemUsage", "SystemUsage2Table",
    "SystemUsageTable", "TCPProxyServiceSummary", "TCPSummary", "TCPTable",
    "TemperatureSensors", "TibcoEMSSourceProtocolHandlerSummary",
    "TibcoEMSStatus", "TransmitKbpsThroughput",
    "TransmitPacketThroughput", "UDDISubscriptionKeyStatusSimpleIndex",
    "UDDISubscriptionServiceStatusSimpleIndex",
    "UDDISubscriptionStatusSimpleIndex", "Version",
    "VlanInterfaceStatus", "VlanInterfaceStatus2", "VoltageSensors",
    "WebAppFwAccepted", "WebAppFwRejected", "WebAppFWSummary",
    "WebSphereJMSSourceProtocolHandlerSummary", "WebSphereJMSStatus",
    "WebTokenServiceSummary", "WSGatewaySummary", "WSMAgentSpoolers",
    "WSMAgentStatus", "WSOperationMetrics", "WSOperationMetricsSimpleIndex",
    "WSOperationsStatus", "WSOperationsStatusSimpleIndex",
    "WSRRSavdSrchSubsPolicyAttachmentsStatus",
    "WSRRSavedSearchSubscriptionServiceStatus",
    "WSRRSavedSearchSubscriptionStatus",
    "WSRRSubscriptionPolicyAttachmentsStatus",
    "WSRRSubscriptionServiceStatus", "WSRRSubscriptionStatus",
    "WSWSDLStatus", "WSWSDLStatusSimpleIndex", "XC10GridStatus",
    "XMLFirewallServiceSummary", "XMLNamesStatus", "XSLCoprocServiceSummary",
    "XSLProxyServiceSummary", "XTCProtocolHandlerSummary", "ZHybridTCSstatus",
    "ZosNSSstatus"]


def _zipdir(path, z):
    """Create a zip file z of all files in path recursively"""
    for root, _, files in os.walk(path):
        for f in files:
            filename = os.path.join(
                *os.path.join(root, f).split(os.path.sep)[2:])
            z.write(os.path.join(root, f), filename)


def get_module(plugin):
    """Return the imported objects which correspond to plugin.
    These are all from bin (which is a module itself)."""
    module = __import__("mast.datapower", globals(), locals(), [plugin], -1)
    return getattr(module, plugin)


def unescape(text):
    """Removes HTML or XML character references and entities from a text string.
    @param text The HTML (or XML) source text.
    @return The plain text, as a Unicode string, if necessary.

    This function was taken from:
    http://effbot.org/zone/re-sub.htm#unescape-html

    written by: Fredrik Lundh"""

    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text  # leave as is
    return re.sub("&#?\w+;", fixup, text)



def html(plugin):
    """Return the html for plugin's tab"""
    htm = []
    module = get_module(plugin.replace("mast.datapower.", ""))
    last_category = ''
    for item in sorted(
            module.cli._command_list, key=lambda item: item.category):
        if not item.name == 'help':
            callable_name = item.callable.__name__.replace('_', ' ')
            current_category = item.category
            if current_category != last_category:
                htm.append(
                    flask.render_template(
                        'categorylabel.html', category=current_category))
            htm.append(
                flask.render_template(
                    'dynbutton.html', plugin=plugin, callable=callable_name))
            last_category = current_category
    return unescape(flask.render_template(
        'dynplugin.html', plugin=plugin, buttons=''.join(htm)))


def _get_arguments(plugin, fn_name):
    """Return a list of two-tuples containing the argument names and
    default values for function name and the actual function."""
    module = get_module(plugin)
    for item in module.cli._command_list:
        if item.callable.__name__ == fn_name:
            args, _, __, defaults = inspect.getargspec(item.callable)
            break
    return (list(zip(args, defaults)), item.callable)


def render_textbox(key, value):
    """Render a textbox for a dynamic form."""
    name = key
    label = key.replace('_', ' ')
    return flask.render_template(
        "textbox.html", name=name,
        label=label, value=value)


def render_password_box(key, value):
    """Render a textbox for a dynamic form."""
    name = key
    label = key.replace('_', ' ')
    return flask.render_template(
        "passwordbox.html", name=name,
        label=label, value=value)


def render_checkbox(key, checked=False):
    """Render a checkbox for a dynamic form."""
    name = key
    label = key.replace('_', ' ')
    checked = "checked=checked" if checked else ""
    return flask.render_template(
        "checkbox.html", name=name,
        label=label, checked=checked)


def render_multitext(key):
    """Render a multi-value textbox for a dynamic form."""
    _id = key
    label = key.replace('_', ' ')
    return flask.render_template("multitext.html", id=_id, label=label)


def render_file_upload(plugin, key):
    """Render our custom file upload form control for a dynamic form."""
    name = key
    label = key.replace('_', ' ')
    return flask.render_template(
        "fileupload.html", name=name,
        label=label, plugin=plugin)


def render_select_object_status(key, env):
    options = env.common_config(key)
    return flask.render_template(
        'dynselect.html',
        options=options,
        name=key,
        disclaimer=True)


def render_multiselect_object_status(key, env):
    options = env.common_config(key)
    return flask.render_template(
        "multiselect.html",
        options=options,
        key=key,
        disclaimer=True)


def render_multiselect_status_provider(key):
    return flask.render_template("multiselect.html", options=STATUS_PROVIDERS,
        key=key, disclaimer=False)


def render_select_status_provider(key):
    return flask.render_template("dynselect.html", options=STATUS_PROVIDERS,
        name=key, disclaimer=False)


def render_multiselect_object_class(key):
    return flask.render_template("multiselect.html", options=OBJECT_STATUS_ARGS,
        key=key, disclaimer=False)


def render_select_object_class(key):
    return flask.render_template("dynselect.html", options=OBJECT_STATUS_ARGS,
        name=key, disclaimer=False)


def get_form(plugin, fn_name, appliances, credentials, no_check_hostname=True):
    """Return a form suitable for gathering arguments to function name"""
    check_hostname = not no_check_hostname
    textboxes = []
    checkboxes = []
    file_uploads = []
    selects = []

    env = Environment(appliances, credentials, check_hostname=check_hostname)

    forms = ['<div class="{0}Form"><div name="{1}">'.format(plugin, fn_name)]

    label = fn_name.replace('_', ' ')
    forms.append(flask.render_template('formlabel.html', label=label))

    #md = markdown.Markdown(extensions=['markdown.extensions.extra'])
    arguments, fn = _get_arguments(plugin, fn_name)
    forms.append('<a href="#" class="help">help</a>')
    forms.append('<div class="hidden help_content">{}</div>'.format(
        flask.Markup(markdown.markdown(dedent(str(fn.__doc__))))))
    for arg in arguments:
        key, value = arg
        if isinstance(value, bool):
            if key == "web":
                continue
            if value:
                checkboxes.append(render_checkbox(key, checked=True))
                continue
            else:
                checkboxes.append(render_checkbox(key))
                continue
        elif isinstance(value, list):
            if key == 'appliances' or key == 'credentials':
                continue
            elif key in OBJECT_STATUS_ARGS:
                selects.append(render_multiselect_object_status(key, env))
                continue
            elif key == "StatusProvider":
                selects.append(render_multiselect_status_provider(key))
                continue
            elif key == "ObjectClass":
                selects.append(render_multiselect_object_class(key))
                continue
            textboxes.append(render_multitext(key))
        elif isinstance(value, basestring):
            if key == 'out_dir':
                continue
            elif key == 'out_file':
                continue
            elif key in OBJECT_STATUS_ARGS:
                selects.append(render_select_object_status(key, env))
                continue
            elif key == "StatusProvider":
                selects.append(render_select_status_provider(key))
                continue
            elif key == "ObjectClass":
                selects.append(render_select_object_class(key))
                continue
            elif "password" in key:
                textboxes.append(render_password_box(key, value))
                continue
            textboxes.append(render_textbox(key, value))
        elif isinstance(value, int):
            textboxes.append(render_textbox(key, value))
        elif value is None:
            if key == 'out_file':
                continue
            elif key == 'file_in':
                file_uploads.append(render_file_upload(plugin, key))
                continue
            textboxes.append(render_textbox(key, ''))

    forms.extend(textboxes)
    forms.extend(selects)
    forms.extend(file_uploads)
    forms.extend(checkboxes)
    forms.append(flask.render_template('submitbutton.html', plugin=plugin))
    forms.append('</div></div>')
    return '<br />\n'.join(forms)


def _call_method(func, kwargs):
    """Call func with kwargs if web is in kwargs, func should return a
    two-tupple containing (html, request_history). Here, we write the hsitory
    to a file and return the html for inclusion in the web GUI."""
    import random
    random.seed()
    if "appliances" not in kwargs:
        pass
    elif not kwargs["appliances"][0]:
        # Kind of a hack to return the response we want in case no appliances
        # were checked in the gui
        def _func(*args, **kwargs):
            return (
                "Must select at least one appliance.",
                "Must select at least one appliance.")
        func = _func
    if "web" in kwargs:
        try:
            out, hist = func(**kwargs)
        except Exception, e:
            # The actions implemented should handle their own exceptions,
            # but if one makes it's way up here, we need to let the user know
            # part of that is suppressing the exception (because otherwise
            # we have no way of sending back the details)
            import traceback
            msg = "Sorry, an unhandled exception occurred while "
            msg += "performing action:\n\n\t {}".format(str(e))
            out, hist = msg, traceback.format_exc()
            sys.stderr.write(traceback.format_exc())
        t = Timestamp()

        # TODO: move this path to configuration
        filename = os.path.join(
            "var", "www", "static", "tmp", "request_history", t.timestamp)
        if not os.path.exists(filename):
            os.makedirs(filename)
        rand = random.randint(10000, 99999)
        _id = "{}-{}.log".format(str(t.timestamp), str(rand))
        filename = os.path.join(filename, _id)
        with open(filename, 'wb') as fout:
            fout.write(hist)
        return flask.Markup(out), _id


def call_method(plugin, form):
    """Gather the arguments and function name from form then invoke
    _call_method. Wrap the results in html and return them."""
    t = Timestamp()
    name = form.get("callable")
    arguments, func = _get_arguments(plugin, name)
    kwargs = {}
    for arg, default in arguments:
        if isinstance(default, bool):
            if arg == "web":
                kwargs[arg] = True
                continue
            value = form.get(arg)
            if value == 'true':
                kwargs[arg] = True
            else:
                kwargs[arg] = False
        elif isinstance(default, list):
            # TODO: This needs to implement a selection feature
            if arg == 'appliances':
                kwargs[arg] = form.getlist(arg + '[]')
            elif arg == 'credentials':
                kwargs[arg] = [
                    xordecode(
                        _, key=xorencode(
                            flask.request.cookies["9x4h/mmek/j.ahba.ckhafn"]))
                            for _ in form.getlist(arg + '[]')]
            else:
                kwargs[arg] = form.getlist(arg + '[]')
        elif isinstance(default, basestring):
            if arg == 'out_dir':
                kwargs[arg] = os.path.join('tmp', 'web', name, t.timestamp)
            elif arg == 'out_file' and default is not None:
                kwargs[arg] = os.path.join("tmp",
                                           "web",
                                           name,
                                           "{}-{}{}".format(t.timestamp,
                                                            name,
                                                            os.path.splitext(default)[1])
                ).replace(os.path.sep, "/")
            else:
                kwargs[arg] = form.get(arg) or default
        elif isinstance(default, int):
            kwargs[arg] = int(form.get(arg)) or default
        elif default is None:
            kwargs[arg] = form.get(arg) or default
    out, history_id = _call_method(func, kwargs)
    link = ""
    if 'out_dir' in kwargs:
        config = get_config("server.conf")
        static_dir = config.get('dirs', 'static')

        fname = ""
        for appliance in kwargs['appliances']:
            fname = "{}-{}".format(fname, appliance)
        fname = "{}-{}{}.zip".format(t.timestamp, name, fname)
        zip_filename = os.path.join(
            static_dir,
            'tmp',
            fname)
        zip_file = zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED)
        _zipdir(kwargs['out_dir'], zip_file)
        zip_file.close()
        #filename = '%s-%s.zip' % (t.timestamp, name)
        link = flask.Markup(flask.render_template('link.html', filename=fname))
    if 'out_file' in kwargs and kwargs["out_file"] is not None:
        import shutil
        config = get_config("server.conf")
        static_dir = config.get('dirs', 'static')
        dst = os.path.join(static_dir,
                           "tmp",
                           os.path.basename(kwargs["out_file"]))
        shutil.copyfile(kwargs["out_file"], dst)

        link = flask.Markup(flask.render_template('link.html',
                                                  filename=os.path.basename(kwargs["out_file"])))
    out = flask.render_template(
        'output.html',
        output=out,
        callable=name,
        timestamp=str(t),
        history_id=history_id,
        link=link)
    if 'out_dir' in kwargs:
        out = out
    return out


def handle(plugin):
    """main funcion which will be routed to the plugin's endpoint"""
    logger = make_logger("mast.plugin_functions")
    import urllib
    if flask.request.method == 'GET':
        logger.info("GET Request received")
        name = flask.request.args.get('callable')
        logger.debug("name: {}".format(name))
        appliances = flask.request.args.getlist('appliances[]')
        logger.debug("appliances: {}".format(str(appliances)))
        credentials = [xordecode(urllib.unquote(_), key=xorencode(
                        flask.request.cookies["9x4h/mmek/j.ahba.ckhafn"]))
                        for _ in flask.request.args.getlist('credentials[]')]

        logger.debug("getting form")
        try:
            form = get_form(plugin.replace("mast.", ""), name, appliances, credentials)
        except:
            logger.exception("An unhandled exception occurred during execution.")
            raise
        logger.debug("Got form")
        return form
    elif flask.request.method == 'POST':
        logger.info("Received POST request for {}".format(plugin))
        try:
            return flask.Markup(str(call_method(plugin, flask.request.form)))
        except:
            logger.exception("An unhandled exception occurred during processing of request.")
            raise

