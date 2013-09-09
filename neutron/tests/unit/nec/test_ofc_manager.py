# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 NEC Corporation.  All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
# @author: Ryota MIBU

import mock

from neutron import context
from neutron.openstack.common import uuidutils
from neutron.plugins.nec.common import config
from neutron.plugins.nec.db import api as ndb
from neutron.plugins.nec.db import models as nmodels  # noqa
from neutron.plugins.nec import ofc_manager
from neutron.tests import base


class FakePortInfo(object):
    def __init__(self, id, datapath_id, port_no=0,
                 vlan_id=65535, mac='00:11:22:33:44:55'):
        self.data = {'id': id, 'datapath_id': datapath_id,
                     'port_no': port_no, 'vlan_id': vlan_id, 'mac': mac}

    def __getattr__(self, name):
        if name in self.fields:
            return self[name]
        else:
            raise AttributeError(name)


class OFCManagerTestBase(base.BaseTestCase):
    """Class conisting of OFCManager unit tests."""

    def setUp(self):
        super(OFCManagerTestBase, self).setUp()
        driver = "neutron.tests.unit.nec.stub_ofc_driver.StubOFCDriver"
        config.CONF.set_override('driver', driver, 'OFC')
        ndb.initialize()
        self.addCleanup(ndb.clear_db)
        self.ofc = ofc_manager.OFCManager()
        self.ctx = context.get_admin_context()
        self.addCleanup(mock.patch.stopall)

    def get_random_params(self):
        """create random parameters for portinfo test."""
        tenant = uuidutils.generate_uuid()
        network = uuidutils.generate_uuid()
        port = uuidutils.generate_uuid()
        _filter = uuidutils.generate_uuid()
        none = uuidutils.generate_uuid()
        return tenant, network, port, _filter, none


