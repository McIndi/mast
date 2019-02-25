import mast.datapower.datapower
import unittest
import mock


mock_response = mast.datapower.datapower.DPResponse("""
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
    <env:Body>
        <dp:response xmlns:dp="http://www.datapower.com/schemas/management">
            <dp:timestamp>2016-05-03T13:29:55-04:00</dp:timestamp>
            <dp:file name="logtemp://default-log-xml.0"/>
        </dp:response>
    </env:Body>
</env:Envelope>
""")

class TestForRegressionInGetFile(unittest.TestCase):
    
    @mock.patch("mast.datapower.datapower.DataPower.send_request",
                return_value=mock_response)
    def test_getfile_will_create_empty_file_when_file_node_is_empty(
            self,
            send_request_mock):
        dp = mast.datapower.datapower.DataPower("test", "user:pass")
        result = dp.getfile("default", "logtemp:///default-log.xml.0")
        self.assertEqual("", result)
