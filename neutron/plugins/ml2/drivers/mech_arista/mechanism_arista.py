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

import jsonrpclib
import threading

from neutron.openstack.common import log as logging
from neutron.plugins.ml2 import driver_api
from neutron.plugins.ml2.drivers.mech_arista import config  # noqa
from neutron.plugins.ml2.drivers.mech_arista import db
from neutron.plugins.ml2.drivers.mech_arista import exceptions as arista_exc
from oslo.config import cfg


LOG = logging.getLogger(__name__)


class AristaRPCWrapper(object):
    """Wraps Arista JSON RPC.

    All communications between Neutron and EOS are over JSON RPC.
    EOS - operating system used on Arista hardware
    Command API - JSON RPC API provided by Arista EOS
    """
    required_options = ['eapi_username',
                        'eapi_password',
                        'eapi_host']

    def __init__(self):
        self._server = jsonrpclib.Server(self._eapi_host_url())
        self.keystone_conf = cfg.CONF.keystone_authtoken
        self.region = cfg.CONF.ARISTA_DRIVER.region_name

    def _keystone_url(self):
        keystone_auth_url = '%s://%s:%s/v2.0/' % \
                            (self.keystone_conf.auth_protocol,
                             self.keystone_conf.auth_host,
                             self.keystone_conf.auth_port)
        return keystone_auth_url

    def get_tenants_list(self):
        """Returns dict of all tanants known by EOS.

        :returns: dictionary containing the networks per tenant
                  and VMs allocated per tenant
        """
        cmds = ['show openstack config region %s' % self.region]
        command_output = self._run_openstack_cmds(cmds)
        tenants = command_output[0]['tenants']

        return tenants

    def plug_host_into_network(self, vm_id, host, port_id,
                               network_id, tenant_id, port_name):
        """Creates VLAN between TOR and compute host.

        :param vm_id: globally unique identifier for VM instance
        :param host: ID of the host where the VM is placed
        :param port_id: globally unique port ID that connects VM to network
        :param network_id: globally unique neutron network identifier
        :param tenant_id: globally unique neutron tenant identifier
        :param port_name: Name of the port - for display purposes
        """
        cmds = ['tenant %s' % tenant_id,
                'vm id %s hostid %s' % (vm_id, host)]
        if port_name:
            cmds.append('port id %s name %s network-id %s' %
                        (port_id, port_name, network_id))
        else:
            cmds.append('port id %s network-id %s' %
                        (port_id, network_id))
        cmds.append('exit')
        cmds.append('exit')
        self._run_openstack_cmds(cmds)

    def unplug_host_from_network(self, vm_id, host, port_id,
                                 network_id, tenant_id):
        """Removes previously configured VLAN between TOR and a host.

        :param vm_id: globally unique identifier for VM instance
        :param host: ID of the host where the VM is placed
        :param port_id: globally unique port ID that connects VM to network
        :param network_id: globally unique neutron network identifier
        :param tenant_id: globally unique neutron tenant identifier
        """
        cmds = ['tenant %s' % tenant_id,
                'vm id %s host %s' % (vm_id, host),
                'no port id %s network-id %s' % (port_id, network_id),
                'exit',
                'exit']
        self._run_openstack_cmds(cmds)

    def create_network(self, tenant_id, network_id, network_name, seg_id):
        """Creates a network on Arista Hardware

        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        :param network_name: Network name - for display purposes
        :param seg_id: Segment ID of the network
        """
        cmds = ['tenant %s' % tenant_id]
        if network_name:
            cmds.append('network id %s name %s' % (network_id, network_name))
        else:
            cmds.append('network id %s' % (network_id))
        cmds.append('segment 1 type vlan id %d' % seg_id)
        cmds.append('exit')
        cmds.append('exit')
        cmds.append('exit')

        self._run_openstack_cmds(cmds)

    def create_network_segments(self, tenant_id, network_id,
                                network_name, segments):
        """Creates a network on Arista Hardware

        Note: This method is not used at the moment. create_network()
        is used instead. This will be used once the support for
        multiple segments is added in Neutron.

        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        :param network_name: Network name - for display purposes
        :param segments: List of segments in a given network
        """
        if segments:
            cmds = ['tenant %s' % tenant_id,
                    'network id %s name %s' % (network_id, network_name)]
            seg_num = 1
            for seg in segments:
                cmds.append('segment %d type %s id %d' % (seg_num,
                            seg['network_type'], seg['segmentation_id']))
                seg_num = seg_num + 1
            cmds.append('exit')  # exit for segment mode
            cmds.append('exit')  # exit for network mode
            cmds.append('exit')  # exit for tenant mode

            self._run_openstack_cmds(cmds)

    def delete_network(self, tenant_id, network_id):
        """Deletes a specified network for a given tenant

        :param tenant_id: globally unique neutron tenant identifier
        :param network_id: globally unique neutron network identifier
        """
        cmds = ['tenant %s' % tenant_id,
                'no network id %s' % network_id,
                'exit',
                'exit']
        self._run_openstack_cmds(cmds)

    def delete_vm(self, tenant_id, vm_id):
        """Deletes a VM from EOS for a given tenant

        :param tenant_id : globally unique neutron tenant identifier
        :param vm_id : id of a VM that needs to be deleted.
        """
        cmds = ['tenant %s' % tenant_id,
                'no vm id %s' % vm_id,
                'exit',
                'exit']
        self._run_openstack_cmds(cmds)

    def delete_tenant(self, tenant_id):
        """Deletes a given tenant and all its networks and VMs from EOS.

        :param tenant_id: globally unique neutron tenant identifier
        """
        cmds = ['no tenant %s' % tenant_id, 'exit']
        self._run_openstack_cmds(cmds)

    def delete_this_region(self):
        """Deletes this entire region from EOS.

        This is equivalent of unregistering this Neurtron stack from EOS
        All networks for all tenants are removed.
        """
        cmds = []
        self._run_openstack_cmds(cmds, deleteRegion=True)

    def _register_with_eos(self):
        """This is the registration request with EOS.

        This the initial handshake between Neutron and EOS.
        critical end-point information is registered with EOS.
        """
        cmds = ['auth url %s user %s password %s' %
                (self._keystone_url(),
                self.keystone_conf.admin_user,
                self.keystone_conf.admin_password)]

        self._run_openstack_cmds(cmds)

    def _run_openstack_cmds(self, commands, deleteRegion=None):

        command_start = ['enable', 'configure', 'management openstack']
        if deleteRegion:
            command_start.append('no region %s' % self.region)
        else:
            command_start.append('region %s' % self.region)
        command_end = ['exit', 'exit']
        full_command = command_start + commands + command_end

        LOG.info(_('Executing command on Arista EOS: %s'), full_command)

        ret = None

        try:
            # this returns array of return values for every command in
            # full_command list
            ret = self._server.runCmds(version=1, cmds=full_command)

            # Remove return values for 'configure terminal',
            # 'management openstack' and 'exit' commands
            ret = ret[len(command_start):-len(command_end)]
        except Exception as error:
            host = cfg.CONF.ARISTA_DRIVER.eapi_host
            msg = _('Error %(error)s while trying to execute commands '
                    '%(full_command)s on EOS %(host)s') % locals()
            LOG.error(msg)
            raise arista_exc.AristaRpcError(msg=msg)

        return ret

    def _eapi_host_url(self):
        self._validate_config()

        user = cfg.CONF.ARISTA_DRIVER.eapi_username
        pwd = cfg.CONF.ARISTA_DRIVER.eapi_password
        host = cfg.CONF.ARISTA_DRIVER.eapi_host

        eapi_server_url = ('https://%(user)s:%(pwd)s@%(host)s/command-api' %
                           locals())
        return eapi_server_url

    def _validate_config(self):
        for option in self.required_options:
            if cfg.CONF.ARISTA_DRIVER.get(option) is None:
                msg = _('Required option %s is not set') % option
                LOG.error(msg)
                raise arista_exc.AristaConfigError(msg=msg)


