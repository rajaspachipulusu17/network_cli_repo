#!/usr/bin/python
""" PN Fabric Creation """
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

import shlex
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.network.netvisor.pn_netvisor import *
from ansible.module_utils.network.netvisor.netvisor import run_commands

DOCUMENTATION = """
---
module: pn_ztp_initial_setup
author: 'Pluribus Networks (devops@pluribusnetworks.com)'
short_description: Module to perform fabric creation/join.
description:
    Zero Touch Provisioning (ZTP) allows you to provision new switches in your
    network automatically, without manual intervention.
    It performs following steps:
        - Disable STP
        - Enable all ports
        - Create/Join fabric
        - Enable STP
options:
    pn_fabric_name:
      description:
        - Specify name of the fabric.
      required: False
      type: str
    pn_fabric_network:
      description:
        - Specify fabric network type as either mgmt or in-band.
      required: False
      type: str
      choices: ['mgmt', 'in-band']
      default: 'mgmt'
    pn_fabric_control_network:
      description:
        - Specify fabric control network as either mgmt or in-band.
      required: False
      type: str
      choices: ['mgmt', 'in-band']
      default: 'mgmt'
    pn_toggle_port_speed:
      description:
        - Flag to indicate if 40g/100g ports should be converted to 10g/25g ports or not.
      required: False
      default: True
      type: bool
    pn_spine_list:
      description:
        - Specify list of Spine hosts
      required: False
      type: list
    pn_leaf_list:
      description:
        - Specify list of leaf hosts
      required: False
      type: list
    pn_inband_ipv4:
      description:
        - Inband ips to be assigned to switches starting with this value.
      required: False
      default: 192.168.0.1/24.
      type: str
    pn_inband_ipv6:
      description:
        - Inband ips to be assigned to switches starting with this value.
      required: False
      type: str
    pn_current_switch:
      description:
        - Name of the switch on which this task is currently getting executed.
      required: False
      type: str
    pn_static_setup:
      description:
        - Flag to indicate if static values should be assign to
        following switch setup params.
      required: False
      default: False
      type: bool
    pn_mgmt_ip:
      description:
        - Specify MGMT-IP value to be assign if pn_static_setup is True.
      required: False
      type: str
    pn_mgmt_ip_subnet:
      description:
        - Specify subnet mask for MGMT-IP value to be assign if
        pn_static_setup is True.
      required: False
      type: str
    pn_gateway_ip:
      description:
        - Specify GATEWAY-IP value to be assign if pn_static_setup is True.
      required: False
      type: str
    pn_dns_ip:
      description:
        - Specify DNS-IP value to be assign if pn_static_setup is True.
      required: False
      type: str
    pn_dns_secondary_ip:
      description:
        - Specify DNS-SECONDARY-IP value to be assign if pn_static_setup is True
      required: False
      type: str
    pn_domain_name:
      description:
        - Specify DOMAIN-NAME value to be assign if pn_static_setup is True.
      required: False
      type: str
    pn_ntp_server:
      description:
        - Specify NTP-SERVER value to be assign if pn_static_setup is True.
      required: False
      type: str
    pn_web_api:
      description:
        - Flag to enable web api.
      default: True
      type: bool
    pn_stp:
      description:
        - Flag to enable STP at the end.
      required: False
      default: True
      type: bool
    pn_autotrunk:
      description:
        - Flag to enable/disable auto-trunk setting.
      required: False
      choices: ['enable', 'disable']
      type: str
    pn_autoneg:
      description:
        - Flag to enable/disable auto-neg for T2+ platforms.
      required: False
      type: bool
"""

EXAMPLES = """
- name: Fabric creation/join
    pn_ztp_initial_setup:
      pn_fabric_name: 'ztp-fabric'
      pn_current_switch: "{{ inventory_hostname }}"
      pn_spine_list: "{{ groups['spine'] }}"
      pn_leaf_list: "{{ groups['leaf'] }}"
"""

