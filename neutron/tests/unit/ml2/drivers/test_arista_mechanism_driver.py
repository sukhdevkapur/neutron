# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright (c) 2013 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#import copy
import mock

from neutron.plugins.ml2.drivers.mech_arista import db
from neutron.plugins.ml2.drivers.mech_arista import exceptions as arista_exc
from neutron.plugins.ml2.drivers.mech_arista import mechanism_arista as arista
from neutron.tests import base
from oslo.config import cfg


def clear_config():
    cfg.CONF.clear()


def setup_arista_wrapper_config(value=None):
    cfg.CONF.keystone_authtoken = fake_keystone_info_class()
    for opt in arista.AristaRPCWrapper.required_options:
        cfg.CONF.set_override(opt, value, "ARISTA_DRIVER")


def setup_valid_config():
    # Config is not valid if value is not set
    setup_arista_wrapper_config('value')


class AristaRPCWrapperInvalidConfigTestCase(base.BaseTestCase):
    """Negative test cases to test the Arista Driver configuration."""

    def setUp(self):
        super(AristaRPCWrapperInvalidConfigTestCase, self).setUp()
        self.setup_invalid_config()  # Invalid config, required options not set

    def tearDown(self):
        super(AristaRPCWrapperInvalidConfigTestCase, self).tearDown()
        clear_config()

    def setup_invalid_config(self):
        setup_arista_wrapper_config(None)

    def test_raises_exception_on_wrong_configuration(self):
        self.assertRaises(arista_exc.AristaConfigError,
                          arista.AristaRPCWrapper)


class NegativeRPCWrapperTestCase(base.BaseTestCase):
    """Negative test cases to test the RPC between Arista Driver and EOS."""

    def setUp(self):
        super(NegativeRPCWrapperTestCase, self).setUp()
        setup_valid_config()

    def tearDown(self):
        super(NegativeRPCWrapperTestCase, self).tearDown()
        clear_config()

    def test_exception_is_raised_on_json_server_error(self):
        drv = arista.AristaRPCWrapper()

        drv._server = mock.MagicMock()
        drv._server.runCmds.side_effect = Exception('server error')

        self.assertRaises(arista_exc.AristaRpcError, drv.get_tenants_list)


class RealNetStorageAristaDriverTestCase(base.BaseTestCase):
    """Main test cases for Arista Mechanism driver.

    Tests all mechanism driver APIs supported by Arista Driver. It invokes
    all the APIs as they would be invoked in real world scenarios and
    verifies the functionality.
    """
    def setUp(self):
        super(RealNetStorageAristaDriverTestCase, self).setUp()
        self.fake_rpc = mock.MagicMock()
        self.net_storage = db.ProvisionedNetsStorage()
        self.net_storage.initialize_db()
        self.drv = arista.AristaDriver(self.fake_rpc, self.net_storage)
        self.storage_drv = db.ProvisionedNetsStorage()

    def tearDown(self):
        super(RealNetStorageAristaDriverTestCase, self).tearDown()
        self.net_storage.tear_down()
        cfg.CONF.clear()

    def test_create_and_delete_network(self):
        tenant_id = 'ten-1'
        network_id = 'net1-id'
        segmentation_id = 1001

        network_context = self._get_network_context(tenant_id,
                                                    network_id,
                                                    segmentation_id)
        self.drv.create_network_precommit(network_context)

        net_provisioned = self.storage_drv.is_network_provisioned(tenant_id,
                                                                  network_id)

        self.assertTrue(net_provisioned, 'The network should be created')

        expected_num_nets = 1
        num_nets_provisioned = self.storage_drv.num_nets_provisioned(tenant_id)

        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

        #Now test the delete network
        self.drv.delete_network_precommit(network_context)

        net_provisioned = self.storage_drv.is_network_provisioned(tenant_id,
                                                                  network_id)

        self.assertFalse(net_provisioned, 'The network should be created')

        expected_num_nets = 0
        num_nets_provisioned = self.storage_drv.num_nets_provisioned(tenant_id)
        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

    def test_create_and_delete_multiple_networks(self):
        tenant_id = 'ten-1'
        expected_num_nets = 100
        segmentation_id = 1001
        host_id = 'ubuntu1'
        nets = ['id%s' % n for n in range(expected_num_nets)]
        for net_id in nets:
            network_context = self._get_network_context(tenant_id,
                                                        net_id,
                                                        segmentation_id)
            self.drv.create_network_precommit(network_context)

        num_nets_provisioned = self.storage_drv.num_nets_provisioned(tenant_id)

        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

        #now test the delete networks
        for net_id in nets:
            network_context = self._get_network_context(tenant_id,
                                                        net_id,
                                                        segmentation_id)
            self.drv.delete_network_precommit(network_context)

        num_nets_provisioned = self.storage_drv.num_nets_provisioned(tenant_id)
        expected_num_nets = 0
        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

    def test_create_and_delete_ports(self):
        tenant_id = 'ten-1'
        network_id = 'net1-id'
        segmentation_id = 1001
        vms = ['vm1', 'vm2', 'vm3']

        network_context = self._get_network_context(tenant_id,
                                                    network_id,
                                                    segmentation_id)
        self.drv.create_network_precommit(network_context)

        for vm_id in vms:
            port_context = self._get_port_context(tenant_id,
                                                  network_id,
                                                  vm_id,
                                                  network_context)
            self.drv.create_port_precommit(port_context)

        vm_list = self.storage_drv.get_vm_list(tenant_id)
        provisioned_vms = len(vm_list)
        expected_vms = len(vms)
        self.assertEqual(expected_vms, provisioned_vms,
                         'There should be %(expected_vms)d '
                         'hosts, not %(provisioned_vms)d' % locals())

        # Now test the delete ports
        for vm_id in vms:
            port_context = self._get_port_context(tenant_id,
                                                  network_id,
                                                  vm_id,
                                                  network_context)
            self.drv.delete_port_precommit(port_context)

        vm_list = self.storage_drv.get_vm_list(tenant_id)
        provisioned_vms = len(vm_list)
        expected_vms = 0
        self.assertEqual(expected_vms, provisioned_vms,
                         'There should be %(expected_vms)d '
                         'hosts, not %(provisioned_vms)d' % locals())

    def _get_network_context(self, tenant_id, net_id, seg_id):
        network = {'id': net_id,
                   'tenant_id': tenant_id}
        network_segments = [{'segmentation_id': seg_id}]
        return FakeNetworkContext(network, network_segments, network)

    def _get_port_context(self, tenant_id, net_id, vm_id, network):
        port = {'device_id': vm_id,
                'device_owner': 'compute',
                'binding:host_id': 'ubuntu1',
                'tenant_id': tenant_id,
                'id': 101,
                'network_id': net_id
                }
        return FakePortContext(port, port, network)


class fake_keystone_info_class:
    auth_protocol = 'abc'
    auth_host = 'host'
    auth_port = 5000
    admin_user = 'neutron'
    admin_password = 'fun'


class FakeNetworkContext():
    """To generate network context for testing purposes only."""

    def __init__(self, network, segments=None, original_network=None):
        self._network = network
        self._original_network = original_network
        self._segments = segments

    def current(self):
        return self._network

    def original(self):
        return self._original_network

    def network_segments(self):
        return self._segments


class FakePortContext():
    """To generate port context for testing purposes only."""

    def __init__(self, port, original_port, network):
        self._port = port
        self._original_port = original_port
        self._network_context = network

    def current(self):
        return self._port

    def original(self):
        return self._original_port

    def network(self):
        return self._network_context
