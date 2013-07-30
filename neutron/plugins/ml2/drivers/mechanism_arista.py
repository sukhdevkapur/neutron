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

import pdb
import threading

import jsonrpclib
import sqlalchemy
import socket

import neutron.db.api as db
from neutron.db import model_base
from oslo.config import cfg
from neutron.common import exceptions
from neutron.plugins.ml2 import driver_api
from neutron.openstack.common import log as logging

VLAN_SEGMENTATION = 'vlan'

LOG = logging.getLogger(__name__)


ARISTA_DRIVER_OPTS = [
    cfg.StrOpt('eapi_user',
               default=None,
               help=_('Username for Arista EOS')),
    cfg.StrOpt('eapi_pass',
               default=None,
               secret=True,  # do not expose value in the logs
               help=_('Password for Arista EOS')),
    cfg.StrOpt('eapi_host',
               default=None,
               help=_('Arista EOS host IP')),
    cfg.BoolOpt('use_fqdn',
                default=False,
                help=_('Defines if hostnames are sent to Arista EOS as FQDNs '
                       '("node1.domain.com") or as short names ("node1")')),
    cfg.IntOpt('sync_interval',
               default=10,
               help=_('Sync interval in seconds between Neutron plugin and '
                      'EOS'))
]

cfg.CONF.register_opts(ARISTA_DRIVER_OPTS, "ARISTA_DRIVER")


class AristaRpcError(exceptions.NeutronException):
    message = _('%(msg)s')


class AristaConfigError(exceptions.NeutronException):
    message = _('%(msg)s')

class ProvisionedNetsStorage(object):
    class AristaProvisionedNets(model_base.BASEV2):
        """
        Stores networks provisioned on Arista EOS. Limits the nubmer of RPC
        calls to the EOS command API in case network was provisioned before.
        """
        __tablename__ = 'arista_provisioned_nets'

        id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
        network_id = sqlalchemy.Column(sqlalchemy.String(36))
        segmentation_id = sqlalchemy.Column(sqlalchemy.Integer)
        host_id = sqlalchemy.Column(sqlalchemy.String(255))

        def __init__(self, network_id, segmentation_id=None, host_id=None):
            self.network_id = network_id
            self.segmentation_id = segmentation_id
            self.host_id = host_id
	    print  network_id, segmentation_id, host_id

        def __repr__(self):
            return "<AristaProvisionedNets(%s,%d,%s)>" % (self.network_id,
                                                          self.segmentation_id,
                                                          self.host_id)

        def eos_representation(self, segmentation_type):
            return {u'hostId': self.host_id,
                    u'name': self.network_id,
                    u'segmentationId': self.segmentation_id,
                    u'segmentationType': segmentation_type}

    def initialize_db(self):
        db.configure_db()

    def tear_down(self):
        db.clear_db()

    def remember_host(self, network_id, segmentation_id, host_id):
        session = db.get_session()
        with session.begin():
            net = (session.query(self.AristaProvisionedNets).
                   filter_by(network_id=network_id).first())

            if net and not net.segmentation_id and not net.host_id:
                net.segmentation_id = segmentation_id
                net.host_id = host_id
            else:
                provisioned_vlans = self.AristaProvisionedNets(network_id,
                                                               segmentation_id,
                                                               host_id)
                session.add(provisioned_vlans)

    def forget_host(self, network_id, host_id):
        session = db.get_session()
        with session.begin():
            (session.query(self.AristaProvisionedNets).
             filter_by(network_id=network_id, host_id=host_id).
             delete())

    def remember_network(self, network_id, segmentation_id):
        session = db.get_session()
        with session.begin():
            net = (session.query(self.AristaProvisionedNets).
                   filter_by(network_id=network_id).first())

            if not net:
                net = self.AristaProvisionedNets(network_id)
                net.segmentation_id = segmentation_id
                session.add(net)

    def get_segmentation_id(self, network_id):
        session = db.get_session()
        with session.begin():
            net = (session.query(self.AristaProvisionedNets).
                   filter_by(network_id=network_id).first())
            return net and net.segmentation_id or None

    def forget_network(self, network_id):
        session = db.get_session()
        with session.begin():
            (session.query(self.AristaProvisionedNets).
             filter_by(network_id=network_id).
             delete())

    def is_network_provisioned(self, network_id,
                               segmentation_id=None,
                               host_id=None):
        session = db.get_session()
        with session.begin():
            num_nets = 0
            if not segmentation_id and not host_id:
                num_nets = (session.query(self.AristaProvisionedNets).
                            filter_by(network_id=network_id).count())
            else:
                num_nets = (session.query(self.AristaProvisionedNets).
                            filter_by(network_id=network_id,
                                      segmentation_id=segmentation_id,
                                      host_id=host_id).count())
            return num_nets > 0

    def get_all(self):
        session = db.get_session()
        with session.begin():
            return session.query(self.AristaProvisionedNets).all()

    def num_nets_provisioned(self):
        session = db.get_session()
        with session.begin():
            return session.query(self.AristaProvisionedNets).count()

    def num_hosts_for_net(self, network_id):
        session = db.get_session()
        with session.begin():
            return (session.query(self.AristaProvisionedNets).
                    filter_by(network_id=network_id).count())

    def get_all_hosts_for_net(self, network_id):
        session = db.get_session()
        with session.begin():
            return (session.query(self.AristaProvisionedNets).
                    filter_by(network_id=network_id).all())

    def store_provisioned_vlans(self, networks):
        for net in networks:
            self.remember_host(net['name'],
                               net['segmentationId'],
                               net['hostId'])

    def get_network_list(self):
        """Returns all networks in EOS-compatible format.

        See AristaRPCWrapper.get_network_list() for return value format.
        """
        session = db.get_session()
        with session.begin():
            model = self.AristaProvisionedNets
            # hack for pep8 E711: comparison to None should be
            # 'if cond is not None'
            none = None
            all_nets = (session.query(model).
                        filter(model.host_id != none).
                        filter(model.segmentation_id != none).
                        all())
            res = {}
            for net in all_nets:
                all_hosts = self.get_all_hosts_for_net(net.network_id)
                hosts = [host.host_id for host in all_hosts]
                res[net.network_id] = net.eos_representation(VLAN_SEGMENTATION)
                res[net.network_id]['hostId'] = sorted(hosts)
            return res