RETURN = """
summary:
  description: It contains output of each configuration along with switch name.
  returned: always
  type: str
changed:
  description: Indicates whether the CLI caused changes on the target.
  returned: always
  type: bool
unreachable:
  description: Indicates whether switch was unreachable to connect.
  returned: always
  type: bool
failed:
  description: Indicates whether or not the execution failed on the target.
  returned: always
  type: bool
exception:
  description: Describes error/exception occurred while executing CLI command.
  returned: always
  type: str
task:
  description: Name of the task getting executed on switch.
  returned: always
  type: str
msg:
  description: Indicates whether configuration made was successful or failed.
  returned: always
  type: str
"""

CHANGED_FLAG = []


def update_switch_names(module, switch_name, task, msg):
    """
    Method to update switch names.
    :param module: The Ansible module to fetch input parameters.
    :param switch_name: Name to assign to the switch.
    :return: String describing switch name got modified or not.
    """
    cli = pn_cli(module)
    cli += 'switch-setup-show format switch-name'
#    if switch_name == run_command(module, cli, task, msg).split()[1]:
    if switch_name == run_commands(module, cli, chop=False)[1].split()[1]:
        return ' Switch name is same as hostname! '
    else:
        cli = pn_cli(module)
        cli += ' switch-setup-modify switch-name ' + switch_name
        #run_command(module, cli, task, msg)
        run_commands(module, cli)
        return ' Updated switch name to match hostname! '


def modify_stp_local(module, modify_flag, task, msg):
    """
    Method to enable/disable STP (Spanning Tree Protocol) on a switch.
    :param module: The Ansible module to fetch input parameters.
    :param modify_flag: Enable/disable flag to set.
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    cli += ' switch-local stp-show format enable '
    current_state = run_command(module, cli, task, msg).split()

    if len(current_state) == 1:
        cli = pn_cli(module)
        cli += ' switch-local stp-modify ' + modify_flag
        return run_command(module, cli, task, msg)
    elif current_state[1] == 'yes':
        cli = pn_cli(module)
        cli += ' switch-local stp-modify ' + modify_flag
        return run_command(module, cli, task, msg)
    else:
        return ' Already modified '


def create_or_join_fabric(module, fabric_name, fabric_network, task, msg):
    """
    Method to create/join a fabric with default fabric type as mgmt.
    :param module: The Ansible module to fetch input parameters.
    :param fabric_name: Name of the fabric to create/join.
    :param fabric_network: Type of the fabric to create (mgmt/in-band).
    Default value: mgmt
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    clicopy = cli

    cli += ' fabric-show format name no-show-headers '
    existing_fabrics = run_command(module, cli, task, msg).split()

    if fabric_name not in existing_fabrics:
        cli = clicopy
        cli += ' admin-service-modify web if mgmt '
        run_command(module, cli, task, msg)
        cli = clicopy
        cli += ' fabric-create name ' + fabric_name
        cli += ' fabric-network ' + fabric_network
        return run_command(module, cli, task, msg)
    else:
        cli = clicopy
        cli += ' fabric-info format name no-show-headers'
        cli = shlex.split(cli)
        rc, out, err = module.run_command(cli)

        if err:
            cli = clicopy
            cli += ' fabric-join name ' + fabric_name
        elif out:
            present_fabric_name = out.split()
            if present_fabric_name[1] not in existing_fabrics:
                cli = clicopy
                cli += ' fabric-join name ' + fabric_name
            else:
                return 'Switch already in the fabric'

    return run_command(module, cli, task, msg)