class SyncService(object):
    """Synchronizatin of information between Neutron and EOS

    Periodically (through configuration option), this service
    ensures that Networks and VMs configured on EOS/Arista HW
    are always in sync with Neutron DB.
    """
    def __init__(self, net_storage, rpc_wrapper, neutron_db):
        self._db = net_storage
        self._rpc = rpc_wrapper
        self._ndb = neutron_db

    def synchronize(self):
        """Sends data to EOS which differs from neutron DB."""

        LOG.info('Syncing Neutron  <-> EOS')
        try:
            eos_tenants = self._rpc.get_tenants_list()
        except arista_exc.AristaRpcError:
            msg = _('EOS is not available, will try sync later')
            LOG.warning(msg)
            return

        db_tenants = self._db.get_tenant_list()

        if not db_tenants and eos_tenants:
            # No tenants configured in Neutron. Clear all EOS state
            self._rpc.delete_this_region()
            msg = _('No Tenants configured in Neutron DB. But %d '
                    'tenants disovered in EOS during synchronization.'
                    'Enitre EOS region is cleared') % len(eos_tenants)
            LOG.warning(msg)
            return

        if len(eos_tenants) > len(db_tenants):
            # EOS has extra tenants configured which should not be there.
            for tenant in eos_tenants:
                if tenant not in db_tenants:
                    self._rpc.delete_tenant(tenant)

        # EOS and Neutron has matching set of tenants. Now check
        # to ensure that networks and VMs match on both sides for
        # each tenant.
        for tenant in db_tenants:
            neutron_nets = self._ndb._get_all_networks()
            neutron_ports = self._ndb._get_all_ports()
            db_net_list = self._db.get_network_list(tenant)
            db_vm_list = self._db.get_vm_list(tenant)
            eos_net_list = self._get_eos_network_list(eos_tenants, tenant)
            eos_vm_list = self._get_eos_vm_list(eos_tenants, tenant)

            # Check for the case if everything is already in sync.
            if eos_net_list == db_net_list:
                # Net list is same in both Neutron and EOS.
                # check the vM list
                if eos_vm_list == db_vm_list:
                    # Nothing to do. Everything is in sync for this tenant
                    break

            # Here if some sort of synchronization is required.

            # First delete anything which should not be EOS
            # delete VMs from EOS if it is not present in neutron DB
            for vm_id in eos_vm_list:
                if vm_id not in db_vm_list:
                    vm = eos_vm_list[vm_id]
                    self._rpc.delete_vm(tenant, vm_id)

            # delete network from EOS if it is not present in neutron DB
            for net_id in eos_net_list:
                if net_id not in db_net_list:
                    self._rpc.delete_network(tenant, net_id)

            # update networks in EOS if it is present in neutron DB
            for net_id in db_net_list:
                if net_id not in eos_net_list:
                    vlan_id = db_net_list[net_id]['segmentationTypeId']
                    net_name = self._get_network_name(neutron_nets, net_id)
                    self._rpc.create_network(tenant, net_id,
                                             net_name,
                                             vlan_id)

            # Update VMs in EOS if it is present in neutron DB
            for vm_id in db_vm_list:
                if vm_id not in eos_vm_list:
                    vm = db_vm_list[vm_id]
                    ports = self._get_ports_for_vm(neutron_ports, vm_id)
                    for port in ports:
                        port_id = port['id']
                        network_id = port['network_id']
                        port_name = port['name']
                        self._rpc.plug_host_into_network(vm['vmId'],
                                                         vm['host'],
                                                         port_id,
                                                         network_id,
                                                         tenant,
                                                         port_name)

    def _get_network_name(self, neutron_nets, network_id):
        network_name = None
        for network in neutron_nets:
            if network['id'] == network_id:
                network_name = network['name']
                break
        return network_name

    def _get_port_name(self, neutron_ports, port_id, network_id):
        port_name = None
        for port in neutron_ports:
            if port['id'] == port_id and port['network_id'] == network_id:
                port_name = port['name']
                break
        return port_name

    def _get_eos_network_list(self, eos_tenants, tenant):
        tenants = []
        if eos_tenants:
            tenants = eos_tenants[tenant]['tenantNetworks']
        return tenants

    def _get_eos_vm_list(self, eos_tenants, tenant):
        vms = []
        if eos_tenants:
            vms = eos_tenants[tenant]['tenantVmInstances']
        return vms

    def _get_ports_for_vm(self, neutron_ports, vm_id):
        ports = []
        for port in neutron_ports:
            if port['device_id'] == vm_id:
                ports.append(port)
        return ports


