"""
Base class for all Xena package tests.

@author yoram@ignissoft.com
"""

from os import path
import pytest

from trafficgenerator.tgn_utils import ApiType
from trafficgenerator.test.test_tgn import TgnTest
from xenavalkyrie.xena_app import init_xena
from xenavalkyrie.xena_stream import XenaStream


class XenaTestBase(TgnTest):

    TgnTest.config_file = path.join(path.dirname(__file__), 'XenaValkyrie.ini')

    def setUp(self):
        super(XenaTestBase, self).setUp()

        self._get_config()

        self.xm = init_xena(self.api, self.logger, self.config.get('Xena', 'owner'), self.server_ip, self.server_port)
        self.temp_dir = self.config.get('General', 'temp_dir')
        self.xm.session.add_chassis(self.chassis)
        if self.xm.session.add_chassis(self.config.get('Xena', 'chassis2')):
            self.xm.session.add_chassis(self.config.get('Xena', 'chassis2'))
        self.port3 = self.config.get('Xena', 'port3')
        XenaStream.next_tpld_id = 0

    def tearDown(self):
        self.xm.session.disconnect()

    def test_hello_world(self):
        pass

    def _get_config(self):

        self.api = ApiType[pytest.config.getoption('--api')]  # @UndefinedVariable
        self.server_ip = pytest.config.getoption('--server')  # @UndefinedVariable
        self.chassis = pytest.config.getoption('--chassis')  # @UndefinedVariable
        self.port1 = '{}/{}'.format(self.chassis, pytest.config.getoption('--port1'))  # @UndefinedVariable
        self.port2 = '{}/{}'.format(self.chassis, pytest.config.getoption('--port2'))  # @UndefinedVariable
        if self.server_ip:
            self.server_ip = self.server_ip.split(':')[0]
            self.server_port = self.server_ip.split(':')[1] if len(self.server_ip.split(':')) == 2 else '57911'
        else:
            self.server_ip = self.chassis
            self.server_port = '57911'