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

import sqlalchemy as sa

from neutron import context as nctx
import neutron.db.api as db
from neutron.db import db_base_plugin_v2
from neutron.db import model_base
from neutron.db import models_v2

VLAN_SEGMENTATION = 'vlan'

UUID_LEN = 36
STR_LEN = 255


class ProvisionedNetsStorage(object):
    class AristaProvisionedNets(model_base.BASEV2, models_v2.HasId,
                                models_v2.HasTenant):
        """Stores networks provisioned on Arista EOS.

        Saves the segmentation ID for each network that is provisioned
        on EOS. This information is used during synchronization between
        Neutron and EOS.
        """
        __tablename__ = 'arista_provisioned_nets'

        network_id = sa.Column(sa.String(UUID_LEN))
        segmentation_id = sa.Column(sa.Integer)

        def __init__(self, tenant_id, network_id, segmentation_id=None):
            self.tenant_id = tenant_id
            self.network_id = network_id
            self.segmentation_id = segmentation_id

        def __repr__(self):
            r = "<AristaProvisionedNets(%s,%s,%d,%s)>" % (self.tenant_id,
                                                          self.network_id,
                                                          self.segmentation_id)
            return r

        def eos_network_representation(self, segmentation_type):
            return {u'networkId': self.network_id,
                    u'segmentationTypeId': self.segmentation_id,
                    u'segmentationType': segmentation_type}

    class AristaProvisionedVms(model_base.BASEV2, models_v2.HasId,
                               models_v2.HasTenant):
        """Stores VMs provisioned on Arista EOS.

        All VMs launched on physical hosts connected to Arista
        Switches are remembered
        """
        __tablename__ = 'arista_provisioned_vms'

        vm_id = sa.Column(sa.String(UUID_LEN))
        host_id = sa.Column(sa.String(STR_LEN))
        port_id = sa.Column(sa.String(UUID_LEN))
        network_id = sa.Column(sa.String(UUID_LEN))

        def __init__(self, vm_id, host_id, port_id, network_id, tenant_id):
            self.vm_id = vm_id
            self.host_id = host_id
            self.port_id = port_id
            self.network_id = network_id
            self.tenant_id = tenant_id

        def __repr__(self):
            return "<AristaProvisionedVms(%s,%s,%s,%s,%s)>" % (self.vm_id,
                                                               self.host_id,
                                                               self.port_id,
                                                               self.network_id,
                                                               self.tenant_id)

        def eos_vm_representation(self):
            return {u'vmId': self.vm_id,
                    u'host': self.host_id,
                    u'ports': {self.port_id: [{u'portId': self.port_id,
                                              u'networkId': self.network_id}]}}

        def eos_port_representation(self):
            return {u'vmId': self.vm_id,
                    u'host': self.host_id,
                    u'portId': self.port_id,
                    u'networkId': self.network_id}

    class AristaProvisionedTenants(model_base.BASEV2, models_v2.HasId,
                                   models_v2.HasTenant):
        """Stores Tenants provisioned on Arista EOS.

        Tenants list is maintained for sync between Neutron and EOS.
        """
        __tablename__ = 'arista_provisioned_tenants'

        def __init__(self, tenant_id):
            self.tenant_id = tenant_id

        def __repr__(self):
            return "<AristaProvisionedTenants(%s)>" % (self.tenant_id)

        def eos_tenant_representation(self):
            return {u'tenantId': self.tenant_id}

    def initialize_db(self):
        db.configure_db()

    def remember_tenant(self, tenant_id):
        """Stores a tenant information in repository.

        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            tenant = (session.query(self.AristaProvisionedTenants).
                      filter_by(tenant_id=tenant_id).first())

            if not tenant:
                tenant = self.AristaProvisionedTenants(tenant_id)
                session.add(tenant)

    def forget_tenant(self, tenant_id):
        """Removes a tenant information from repository.

        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            (session.query(self.AristaProvisionedTenants).
             filter_by(tenant_id=tenant_id).
             delete())

    def get_all_tenants(self):
        """Returns a list of all tenants stored in repository."""
        session = db.get_session()
        with session.begin():
            return session.query(self.AristaProvisionedTenants).all()

    def num_provisioned_tenants(self):
        """Returns number of tenants stored in repository."""
        session = db.get_session()
        with session.begin():
            return (session.query(self.AristaProvisionedTenants).count())

    def remember_vm(self, vm_id, host_id, port_id, network_id, tenant_id):
        """Stores all relevent information about a VM in repository.

        :param vm_id: globally unique identifier for VM instance
        :param host: ID of the host where the VM is placed
        :param port_id: globally unique port ID that connects VM to network
        :param network_id: globally unique neutron network identifier
        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            vm = (session.query(self.AristaProvisionedVms).
                  filter_by(vm_id=vm_id, host_id=host_id,
                            port_id=port_id, tenant_id=tenant_id,
                            network_id=network_id).first())

            if not vm:
                vm = self.AristaProvisionedVms(vm_id, host_id, port_id,
                                               network_id, tenant_id)
                session.add(vm)

    def forget_vm(self, vm_id, host_id, port_id, network_id, tenant_id):
        """Removes all relevent information about a VM from repository.

        :param vm_id: globally unique identifier for VM instance
        :param host: ID of the host where the VM is placed
        :param port_id: globally unique port ID that connects VM to network
        :param network_id: globally unique neutron network identifier
        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            (session.query(self.AristaProvisionedVms).
             filter_by(vm_id=vm_id, host_id=host_id,
                       port_id=port_id, tenant_id=tenant_id,
                       network_id=network_id).delete())

    def remember_network(self, tenant_id, network_id, segmentation_id):
        """Stores all relevent information about a Network in repository.

        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        :param segmentation_id: VLAN ID that is assigned to the network
        """
        session = db.get_session()
        with session.begin():
            net = (session.query(self.AristaProvisionedNets).
                   filter_by(tenant_id=tenant_id,
                             network_id=network_id).first())

            if not net:
                net = self.AristaProvisionedNets(tenant_id, network_id,
                                                 segmentation_id)
                session.add(net)

    def forget_network(self, tenant_id, network_id):
        """Deletes all relevent information about a Network from repository.

        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        """
        session = db.get_session()
        with session.begin():
            (session.query(self.AristaProvisionedNets).
             filter_by(tenant_id=tenant_id, network_id=network_id).
             delete())

    def get_segmentation_id(self, tenant_id, network_id):
        """Returns Segmentation ID (VLAN) associated with a network.

        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        """
        session = db.get_session()
        with session.begin():
            net = (session.query(self.AristaProvisionedNets).
                   filter_by(tenant_id=tenant_id,
                             network_id=network_id).first())
            return net and net.segmentation_id or None

    def is_vm_provisioned(self, vm_id, host_id, port_id,
                          network_id, tenant_id):
        """Checks if a VM is already known to EOS

        :returns: True, if yes; False otherwise.
        :param vm_id: globally unique identifier for VM instance
        :param host: ID of the host where the VM is placed
        :param port_id: globally unique port ID that connects VM to network
        :param network_id: globally unique neutron network identifier
        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            num_vm = (session.query(self.AristaProvisionedVms).
                      filter_by(tenant_id=tenant_id,
                                vm_id=vm_id,
                                port_id=port_id,
                                network_id=network_id,
                                host_id=host_id).count())
            return num_vm > 0

    def is_network_provisioned(self, tenant_id, network_id, seg_id=None):
        """Checks if a networks is already known to EOS

        :returns: True, if yes; False otherwise.
        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        :param seg_id: Optionally matches the segmentation ID (VLAN)
        """
        session = db.get_session()
        with session.begin():
            if not seg_id:
                num_nets = (session.query(self.AristaProvisionedNets).
                            filter_by(tenant_id=tenant_id,
                                      network_id=network_id).count())
            else:
                num_nets = (session.query(self.AristaProvisionedNets).
                            filter_by(tenant_id=tenant_id,
                                      network_id=network_id,
                                      segmentation_id=seg_id).count())
            return num_nets > 0

    def is_tenant_provisioned(self, tenant_id):
        """Checks if a tenant is already known to EOS

        :returns: True, if yes; False otherwise.
        :param tenant_id: globally unique neutron tenant identifier
        """
        num_tenants = 0
        session = db.get_session()
        with session.begin():
            num_tenants = (session.query(self.AristaProvisionedTenants).
                           filter_by(tenant_id=tenant_id).count())
        return num_tenants > 0

    def num_nets_provisioned(self, tenant_id):
        """Returns number of networks for a given tennat.

        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            return (session.query(self.AristaProvisionedNets).
                    filter_by(tenant_id=tenant_id).count())

    def get_networks(self, tenant_id):
        """Returns all networks for a given tenant in EOS-compatible format.

        See AristaRPCWrapper.get_network_list() for return value format.
        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            model = self.AristaProvisionedNets
            # hack for pep8 E711: comparison to None should be
            # 'if cond is not None'
            none = None
            all_nets = (session.query(model).
                        filter(model.tenant_id != none).
                        filter(model.segmentation_id != none))
            res = {}
            for net in all_nets:
                res[net.network_id] = net.eos_network_representation(
                    VLAN_SEGMENTATION)
            return res

    def get_vms(self, tenant_id):
        """Returns all VMs for a given tenant in EOS-compatible format.

        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            model = self.AristaProvisionedVms
            # hack for pep8 E711: comparison to None should be
            # 'if cond is not None'
            none = None
            all_vms = (session.query(model).
                       filter(model.tenant_id != none).
                       filter(model.host_id != none).
                       filter(model.vm_id != none).
                       filter(model.network_id != none).
                       filter(model.port_id != none))
            res = {}
            for vm in all_vms:
                res[vm.vm_id] = vm.eos_vm_representation()
            return res

    def get_ports(self, tenant_id):
        """Returns all ports of VMs in EOS-compatible format.

        :param tenant_id: globally unique neutron tenant identifier
        """
        session = db.get_session()
        with session.begin():
            model = self.AristaProvisionedVms
            # hack for pep8 E711: comparison to None should be
            # 'if cond is not None'
            none = None
            all_ports = (session.query(model).
                         filter(model.tenant_id != none).
                         filter(model.host_id != none).
                         filter(model.vm_id != none).
                         filter(model.network_id != none).
                         filter(model.port_id != none))
            res = {}
            for port in all_ports:
                res[port.port_id] = port.eos_port_representation()
            return res

    def get_tenants(self):
        """Returns list of all tenants in EOS-compatible format."""
        session = db.get_session()
        with session.begin():
            model = self.AristaProvisionedTenants
            all_tenants = session.query(model)
            res = {}
            for tenant in all_tenants:
                res[tenant.tenant_id] = tenant.eos_tenant_representation()
            return res


