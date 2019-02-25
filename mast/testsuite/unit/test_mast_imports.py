from time import time
import unittest


class TestMASTImports(unittest.TestCase):
    """
    Basic smoke tests. Basically checks for syntax errors and such
    by ensuring that each module can be imported. Also checks that each
    version has knowlege of its `__version__` which is a recent requirement.
    """
    def setUp(self):
        self.start_time = time()

    def tearDown(self):
        self.time_taken = time() - self.start_time
        print "%.3f: %s" % (self.time_taken, self.id())

    def test_import_mast_cli(self):
        import mast.cli as cli
        self.assertTrue(hasattr(cli, "__version__"))

    def test_import_mast_config(self):
        import mast.config as config
        self.assertTrue(hasattr(config, "__version__"))

    def test_import_mast_cron(self):
        import mast.cron as cron
        self.assertTrue(hasattr(cron, "__version__"))

    def test_import_mast_daemon(self):
        import mast.daemon as daemon
        self.assertTrue(hasattr(daemon, "__version__"))

    def test_import_mast_datapower_accounts(self):
        import mast.datapower.accounts as accounts
        self.assertTrue(hasattr(accounts, "__version__"))

    def test_import_mast_datapower_backups(self):
        import mast.datapower.backups as backups
        self.assertTrue(hasattr(backups, "__version__"))

    def test_import_mast_datapower_crypto(self):
        import mast.datapower.crypto as crypto
        self.assertTrue(hasattr(crypto, "__version__"))

    def test_import_mast_datapower_datapower(self):
        import mast.datapower.datapower as datapower
        self.assertTrue(hasattr(datapower, "__version__"))

    def test_import_mast_datapower_deployment(self):
        import mast.datapower.deployment as deployment
        self.assertTrue(hasattr(deployment, "__version__"))

    def test_import_mast_datapower_developer(self):
        import mast.datapower.developer as developer
        self.assertTrue(hasattr(developer, "__version__"))

    def test_import_mast_datapower_network(self):
        import mast.datapower.network as network
        self.assertTrue(hasattr(network, "__version__"))

    def test_import_mast_datapower_ssh(self):
        import mast.datapower.ssh as ssh
        self.assertTrue(hasattr(ssh, "__version__"))

    def test_import_mast_datapower_status(self):
        import mast.datapower.status as status
        self.assertTrue(hasattr(status, "__version__"))

    def test_import_mast_datapower_system(self):
        import mast.datapower.system as system
        self.assertTrue(hasattr(system, "__version__"))

    def test_import_mast_datapower_web(self):
        import mast.datapower.web as web
        self.assertTrue(hasattr(web, "__version__"))

    def test_import_mast_hashes(self):
        import mast.hashes as hashes
        self.assertTrue(hasattr(hashes, "__version__"))

    def test_import_mast_logging(self):
        import mast.logging as logging
        self.assertTrue(hasattr(logging, "__version__"))

    def test_import_mast_plugins(self):
        import mast.plugins as plugins
        self.assertTrue(hasattr(plugins, "__version__"))

    def test_import_mast_plugin_utils(self):
        import mast.plugin_utils as plugin_utils
        self.assertTrue(hasattr(plugin_utils, "__version__"))

    def test_import_mast_pprint(self):
        import mast.pprint as pprint
        self.assertTrue(hasattr(pprint, "__version__"))

    def test_import_mast_test(self):
        import mast.test as test
        self.assertTrue(test, "__version__")

    def test_import_mast_timestamp(self):
        import mast.timestamp as timestamp
        self.assertTrue(hasattr(timestamp, "__version__"))

    def test_import_mast_xor(self):
        import mast.xor as xor
        self.assertTrue(hasattr(xor, "__version__"))

    def test_import_commandr(self):
        import commandr
        self.assertTrue(hasattr(commandr, "Commandr"))

    def test_import_cherrypy(self):
        import cherrypy
        self.assertTrue(hasattr(cherrypy, "tree"))

    def test_import_paramiko(self):
        import paramiko
        self.assertTrue(hasattr(paramiko, "message"))

    def test_import_markdown(self):
        import markdown
        self.assertTrue(hasattr(markdown, "Markdown"))

    def test_import_ecdsa(self):
        import ecdsa
        self.assertTrue(ecdsa, "ecdsa")


if __name__ == "__main__":
    unittest.main()