class AristaRPCWrapper(object):
    """Wraps Arista JSON RPC.

    EOS - operating system used on Arista hardware
    Command API - JSON RPC API provided by Arista EOS
    TOR - Top Of Rack switch, Arista HW switch
    """
    required_options = ['eapi_user',
                        'eapi_pass',
                        'eapi_host']

    def __init__(self):
        self._server = jsonrpclib.Server(self._eapi_host_url())

    def get_network_list(self):
        """Returns dict of all networks known by EOS.

        :returns: dictionary with the following fields:
           {networkId:
             {
               'hostId': [list of hosts connected to the network],
               'name': network name, currently neutron net id,
               'segmentationId': VLAN id,
               'segmentationType': L2 segmentation type; currently 'vlan' only
             }
           }
        """
        command_output = self._run_openstack_cmd(['show openstack'])
        networks = command_output[0]['networks']
        for net in networks.values():
            net['hostId'].sort()

        return networks

    def get_network_info(self, network_id):
        """Returns list of VLANs for a given network.

        :param network_id:
        """
        net_list = self.get_network_list()

        for net in net_list:
            if net['network_id'] == network_id:
                return net

        return None

    def plug_host_into_vlan(self, network_id, vlan_id, host):
        """Creates VLAN between TOR and compute host.

        :param network_id: globally unique neutron network identifier
        :param vlan_id: VLAN ID
        :param host: compute node to be connected to a VLAN
        """
        # Interim solution till we figure out a better way
        # to query where the q-dhcp agent got placed, assume
        # its the same as this host (running neutron)
        cmds = ['tenant-network %s' % network_id,
                'type vlan id %s host %s' % (vlan_id, host),
                'type vlan id %s host %s' % (vlan_id, socket.gethostname())]
        self._run_openstack_cmd(cmds)

    def unplug_host_from_vlan(self, network_id, vlan_id, host_id):
        """Removes previously configured VLAN between TOR and a host.

        :param network_id: globally unique neutron network identifier
        :param vlan_id: VLAN ID
        :param host_id: target host to remove VLAN
        """
        cmds = ['tenant-network %s' % network_id,
                'no type vlan id %s host %s' % (vlan_id, host_id)]
        self._run_openstack_cmd(cmds)

    def delete_network(self, network_id):
        """Deletes all tenant networks.

        :param network_id: globally unique neutron network identifier
        """
        cmds = ['no tenant-network %s' % network_id]
        self._run_openstack_cmd(cmds)

    def _run_openstack_cmd(self, commands):
        if type(commands) is not list:
            commands = [commands]

        command_start = ['enable', 'configure', 'management openstack']
        command_end = ['exit']
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
            raise AristaRpcError(msg=msg)

        return ret

    def _eapi_host_url(self):
        self._validate_config()

        user = cfg.CONF.ARISTA_DRIVER.eapi_user
        pwd = cfg.CONF.ARISTA_DRIVER.eapi_pass
        host = cfg.CONF.ARISTA_DRIVER.eapi_host

        eapi_server_url = ('https://%(user)s:%(pwd)s@%(host)s/command-api' %
                           locals())

        return eapi_server_url

    def _validate_config(self):
        for option in self.required_options:
            if cfg.CONF.ARISTA_DRIVER.get(option) is None:
                msg = _('Required option %s is not set') % option
                LOG.error(msg)
                raise AristaConfigError(msg=msg)