class NeutronNets(db_base_plugin_v2.NeutronDbPluginV2):
    """Access to Neutron DB.

    Provides access to the Neutron Data bases for all provisioned
    networks as well ports. This data is used during the synchronization
    of DB between ML2 Mechanism Driver and Arista EOS
    Names of the networks and ports are not stroed in Arista repository
    They are pulled from Neutron DB.
    """

    def __init__(self):
        self.admin_ctx = nctx.get_admin_context()

    def get_network_name(self, tenant_id, network_id):
        network = self._get_network(tenant_id, network_id)
        network_name = None
        if network:
            network_name = network[0]['name']
        return network_name

    def get_all_networks_for_tenant(self, tenant_id):
        filters = {'tenant_id': [tenant_id]}
        return super(NeutronNets,
                     self).get_networks(self.admin_ctx, filters=filters) or []

    def get_all_ports_for_tenant(self, tenant_id):
        filters = {'tenant_id': [tenant_id]}
        return super(NeutronNets,
                     self).get_ports(self.admin_ctx, filters=filters) or []

    def get_all_ports_for_vm(self, tenant_id, vm_id):
        filters = {'tenant_id': [tenant_id],
                   'device_id': [vm_id]}
        return super(NeutronNets,
                     self).get_ports(self.admin_ctx, filters=filters) or []

    def _get_network(self, tenant_id, network_id):
        filters = {'tenant_id': [tenant_id],
                   'id': [network_id]}
        return super(NeutronNets,
                     self).get_networks(self.admin_ctx, filters=filters) or []
