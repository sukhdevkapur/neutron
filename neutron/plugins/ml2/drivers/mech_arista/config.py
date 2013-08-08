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


from oslo.config import cfg

""" Arista ML2 Mechanism driver specific configuration knobs.

Following are user configurable options for Arista ML2 Mechanism
driver. The eapi_username, eapi_password, and eapi_host are
required options. Region Name must be the same that is used by
Keystone service. This option is available to support multiple
OpenStack/Neutron controllers.
"""

ARISTA_DRIVER_OPTS = [
    cfg.StrOpt('eapi_username',
               default=None,
               help=_('Username for Arista EOS')),
    cfg.StrOpt('eapi_password',
               default=None,
               secret=True,  # do not expose value in the logs
               help=_('Password for Arista EOS')),
    cfg.StrOpt('eapi_host',
               default=None,
               help=_('Arista EOS host IP')),
    cfg.BoolOpt('use_fqdn',
                default=True,
                help=_('Defines if hostnames are sent to Arista EOS as FQDNs '
                       '("node1.domain.com") or as short names ("node1")')),
    cfg.IntOpt('sync_interval',
               default=180,
               help=_('Sync interval in seconds between Neutron plugin and '
                      'EOS. This interval defines how often the'
                      'synchronization is performed')),
    cfg.StrOpt('region_name',
               default='RegionOne',
               help=_('Region name assigned to this OpenStack Controller '
                      'This is useful when multiple Openstack/Neutron '
                      'controllers are managining same Arista HW clusters'))
]

cfg.CONF.register_opts(ARISTA_DRIVER_OPTS, "ARISTA_DRIVER")