# TODO: add support for non-vlan mode (use checks before calling
#       plug_host_Into_vlan())
class SyncService(object):
    def __init__(self, net_storage, rpc_wrapper):
        self._db = net_storage
        self._rpc = rpc_wrapper

    def synchronize(self):
        """Sends data to EOS which differs from neutron DB."""
        LOG.info('Syncing Neutron  <-> EOS')
        try:
            eos_net_list = self._rpc.get_network_list()
        except AristaRpcError:
            msg = _('EOS is not available, will try sync later')
            LOG.warning(msg)
            return

        db_net_list = self._db.get_network_list()

        # do nothing if net lists are the same in neutron and on EOS
        if eos_net_list == db_net_list:
            return

        # delete network from EOS if it is not present in neutron DB
        for net_id in eos_net_list:
            if net_id not in db_net_list:
                self._rpc.delete_network(net_id)

        for net_id in db_net_list:
            db_net = db_net_list[net_id]

            # update EOS if network is present in neutron DB but does not
            # exist on EOS
            if net_id not in eos_net_list:
                self._send_network_configuration(db_net_list, net_id)
            # if network exists, but hosts do not match
            elif db_net != eos_net_list[net_id]:
                eos_net = eos_net_list[net_id]
                if db_net['hostId'] != eos_net['hostId']:
                    self._plug_missing_hosts(net_id, db_net, eos_net)

    def _send_network_configuration(self, db_net_list, net_id):
        segm_id = db_net_list[net_id]['segmentationId']
        for host in db_net_list[net_id]['hostId']:
            self._rpc.plug_host_into_vlan(net_id, segm_id, host)

    def _plug_missing_hosts(self, net_id, db_net, eos_net):
        db_hosts = set(db_net['hostId'])
        eos_hosts = set(eos_net['hostId'])
        missing_hosts = db_hosts - eos_hosts
        vlan_id = db_net['segmentationId']
        for host in missing_hosts:
            self._rpc.plug_host_into_vlan(net_id, vlan_id, host)


