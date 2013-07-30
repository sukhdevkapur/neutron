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

import copy
import mock

from neutron.plugins.ml2.drivers import mechanism_arista as arista
from neutron.tests import base
from oslo.config import cfg


def clear_config():
    cfg.CONF.clear()


def setup_arista_wrapper_config(value=None):
    for opt in arista.AristaRPCWrapper.required_options:
        cfg.CONF.set_override(opt, value, "ARISTA_DRIVER")


def setup_valid_config():
    # Config is not valid if value is not set
    setup_arista_wrapper_config('value')


class AristaProvisionedVlansStorageTestCase(base.BaseTestCase):
    """Test storing and retriving functionality of Arista mechanism driver.

    Tests all methods of this class by invoking them seperately as well
    as a goup.
    """

    def setUp(self):
        super(AristaProvisionedVlansStorageTestCase, self).setUp()
        self.drv = arista.ProvisionedNetsStorage()
        self.drv.initialize_db()

    def tearDown(self):
        super(AristaProvisionedVlansStorageTestCase, self).tearDown()
        self.drv.tear_down()

    def test_network_is_remembered(self):
        network_id = '123'
        segmentation_id = 456
        host_id = 'host123'

        self.drv.remember_host(network_id, segmentation_id, host_id)
        net_provisioned = self.drv.is_network_provisioned(network_id)
        self.assertTrue(net_provisioned, 'Network must be provisioned')

    def test_network_is_removed(self):
        network_id = '123'
        segmentation_id = 456

        self.drv.remember_network(network_id, segmentation_id)
        self.drv.forget_network(network_id)

        net_provisioned = self.drv.is_network_provisioned(network_id)

        self.assertFalse(net_provisioned, 'The network should be deleted')

    def test_remembers_multiple_networks(self):
        expected_num_nets = 100
        nets = ['id%s' % n for n in range(expected_num_nets)]
        for net_id in nets:
            self.drv.remember_network(net_id, 123)
            self.drv.remember_host(net_id, 123, 'host')

        num_nets_provisioned = len(self.drv.get_all())

        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

    def test_removes_all_networks(self):
        num_nets = 100
        nets = ['id%s' % n for n in range(num_nets)]
        host_id = 'host123'
        for net_id in nets:
            self.drv.remember_network(net_id, 123)
            self.drv.remember_host(net_id, 123, host_id)
            self.drv.forget_host(net_id, host_id)

        num_nets_provisioned = self.drv.num_nets_provisioned()
        expected = 0

        self.assertEqual(expected, num_nets_provisioned,
                         'There should be %(expected)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

    def test_network_is_not_deleted_on_forget_host(self):
        network_id = '123'
        vlan_id = 123
        host1_id = 'host1'
        host2_id = 'host2'

        self.drv.remember_network(network_id, vlan_id)
        self.drv.remember_host(network_id, vlan_id, host1_id)
        self.drv.remember_host(network_id, vlan_id, host2_id)
        self.drv.forget_host(network_id, host2_id)

        net_provisioned = (self.drv.is_network_provisioned(network_id) and
                           self.drv.is_network_provisioned(network_id,
                                                           vlan_id,
                                                           host1_id))

        self.assertTrue(net_provisioned, 'The network should not be deleted')

    def test_net_is_not_stored_on_delete(self):
        network_id = '123'
        vlan_id = 123
        removed_host = 'removed_host'
        avail_host = 'available_host'

        self.drv.remember_network(network_id, vlan_id)
        self.drv.remember_host(network_id, vlan_id, removed_host)
        self.drv.remember_host(network_id, vlan_id, avail_host)
        self.drv.forget_host(network_id, removed_host)

        network_is_available = self.drv.is_network_provisioned(network_id)
        removed_host_is_available = (self.drv.
                                     is_network_provisioned(network_id,
                                                            vlan_id,
                                                            removed_host))

        self.assertTrue(network_is_available,
                        'The network should stay available')
        self.assertFalse(removed_host_is_available,
                         '%(removed_host)s should not be available' % locals())

    def test_num_networks_is_valid(self):
        network_id = '123'
        vlan_id = 123
        hosts_to_remember = ['host1', 'host2', 'host3']
        hosts_to_forget = ['host2', 'host1']

        self.drv.remember_network(network_id, vlan_id)
        for host in hosts_to_remember:
            self.drv.remember_host(network_id, vlan_id, host)
        for host in hosts_to_forget:
            self.drv.forget_host(network_id, host)

        num_hosts = self.drv.num_hosts_for_net(network_id)
        expected = len(hosts_to_remember) - len(hosts_to_forget)

        self.assertEqual(expected, num_hosts,
                         'There should be %(expected)d records, '
                         'got %(num_hosts)d records' % locals())

    def test_get_network_list_returns_eos_compatible_data(self):
        segm_type = 'vlan'
        network_id = '123'
        network2_id = '1234'
        vlan_id = 123
        vlan2_id = 1234
        hosts_net1 = ['host1', 'host2', 'host3']
        hosts_net2 = ['host1']
        expected_eos_net_list = {network_id: {'name': network_id,
                                              'hostId': hosts_net1,
                                              'segmentationId': vlan_id,
                                              'segmentationType': segm_type},
                                 network2_id: {'name': network2_id,
                                               'hostId': hosts_net2,
                                               'segmentationId': vlan2_id,
                                               'segmentationType': segm_type}}

        self.drv.remember_network(network_id, vlan_id)
        for host in hosts_net1:
            self.drv.remember_host(network_id, vlan_id, host)
        self.drv.remember_network(network2_id, vlan2_id)
        for host in hosts_net2:
            self.drv.remember_host(network2_id, vlan2_id, host)

        net_list = self.drv.get_network_list()

        self.assertTrue(net_list == expected_eos_net_list,
                        ('%(net_list)s != %(expected_eos_net_list)s' %
                         locals()))


class PositiveRPCWrapperValidConfigTestCase(base.BaseTestCase):
    """Test cases to test the RPC between Arista Driver and EOS.

    Tests all methods used to send commands between Arista Driver and EOS
    """

    def setUp(self):
        super(PositiveRPCWrapperValidConfigTestCase, self).setUp()
        setup_valid_config()
        self.drv = arista.AristaRPCWrapper()
        self.drv._server = mock.MagicMock()

    def tearDown(self):
        super(PositiveRPCWrapperValidConfigTestCase, self).tearDown()
        clear_config()

    def test_no_exception_on_correct_configuration(self):
        self.assertNotEqual(self.drv, None)

    def test_plug_host_into_vlan_calls_rpc(self):
        network_id = 'net-id'
        vlan_id = 123
        host = 'host'

        self.drv.plug_host_into_vlan(network_id, vlan_id, host)
        cmds = ['enable', 'configure', 'management openstack',
                'tenant-network net-id', 'type vlan id 123 host host',
                'type vlan id 123 host ubuntu', 'exit']

        self.drv._server.runCmds.assert_called_once_with(version=1, cmds=cmds)

    def test_unplug_host_from_vlan_calls_rpc(self):
        network_id = 'net-id'
        vlan_id = 123
        host = 'host'
        self.drv.unplug_host_from_vlan(network_id, vlan_id, host)
        cmds = ['enable', 'configure', 'management openstack',
                'tenant-network net-id', 'no type vlan id 123 host host',
                'exit']
        self.drv._server.runCmds.assert_called_once_with(version=1, cmds=cmds)

    def test_delete_network_calls_rpc(self):
        network_id = 'net-id'
        self.drv.delete_network(network_id)
        cmds = ['enable', 'configure', 'management openstack',
                'no tenant-network net-id', 'exit']
        self.drv._server.runCmds.assert_called_once_with(version=1, cmds=cmds)

    def test_get_network_info_returns_none_when_no_such_net(self):
        unavailable_network_id = '12345'

        self.drv.get_network_list = mock.MagicMock()
        self.drv.get_network_list.return_value = []

        net_info = self.drv.get_network_info(unavailable_network_id)

        self.drv.get_network_list.assert_called_once_with()
        self.assertEqual(net_info, None, ('Network info must be "None"'
                                          'for unknown network'))

    def test_get_network_info_returns_info_for_available_net(self):
        valid_network_id = '12345'
        valid_net_info = {'network_id': valid_network_id,
                          'some_info': 'net info'}
        known_nets = [valid_net_info]

        self.drv.get_network_list = mock.MagicMock()
        self.drv.get_network_list.return_value = known_nets

        net_info = self.drv.get_network_info(valid_network_id)
        self.assertEqual(net_info, valid_net_info,
                         ('Must return network info for a valid net'))


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
        self.assertRaises(arista.AristaConfigError, arista.AristaRPCWrapper)


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

        self.assertRaises(arista.AristaRpcError, drv.get_network_list)


class KeepAliveServicTestCase(base.BaseTestCase):
    """Tests Sync facility of the Arista Driver.

    Tests the functionality which ensures that Arista Driver DB and EOS
    state is always in sync.
    """
    def setUp(self):
        super(KeepAliveServicTestCase, self).setUp()
        self.rpc = mock.Mock(spec=arista.AristaRPCWrapper)
        self.db = mock.Mock(spec=arista.ProvisionedNetsStorage)

        self.service = arista.SyncService(self.db, self.rpc)

    def test_network_gets_deleted_if_not_present_in_quantum_db(self):
        service = self.service

        eos_nets = ['net1-id', 'net2-id']
        eos_hosts = ['host1', 'host2']
        vlan_id = 123
        eos_data = self._eos_data_factory(eos_nets, eos_hosts, vlan_id)

        db_nets = ['net3-id', 'net4-id']
        db_hosts = ['host1', 'host2']
        vlan_id = 234
        db_data = self._eos_data_factory(db_nets, db_hosts, vlan_id)

        self.rpc.get_network_list.return_value = eos_data
        self.db.get_network_list.return_value = db_data

        service.synchronize()

        deleted_nets = []
        for net in eos_nets:
            if net not in db_nets:
                deleted_nets.append(net)

        expected_calls = [mock.call(net) for net in deleted_nets].sort()
        actual_calls = self.rpc.delete_network.call_args_list.sort()

        self.assertTrue(expected_calls == actual_calls, ('Expected '
                        '%(expected_calls)s, got %(actual_calls)s' % locals()))

    def test_synchronize_sends_missing_hosts_to_eos(self):
        service = self.service
        net_id = ['123']
        db_hosts = ['host1', 'host2', 'host3']
        eos_hosts = db_hosts[:1]
        missing_hosts = set(db_hosts) - set(eos_hosts)
        vlan_id = 123

        db_data = self._eos_data_factory(net_id, db_hosts, vlan_id)
        eos_data = self._eos_data_factory(net_id, eos_hosts, vlan_id)

        print db_data
        print eos_data

        self.db.get_network_list.return_value = db_data
        self.rpc.get_network_list.return_value = eos_data

        service.synchronize()

        expected_calls = []

        for host in missing_hosts:
            expected_calls.append(mock.call(net_id[0], vlan_id, host))

        provisioned_hosts = (self.rpc.plug_host_into_vlan.call_args_list ==
                             expected_calls)

        self.assertTrue(provisioned_hosts)

    def test_synchronize_sends_missing_networks_to_eos(self):
        service = self.service

        db_net_ids = ['123', '234', '345']
        eos_net_ids = db_net_ids[:1]
        missing_nets = set(db_net_ids) - set(eos_net_ids)

        db_hosts = ['host1', 'host2', 'host3']
        eos_hosts = copy.deepcopy(db_hosts)
        vlan_id = 123

        db_data = self._eos_data_factory(db_net_ids, db_hosts, vlan_id)
        eos_data = self._eos_data_factory(eos_net_ids, eos_hosts, vlan_id)

        self.db.get_network_list.return_value = db_data
        self.rpc.get_network_list.return_value = eos_data

        service.synchronize()

        expected_calls = []

        for net in missing_nets:
            for host in db_hosts:
                expected_calls.append(mock.call(net, vlan_id, host))

        provisioned_hosts = (self.rpc.plug_host_into_vlan.call_args_list ==
                             expected_calls)

        self.assertTrue(provisioned_hosts)

    def _eos_data_factory(self, nets, hosts, segm_id):
        data = {}

        for net in nets:
            data[net] = {'name': net,
                         'hostId': hosts,
                         'segmentationId': segm_id,
                         'segmentationType': 'vlan'}

        return data


class RealNetStorageAristaDriverTestCase(base.BaseTestCase):
    """Main test cases for Arista Mechanism driver.

    Tests all mechanism driver APIs supported by Arista Driver. It invokes
    all the APIs as they would be invoked in real world scenarios and
    verifies the functionality.
    """
    def setUp(self):
        super(RealNetStorageAristaDriverTestCase, self).setUp()
        self.fake_rpc = mock.MagicMock()
        self.net_storage = arista.ProvisionedNetsStorage()
        self.net_storage.initialize_db()
        self.drv = arista.AristaDriver(self.fake_rpc, self.net_storage)
        self.storage_drv = arista.ProvisionedNetsStorage()

    def tearDown(self):
        super(RealNetStorageAristaDriverTestCase, self).tearDown()
        self.net_storage.tear_down()
        cfg.CONF.clear()

    def test_create_and_delete_network(self):
        network_id = 'net1-id'
        segmentation_id = 1001

        network_context = self._get_network_context(network_id,
                                                    segmentation_id)
        self.drv.create_network_precommit(network_context)

        net_provisioned = self.storage_drv.is_network_provisioned(network_id)

        self.assertTrue(net_provisioned, 'The network should be created')

        expected_num_nets = 1
        num_nets_provisioned = self.storage_drv.num_nets_provisioned()

        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

        #Now test the delete network
        self.drv.delete_network_precommit(network_context)

        net_provisioned = self.storage_drv.is_network_provisioned(network_id)

        self.assertFalse(net_provisioned, 'The network should be created')

        expected_num_nets = 0
        num_nets_provisioned = self.storage_drv.num_nets_provisioned()
        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

    def test_create_and_delete_multiple_networks(self):
        expected_num_nets = 100
        segmentation_id = 1001
        host_id = 'ubuntu1'
        nets = ['id%s' % n for n in range(expected_num_nets)]
        for net_id in nets:
            network_context = self._get_network_context(net_id,
                                                        segmentation_id)
            self.drv.create_network_precommit(network_context)

        num_nets_provisioned = len(self.storage_drv.get_all())

        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

        #now test the delete networks
        for net_id in nets:
            network_context = self._get_network_context(net_id,
                                                        segmentation_id)
            self.drv.delete_network_precommit(network_context)

        num_nets_provisioned = len(self.storage_drv.get_all())
        expected_num_nets = 0
        self.assertEqual(expected_num_nets, num_nets_provisioned,
                         'There should be %(expected_num_nets)d '
                         'nets, not %(num_nets_provisioned)d' % locals())

    def test_create_and_delete_ports(self):
        network_id = 'net1-id'
        segmentation_id = 1001
        hosts = ['ubuntu1', 'ubuntu2', 'ubuntu3']

        network_context = self._get_network_context(network_id,
                                                    segmentation_id)
        self.drv.create_network_precommit(network_context)

        for host_id in hosts:
            port_context = self._get_port_context(network_id, host_id,
                                                  network_context)
            self.drv.create_port_precommit(port_context)

        provisioned_hosts = self.storage_drv.num_hosts_for_net(network_id)
        expected_hosts = len(hosts)
        self.assertEqual(expected_hosts, provisioned_hosts,
                         'There should be %(expected_hosts)d '
                         'hosts, not %(provisioned_hosts)d' % locals())

        # Now test the delete ports
        for host_id in hosts:
            port_context = self._get_port_context(network_id, host_id,
                                                  network_context)
            self.drv.delete_port_precommit(port_context)

        provisioned_hosts = self.storage_drv.num_hosts_for_net(network_id)
        expected_hosts = 0
        self.assertEqual(expected_hosts, provisioned_hosts,
                         'There should be %(expected_hosts)d '
                         'hosts, not %(provisioned_hosts)d' % locals())

    def _get_network_context(self, net_id, seg_id):
        network = {'id': net_id}
        network_segments = [{'segmentation_id': seg_id}]
        return FakeNetworkContext(network, network_segments, network)

    def _get_port_context(self, net_id, host_id, network):
        port = {'device_id': '123',
                'device_owner': 'compute',
                'binding:host_id': host_id,
                'network_id': net_id
                }
        return FakePortContext(port, port, network)


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