class AristaDriver(driver_api.MechanismDriver):
    """Ml2 Mechanism driver for Arista networking hardware.

    Remebers all networks and VMs that are provisioned on Arista Hardware.
    Does not send network provisioning request if the network has already been
    provisioned before for the given port.
    """

    def __init__(self, rpc=None, net_storage=db.ProvisionedNetsStorage()):

        if rpc is None:
            self.rpc = AristaRPCWrapper()
        else:
            self.rpc = rpc

        self.ndb = db.NeutronNets()

        self.net_storage = net_storage
        self.net_storage.initialize_db()

        confg = cfg.CONF.ARISTA_DRIVER
        self.segmentation_type = db.VLAN_SEGMENTATION
        self.eos = SyncService(self.net_storage, self.rpc, self.ndb)
        self.sync_timeout = confg['sync_interval']
        self.eos_sync_lock = threading.Lock()

        self._synchronization_thread()

    def initialize(self):
        self.rpc._register_with_eos()

    def create_network_precommit(self, context):
        """Remember the tenant, and network information."""

        network = context.current()
        segments = context.network_segments()
        network_id = network['id']
        tenant_id = network['tenant_id']
        segmentation_id = segments[0]['segmentation_id']
        with self.eos_sync_lock:
            self.net_storage.remember_tenant(tenant_id)
            self.net_storage.remember_network(tenant_id,
                                              network_id,
                                              segmentation_id)

    def create_network_postcommit(self, context):
        """Provision the network on the Arista Hardware."""

        network = context.current()
        network_id = network['id']
        network_name = network['name']
        tenant_id = network['tenant_id']
        segments = context.network_segments()
        vlan_id = segments[0]['segmentation_id']
        with self.eos_sync_lock:
            if self.net_storage.is_network_provisioned(tenant_id, network_id):
                try:
                    self.rpc.create_network(tenant_id,
                                            network_id,
                                            network_name,
                                            vlan_id)
                except arista_exc.AristaRpcError:
                    msg = _('Unable to reach EOS, will update it\'s state '
                            'during synchronization')
                    LOG.info(msg)

    def update_network_precommit(self, context):
        """At the moment we only support network name change

        Any other change in network is not supprted at this time.
        We do not store the network names, therefore, no DB store
        action is performed here.
        """
        new_network = context.current()
        orig_network = context.original()
        if new_network['name'] != orig_network['name']:
            msg = _('Network name changed to %s') % new_network['name']
            LOG.info(msg)

    def update_network_postcommit(self, context):
        """At the moment we only support network name change

        If network name is changed, a new network create request is
        sent to the Arista Hardware.
        """
        new_network = context.current()
        orig_network = context.original()
        if new_network['name'] != orig_network['name']:
            network_id = new_network['id']
            network_name = new_network['name']
            tenant_id = new_network['tenant_id']
            vlan_id = new_network['provider:segmentation_id']
            with self.eos_sync_lock:
                if self.net_storage.is_network_provisioned(tenant_id,
                                                           network_id):
                    try:
                        self.rpc.create_network(tenant_id,
                                                network_id,
                                                network_name,
                                                vlan_id)
                    except arista_exc.AristaRpcError:
                        msg = _('Unable to reach EOS, will update it\'s state '
                                'during synchronization')
                        LOG.info(msg)

    def delete_network_precommit(self, context):
        """Delete the network infromation from the DB."""

        network = context.current()
        network_id = network['id']
        tenant_id = network['tenant_id']
        with self.eos_sync_lock:
            if self.net_storage.is_network_provisioned(tenant_id, network_id):
                self.net_storage.forget_network(tenant_id, network_id)

    def delete_network_postcommit(self, context):
        """Send network delete request to Arista HW."""

        network = context.current()
        network_id = network['id']
        tenant_id = network['tenant_id']
        with self.eos_sync_lock:
            # Succeed deleting network in case EOS is not accessible.
            # EOS state will be updated by sync thread once EOS gets
            # alive.
            try:
                self.rpc.delete_network(tenant_id, network_id)
            except arista_exc.AristaRpcError:
                msg = _('Unable to reach EOS, will update it\'s state '
                        'during synchronization')
                LOG.info(msg)

    def create_port_precommit(self, context):
        """Remember the infromation about a VM and its ports

        A VM information, along with the physical host information
        is saved.
        """
        port = context.current()
        device_id = port['device_id']
        device_owner = port['device_owner']

        # TODO(sukhdev) revisit this once port biniding support is implemented
        host = port['binding:host_id']

        # device_id and device_owner are set on VM boot
        is_vm_boot = device_id and device_owner
        if host and is_vm_boot:
            port_id = port['id']
            network_id = port['network_id']
            tenant_id = port['tenant_id']
            with self.eos_sync_lock:
                self.net_storage.remember_vm(device_id, host, port_id,
                                             network_id, tenant_id)

    def create_port_postcommit(self, context):
        """Plug a physical host into a network.

        Send provisioning request to Arista Hardware to plug a host
        into appropriate network.
        """
        port = context.current()
        device_id = port['device_id']
        device_owner = port['device_owner']

        # TODO(sukhdev) revisit this once port biniding support is implemented
        host = port['binding:host_id']

        # device_id and device_owner are set on VM boot
        is_vm_boot = device_id and device_owner
        if host and is_vm_boot:
            port_id = port['id']
            port_name = port['name']
            network_id = port['network_id']
            tenant_id = port['tenant_id']
            try:
                with self.eos_sync_lock:
                    s = self.net_storage
                    hostname = self._host_name(host)
                    segmentation_id = s.get_segmentation_id(tenant_id,
                                                            network_id)
                    vm_provisioned = s.is_vm_provisioned(device_id,
                                                         host,
                                                         port_id,
                                                         network_id,
                                                         tenant_id)
                    net_provisioned = s.is_network_provisioned(tenant_id,
                                                               network_id,
                                                               segmentation_id)
                    if vm_provisioned and net_provisioned:
                        self.rpc.plug_host_into_network(device_id,
                                                        hostname,
                                                        port_id,
                                                        network_id,
                                                        tenant_id,
                                                        port_name)
            except arista_exc.AristaRpcError:
                msg = _('Unable to reach EOS, will update it\'s state '
                        'during synchronization')
                LOG.info(msg)

    def update_port_precommit(self, context):
        # TODO(sukhdev) revisit once the port binding support is implemented
        return

    def update_port_postcommit(self, context):
        # TODO(sukhdev) revisit once the port binding support is implemented
        return

    def delete_port_precommit(self, context):
        """Delete information about a VM and host from the DB."""

        port = context.current()

        # TODO(sukhdev) revisit this once port biniding support is implemented
        host_id = port['binding:host_id']
        device_id = port['device_id']
        tenant_id = port['tenant_id']
        network_id = port['network_id']
        port_id = port['id']
        with self.eos_sync_lock:
            if self.net_storage.is_vm_provisioned(device_id, host_id, port_id,
                                                  network_id, tenant_id):
                self.net_storage.forget_vm(device_id, host_id, port_id,
                                           network_id, tenant_id)

    def delete_port_postcommit(self, context):
        """unPlug a physical host from a network.

        Send provisioning request to Arista Hardware to unplug a host
        from appropriate network.
        """
        port = context.current()
        device_id = port['device_id']

        # TODO(sukhdev) revisit this once port biniding support is implemented
        host = port['binding:host_id']

        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']

        try:
            with self.eos_sync_lock:
                hostname = self._host_name(host)
                self.rpc.unplug_host_from_network(device_id,
                                                  hostname,
                                                  port_id,
                                                  network_id,
                                                  tenant_id)
        except arista_exc.AristaRpcError:
            msg = _('Unable to reach EOS, will update it\'s state '
                    'during synchronization')
            LOG.info(msg)
        return

    def _host_name(self, hostname):
        fqdns_used = cfg.CONF.ARISTA_DRIVER['use_fqdn']
        return hostname if fqdns_used else hostname.split('.')[0]

    def _synchronization_thread(self):
        with self.eos_sync_lock:
            self.eos.synchronize()

        t = threading.Timer(self.sync_timeout, self._synchronization_thread)
        t.start()

    def _vlans_used(self):
        return self._segm_type_used(db.VLAN_SEGMENTATION)

    def _segm_type_used(self, segm_type):
        return self.segmentation_type == segm_type
