# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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

from neutron.common import exceptions as qexc


class OFCException(qexc.NeutronException):
    message = _("An OFC exception has occurred: %(reason)s")


class NECDBException(qexc.NeutronException):
    message = _("An exception occurred in NECPluginV2 DB: %(reason)s")


class OFCConsistencyBroken(qexc.NeutronException):
    message = _("Consistency of neutron-OFC resource map is broken: "
                "%(reason)s")


class PortInfoNotFound(qexc.NotFound):
    message = _("PortInfo %(id)s could not be found")


class ProfilePortInfoInvalidDataPathId(qexc.InvalidInput):
    message = _('Invalid input for operation: '
                'portinfo:datapath_id should be a hex string '
                'with at most 8 bytes')


class ProfilePortInfoInvalidPortNo(qexc.InvalidInput):
    message = _('Invalid input for operation: '
                'portinfo:port_no should be [0:65535]')