class OFCManagerTest(OFCManagerTestBase):
    def testa_create_ofc_tenant(self):
        """test create ofc_tenant."""
        t, n, p, f, none = self.get_random_params()
        self.assertFalse(ndb.get_ofc_item(self.ctx.session, 'ofc_tenant', t))
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session, 'ofc_tenant', t))
        tenant = ndb.get_ofc_item(self.ctx.session, 'ofc_tenant', t)
        self.assertEqual(tenant.ofc_id, "ofc-" + t[:-4])

    def testb_exists_ofc_tenant(self):
        """test exists_ofc_tenant."""
        t, n, p, f, none = self.get_random_params()
        self.assertFalse(self.ofc.exists_ofc_tenant(self.ctx, t))
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.assertTrue(self.ofc.exists_ofc_tenant(self.ctx, t))

    def testc_delete_ofc_tenant(self):
        """test delete ofc_tenant."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session, 'ofc_tenant', t))
        self.ofc.delete_ofc_tenant(self.ctx, t)
        self.assertFalse(ndb.get_ofc_item(self.ctx.session, 'ofc_tenant', t))

    def testd_create_ofc_network(self):
        """test create ofc_network."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.assertFalse(ndb.get_ofc_item(self.ctx.session, 'ofc_network', n))
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session, 'ofc_network', n))
        network = ndb.get_ofc_item(self.ctx.session, 'ofc_network', n)
        self.assertEqual(network.ofc_id, "ofc-" + n[:-4])

    def teste_exists_ofc_network(self):
        """test exists_ofc_network."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.assertFalse(self.ofc.exists_ofc_network(self.ctx, n))
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertTrue(self.ofc.exists_ofc_network(self.ctx, n))

    def testf_delete_ofc_network(self):
        """test delete ofc_network."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session, 'ofc_network', n))
        self.ofc.delete_ofc_network(self.ctx, n, {'tenant_id': t})
        self.assertFalse(ndb.get_ofc_item(self.ctx.session, 'ofc_network', n))

    def _mock_get_portinfo(self, port_id, datapath_id='0xabc', port_no=1):
        get_portinfo = mock.patch.object(ndb, 'get_portinfo').start()
        fake_portinfo = FakePortInfo(id=port_id, datapath_id=datapath_id,
                                     port_no=port_no)
        get_portinfo.return_value = fake_portinfo
        return get_portinfo

    def testg_create_ofc_port(self):
        """test create ofc_port."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertFalse(ndb.get_ofc_item(self.ctx.session, 'ofc_port', p))
        get_portinfo = self._mock_get_portinfo(p)
        port = {'tenant_id': t, 'network_id': n}
        self.ofc.create_ofc_port(self.ctx, p, port)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session, 'ofc_port', p))
        port = ndb.get_ofc_item(self.ctx.session, 'ofc_port', p)
        self.assertEqual(port.ofc_id, "ofc-" + p[:-4])
        get_portinfo.assert_called_once_with(mock.ANY, p)

    def testh_exists_ofc_port(self):
        """test exists_ofc_port."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertFalse(self.ofc.exists_ofc_port(self.ctx, p))
        get_portinfo = self._mock_get_portinfo(p)
        port = {'tenant_id': t, 'network_id': n}
        self.ofc.create_ofc_port(self.ctx, p, port)
        self.assertTrue(self.ofc.exists_ofc_port(self.ctx, p))
        get_portinfo.assert_called_once_with(mock.ANY, p)

    def testi_delete_ofc_port(self):
        """test delete ofc_port."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        get_portinfo = self._mock_get_portinfo(p)
        port = {'tenant_id': t, 'network_id': n}
        self.ofc.create_ofc_port(self.ctx, p, port)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session, 'ofc_port', p))
        self.ofc.delete_ofc_port(self.ctx, p, port)
        self.assertFalse(ndb.get_ofc_item(self.ctx.session, 'ofc_port', p))
        get_portinfo.assert_called_once_with(mock.ANY, p)

    def testj_create_ofc_packet_filter(self):
        """test create ofc_filter."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertFalse(ndb.get_ofc_item(self.ctx.session,
                                          'ofc_packet_filter', f))
        pf = {'tenant_id': t, 'network_id': n}
        self.ofc.create_ofc_packet_filter(self.ctx, f, pf)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session,
                                         'ofc_packet_filter', f))
        _filter = ndb.get_ofc_item(self.ctx.session, 'ofc_packet_filter', f)
        self.assertEqual(_filter.ofc_id, "ofc-" + f[:-4])

    def testk_exists_ofc_packet_filter(self):
        """test exists_ofc_packet_filter."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        self.assertFalse(self.ofc.exists_ofc_packet_filter(self.ctx, f))
        pf = {'tenant_id': t, 'network_id': n}
        self.ofc.create_ofc_packet_filter(self.ctx, f, pf)
        self.assertTrue(self.ofc.exists_ofc_packet_filter(self.ctx, f))

    def testl_delete_ofc_packet_filter(self):
        """test delete ofc_filter."""
        t, n, p, f, none = self.get_random_params()
        self.ofc.create_ofc_tenant(self.ctx, t)
        self.ofc.create_ofc_network(self.ctx, t, n)
        pf = {'tenant_id': t, 'network_id': n}
        self.ofc.create_ofc_packet_filter(self.ctx, f, pf)
        self.assertTrue(ndb.get_ofc_item(self.ctx.session,
                                         'ofc_packet_filter', f))
        self.ofc.delete_ofc_packet_filter(self.ctx, f)
        self.assertFalse(ndb.get_ofc_item(self.ctx.session,
                                          'ofc_packet_filter', f))


class OFCManagerTestWithOldMapping(OFCManagerTestBase):

    def test_exists_ofc_tenant(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_tenant(self.ctx, t))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_tenant', t, ofc_t, old_style=True)
        self.assertTrue(self.ofc.exists_ofc_tenant(self.ctx, t))

    def test_delete_ofc_tenant(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_tenant(self.ctx, t))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_tenant', t, ofc_t, old_style=True)
        self.assertTrue(self.ofc.exists_ofc_tenant(self.ctx, t))

        self.ofc.delete_ofc_tenant(self.ctx, t)
        self.assertFalse(self.ofc.exists_ofc_tenant(self.ctx, t))

    def test_exists_ofc_network(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_network(self.ctx, n))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_network', n, ofc_n, old_style=True)
        self.assertTrue(self.ofc.exists_ofc_network(self.ctx, n))

    def test_delete_ofc_network(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_network(self.ctx, n))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_network', n, ofc_n, old_style=True)
        self.assertTrue(self.ofc.exists_ofc_network(self.ctx, n))

        net = {'tenant_id': t}
        self.ofc.delete_ofc_network(self.ctx, n, net)
        self.assertFalse(self.ofc.exists_ofc_network(self.ctx, n))

    def test_exists_ofc_port(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_port(self.ctx, p))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_port', p, ofc_p, old_style=True)
        self.assertTrue(self.ofc.exists_ofc_port(self.ctx, p))

    def test_delete_ofc_port(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_port(self.ctx, p))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_port', p, ofc_p, old_style=True)
        self.assertTrue(self.ofc.exists_ofc_port(self.ctx, p))

        port = {'tenant_id': t, 'network_id': n}
        self.ofc.delete_ofc_port(self.ctx, p, port)
        self.assertFalse(self.ofc.exists_ofc_port(self.ctx, p))

    def test_exists_ofc_packet_filter(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_packet_filter(self.ctx, f))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_packet_filter', f, ofc_f,
                         old_style=True)
        self.assertTrue(self.ofc.exists_ofc_packet_filter(self.ctx, f))

    def test_delete_ofc_packet_filter(self):
        t, n, p, f, none = self.get_random_params()
        ofc_t, ofc_n, ofc_p, ofc_f, ofc_none = self.get_random_params()

        self.assertFalse(self.ofc.exists_ofc_packet_filter(self.ctx, f))

        session = self.ctx.session
        ndb.add_ofc_item(session, 'ofc_packet_filter', f, ofc_f,
                         old_style=True)
        self.assertTrue(self.ofc.exists_ofc_packet_filter(self.ctx, f))

        self.ofc.delete_ofc_packet_filter(self.ctx, f)
        self.assertFalse(self.ofc.exists_ofc_packet_filter(self.ctx, f))