def assign_ipv6_address(module, ipv6_address, current_switch, ip_type, task, msg):
    """
    Add loopback interface and router id to vrouters.
    :param module: The Ansible module to fetch input parameters.
    :param ipv6_address: The loopback ip to be assigned.
    :param current_switch: The name of current running switch.
    :param ip_type: ip type inband/mgmt.
    :return: String describing if loopback ip/router id got assigned or not.
    """
    global CHANGED_FLAG
    output = ''

    leaf_list = module.params['pn_leaf_list']
    spine_list = module.params['pn_spine_list']
    cli = pn_cli(module)

    if current_switch in spine_list:
        count = spine_list.index(current_switch)
    elif current_switch in leaf_list:
        count = leaf_list.index(current_switch) + 2

    if ipv6_address:
        ipv6 = ipv6_address.split('/')
        subnet_ipv6 = ipv6[1]
        ipv6 = ipv6[0]
        ipv6 = ipv6.split(':')
        if not ipv6[-1]:
            ipv6[-1] = "0"
        host_count_ipv6 = int(ipv6[-1], 16)
        host_count_ipv6 += count
        ipv6[-1] = str(hex(host_count_ipv6)[2:])
        ipv6_ip = ':'.join(ipv6)

    cli = pn_cli(module)
    clicopy = cli
    cli += ' switch-local switch-setup-show format %s ' % ip_type
    existing_ip = run_command(module, cli, task, msg).split()

    if ipv6_address not in existing_ip:
        cli = clicopy
        cli += ' switch %s switch-setup-modify ' % current_switch
        cli += ' %s %s/%s ' % (ip_type, ipv6_ip, subnet_ipv6)
        run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)
        output += 'Assigned %s ip ' % ipv6_ip
    else:
        output += 'ip %s already assigned ' % ipv6_ip

    return output


def main():
    """ This section is for arguments parsing """
    module = AnsibleModule(
        argument_spec=dict(
            pn_fabric_name=dict(required=True, type='str'),
            pn_fabric_network=dict(required=False, type='str',
                                   choices=['mgmt', 'in-band'], default='mgmt'),
            pn_fabric_control_network=dict(required=False, type='str',
                                           choices=['mgmt', 'in-band'],
                                           default='mgmt'),
            pn_toggle_port_speed=dict(required=False, type='bool', default=True),
            pn_spine_list=dict(required=False, type='list', default=[]),
            pn_leaf_list=dict(required=False, type='list', default=[]),
            pn_inband_ipv4=dict(required=False, type='str', default='192.16.0.1/24'),
            pn_inband_ipv6=dict(required=False, type='str'),
            pn_mgmt_ip=dict(required=False, type='str'),
            pn_mgmt_ip_subnet=dict(required=False, type='str'),
            pn_mgmt_ipv6=dict(required=False, type='str'),
            pn_current_switch=dict(required=False, type='str'),
            pn_static_setup=dict(required=False, type='bool', default=False),
            pn_gateway_ip=dict(required=False, type='str'),
            pn_dns_ip=dict(required=False, type='str'),
            pn_dns_secondary_ip=dict(required=False, type='str'),
            pn_domain_name=dict(required=False, type='str'),
            pn_ntp_server=dict(required=False, type='str'),
            pn_web_api=dict(type='bool', default=True),
            pn_stp=dict(required=False, type='bool', default=True),
            pn_autotrunk=dict(required=False, type='str',
                              choices=['enable', 'disable']),
            pn_autoneg=dict(required=False, type='bool')
        )
    )

    mgmt_ip = module.params['pn_mgmt_ip']
    mgmt_ip_subnet = module.params['pn_mgmt_ip_subnet']
    gateway_ip = module.params['pn_gateway_ip']
    dns_ip = module.params['pn_dns_ip']
    dns_secondary_ip = module.params['pn_dns_secondary_ip']
    domain_name = module.params['pn_domain_name']
    ntp_server = module.params['pn_ntp_server']
    fabric_name = module.params['pn_fabric_name']
    fabric_network = module.params['pn_fabric_network']
    control_network = module.params['pn_fabric_control_network']
    toggle_flag = module.params['pn_toggle_port_speed']
    current_switch = module.params['pn_current_switch']
    autotrunk = module.params['pn_autotrunk']
    autoneg = module.params['pn_autoneg']
    mgmt_ipv6 = module.params['pn_mgmt_ipv6']
    in_band_ipv6 = module.params['pn_inband_ipv6']
    switch_list = module.params['pn_spine_list'] + module.params['pn_leaf_list']
    spine_list = module.params['pn_spine_list']
    current_switch = module.params['pn_current_switch']
    inband_ipv4 = module.params['pn_inband_ipv4']
    results = []
    global CHANGED_FLAG

    global task
    global msg

    task = 'Fabric creation'
    msg = 'Fabric setup failed'

    # Make switch setup static
    if module.params['pn_static_setup']:
        make_switch_setup_static(module, dns_ip, dns_secondary_ip, domain_name, ntp_server, task, msg,
                                 mgmt_ip, mgmt_ip_subnet, gateway_ip)
        CHANGED_FLAG.append(True)
        results.append({
            'switch': current_switch,
            'output': 'Switch setup successful'
        })