class AristaDriver(driver_api.MechanismDriver):
    """Ml2 Mechanism driver for Arista networking hardware.

    Remebers all networks that are provisioned on Arista Hardware.
    Does not send network provisioning request if the network has already been
    provisioned before for the given port.
    """

    def __init__(self, rpc=None, net_storage=ProvisionedNetsStorage()):

        if rpc is None:
            self.rpc = AristaRPCWrapper()
        else:
            self.rpc = rpc

        print self.rpc

        self.net_storage = net_storage
        self.net_storage.initialize_db()

        config = cfg.CONF.ARISTA_DRIVER
        self.segmentation_type = VLAN_SEGMENTATION
        self.eos = SyncService(self.net_storage, self.rpc)
        self.sync_timeout = config['sync_interval']
        self.eos_sync_lock = threading.Lock()

        self._synchronization_thread()

    def initialize(self):
	pass

    def create_network_precommit(self, context):
	network = context.current()
	segments = context.network_segments()
        network_id = network['id']
        segmentation_id = segments[0]['segmentation_id']
        with self.eos_sync_lock:
            self.net_storage.remember_network(network_id, segmentation_id)

    def create_network_postcommit(self, context):
        """We do not need to do anything in the create_network. 
        The real work is done in the create_network_precommit() method
        """
        pass

    #def update_network_precommit(self, original_network, updated_network):
    def update_network_precommit(self, context):
        """We do not support update network yet.
        The real work is done in the create_network_precommit() method
        """
        pass

    def update_network_postcommit(self, context):
        """We do not support update network yet.
        The real work is done in the create_network_precommit() method
        """
        pass

    def delete_network_precommit(self, context):
	network = context.current()
        network_id = network['id']
        with self.eos_sync_lock:
            if self.net_storage.is_network_provisioned(network_id):
                self.net_storage.forget_network(network_id)

    def delete_network_postcommit(self, context):
	network = context.current()
        network_id = network['id']
        with self.eos_sync_lock:
            # Succeed deleting network in case EOS is not accessible.
            # EOS state will be updated by sync thread once EOS gets
            # alive.
            try:
                self.rpc.delete_network(network_id)
            except AristaRpcError:
                msg = _('Unable to reach EOS, will update it\'s state '
                        'during synchronization')
                LOG.info(msg)

    def create_port_precommit(self, context):
	port = context.current()
        #p = port
        #p = port['port']
        #host = p.get(binding.HOST_ID)                                           
        #device_id = p.get('device_id')                                               
        #device_owner = p.get('device_owner')                                         
        device_id = port['device_id']                                               
        device_owner = port['device_owner']                                         
        host = port['binding:host_id']                                           
	#### Hack to test - must remove ######  Sukhdev
	host = 'os-comp2'

        # device_id and device_owner are set on VM boot                              
        is_vm_boot = device_id and device_owner                                      
	if host and is_vm_boot:                                                      
            network_id = port['network_id']                                             
            self.plug_host(network_id, host)

    def create_port_postcommit(self, context):
        self.create_port_precommit(context)

    def update_port_precommit(self, context):
        self.create_port_precommit(context)

    def update_port_postcommit(self, context):
        # TODO(sukhdev) revisit once the port binding support is implemented
        return

    def delete_port_precommit(self, context):
	port = context.current()
        #p = port['port']
        #host = p.get(portbindings.HOST_ID)                                           
        host = port['binding:host_id']                                           
	#### Hack to test - must remove ######  Sukhdev
	host = 'os-comp2'
        network_id = port['network_id']                                             
        self.unplug_host(network_id, host)

    def delete_port_postcommit(self, context):
        self.delete_port_precommit(context)

    def unplug_host(self, network_id, host_id):
        with self.eos_sync_lock:
            storage = self.net_storage
            hostname = self._host_name(host_id)
            segmentation_id = storage.get_segmentation_id(network_id)
            was_provisioned = storage.is_network_provisioned(network_id,
                                                             segmentation_id,
                                                             hostname)

            if was_provisioned:
                if self._vlans_used():
                    self.rpc.unplug_host_from_vlan(network_id, segmentation_id,
                                                   hostname)
                storage.forget_host(network_id, hostname)

    def plug_host(self, network_id, host_id):
        with self.eos_sync_lock:
            s = self.net_storage
            hostname = self._host_name(host_id)
            segmentation_id = s.get_segmentation_id(network_id)
            already_provisioned = s.is_network_provisioned(network_id,
                                                           segmentation_id,
                                                           hostname)
            if not already_provisioned:
                if self._vlans_used():
                    self.rpc.plug_host_into_vlan(network_id,
                                                 segmentation_id,
                                                 hostname)
                s.remember_host(network_id, segmentation_id, hostname)
                s.remember_host(network_id, segmentation_id, socket.gethostname())

    def _host_name(self, hostname):
        fqdns_used = cfg.CONF.ARISTA_DRIVER['use_fqdn']
        return hostname if not fqdns_used else hostname.split('.')[0]

    def _synchronization_thread(self):
        with self.eos_sync_lock:
            self.eos.synchronize()

        t = threading.Timer(self.sync_timeout, self._synchronization_thread)
        t.start()

    #def _extract_segmentation_id(self, network):
        #return self._segm_type_used(driver_api.VLAN_SEGMENTATION)

    def _vlans_used(self):
        return self._segm_type_used(VLAN_SEGMENTATION)

    def _segm_type_used(self, segm_type):
        return self.segmentation_type == segm_type