#
##
    # Update switch names to match host names from hosts file
    if 'Updated' in update_switch_names(module, current_switch, task, msg):
        CHANGED_FLAG.append(True)
#
#    # Create/join fabric
#    if 'created' in create_or_join_fabric(module, fabric_name,
#                                          fabric_network, task, msg):
#        CHANGED_FLAG.append(True)
#        results.append({
#            'switch': current_switch,
#            'output': u"Created fabric '{}'".format(fabric_name)
#        })
#        # enable_web_api(module, task, msg)
#    else:
#        CHANGED_FLAG.append(True)
#        results.append({
#            'switch': current_switch,
#            'output': u"Joined fabric '{}'".format(fabric_name)
#        })
#
    # Find internal ports
    internal_ports = find_internal_ports(module, current_switch, task, msg)
#
#    # Modify auto-neg for T2+ platforms
#    if autoneg is True and current_switch in spine_list:
#        out = modify_auto_neg(module, current_switch, internal_ports, spine_list)
#        CHANGED_FLAG.append(True)
#        results.append({
#            'switch': current_switch,
#            'output': out
#        })
#
#    # Configure fabric control network to either mgmt or in-band
#    configure_control_network(module, control_network, task, msg)
#    CHANGED_FLAG.append(True)
#    results.append({
#        'switch': current_switch,
#        'output': u"Configured fabric control network to '{}'".format(
#            control_network)
#    })
#
#    # Enable/disable auto-trunk
#    if autotrunk:
#        modify_auto_trunk(module, autotrunk, task, msg)
#        results.append({
#            'switch': current_switch,
#            'output': u"Auto-trunk {}d".format(autotrunk)
#        })
#
#    # Enable STP
#    if 'Success' in modify_stp_local(module, 'enable', task, msg):
#        CHANGED_FLAG.append(True)
#
#    # Enable jumbo flag
#    if 'Success' in ports_modify_jumbo(module, 'jumbo', internal_ports, task, msg):
#        CHANGED_FLAG.append(True)
#        results.append({
#            'switch': current_switch,
#            'output': 'Jumbo enabled in ports'
#        })
#
#    # Enable ports
#    if 'Success' in enable_ports(module, internal_ports, task, msg):
#        CHANGED_FLAG.append(True)
#        results.append({
#            'switch': current_switch,
#            'output': 'Ports enabled'
#        })
#
#    # Toggle 40g/100g ports to 10g/25g
#    if toggle_flag:
#        out = toggle_ports(module, module.params['pn_current_switch'], internal_ports, task, msg)
#        CHANGED_FLAG.append(True)
#        results.append({
#            'switch': current_switch,
#            'output': out
#        })

    # Assign in-band ipv4.
    out, CHANGED_FLAG = assign_inband_ipv4(module, switch_list, current_switch,
                                           inband_ipv4, CHANGED_FLAG, task, msg)
    results.append({
        'switch': current_switch,
        'output': out
    })

#    # Assign mgmt ipv6.
#    if mgmt_ipv6:
#        out = assign_ipv6_address(module, mgmt_ipv6, current_switch, "mgmt-ip6",
#                                  task, msg)
#        results.append({
#            'switch': current_switch,
#            'output': out
#        })
#
#    # Enable STP if flag is True
#    if module.params['pn_stp']:
#        if 'Success' in modify_stp_local(module, 'enable', task, msg):
#            CHANGED_FLAG.append(True)
#            results.append({
#                'switch': current_switch,
#                'output': 'STP enabled'
#            })

    # Exit the module and return the required JSON
    module.exit_json(
        unreachable=False,
        msg='Fabric creation succeeded',
        summary=results,
        exception='',
        task='Fabric creation',
        failed=False,
        changed=True if True in CHANGED_FLAG else False
    )


if __name__ == '__main__':
    main()
