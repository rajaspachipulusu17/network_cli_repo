#!/usr/bin/python

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import shlex
import time

from ansible.module_utils.network.netvisor.netvisor import run_commands


def pn_cli(module, switch=None, username=None, password=None, switch_local=None):
    """
    Method to generate the cli portion to launch the Netvisor cli.
    :param module: The Ansible module to fetch username and password.
    :return: The cli string for further processing.
    """

    cli = ''

    if username and password:
        cli += '--user "%s":"%s" ' % (username, password)
    if switch:
        cli += ' switch ' + switch
    if switch_local:
        cli += ' switch-local '

    return cli


def run_command(module, cli, task, msg):
    """
    Method to execute the cli command on the target node(s) and returns the
    output.
    :param module: The Ansible module to fetch input parameters.
    :param cli: The complete cli string to be executed on the target node(s).
    :return: Output/Error or Success msg depending upon the response from cli.
    """
    cli = shlex.split(cli)
    rc, out, err = module.run_command(cli)
    results = []
    if out:
        return out

    if err:
        json_msg = {
            'switch': '',
            'output': u'Operation Failed: {}'.format(' '.join(cli))
        }
        results.append(json_msg)
        module.exit_json(
            unreachable=False,
            failed=True,
            exception=err.strip(),
            summary=results,
            task=task,
            msg=msg,
            changed=False
        )
    else:
        return 'Success'


def booleanArgs(arg, trueString, falseString):
    if arg is True:
        return " %s " % trueString
    elif arg is False:
        return " %s " % falseString
    else:
        return ""


def run_cli(module, cli, state_map):
    """
    This method executes the cli command on the target node(s) and returns the
    output. The module then exits based on the output.
    :param cli: the complete cli string to be executed on the target node(s).
    :param module: The Ansible module to fetch command
    """
    state = module.params['state']
    command = state_map[state]

    cmd = shlex.split(cli)
    result, out, err = module.run_command(cmd)

    remove_cmd = '/usr/bin/cli --quiet -e --no-login-prompt'

    results = dict(
        command=' '.join(cmd).replace(remove_cmd, ''),
        msg="%s operation completed" % command,
        changed=True
    )
    # Response in JSON format
    if result != 0:
        module.exit_json(
            command=' '.join(cmd).replace(remove_cmd, ''),
            stderr=err.strip(),
            msg="%s operation failed" % command,
            changed=False
        )

    if out:
        results['stdout'] = out.strip()
    module.exit_json(**results)


def calculate_link_ip_addresses_ipv4(address_str, cidr_str, supernet_str):
    """
    Method to calculate link IPs for layer 3 fabric.
    :param address_str: Host/network address.
    :param cidr_str: Subnet mask.
    :param supernet_str: Supernet mask.
    :return: List of available IP addresses that can be assigned to vrouter
    interfaces for layer 3 fabric.
    """
    # Split address into octets and turn CIDR, supernet mask into int
    address = address_str.split('.')
    cidr = int(cidr_str)
    supernet = int(supernet_str)
    supernet_range = (1 << (32 - supernet)) - 2
    base_addr = int(address[3])

    # Initialize the netmask and calculate based on CIDR mask
    mask = [0, 0, 0, 0]
    for i in range(cidr):
        mask[i // 8] += (1 << (7 - i % 8))

    # Initialize net and binary and netmask with addr to get network
    network = []
    for i in range(4):
        network.append(int(address[i]) & mask[i])

    # Duplicate net into broad array, gather host bits, and generate broadcast
    broadcast = list(network)
    broadcast_range = 32 - cidr
    for i in range(broadcast_range):
        broadcast[3 - i // 8] += (1 << (i % 8))

    last_ip = list(broadcast)
    diff = base_addr % (supernet_range + 2)
    host = base_addr - diff
    count, hostmin, hostmax = 0, 0, 0
    third_octet = network[2]
    available_ips = []
    while third_octet <= last_ip[2]:
        ips_list = []
        while count < last_ip[3]:
            hostmin = host + 1
            hostmax = hostmin + supernet_range - 1
            if supernet == 31:
                while hostmax <= hostmin:
                    ips_list.append(hostmax)
                    hostmax += 1
                host = hostmin + 1
            else:
                while hostmin <= hostmax:
                    ips_list.append(hostmin)
                    hostmin += 1
                host = hostmax + 2

            count = host

        list_index = 0
        ip_address = str(last_ip[0]) + '.' + str(last_ip[1]) + '.'
        ip_address += str(third_octet)
        while list_index < len(ips_list):
            ip = ip_address + '.' + str(ips_list[list_index]) + "/"
            ip += supernet_str
            available_ips.append(ip)
            list_index += 1

        host, count, hostmax, hostmin = 0, 0, 0, 0
        third_octet += 1

    return available_ips


def find_network_v6(address, mask):
    """
    Method to find the network address
    :param address: The address whose network to be found.
    :param mask: Subnet mask.
    :return: The network ip.
    """
    network = []
    for i in range(8):
        network.append(int(address[i], 16) & mask[i])

    return network


def find_broadcast_v6(network, cidr):
    """
    Method to find the broadcast address
    :param network: The network ip whose broadcast ip to be found.
    :param cidr: Subnet mask.
    :return: The broadcast ip.
    """
    broadcast = list(network)
    broadcast_range = 128 - cidr
    for i in range(broadcast_range):
        broadcast[7 - i // 16] += (1 << (i % 16))

    return broadcast


def find_mask_v6(cidr):
    """
    Method to find the subnet mask.
    :param cidr: Subnet mask.
    :return: The subnet mask
    """
    mask = [0, 0, 0, 0, 0, 0, 0, 0]
    for i in range(cidr):
        mask[i // 16] += (1 << (15 - i % 16))

    return mask


def find_network_supernet_v6(broadcast, cidr, supernet):
    """
    Method to find the subnet address
    :param broadcast: The next subnet to be found after the broadcast ip.
    :param cidr: Subnet mask.
    :param supernet: Supernet mask.
    :return: The next subnet after the broadcast ip.
    """
    host_bit = ''
    for j in range(128-supernet):
        host_bit += '0'

    subnet_network_bit = []
    for j in range((supernet//16) + 1):
        subnet_network_bit.append(str(bin(broadcast[j])[2:]).rjust(16, '0'))
    subnet_network_bit = ''.join(subnet_network_bit)

    network_bit = subnet_network_bit[:cidr]

    subnet_bit = subnet_network_bit[cidr:supernet]
    subnet_bit = bin(int(subnet_bit, 2) + 1)[2:].rjust(supernet - cidr, '0')

    final_subnet_binary = network_bit + subnet_bit + host_bit
    final_subnet = []
    temp1 = ''
    for k in range(32):
        temp = final_subnet_binary[(4 * k):(4 * (k+1))]
        temp1 += hex(int(temp, 2))[2:]

        if (k % 4) == 3:
            final_subnet.append(int(temp1, 16))
            temp1 = ''

    return final_subnet


def calculate_link_ip_addresses_ipv6(address_str, cidr_str, supernet_str, ip_count):
    """
    Generator to calculate link IPs for layer 3 fabric.
    :param address_str: Host/network address.
    :param cidr_str: Subnet mask.
    :param supernet_str: Supernet mask.
    :ip_count: No. of ips required per build.
    :return: List of available IP addresses that can be assigned to vrouter
    interfaces for layer 3 fabric.
    """
    if '::' in address_str:
        add_str = ''
        count = (address_str.count(':'))
        if address_str[-1] == ':':
            count -= 2
            while count < 7:
                add_str += ':0'
                count += 1
        else:
            while count < 8:
                add_str += ':0'
                count += 1
            add_str += ':'

        address_str = address_str.replace('::', add_str)

    address = address_str.split(':')
    cidr = int(cidr_str)
    supernet = int(supernet_str)

    mask_cidr = find_mask_v6(cidr)
    network = find_network_v6(address, mask_cidr)
    broadcast = find_broadcast_v6(network, cidr)

    mask_supernet = find_mask_v6(supernet)
    network_hex = []
    for i in range(8):
        network_hex.append(hex(network[i])[2:])
    network_supernet = find_network_v6(address, mask_supernet)
    broadcast_supernet = find_broadcast_v6(network_supernet, supernet)

    initial_ip = network_supernet[7]
    ip_checking = list(network_supernet)
    while not(initial_ip >= broadcast[7] and ip_checking[:7] == broadcast[:7]):
        initial_ip = network_supernet[7]
        ips_list = []
        no_of_ip = 0
        while initial_ip <= broadcast_supernet[7] and no_of_ip < ip_count:
            ip = list(network_supernet)
            ip[7] = initial_ip

            for i in range(0, 8):
                ip[i] = hex(ip[i])[2:]

            ip = ':'.join(ip)
            ip += '/' + str(supernet)
            ips_list.append(ip)
            initial_ip += 1
            no_of_ip += 1
            ip_checking = list(broadcast_supernet)
        initial_ip = broadcast_supernet[7]
        network_supernet = find_network_supernet_v6(broadcast_supernet, cidr, supernet)
        broadcast_supernet = find_broadcast_v6(network_supernet, supernet)

        yield ips_list


def assign_inband_ipv4(module, switches_list, switch, inband_ip, CHANGED_FLAG, task, msg):

    switch_ip = {}

    if inband_ip:
        address = inband_ip.split('.')
        static_part = str(address[0]) + '.' + str(address[1]) + '.'
        static_part += str(address[2]) + '.'
        last_octet = str(address[3]).split('/')
        subnet = last_octet[1]
        count = int(last_octet[0])
    else:
        return 'in-band ipv4 not specified '

    for sw in switches_list:
        switch_ip[sw] = static_part + str(count) + '/' + subnet
        count += 1

    # Get existing in-band ip.
    cli = pn_cli(module)
    clicopy = cli
    cli += ' switch-local switch-setup-show format in-band-ip'
    #existing_inband_ip = run_command(module, cli, task, msg).split()
    existing_inband_ip = run_commands(module, cli)[1].split()
    
#    module.exit_json(
#        skipped=True,
#        msg=existing_inband_ip,
#        cli=cli,
#        len1=len(existing_inband_ip)
#    )

    if switch_ip[switch] not in existing_inband_ip:
        cli = clicopy
        cli += ' switch %s switch-setup-modify ' % switch
        cli += ' in-band-ip ' + switch_ip[switch]
        #run_command(module, cli, task, msg)
        out = run_commands(module, cli)[1]
        CHANGED_FLAG.append(True)

    return 'Assigned in-band ip ' + switch_ip[switch], CHANGED_FLAG


def find_internal_ports(module, switch, task, msg):
    """
    Method to enable/disable Jumbo flag on a switch ports.
    :param module: The Ansible module to fetch input parameters.
    :return: The output of run_command() method.
    """
    internal_ports = list()

    cli = 'switch %s port-show status PN-internal, format port, no-show-headers ' % switch
    #ports = run_command(module, cli, task, msg)
    ports = run_commands(module, cli)[1]
    module.exit_json(
        skipped=True,
        msg=ports.strip().split(),
        cli=cli,
    )

    if ports:
        return ports.strip().split()

    return internal_ports


def ports_modify_jumbo(module, modify_flag, internal_ports, task, msg):
    """
    Method to enable/disable Jumbo flag on a switch ports.
    :param module: The Ansible module to fetch input parameters.
    :param modify_flag: Enable/disable flag to set.
    :param internal_ports: Internal ports.
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    clicopy = cli
    trunk_ports = []
    cli += ' switch-local port-show format port,trunk status trunk no-show-headers'
    cli_out = run_command(module, cli, task, msg)
    if cli_out == 'Success':
        pass
    else:
        cli_out = cli_out.strip().split('\n')
        for output in cli_out:
            output = output.strip().split()
            port, trunk_name = output[0], output[1]
            trunk_ports.append(port)
            cli = clicopy
            cli += 'trunk-modify name %s jumbo ' % trunk_name
            run_command(module, cli, task, msg)

    cli = clicopy
    cli += ' switch-local port-config-show format port no-show-headers'
    ports = run_command(module, cli, task, msg).split()
    ports_to_modify = list(set(ports) - set(trunk_ports + internal_ports))
    ports_to_modify = ','.join(ports_to_modify)
    cli = clicopy
    cli += ' switch-local port-config-modify port %s %s' \
           % (ports_to_modify, modify_flag)
    return run_command(module, cli, task, msg)


def make_switch_setup_static(module, dns_ip, dns_secondary_ip, domain_name, ntp_server, task, msg, mgmt_ip=None, mgmt_ip_subnet=None, gateway_ip=None):
    """
    Method to assign static values to different switch setup parameters.
    :param module: The Ansible module to fetch input parameters.
    """
    cli = pn_cli(module)
    cli += ' switch-setup-modify '

    if mgmt_ip:
        ip = mgmt_ip + '/' + mgmt_ip_subnet
        cli += ' mgmt-ip ' + ip

    if gateway_ip:
        cli += ' gateway-ip ' + gateway_ip

    if dns_ip:
        cli += ' dns-ip ' + dns_ip

    if dns_secondary_ip:
        cli += ' dns-secondary-ip ' + dns_secondary_ip

    if domain_name:
        cli += ' domain-name ' + domain_name

    if ntp_server:
        cli += ' ntp-server ' + ntp_server

    clicopy = cli
    if clicopy.split('switch-setup-modify')[1] != ' ':
        #run_command(module, cli, task, msg)
        run_commands(module, cli)


def configure_control_network(module, network, task, msg):
    """
    Configure the fabric control network to mgmt.
    :param module: The Ansible module to fetch input parameters.
    """
    cli = pn_cli(module)
    cli += ' fabric-info format control-network '
    time.sleep(4)
    current_control_network = run_command(module, cli, task, msg).split()[1]

    if current_control_network != network:
        cli = pn_cli(module)
        cli += ' fabric-local-modify control-network %s ' % network
        run_command(module, cli, task, msg)


def enable_ports(module, internal_ports, task, msg):
    """
    Method to enable all ports of a switch.
    :param module: The Ansible module to fetch input parameters.
    :return: The output of run_command() method or None.
    :param internal_ports: Internal ports.
    """
    cli = pn_cli(module)
    clicopy = cli
    cli += ' switch-local port-config-show format enable no-show-headers '
    if 'off' in run_command(module, cli, task, msg).split():
        cli = clicopy
        cli += ' switch-local port-config-show format port no-show-headers '
        out = run_command(module, cli, task, msg)

        cli = clicopy
        cli += ' switch-local port-config-show format port speed 40g '
        cli += ' no-show-headers '
        out_40g = run_command(module, cli, task, msg)
        out_remove10g = []

        if len(out_40g) > 0 and out_40g != 'Success':
            out_40g = out_40g.split()
            out_40g = list(set(out_40g))
            if len(out_40g) > 0:
                for port_number in out_40g:
                    out_remove10g.append(str(int(port_number) + int(1)))
                    out_remove10g.append(str(int(port_number) + int(2)))
                    out_remove10g.append(str(int(port_number) + int(3)))

        if out:
            out = out.split()
            out = set(out) - set(out_remove10g + internal_ports)
            out = list(out)
            if out:
                ports = ','.join(out)
                cli = clicopy
                cli += ' switch-local port-config-modify port %s enable ' % (
                    ports)
                return run_command(module, cli, task, msg)

    return 'Success'


def modify_auto_trunk(module, flag, task, msg):
    """
    Method to enable/disable auto trunk setting of a switch.
    :param module: The Ansible module to fetch input parameters.
    :param flag: Enable/disable flag for the cli command.
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    if flag.lower() == 'enable':
        cli += ' system-settings-modify auto-trunk '
        return run_command(module, cli, task, msg)
    elif flag.lower() == 'disable':
        cli += ' system-settings-modify no-auto-trunk '
        return run_command(module, cli, task, msg)


def modify_auto_neg(module, current_switch, internal_ports, spines=None, switches=None):
    """
    Module to enable/disable auto-neg for T2+ platforms.
    :param module:
    :return: Nothing
    """
    if current_switch in (spines or switches):
        cli = pn_cli(module)
        cli += ' switch-local bezel-portmap-show format port no-show-headers '
        cli = shlex.split(cli)
        out = module.run_command(cli)[1]
        all_ports = out.splitlines()
        all_ports = [port.strip() for port in all_ports]
        time.sleep(1)

        cli = pn_cli(module)
        cli += ' switch-local lldp-show format local-port no-show-headers '
        cli = shlex.split(cli)
        out = module.run_command(cli)[1]
        lldp_ports = out.splitlines()
        lldp_ports = [port.strip() for port in lldp_ports]
        time.sleep(1)

        idle_ports = list(set(all_ports) ^ set(lldp_ports))
        idle_ports = list(set(all_ports) - set(internal_ports))
        cli = pn_cli(module)
        cli += ' switch-local port-config-modify port %s autoneg ' % ','.join(idle_ports)
        cli = shlex.split(cli)
        module.run_command(cli)
        time.sleep(1)

        cli = pn_cli(module)
        cli += ' switch-local lldp-show format local-port no-show-headers '
        cli = shlex.split(cli)
        out = module.run_command(cli)[1]
        lldp_ports = out.splitlines()
        lldp_ports = [port.strip() for port in lldp_ports]
        time.sleep(1)

        idle_ports = list(set(all_ports) ^ set(lldp_ports))
        idle_ports = list(set(all_ports) - set(internal_ports))
        cli = pn_cli(module)
        cli += ' switch-local port-config-modify port %s no-autoneg ' % ','.join(idle_ports)
        module.run_command(cli)
        time.sleep(1)

        return "Auto-neg Configured"


def toggle(module, curr_switch, toggle_ports, toggle_speed, port_speed, splitter_ports, quad_ports, task, msg):
    """
    Method to toggle ports for topology discovery
    :param module: The Ansible module to fetch input parameters.
    :return: The output messages for assignment.
    :param curr_switch on which we run toggle.
    :param toggle_ports to be toggled.
    :param toggle_speed to which ports to be toggled.
    :param splitter_ports are splitter ports
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli
    count = 0

    for speed in toggle_speed:
        if int(port_speed.strip('g'))/int(speed.strip('g')) >= 4:
            is_splittable = True
        else:
            is_splittable = False

        while (count <= 10):
            cli = clicopy
            cli += 'switch %s lldp-show format local-port ' % curr_switch
            cli += 'parsable-delim ,'
            out = run_command(module, cli, task, msg)
            if out:
                local_ports = out.split()
                break
            else:
                time.sleep(3)
            count += 1

        if not local_ports:
            module.fail_json(
                    unreachable=False,
                    failed=True,
                    exception='',
                    summary='Unable to discover topology',
                    task='Fabric creation',
                    msg='Fabric creation failed',
                    changed=False
                )

        _undiscovered_ports = sorted(list(set(toggle_ports) - set(local_ports)),
                                     key=lambda x: int(x))
        non_splittable_ports = []
        undiscovered_ports = []

        for _port in _undiscovered_ports:
            if splitter_ports.get(_port, 0) == 1:
                undiscovered_ports.append("%s-%s" % (_port, int(_port)+3))
            elif splitter_ports.get(_port, 0) == 0:
                undiscovered_ports.append(_port)
            else:
                # Skip intermediate splitter ports
                continue
            if not is_splittable:
                non_splittable_ports.append(_port)
        undiscovered_ports = ",".join(undiscovered_ports)

        if not undiscovered_ports:
            continue

        cli = clicopy
        cli += 'switch %s port-config-modify port %s ' % (curr_switch, undiscovered_ports)
        cli += 'disable'
        run_command(module, cli, task, msg)

        if non_splittable_ports:
            non_splittable_ports = ",".join(non_splittable_ports)
            cli = clicopy
            cli += 'switch %s port-config-modify ' % curr_switch
            cli += 'port %s ' % non_splittable_ports
            cli += 'speed %s enable' % speed
            run_command(module, cli, task, msg)
        else:
            cli = clicopy
            cli += 'switch %s port-config-modify ' % curr_switch
            cli += 'port %s ' % undiscovered_ports
            cli += 'speed %s enable' % speed
            run_command(module, cli, task, msg)

        time.sleep(10)

    # Revert undiscovered ports back to their original speed
    cli = clicopy
    cli += 'switch %s lldp-show format local-port ' % curr_switch
    cli += 'parsable-delim ,'
    local_ports = run_command(module, cli, task, msg)
    _undiscovered_ports = sorted(list(set(toggle_ports) - set(local_ports)),
                                 key=lambda x: int(x))
    disable_ports = []
    undiscovered_ports = []
    for _port in _undiscovered_ports:
        if _port in quad_ports:
            disable_ports.append(str(_port))
            # dont add to undiscovered ports
        elif splitter_ports.get(_port, 0) == 1:
            splitter_ports_range = set(map(str, (range(int(_port), int(_port)+4))))
            if not splitter_ports_range.intersection(set(local_ports)):
                disable_ports.append("%s-%s" % (_port, int(_port)+3))
                undiscovered_ports.append(_port)
        elif splitter_ports.get(_port, 0) == 0:
            disable_ports.append(str(_port))
            undiscovered_ports.append(_port)
        else:
            # Skip intermediate splitter ports
            pass

    disable_ports = ",".join(disable_ports)
    if disable_ports:
        cli = clicopy
        cli += 'switch %s port-config-modify port %s disable' % (curr_switch, disable_ports)
        run_command(module, cli, task, msg)

    undiscovered_ports = ",".join(undiscovered_ports)
    if not undiscovered_ports:
        return 'Toggle completed successfully '

    cli = clicopy
    cli += 'switch %s port-config-modify ' % curr_switch
    cli += 'port %s ' % undiscovered_ports
    cli += 'speed %s enable' % port_speed
    run_command(module, cli, task, msg)
    output += 'Toggle completed successfully '

    return output


def toggle_ports(module, curr_switch, internal_ports, task, msg):
    """
    Method to discover the toggle ports.
    :param module: The Ansible module to fetch input parameters.
    :param curr_switch on which toggle discovery happens.
    :param internal_ports: Internal ports.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli
    g_toggle_ports = {
        '25g': {'ports': [], 'speeds': ['10g']},
        '40g': {'ports': [], 'speeds': ['10g']},
        '100g': {'ports': [], 'speeds': ['10g', '25g', '40g']}
    }
    ports_25g = []
    ports_40g = []
    ports_100g = []

    cli += 'switch %s port-config-show format port,speed ' % curr_switch
    cli += 'parsable-delim ,'
    max_ports = run_command(module, cli, task, msg).split()

    all_next_ports = []
    for port_info in max_ports:
        if port_info:
            port, speed = port_info.strip().split(',')
            all_next_ports.append(str(int(port)+1))
            if port in internal_ports:
                continue
            if g_toggle_ports.get(speed, None):
                g_toggle_ports[speed]['ports'].append(port)

    # Get info on splitter ports
    g_splitter_ports = {}
    all_next_ports = ','.join(all_next_ports)
    cli = clicopy
    cli += 'switch %s port-show port %s format ' % (curr_switch, all_next_ports)
    cli += 'port,bezel-port parsable-delim ,'
    splitter_info = run_command(module, cli, task, msg).split()

    for sinfo in splitter_info:
        if not sinfo:
            break
        _port, _sinfo = sinfo.split(',')
        _port = int(_port)
        if '.2' in _sinfo:
            for i in range(4):
                g_splitter_ports[str(_port-1 + i)] = 1 + i
        else:
            for i in range(4):
                g_splitter_ports[str(_port-1 + i)] = 1 + i

    # Get info on Quad Ports
    g_quad_ports = {'25g': []}
    cli = clicopy
    cli += 'switch %s switch-info-show format model, layout horizontal ' % curr_switch
    cli += 'parsable-delim ,'
    model_info = run_command(module, cli, task, msg).split()

    for modinfo in model_info:
        if not modinfo:
            break
        model = modinfo
        if model == "ACCTON-AS7316-54X" and g_toggle_ports.get('25g', None):
            for _port in g_toggle_ports['25g']['ports']:
                if _port not in g_splitter_ports:
                    g_quad_ports['25g'].append(_port)

    for port_speed, port_info in g_toggle_ports.iteritems():
        if port_info['ports']:
            output += toggle(module, curr_switch, port_info['ports'], port_info['speeds'], port_speed,
                             g_splitter_ports, g_quad_ports.get(port_speed, []), task, msg)

    return output


def create_vrouter(module, switch, CHANGED_FLAG, task, msg, vrrp_id=None, ospf_redistribute=None, pim_ssm=None, bgp_redistribute=None, bgp_as=None):
    """
    Create a hardware vrouter.
    :param module: The Ansible module to fetch input parameters.
    :param switch: The name of current running switch.
    :return: String describing if vrouter got created or not.
    """
    output = ''

    cli = pn_cli(module)
    cli += ' fabric-node-show format fab-name no-show-headers '
    fabric_name = list(set(run_command(module, cli, task, msg).split()))[0]
    vnet_name = fabric_name + '-global'

    cli = pn_cli(module)
    cli += ' vrouter-show format name no-show-headers '
    existing_vrouter_names = run_command(module, cli, task, msg)

    if existing_vrouter_names is not None:
        existing_vrouter_names = existing_vrouter_names.split()

    new_vrouter = False
    vrouter_name = switch + '-vrouter'

    if (existing_vrouter_names is not None and vrouter_name not in
            existing_vrouter_names):
        new_vrouter = True

    if new_vrouter or existing_vrouter_names is None:
        if pim_ssm is True:
            pim_ssm = 'pim-ssm'
        else:
            pim_ssm = 'none'

        cli = pn_cli(module)
        cli += ' switch %s ' % switch
        cli += ' vrouter-create name %s vnet %s hw-vrrp-id %s enable ' % (
            vrouter_name, vnet_name, vrrp_id)
        cli += ' router-type hardware proto-multi %s ' % pim_ssm
        if ospf_redistribute:
            cli += ' ospf-redistribute %s ' % ospf_redistribute
        if bgp_as:
            cli += ' bgp-as %s' % bgp_as
        if bgp_redistribute:
            cli += ' bgp-redistribute %s' % bgp_redistribute
        run_command(module, cli, task, msg)
        output = ' %s: Created vrouter with name %s \n' % (switch, vrouter_name)

    return CHANGED_FLAG, output


def assign_loopback_and_router_id(module, loopback_address, current_switch, CHANGED_FLAG, task, msg):
    """
    Add loopback interface and router id to vrouters.
    :param module: The Ansible module to fetch input parameters.
    :param loopback_address: The loopback ip to be assigned.
    :param current_switch: The name of current running switch.
    :return: String describing if loopback ip/router id got assigned or not.
    """
    output = ''

    leaf_list = module.params['pn_leaf_list']
    spine_list = module.params['pn_spine_list']
    address = loopback_address.split('.')
    static_part = str(address[0]) + '.' + str(address[1]) + '.'
    static_part += str(address[2]) + '.'
    vrouter_count = int(address[3].split('/')[0])
    add_loopback = False
    vrouter = current_switch + '-vrouter'
    cli = pn_cli(module)

    switch_list = spine_list + leaf_list

    if current_switch in switch_list:
        count = switch_list.index(current_switch)

    if module.params['pn_loopback_ip_v6']:
        add_loopback_v6 = False
        loopback_ipv6 = module.params['pn_loopback_ip_v6']
        ipv6 = loopback_ipv6.split('/')
        subnet_ipv6 = ipv6[1]
        ipv6 = ipv6[0]
        ipv6 = ipv6.split(':')
        if not ipv6[-1]:
            ipv6[-1] = "0"
        host_count_ipv6 = int(ipv6[-1], 16)
        host_count_ipv6 += count
        ipv6[-1] = str(hex(host_count_ipv6)[2:])
        loopback_ipv6_ip = ':'.join(ipv6)

        # Check existing loopback ip v6
        cli = pn_cli(module)
        cli += ' vrouter-loopback-interface-show ip %s ' % loopback_ipv6_ip
        cli += ' format switch no-show-headers '
        existing_vrouter = run_command(module, cli, task, msg)

        if existing_vrouter is not None:
            existing_vrouter = existing_vrouter.split()
            if vrouter not in existing_vrouter:
                add_loopback_v6 = True

        # Add loopback ip v6 if not already exists
        if add_loopback_v6 or existing_vrouter is None:
            cli = pn_cli(module)
            cli += ' vrouter-loopback-interface-add '
            cli += ' vrouter-name %s ip %s ' % (vrouter, loopback_ipv6_ip)
            run_command(module, cli, task, msg)
            CHANGED_FLAG.append(True)
            output += '%s: Added loopback ip %s to %s\n' % (current_switch, loopback_ipv6_ip, vrouter)

    count += vrouter_count
    ip = static_part + str(count)

    # Add router id
    cli = pn_cli(module)
    cli += ' vrouter-modify name %s router-id %s ' % (vrouter, ip)
    run_command(module, cli, task, msg)
    output += '%s: Added router id %s to %s\n' % (current_switch, ip, vrouter)

    # Check existing loopback ip
    cli = pn_cli(module)
    cli += ' vrouter-loopback-interface-show ip %s ' % ip
    cli += ' format switch no-show-headers '
    existing_vrouter = run_command(module, cli, task, msg)

    if existing_vrouter is not None:
        existing_vrouter = existing_vrouter.split()
        if vrouter not in existing_vrouter:
            add_loopback = True

    # Add loopback ip if not already exists
    if add_loopback or existing_vrouter is None:
        cli = pn_cli(module)
        cli += ' vrouter-loopback-interface-add '
        cli += ' vrouter-name %s ip %s ' % (vrouter, ip)
        run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)
        output += '%s: Added loopback ip %s to %s\n' % (current_switch, ip, vrouter)

    return CHANGED_FLAG, output


def create_vlan(module, vlan_id, switch, CHANGED_FLAG, task, msg, untagged_ports=None):
    """
    Method to create vlans.
    :param module: The Ansible module to fetch input parameters.
    :param vlan_id: vlan id to be created.
    :param switch: Name of the switch on which vlan creation will be executed.
    :return: String describing if vlan got created or if it already exists.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli
    cli += ' vlan-show format id no-show-headers '
    existing_vlan_ids = run_command(module, cli, task, msg).split()
    existing_vlan_ids = list(set(existing_vlan_ids))

    if vlan_id not in existing_vlan_ids:
        cli = clicopy
        cli += ' vlan-create id %s scope fabric ' % vlan_id

        if untagged_ports is not None:
            cli += ' untagged-ports %s ' % untagged_ports

        run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)
        output += ' %s: Created vlan id %s' % (switch, vlan_id)
        output += ' with scope fabric \n'
    return output, CHANGED_FLAG


def create_trunk(module, switch, name, ports, CHANGED_FLAG, task, msg):
    """
    Method to create a trunk on a switch.
    :param module: The Ansible module to fetch input parameters.
    :param switch: Name of the local switch.
    :param name: The name of the trunk to create.
    :param ports: List of connected ports.
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    clicopy = cli
    cli += ' switch %s trunk-show format name no-show-headers ' % switch
    trunk_list = run_command(module, cli, task, msg).split()
    if name not in trunk_list:
        cli = clicopy
        cli += ' switch %s trunk-create name %s ' % (switch, name)
        cli += ' ports %s ' % ports
        run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)

    output = '%s: Created trunk %s\n' % (switch, name)
    return CHANGED_FLAG, output


def get_ports(module, switch, peer_switch, task, msg):
    """
    Method to figure out connected ports between two switches.
    :param module: The Ansible module to fetch input parameters.
    :param switch: Name of the local switch.
    :param peer_switch: Name of the connected peer switch.
    :return: List of connected ports.
    """
    cli = pn_cli(module)
    cli += ' switch %s port-show hostname %s' % (switch, peer_switch)
    cli += ' format port no-show-headers '
    return run_command(module, cli, task, msg).split()


def create_cluster(module, switch, name, node1, node2, mod, CHANGED_FLAG, task, msg):
    """
    Method to create a cluster between two switches.
    :param module: The Ansible module to fetch input parameters.
    :param switch: Name of the local switch.
    :param name: The name of the cluster to create.
    :param node1: First node of the cluster.
    :param node2: Second node of the cluster.
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    clicopy = cli

    if mod == 'l3-vrrp' or mod == 'l2-vrrp':
        spine_list = module.params['pn_spine_list']
        leaf_list = module.params['pn_leaf_list']

        cli += ' switch %s system-settings-show ' % node1
        cli += ' format auto-trunk '
        status = run_command(module, cli, task, msg).split()[1]
        if status != 'on':
            if (node1 in leaf_list and node2 in leaf_list) or \
               (node1 in spine_list and node2 in spine_list):

                ports = get_ports(module, node1, node2, task, msg)
                trunk_name = node1 + '-' + node2 + '-trunk'
                ports_string = ','.join(ports)
                CHANGED_FLAG, output = create_trunk(module, node1, trunk_name, ports_string,
                                                    CHANGED_FLAG, task, msg)
                ports = get_ports(module, node2, node1, task, msg)
                trunk_name = node2 + '-' + node1 + '-trunk'
                ports_string = ','.join(ports)
                CHANGED_FLAG, output = create_trunk(module, node2, trunk_name, ports_string,
                                                    CHANGED_FLAG, task, msg)
        cli = clicopy

    cli += ' switch %s cluster-show format name no-show-headers ' % node1
    cluster_list = list(set(run_command(module, cli, task, msg).split()))
    if name not in cluster_list:
        cli = clicopy
        cli += ' switch %s cluster-create name %s ' % (switch, name)
        cli += ' cluster-node-1 %s cluster-node-2 %s ' % (node1, node2)
        if 'Success' in run_command(module, cli, task, msg):
            CHANGED_FLAG.append(True)
            return ' %s: Created %s \n' % (switch, name), CHANGED_FLAG
    return '', CHANGED_FLAG


def configure_vrrp_for_non_cluster_leafs(module, ip, ip_v6, non_cluster_leaf, vlan_id, CHANGED_FLAG, task, msg):
    """
    Method to configure vrrp for non-cluster switches.
    :param module: The Ansible module to fetch input parameters.
    :param ip: IP address for the default gateway
    :param non_cluster_leaf: Name of non-cluster leaf switch.
    :param vlan_id: The vlan id to be assigned.
    :return: String describing whether interfaces got added or not.
    """
    vrouter_name = non_cluster_leaf + '-vrouter'
    addr_type = module.params['pn_addr_type']

    cli = pn_cli(module)
    clicopy = cli
    cli += 'switch ' + non_cluster_leaf
    cli += ' vrouter-interface-show ip %s vlan %s ' % (ip, vlan_id)
    cli += ' format switch no-show-headers '
    existing_vrouter = run_command(module, cli, task, msg).split()
    existing_vrouter = list(set(existing_vrouter))

    if vrouter_name not in existing_vrouter:
        cli = clicopy
        cli += 'switch ' + non_cluster_leaf
        cli += ' vrouter-interface-add vrouter-name ' + vrouter_name
        cli += ' vlan ' + vlan_id

        if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
            cli += ' ip ' + ip
        if addr_type == 'ipv4_ipv6':
            cli += ' ip2 ' + ip_v6
        if addr_type == 'ipv6':
            cli += ' ip ' + ip_v6
        if module.params['pn_jumbo_frames'] is True:
            cli += ' mtu 9216'
        if module.params['pn_pim_ssm'] is True:
            cli += ' pim-cluster '
        run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)
        output = ' %s: Added vrouter interface with ip %s' % (
            non_cluster_leaf, ip)
        if module.params['pn_addr_type'] == 'ipv4_ipv6':
            output += ' ip2 %s' % ip_v6
        output += ' to %s \n' % vrouter_name
        return output, CHANGED_FLAG
    else:
        return '', CHANGED_FLAG


def create_vrouter_interface(module, switch, vlan_id, vrrp_id,
                             vrrp_priority, list_vips, list_ips, CHANGED_FLAG, task, msg):
    """
    Method to add vrouter interface and assign IP to it along with
    vrrp_id and vrrp_priority.
    :param module: The Ansible module to fetch input parameters.
    :param switch: The switch name on which interfaces will be created.
    :param ip: IP address to be assigned to vrouter interface.
    :param vlan_id: vlan_id to be assigned.
    :param vrrp_id: vrrp_id to be assigned.
    :param vrrp_priority: priority to be given(110 for active switch).
    :param ip_count: The value of fourth octet in the ip
    :return: String describing if vrouter interface got added or not.
    """
    vrouter_name = switch + '-vrouter'
    ospf_area_id = module.params['pn_ospf_area_id']
    addr_type = module.params['pn_addr_type']

    cli = pn_cli(module)
    clicopy = cli
    cli += ' vrouter-interface-show vlan %s ip %s ' % (vlan_id, list_ips[0])
    cli += ' format switch no-show-headers '
    existing_vrouter = run_command(module, cli, task, msg).split()
    existing_vrouter = list(set(existing_vrouter))

    if vrouter_name not in existing_vrouter:
        cli = clicopy
        cli += ' switch ' + switch
        cli += ' vrouter-interface-add vrouter-name ' + vrouter_name
        cli += ' ip ' + list_ips[0]
        cli += ' vlan %s if data ' % vlan_id
        if addr_type == 'ipv4_ipv6':
            cli += ' ip2 ' + list_ips[1]
        if module.params['pn_jumbo_frames'] is True:
            cli += ' mtu 9216'
        if module.params['pn_pim_ssm'] is True:
            cli += ' pim-cluster '
        run_command(module, cli, task, msg)
        output = ' %s: Added vrouter interface with ip %s' % (
            switch, list_ips[0]
        )
        if addr_type == 'ipv4_ipv6':
            output += ' ip2 %s' % list_ips[1]
        output += ' to %s \n' % vrouter_name
        CHANGED_FLAG.append(True)
    else:
        output = ''

    cli = clicopy
    cli += ' vrouter-interface-show vrouter-name %s ip %s vlan %s ' % (
        vrouter_name, list_ips[0], vlan_id
    )
    cli += ' format nic no-show-headers '
    eth_port = run_command(module, cli, task, msg).split()
    eth_port.remove(vrouter_name)

    for ip_vip in list_vips:
        cli = clicopy
        cli += ' vrouter-interface-show vlan %s ip %s vrrp-primary %s ' % (
            vlan_id, ip_vip, eth_port[0]
        )
        cli += ' format switch no-show-headers '
        existing_vrouter = run_command(module, cli, task, msg).split()
        existing_vrouter = list(set(existing_vrouter))

        if vrouter_name not in existing_vrouter:
            cli = clicopy
            cli += ' switch ' + switch
            cli += ' vrouter-interface-add vrouter-name ' + vrouter_name
            cli += ' ip ' + ip_vip
            cli += ' vlan %s if data vrrp-id %s ' % (vlan_id, vrrp_id)
            cli += ' vrrp-primary %s vrrp-priority %s ' % (eth_port[0],
                                                           vrrp_priority)
            if module.params['pn_jumbo_frames'] is True:
                cli += ' mtu 9216'
            if module.params['pn_pim_ssm'] is True:
                cli += ' pim-cluster '
            run_command(module, cli, task, msg)
            CHANGED_FLAG.append(True)
            output += ' %s: Added vrouter interface with ip %s to %s \n' % (
                switch, ip_vip, vrouter_name
            )

    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        ipv4 = list_ips[0]
        cli = clicopy
        cli += ' vrouter-ospf-show'
        cli += ' network %s format switch no-show-headers ' % ipv4
        already_added = run_command(module, cli, task, msg).split()

        if vrouter_name in already_added:
            pass
        else:
            cli = clicopy
            cli += ' vrouter-ospf-add vrouter-name ' + vrouter_name
            cli += ' network %s ospf-area %s' % (ipv4,
                                                 ospf_area_id)

            if 'Success' in run_command(module, cli, task, msg):
                output += ' Added OSPF interface %s to %s \n' % (
                    ipv4, vrouter_name
                )
                CHANGED_FLAG.append(True)

    if addr_type == 'ipv4_ipv6':
        ipv6 = list_ips[1]
    elif addr_type == 'ipv6':
        ipv6 = list_ips[0]

    if addr_type == 'ipv4_ipv6' or addr_type == 'ipv6':
        cli = clicopy
        cli += 'vrouter-interface-show vrouter-name %s' % vrouter_name
        if addr_type == 'ipv4_ipv6':
            cli += ' ip2 %s format nic no-show-headers ' % ipv6
        if addr_type == 'ipv6':
            cli += ' ip %s format nic no-show-headers ' % ipv6
        nic = run_command(module, cli, task, msg).split()
        nic = list(set(nic))
        nic.remove(vrouter_name)
        nic = nic[0]

        cli = clicopy
        cli += 'vrouter-ospf6-show nic %s format switch no-show-headers ' % nic
        ipv6_vrouter = run_command(module, cli, task, msg).split()

        if vrouter_name not in ipv6_vrouter:
            cli = clicopy
            cli += ' vrouter-ospf6-add vrouter-name %s' % vrouter_name
            cli += ' nic %s ospf6-area 0.0.0.0 ' % nic
            run_command(module, cli, task, msg)
            output += ' %s: Added OSPF6 nic %s to %s \n' % (
                vrouter_name, nic, vrouter_name
            )
            CHANGED_FLAG.append(True)

    return output, CHANGED_FLAG


def configure_vrrp_for_clustered_switches(module, vrrp_id, vrrp_ip, vrrp_ipv6,
                                          active_switch, vlan_id, switch_list, mod, CHANGED_FLAG, task, msg):
    """
    Method to configure vrrp interfaces for clustered leaf switches.
    :param module: The Ansible module to fetch input parameters.
    :param vrrp_id: The vrrp_id to be assigned.
    :param vrrp_ip: The vrrp_ip to be assigned.
    :param active_switch: The name of the active switch.
    :param vlan_id: vlan id to be assigned.
    :param switch_list: List of clustered switches.
    :return: The output of the configuration.
    """
    output = ''
    node1 = switch_list[0]
    node2 = switch_list[1]
    name = node1 + '-to-' + node2 + '-cluster'
    list_vips = []
    addr_type = module.params['pn_addr_type']

    if mod == 'l3-vrrp':
        output1, CHANGED_FLAG = create_cluster(module, node2, name, node1, node2, mod, CHANGED_FLAG, task, msg)
        output += output1

    output1, CHANGED_FLAG = create_vlan(module, vlan_id, node2, CHANGED_FLAG, task, msg)
    output += output1

    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        list_vips.append(vrrp_ip)
        ip_addr = vrrp_ip.split('.')
        fourth_octet = ip_addr[3].split('/')
        subnet_ipv4 = fourth_octet[1]
        host_count_ipv4 = int(fourth_octet[0])
        static_ip = ip_addr[0] + '.' + ip_addr[1] + '.' + ip_addr[2] + '.'

    if addr_type == 'ipv4_ipv6' or addr_type == 'ipv6':
        list_vips.append(vrrp_ipv6)
        ipv6 = vrrp_ipv6.split('/')
        subnet_ipv6 = ipv6[1]
        ipv6 = ipv6[0]
        ipv6 = ipv6.split(':')
        if not ipv6[-1]:
            ipv6[-1] = "0"
        host_count_ipv6 = int(ipv6[-1], 16)

    for switch in switch_list:
        list_ips = []
        if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
            host_count_ipv4 = host_count_ipv4 + 1
            vrrp_ipv4 = static_ip + str(host_count_ipv4) + '/' + subnet_ipv4
            list_ips.append(vrrp_ipv4)
        if addr_type == 'ipv4_ipv6' or addr_type == 'ipv6':
            host_count_ipv6 = host_count_ipv6 + 1
            ipv6[-1] = str(hex(host_count_ipv6)[2:])
            vrrp_ipv6_ip = ':'.join(ipv6) + '/' + subnet_ipv6
            list_ips.append(vrrp_ipv6_ip)

        vrrp_priority = '110' if switch == active_switch else '100'
        output1, CHANGED_FLAG = create_vrouter_interface(module, switch, vlan_id, vrrp_id,
                                                         vrrp_priority, list_vips, list_ips,
                                                         CHANGED_FLAG, task, msg)
        output += output1

    return output, CHANGED_FLAG


def delete_trunk(module, switch, switch_port, peer_switch, task, msg):
    """
    Method to delete a conflicting trunk on a switch.
    :param module: The Ansible module to fetch input parameters.
    :param switch: Name of the local switch.
    :param switch_port: The l3-port which is part of conflicting trunk for l3.
    :param peer_switch: Name of the peer switch.
    :return: String describing if trunk got deleted or not.
    """
    cli = pn_cli(module)
    clicopy = cli

    cli += ' switch %s port-show port %s hostname %s ' % (switch, switch_port,
                                                          peer_switch)
    cli += ' format trunk no-show-headers '
    trunk = run_command(module, cli, task, msg).split()
    trunk = list(set(trunk))
    if 'Success' not in trunk and len(trunk) > 0:
        cli = clicopy
        cli += ' switch %s trunk-delete name %s ' % (switch, trunk[0])
        if 'Success' in run_command(module, cli, task, msg):
            CHANGED_FLAG.append(True)
            return ' %s: Deleted %s trunk successfully \n' % (switch, trunk[0])


def update_fabric_network_to_inband(module, switch, task, msg):
    """
    Method to update fabric network type to in-band
    :param module: The Ansible module to fetch input parameters.
    :return: The output of run_command() method.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli

    cli = clicopy
    cli += ' fabric-info format fabric-network '
    fabric_network = run_command(module, cli, task, msg).split()[1]
    if fabric_network != 'in-band':
        cli = clicopy
        cli += ' switch ' + switch
        cli += ' fabric-local-modify fabric-network in-band '
        run_command(module, cli, task, msg)

    output += ' %s: Updated fabric network to in-band \n' % switch

    return output


def modify_auto_trunk_setting(module, switch, flag, task, msg):
    """
    Method to enable/disable auto trunk setting of a switch.
    :param module: The Ansible module to fetch input parameters.
    :param switch: Name of the local switch.
    :param flag: Enable/disable flag for the cli command.
    :return: The output of run_command() method.
    """
    cli = pn_cli(module)
    if flag.lower() == 'enable':
        cli += ' switch %s system-settings-modify auto-trunk ' % switch
        return run_command(module, cli, task, msg)
    elif flag.lower() == 'disable':
        cli += ' switch %s system-settings-modify no-auto-trunk ' % switch
        return run_command(module, cli, task, msg)


def modify_stp(module, modify_flag, switch, CHANGED_FLAG, task, msg):
    """
    Method to enable/disable STP (Spanning Tree Protocol) on all switches.
    :param module: The Ansible module to fetch input parameters.
    :param modify_flag: Enable/disable flag to set.
    :return: The output of run_command() method.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli

    cli = clicopy
    cli += ' switch %s stp-show format enable ' % switch
    current_state = run_command(module, cli, task, msg).split()[1]
    if current_state != 'yes':
        cli = clicopy
        cli += ' switch ' + switch
        cli += ' stp-modify ' + modify_flag
        if 'Success' in run_command(module, cli, task, msg):
            CHANGED_FLAG.append(True)

    output += ' %s: STP enabled \n' % switch

    return CHANGED_FLAG, output


def create_interface(module, switch, ip_ipv4, ip_ipv6, port, addr_type, CHANGED_FLAG, task, msg):
    """
    Method to create vrouter interface and assign IP to it.
    :param module: The Ansible module to fetch input parameters.
    :param switch: The switch name on which vrouter will be created.
    :param ip: IP address to be assigned to vrouter interfaces.
    :param port: l3-port for the interface.
    :return: The output string informing details of vrouter created and
    interface added or if vrouter already exists.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli
    cli += ' vrouter-show location %s format name no-show-headers ' % switch
    vrouter_name = run_command(module, cli, task, msg).split()[0]

    if addr_type == 'ipv4':
        ip = ip_ipv4
    elif addr_type == 'ipv6':
        ip = ip_ipv6
    elif addr_type == 'ipv4_ipv6':
        ip = ip_ipv4
        ip2 = ip_ipv6

    cli = clicopy
    cli += ' vrouter-interface-show l3-port %s ip %s ' % (port, ip)
    cli += ' format switch no-show-headers '
    existing_vrouter = run_command(module, cli, task, msg).split()
    existing_vrouter = list(set(existing_vrouter))

    point_to_point = False
    if vrouter_name not in existing_vrouter:
        # Add vrouter interface.
        cli = clicopy
        cli += ' vrouter-interface-add vrouter-name ' + vrouter_name
        cli += ' ip ' + ip
        if addr_type == 'ipv4_ipv6':
            cli += ' ip2 ' + ip2
        cli += ' l3-port ' + port
        if module.params['pn_jumbo_frames'] is True:
            cli += ' mtu 9216'
        if module.params['pn_if_nat_realm']:
            cli += ' if-nat-realm ' + module.params['pn_if_nat_realm']
        run_command(module, cli, task, msg)
        # Add BFD config to vrouter interface.
        config_args = ''
        if module.params['pn_subnet_ipv4'] == '31' or module.params['pn_subnet_ipv6'] == '127':
            point_to_point = True
        if module.params['pn_bfd']:
            config_args = ' bfd-min-rx %s bfd-multiplier %s' % (module.params['pn_bfd_min_rx'],
                                                                module.params['pn_bfd_multiplier'])
        if config_args or point_to_point:
            cli = clicopy
            cli += ' vrouter-interface-show vrouter-name ' + vrouter_name
            cli += ' l3-port %s format nic no-show-headers ' % port
            nic = run_command(module, cli, task, msg).split()[1]

            cli = clicopy
            cli += ' vrouter-interface-config-add '
            cli += ' vrouter-name %s nic %s ' % (vrouter_name, nic)
            if config_args:
                cli += config_args
            if point_to_point:
                cli += ' ospf-network-type point-to-point'
            run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)

    output += ' %s: Added vrouter interface with ip %s' % (
        switch, ip
    )
    if addr_type == 'ipv4_ipv6':
        output += ' ip2 ' + ip2
    output += ' on %s \n' % vrouter_name
    if module.params['pn_bfd']:
        output += ' %s: Added BFD configuration to %s \n' % (switch,
                                                             vrouter_name)
    if point_to_point:
        output += ' %s: Added OSPF network type as point-to-point to %s \n' % (switch, vrouter_name)

    return CHANGED_FLAG, output


def find_non_clustered_leafs(module, task, msg):
    """
    Method to find leafs which are not part of any cluster.
    :param module: The Ansible module to fetch input parameters.
    :return: List of non clustered leaf switches.
    """
    non_clustered_leafs = []
    cli = pn_cli(module)
    cli += ' cluster-show format cluster-node-1,cluster-node-2 '
    cli += ' no-show-headers '
    clustered_nodes = list(set(run_command(module, cli, task, msg).split()))

    for leaf in module.params['pn_leaf_list']:
        if leaf not in clustered_nodes:
            non_clustered_leafs.append(leaf)

    return non_clustered_leafs


def create_leaf_clusters(module, CHANGED_FLAG, task, msg):
    """
    Method to create cluster between two physically connected leaf switches.
    :param module: The Ansible module to fetch input parameters.
    :return: Output of create_cluster() method.
    """
    output = ''
    non_clustered_leafs = find_non_clustered_leafs(module, task, msg)
    non_clustered_leafs_count = 0
    mod = 'ospf'
    cli = pn_cli(module)
    clicopy = cli

    while non_clustered_leafs_count == 0:
        if len(non_clustered_leafs) == 0:
            non_clustered_leafs_count += 1
        else:
            node1 = non_clustered_leafs[0]
            non_clustered_leafs.remove(node1)

            cli = clicopy
            cli += ' switch %s lldp-show ' % node1
            cli += ' format sys-name no-show-headers '
            system_names = run_command(module, cli, task, msg).split()
            system_names = list(set(system_names))

            cli = clicopy
            cli += ' switch %s fabric-node-show ' % node1
            cli += ' format name no-show-headers '
            nodes_in_fabric = run_command(module, cli, task, msg).split()
            nodes_in_fabric = list(set(nodes_in_fabric))

            for system in system_names:
                if system not in nodes_in_fabric:
                    system_names.remove(system)

            terminate_flag = 0
            node_count = 0
            while (node_count < len(system_names)) and (terminate_flag == 0):
                node2 = system_names[node_count]
                if node2 in non_clustered_leafs:
                    # Cluster creation
                    cluster_name = node1 + '-to-' + node2 + '-cluster'
                    output1, CHANGED_FLAG = create_cluster(module, node2, name, node1, node2, mod, CHANGED_FLAG, task, msg)
                    output += output1

                    non_clustered_leafs.remove(node2)
                    terminate_flag += 1

                node_count += 1

    return CHANGED_FLAG, output


def configure_ospf_bfd(module, vrouter, ip, CHANGED_FLAG, task, msg):
    """
    Method to add ospf_bfd to the vrouter.
    :param module: The Ansible module to fetch input parameters.
    :param vrouter: The vrouter name to add ospf bfd.
    :param ip: The interface ip to associate the ospf bfd.
    :return: String describing if OSPF BFD got added or if it already exists.
    """
    cli = pn_cli(module)
    clicopy = cli
    cli += ' vrouter-interface-show vrouter-name %s' % vrouter
    cli += ' ip %s format nic no-show-headers ' % ip
    nic_interface = run_command(module, cli, task, msg).split()
    nic_interface = list(set(nic_interface))
    nic_interface.remove(vrouter)

    cli = clicopy
    cli += ' vrouter-interface-config-show vrouter-name %s' % vrouter
    cli += ' nic %s format ospf-bfd no-show-headers ' % nic_interface[0]
    ospf_status = run_command(module, cli, task, msg).split()
    ospf_status = list(set(ospf_status))

    cli = clicopy
    cli += ' vrouter-show name ' + vrouter
    cli += ' format location no-show-headers '
    switch = run_command(module, cli, task, msg).split()[0]

    if 'Success' in ospf_status:
        cli = clicopy
        cli += ' vrouter-interface-config-add vrouter-name %s' % vrouter
        cli += ' nic %s ospf-bfd enable' % nic_interface[0]
        if 'Success' in run_command(module, cli, task, msg):
            CHANGED_FLAG.append(True)
            return ' %s: Added OSPF BFD config to %s \n' % (switch, vrouter)
    elif 'enable' not in ospf_status:
        ospf_status.remove(vrouter)
        cli = clicopy
        cli += ' vrouter-interface-config-modify vrouter-name %s' % vrouter
        cli += ' nic %s ospf-bfd enable' % nic_interface[0]
        if 'Success' in run_command(module, cli, task, msg):
            CHANGED_FLAG.append(True)
            output = ' %s: Enabled OSPF BFD for %s \n' % (switch, vrouter)
            return CHANGED_FLAG, output
    else:
        return CHANGED_FLAG, ''


def find_area_id_leaf_switches(module, task, msg):
    """
    Method to find area_id for all leaf switches and store it in a dictionary.
    :param module: The Ansible module to fetch input parameters.
    :return: Dictionary containing area_id of all leaf switches.
    """
    leaf_list = module.params['pn_leaf_list']
    ospf_area_id = int(module.params['pn_ospf_v4_area_id'])
    area_configure_flag = module.params['pn_area_configure_flag']
    cluster_leaf_list = []
    cli = pn_cli(module)
    clicopy = cli
    dict_area_id = {}

    if area_configure_flag == 'singlearea':
        for leaf in leaf_list:
            dict_area_id[leaf] = str(ospf_area_id)
    else:
        cli += ' cluster-show format name no-show-headers'
        cluster_list = list(set(run_command(module, cli, task, msg).split()))

        if 'Success' not in cluster_list:
            for cluster in cluster_list:
                cli = clicopy
                cli += ' cluster-show name %s' % cluster
                cli += ' format cluster-node-1,cluster-node-2 no-show-headers'
                cluster_nodes = run_command(module, cli, task, msg).split()

                if cluster_nodes[0] in leaf_list and cluster_nodes[1] in leaf_list:
                    ospf_area_id += 1
                    dict_area_id[cluster_nodes[0]] = str(ospf_area_id)
                    dict_area_id[cluster_nodes[1]] = str(ospf_area_id)
                    cluster_leaf_list.append(cluster_nodes[0])
                    cluster_leaf_list.append(cluster_nodes[1])

        non_clustered_leaf_list = list(set(leaf_list) - set(cluster_leaf_list))
        for leaf in non_clustered_leaf_list:
            ospf_area_id += 1
            dict_area_id[leaf] = str(ospf_area_id)

    return dict_area_id


def add_ospf_redistribute(module, current_switch, CHANGED_FLAG, task, msg):
    """
    Method to add ospf_redistribute to the vrouters.
    :param module: The Ansible module to fetch input parameters.
    :param vrouter_names: List of vrouter names.
    :return: String describing if ospf-redistribute got added or not.
    """
    output = ''
    pn_ospf_redistribute = module.params['pn_ospf_redistribute']
    cli = pn_cli(module)
    clicopy = cli
    vrouter = current_switch + '-vrouter'

    cli = clicopy
    cli += ' vrouter-modify name %s' % vrouter
    cli += ' ospf-redistribute %s' % pn_ospf_redistribute
    if 'Success' in run_command(module, cli, task, msg):
        output += ' %s: Added ospf_redistribute to %s \n' % (current_switch,
                                                             vrouter)
        CHANGED_FLAG.append(True)

    return CHANGED_FLAG, output


def add_ospf_loopback(module, current_switch, CHANGED_FLAG, task, msg):
    """
    Method to add loopback network to OSPF
    :param module: The Ansible module to fetch input parameters.
    :param current_switch: Switch to add network statements.
    :return: String describing if loopback network got added to OSPF or not.
    """
    output = ''
    cli = pn_cli(module)
    cli += ' switch %s ' % current_switch
    clicopy = cli
    vr_name = current_switch + '-vrouter'

    cli += ' vrouter-loopback-interface-show vrouter-name %s' % vr_name
    cli += ' format ip,router-if parsable-delim ,'
    loopback_ip = run_command(module, cli, task, msg).strip().split('\n')
    for addr in loopback_ip:
        ip1 = addr.split(',')
        ip = ip1[1]
        if len(ip.split('.')) == 1:
            nic = ip1[2]
            cli = clicopy
            cli += ' vrouter-ospf6-show vrouter-name %s' % vr_name
            cli += ' nic %s no-show-headers ' % nic
            already_added = run_command(module, cli, task, msg)
            if 'Success' in already_added:
                cli = clicopy
                cli += ' vrouter-ospf6-add vrouter-name %s' % vr_name
                cli += ' nic %s' % nic
                cli += ' ospf6-area %s' % module.params['pn_ospf_v6_area_id']
                output += run_command(module, cli, task, msg)

            # Add loopback interface 'lo' to ospf6
            cli = clicopy
            nic = "lo"
            cli += ' vrouter-ospf6-show vrouter-name %s' % vr_name
            cli += ' nic %s no-show-headers ' % nic
            already_added = run_command(module, cli, task, msg)
            if 'Success' in already_added:
                cli = clicopy
                cli += ' vrouter-ospf6-add vrouter-name %s' % vr_name
                cli += ' nic %s' % nic
                cli += ' ospf6-area %s' % module.params['pn_ospf_v6_area_id']
                output += run_command(module, cli, task, msg)
        else:
            l_ip = ip1[1]
            cli = clicopy
            cli += ' vrouter-ospf-show vrouter-name %s' % vr_name
            cli += ' network %s no-show-headers ' % l_ip
            already_added = run_command(module, cli, task, msg).split()
            if 'Success' in already_added:
                cli = clicopy
                cli += ' vrouter-ospf-add vrouter-name %s' % vr_name
                cli += ' network %s/32' % l_ip
                cli += ' ospf-area %s' % module.params['pn_ospf_v4_area_id']
                output += run_command(module, cli, task, msg)

    return CHANGED_FLAG, output


def vrouter_iospf_interface_add(module, switch_name, ip_addr, ip2_addr, ospf_area_id, p2p, CHANGED_FLAG, task, msg):
    """
    Method to create interfaces and add ospf neighbors.
    :param module: The Ansible module to fetch input parameters.
    :param switch_name: The name of the switch to run interface.
    :param ip_addr: Interface ipv4 address to create a vrouter interface.
    :param ip2_addr: Interface ipv6 address to create a vrouter interface.
    :param ospf_area_id: The area_id for ospf neighborship.
    :return: String describing if ospf neighbors got added or not.
    """
    output = ''
    vlan_id = module.params['pn_iospf_vlan']
    pim_ssm = module.params['pn_pim_ssm']
    ospf_cost = module.params['pn_ospf_cost']
    addr_type = module.params['pn_addr_type']

    cli = pn_cli(module)
    clicopy = cli
    cli += ' vrouter-show location %s format name' % switch_name
    cli += ' no-show-headers'
    vrouter = run_command(module, cli, task, msg).split()[0]

    cli = clicopy
    cli += ' vrouter-interface-show ip %s vlan %s' % (ip_addr, vlan_id)
    cli += ' format switch no-show-headers'
    existing_vrouter_interface = run_command(module, cli, task, msg).split()

    if vrouter not in existing_vrouter_interface:
        cli = clicopy
        cli += ' vrouter-interface-add vrouter-name %s vlan %s ip %s' % (
            vrouter, vlan_id, ip_addr
        )
        if ip2_addr:
            cli += ' ip2 %s' % (ip2_addr)
        if pim_ssm is True:
            cli += ' pim-cluster '
        if module.params['pn_jumbo_frames'] is True:
            cli += ' mtu 9216'
        run_command(module, cli, task, msg)
        ip_msg = 'ip %s' % (ip_addr)
        if ip2_addr:
            ip_msg += ' ip2 %s' % (ip2_addr)
        output += ' %s: Added vrouter interface with %s on %s \n' % (
            switch_name, ip_msg, vrouter
        )
        CHANGED_FLAG.append(True)

    cli = clicopy
    cli += ' vrouter-interface-show vlan %s ' % vlan_id
    cli += ' vrouter-name %s format nic parsable-delim ,' % vrouter
    nic = run_command(module, cli, task, msg).split(',')[1]

    cli = clicopy
    cli += ' vrouter-interface-config-show vrouter-name %s' % vrouter
    cli += ' nic %s no-show-headers ' % nic
    config_exists = run_command(module, cli, task, msg).split()
    cli = clicopy
    if 'Success' in config_exists:
        cli += ' vrouter-interface-config-add vrouter-name %s' % vrouter
        cli += ' nic %s ospf-cost %s' % (nic, ospf_cost)
    else:
        cli += ' vrouter-interface-config-modify vrouter-name %s' % vrouter
        cli += ' nic %s ospf-cost %s' % (nic, ospf_cost)
    if p2p:
        cli += ' ospf-network-type point-to-point'
    run_command(module, cli, task, msg)

    if ip_addr and (addr_type == 'ipv4' or addr_type == 'ipv4_ipv6'):
        cli = clicopy
        cli += ' vrouter-ospf-show'
        cli += ' network %s format switch no-show-headers ' % ip_addr
        already_added = run_command(module, cli, task, msg).split()

        if vrouter in already_added:
            pass
        else:
            ip_addr_without_subnet = ip_addr.split('/')[0]
            if module.params['pn_bfd']:
                CHANGED_FLAG, output1 = configure_ospf_bfd(module, vrouter,
                                                           ip_addr_without_subnet, CHANGED_FLAG, task, msg)
                output += output1
            cli = clicopy
            cli += ' vrouter-ospf-add vrouter-name ' + vrouter
            cli += ' network %s ospf-area %s' % (ip_addr, ospf_area_id)

            if 'Success' in run_command(module, cli, task, msg):
                output += ' %s: Added OSPF neighbor %s to %s \n' % (
                    switch_name, ip_addr, vrouter
                )
                CHANGED_FLAG.append(True)

    if (ip_addr and addr_type == 'ipv6') or ip2_addr:
        cli = clicopy
        cli += 'vrouter-ospf6-show nic %s format switch no-show-headers ' % nic
        ip2_vrouter = run_command(module, cli, task, msg).split()

        if vrouter not in ip2_vrouter:
            cli = clicopy
            cli += 'vrouter-ospf6-add vrouter-name %s nic %s ospf6-area %s ' % (
                vrouter, nic, module.params['pn_ospf_v6_area_id'])
            run_command(module, cli, task, msg)
            output += ' %s: Added OSPF6 nic %s to %s \n' % (
                switch_name, nic, vrouter
            )

    return CHANGED_FLAG, output


def vrouter_iospf_vlan_ports_add(module, switch_name, cluster_ports, task, msg):
    """
    Method to create iOSPF vlan and add ports to it
    :param module: The Ansible module to fetch input parameters.
    :param switch_name: The name of the switch to run interface.
    :return: String describing if ospf vlan got added or not.
    """
    output = ''
    vlan_id = module.params['pn_iospf_vlan']

    cli = pn_cli(module)
    clicopy = cli
    cli += ' switch %s vlan-show format id no-show-headers ' % switch_name
    existing_vlans = run_command(module, cli, task, msg).split()

    if vlan_id not in existing_vlans:
        cli = clicopy
        cli += ' switch %s vlan-create id %s scope cluster ' % (switch_name,
                                                                vlan_id)
        cli += ' ports none description iOSPF-cluster-vlan '
        run_command(module, cli, task, msg)
        output = ' %s: Created vlan with id %s \n' % (switch_name, vlan_id)

    cli = clicopy
    cli += ' switch %s vlan-port-add vlan-id %s ports %s' % (switch_name, vlan_id, cluster_ports)
    run_command(module, cli, task, msg)

    return output


def assign_leafcluster_ospf_interface(module, dict_area_id, current_switch, CHANGED_FLAG, task, msg):
    """
    Method to create interfaces and add ospf neighbor for leaf cluster.
    :param module: The Ansible module to fetch input parameters.
    :param dict_area_id: Dictionary containing area_id of leafs.
    :return: The output of vrouter_interface_ibgp_add() method.
    """
    output = ''
    ip_1, ip_2, ip2_1, ip2_2 = '', '', '', ''
    spine_list = module.params['pn_spine_list']
    leaf_list = module.params['pn_leaf_list']
    addr_type = module.params['pn_addr_type']
    iospf_v4_range = module.params['pn_iospf_ipv4_range']
    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        cidr_v4 = int(module.params['pn_ospf_cidr_ipv4'])
    subnet_v4 = module.params['pn_ospf_subnet_ipv4']
    iospf_v6_range = module.params['pn_iospf_ipv6_range']
    if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
        cidr_v6 = int(module.params['pn_cidr_ipv6'])
    subnet_v6 = module.params['pn_subnet_ipv6']

    cli = pn_cli(module)
    clicopy = cli

    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        available_ips_ipv4 = calculate_link_ip_addresses_ipv4(iospf_v4_range, cidr_v4, subnet_v4)

    if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
        get_count = 2 if subnet_v6 == '127' else 3
        available_ips_ipv6 = calculate_link_ip_addresses_ipv6(iospf_v6_range, cidr_v6, subnet_v6,
                                                              get_count)

    cli += ' cluster-show format name no-show-headers '
    cluster_list = list(set(run_command(module, cli, task, msg).split()))

    if len(cluster_list) > 0 and cluster_list[0] != 'Success':
        point_to_point = False
        if subnet_v4 == '31' or subnet_v6 == '127':
            point_to_point = True

        for cluster in cluster_list:
            cli = clicopy
            cli += ' cluster-show name %s format cluster-node-1,' % cluster
            cli += 'ports,cluster-node-2,remote-ports no-show-headers'
            c_nod_1, c_por_1, c_nod_2, c_por_2 = run_command(module, cli, task, msg).splitlines()[0].split()

            if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
                ip_1, ip_2 = available_ips_ipv4[0:2]
                available_ips_ipv4.remove(ip_1)
                available_ips_ipv4.remove(ip_2)
            if addr_type == 'ipv4_ipv6':
                ip_list = available_ips_ipv6.next()
                if subnet_v6 == '127':
                    ip2_1, ip2_2 = ip_list[0:2]
                else:
                    ip2_1, ip2_2 = ip_list[1:3]
            if addr_type == 'ipv6':
                ip_list = available_ips_ipv6.next()
                if subnet_v6 == '127':
                    ip_1, ip_2 = ip_list[0:2]
                else:
                    ip_1, ip_2 = ip_list[1:3]

            if c_nod_1 not in spine_list and c_nod_1 in leaf_list:
                ospf_area_id = dict_area_id[c_nod_1]
                output += vrouter_iospf_vlan_ports_add(module, c_nod_1, c_por_1, task, msg)
                CHANGED_FLAG, output1 = vrouter_iospf_interface_add(module, c_nod_1, ip_1, ip2_1,
                                                                    ospf_area_id, point_to_point, CHANGED_FLAG, task, msg)
                output += output1
                output += vrouter_iospf_vlan_ports_add(module, c_nod_2, c_por_2, task, msg)
                CHANGED_FLAG, output1 = vrouter_iospf_interface_add(module, c_nod_2, ip_2, ip2_2,
                                                                    ospf_area_id, point_to_point, CHANGED_FLAG, task, msg)
                output += output1
    else:
        output += ' No leaf clusters present to add iOSPF \n'

    return CHANGED_FLAG, output


def make_interface_passive(module, current_switch, CHANGED_FLAG, task, msg):
    """
    Method to make VRRP interfaces ospf passive.
    :param module: The Ansible module to fetch input parameters.
    :return: String describing if ospf passive interfaces changed or not.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli
    addr_type = module.params['pn_addr_type']

    vrname = "%s-vrouter" % current_switch
    cli = clicopy
    cli += ' switch %s vrouter-interface-config-show vrouter-name ' % current_switch
    cli += ' %s format nic,ospf-passive-if parsable-delim ,' % vrname
    pass_intf = run_command(module, cli, task, msg).split()
    passv_info = {}
    for intf in pass_intf:
        if not intf:
            break
        vrname, intf_index, passv = intf.split(',')
        passv_info[intf_index] = passv

    cli = clicopy
    cli += ' switch %s vrouter-interface-show vrouter-name %s ' % (current_switch, vrname)
    cli += ' format is-vip,is-primary,nic parsable-delim ,'
    intf_info = run_command(module, cli, task, msg).split()

    for intf in intf_info:
        if not intf:
            output += "No router interface exist"
        vrname, is_vip, is_primary, intf_index = intf.split(',')
        if is_vip == 'true' or is_primary == 'true':
            if intf_index in passv_info:
                if passv_info[intf_index] == "false":
                    cli = clicopy
                    cli += ' vrouter-interface-config-modify vrouter-name %s ' % vrname
                    cli += ' nic %s ospf-passive-if ' % intf_index
                    run_command(module, cli, task, msg)
            else:
                cli = clicopy
                cli += ' vrouter-interface-config-add vrouter-name %s ' % vrname
                cli += ' nic %s ospf-passive-if ' % intf_index
                run_command(module, cli, task, msg)
                output += '%s: Added OSPF nic %s to %s \n' % (
                    vrname, intf_index, vrname
                )
            CHANGED_FLAG.append(True)

    # Add interface config to 'lo'
    if addr_type == 'ipv4_ipv6' or addr_type == 'ipv6':
        cli = clicopy
        cli += ' vrouter-interface-config-add vrouter-name %s ' % vrname
        cli += ' nic lo ospf-passive-if '
        run_command(module, cli, task, msg)
        output += '%s: Added OSPF nic lo to %s \n' % (current_switch, vrname)
        CHANGED_FLAG.append(True)

    return CHANGED_FLAG, output


def find_bgp_as_dict(module, task, msg):
    """
    Method to find bgp-as for all switches and store it in a dictionary.
    :param module: The Ansible module to fetch input parameters.
    :return: Dictionary containing switch: bgp_as key value pairs.
    """
    leaf_list = module.params['pn_leaf_list']
    bgp_as = int(module.params['pn_bgp_as_range'])
    cluster_leaf_list = []
    cli = pn_cli(module)
    clicopy = cli
    dict_bgp_as = {}

    for spine in module.params['pn_spine_list']:
        dict_bgp_as[spine] = str(bgp_as)

    cli += ' cluster-show format name no-show-headers'
    cluster_list = list(set(run_command(module, cli, task, msg).split()))

    if 'Success' not in cluster_list:
        for cluster in cluster_list:
            cli = clicopy
            cli += ' cluster-show name %s' % cluster
            cli += ' format cluster-node-1,cluster-node-2 no-show-headers'
            cluster_nodes = list(set(run_command(module, cli, task, msg).split()))

            if cluster_nodes[0] in leaf_list and cluster_nodes[1] in leaf_list:
                bgp_as += 1
                dict_bgp_as[cluster_nodes[0]] = str(bgp_as)
                dict_bgp_as[cluster_nodes[1]] = str(bgp_as)
                cluster_leaf_list.append(cluster_nodes[0])
                cluster_leaf_list.append(cluster_nodes[1])

    non_clustered_leaf_list = list(set(leaf_list) - set(cluster_leaf_list))
    for leaf in non_clustered_leaf_list:
        bgp_as += 1
        dict_bgp_as[leaf] = str(bgp_as)

    return dict_bgp_as


def vrouter_interface_ibgp_add(module, switch_name, interface_ip, neighbor_ip,
                               remote_as, CHANGED_FLAG, task, msg, interface_ipv6=None, neighbor_ipv6=None):
    """
    Method to create interfaces and add ibgp neighbors.
    :param module: The Ansible module to fetch input parameters.
    :param switch_name: The name of the switch to run interface.
    :param interface_ip: Interface ip to create a vrouter interface.
    :param neighbor_ip: Neighbor_ip for the ibgp neighbor.
    :param interface_ipv6: Interface ipv6 to create a vrouter interface.
    :param neighbor_ipv6: Neighbor_ipv6 for the ibgp neighbor.
    :param remote_as: Bgp-as for remote switch.
    :return: String describing if ibgp neighbours got added or already exists.
    """
    output = ''
    vlan_id = module.params['pn_ibgp_vlan']
    pim_ssm = module.params['pn_pim_ssm']

    cli = pn_cli(module)
    clicopy = cli
    cli += ' switch %s vlan-show format id no-show-headers ' % switch_name
    existing_vlans = run_command(module, cli, task, msg).split()

    if vlan_id not in existing_vlans:
        cli = clicopy
        cli += ' switch %s vlan-create id %s scope local ' % (switch_name,
                                                              vlan_id)
        run_command(module, cli, task, msg)

        output += ' %s: Created vlan with id %s \n' % (switch_name, vlan_id)
        CHANGED_FLAG.append(True)

    cli = clicopy
    cli += ' vrouter-show location %s format name' % switch_name
    cli += ' no-show-headers'
    vrouter = run_command(module, cli, task, msg).split()[0]
    cli = clicopy
    cli += ' vrouter-interface-show ip %s ' % interface_ip
    if interface_ipv6:
        cli += 'ip2 %s ' % interface_ipv6
    cli += 'vlan %s' % vlan_id
    cli += ' format switch no-show-headers'
    existing_vrouter_interface = run_command(module, cli, task, msg).split()

    if vrouter not in existing_vrouter_interface:
        cli = clicopy
        cli += 'vrouter-interface-add vrouter-name %s ' % vrouter
        cli += 'ip %s ' % interface_ip
        if interface_ipv6:
            cli += 'ip2 %s ' % interface_ipv6
        if pim_ssm is True:
            cli += ' pim-cluster '
        if module.params['pn_jumbo_frames'] is True:
            cli += ' mtu 9216'
        cli += 'vlan %s ' % vlan_id
        run_command(module, cli, task, msg)

        output += ' %s: Added vrouter interface with ip %s ip2 %s on %s \n' % (
            switch_name, interface_ip, interface_ipv6, vrouter
        )
        CHANGED_FLAG.append(True)

    neighbor_ip = neighbor_ip.split('/')[0]
    cli = clicopy
    cli += ' vrouter-bgp-show remote-as ' + remote_as
    cli += ' neighbor %s format switch no-show-headers' % neighbor_ip
    already_added = run_command(module, cli, task, msg).split()

    if vrouter not in already_added:
        cli = clicopy
        cli += ' vrouter-bgp-add vrouter-name %s' % vrouter
        cli += ' neighbor %s remote-as %s next-hop-self' % (neighbor_ip,
                                                            remote_as)
        if module.params['pn_bfd']:
            cli += ' bfd '

        if 'Success' in run_command(module, cli, task, msg):
            output += ' %s: Added iBGP neighbor %s for %s \n' % (switch_name,
                                                                 neighbor_ip,
                                                                 vrouter)
            CHANGED_FLAG.append(True)

    if neighbor_ipv6:
        neighbor_ipv6 = neighbor_ipv6.split('/')[0]
        cli = clicopy
        cli += ' vrouter-bgp-show remote-as ' + remote_as
        cli += ' neighbor %s format switch no-show-headers' % neighbor_ipv6
        already_added = run_command(module, cli, task, msg).split()

        if vrouter not in already_added:
            cli = clicopy
            cli += ' vrouter-bgp-add vrouter-name %s' % vrouter
            cli += ' neighbor %s remote-as %s next-hop-self' % (neighbor_ipv6,
                                                                remote_as)
            if module.params['pn_bfd']:
                cli += ' bfd '

            if 'Success' in run_command(module, cli, task, msg):
                output += ' %s: Added iBGP neighbor %s for %s \n' % (switch_name,
                                                                     neighbor_ipv6,
                                                                     vrouter)
            CHANGED_FLAG.append(True)

    return CHANGED_FLAG, output


def assign_ibgp_interface(module, dict_bgp_as, CHANGED_FLAG, task, msg):
    """
    Method to create interfaces and add ibgp neighbors.
    :param module: The Ansible module to fetch input parameters.
    :param dict_bgp_as: The dictionary containing bgp-as of all switches.
    :return: The output of vrouter_interface_ibgp_add() method.
    """
    output = ''
    spine_list = module.params['pn_spine_list']
    leaf_list = module.params['pn_leaf_list']
    addr_type = module.params['pn_addr_type']
    ibgp_ipv4_range = module.params['pn_ibgp_ipv4_range']
    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        cidr_v4 = int(module.params['pn_ibgp_cidr_ipv4'])
    subnet_v4 = module.params['pn_ibgp_subnet_ipv4']
    ibgp_ipv6_range = module.params['pn_ibgp_ipv6_range']
    if addr_type == 'ipv6' or addr_type == 'ipv4_ipv6':
        cidr_v6 = int(module.params['pn_cidr_ipv6'])
    subnet_v6 = module.params['pn_subnet_ipv6']

    cli = pn_cli(module)
    clicopy = cli

    if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
        available_ips_ipv4 = calculate_link_ip_addresses_ipv4(ibgp_ipv4_range, cidr_v4, subnet_v4)

    if addr_type == 'ipv4_ipv6' or addr_type == 'ipv6':
        get_count = 2 if subnet_v6 == '127' else 3
        available_ips_ipv6 = calculate_link_ip_addresses_ipv6(ibgp_ipv6_range, cidr_v6, subnet_v6,
                                                              get_count)

    cli = pn_cli(module)
    clicopy = cli

    cli += ' cluster-show format name no-show-headers '
    cluster_list = list(set(run_command(module, cli, task, msg).split()))

    if len(cluster_list) > 0 and cluster_list[0] != 'Success':
        for cluster in cluster_list:
            cli = clicopy
            cli += ' cluster-show name %s format cluster-node-1,' % cluster
            cli += 'cluster-node-2 no-show-headers'
            cluster_node_1, cluster_node_2 = list(set(run_command(module, cli, task, msg).split()))

            if cluster_node_1 not in spine_list and cluster_node_1 in leaf_list:
                if addr_type == 'ipv4' or addr_type == 'ipv4_ipv6':
                    ipv4_1, ipv4_2 = available_ips_ipv4[0:2]
                    available_ips_ipv4.remove(ipv4_1)
                    available_ips_ipv4.remove(ipv4_2)
                if addr_type == 'ipv4_ipv6' or addr_type == 'ipv6':
                    ip_list = available_ips_ipv6.next()
                    if subnet_v6 == '127':
                        ipv6_1, ipv6_2 = ip_list[0:2]
                    else:
                        ipv6_1, ipv6_2 = ip_list[1:3]

            remote_as = dict_bgp_as[cluster_node_1]
            if cluster_node_1 not in spine_list and cluster_node_1 in leaf_list:
                if addr_type == 'ipv4':
                    CHANGED_FLAG, output1 = vrouter_interface_ibgp_add(module, cluster_node_1,
                                                                       ipv4_1, ipv4_2, remote_as,
                                                                       CHANGED_FLAG, task, msg)
                    output += output1
                    CHANGED_FLAG, output1 = vrouter_interface_ibgp_add(module, cluster_node_2,
                                                                       ipv4_2, ipv4_1, remote_as,
                                                                       CHANGED_FLAG, task, msg)
                    output += output1
                elif addr_type == 'ipv4_ipv6':
                    CHANGED_FLAG, output1 = vrouter_interface_ibgp_add(module, cluster_node_1,
                                                                       ipv4_1, ipv4_2, remote_as,
                                                                       CHANGED_FLAG, task, msg, ipv6_1, ipv6_2)
                    output += output1
                    CHANGED_FLAG, output1 = vrouter_interface_ibgp_add(module, cluster_node_2,
                                                                       ipv4_2, ipv4_1, remote_as,
                                                                       CHANGED_FLAG, task, msg, ipv6_2, ipv6_1)
                    output += output1
                else:
                    CHANGED_FLAG, output1 = vrouter_interface_ibgp_add(module, cluster_node_1,
                                                                       ipv6_1, ipv6_2, remote_as, CHANGED_FLAG, task, msg)
                    output += output1
                    CHANGED_FLAG, output1 = vrouter_interface_ibgp_add(module, cluster_node_2,
                                                                       ipv6_2, ipv6_1, remote_as, CHANGED_FLAG, task, msg)
                    output += output1
    else:
        output += ' No leaf clusters present to add iBGP \n'

    return CHANGED_FLAG, output


def configure_bgp(module, vrouter_names, dict_bgp_as, bgp_max, bgp_redis, CHANGED_FLAG, task, msg):
    """
    Method to add bgp_as, bgp_max_path and bgp_redistribute to the vrouters.
    :param module: The Ansible module to fetch input parameters.
    :param dict_bgp_as: Dictionary containing the bgp-as for all the switches.
    :param vrouter_names: List of vrouter names.
    :param bgp_max: Maxpath for bgp.
    :param bgp_redis: Bgp redistribute for bgp.
    :return: String describing if bgp config got added or not.
    """
    output = ''
    cli = pn_cli(module)
    clicopy = cli

    for vrouter in vrouter_names:
        cli = clicopy
        cli += ' vrouter-show name ' + vrouter
        cli += ' format location no-show-headers '
        switch = run_command(module, cli, task, msg).split()[0]

        cli = clicopy
        cli += ' vrouter-modify name %s ' % vrouter
        cli += ' bgp-as %s ' % dict_bgp_as[switch]
        cli += ' bgp-max-paths %s ' % bgp_max
        cli += ' bgp-redistribute %s ' % bgp_redis
        if 'Success' in run_command(module, cli, task, msg):
            output += ' %s: Added bgp_redistribute %s ' % (switch, bgp_redis)
            output += 'bgp_as %s bgp_maxpath %s to %s\n' % (dict_bgp_as[switch],
                                                            bgp_max, vrouter)
            CHANGED_FLAG.append(True)

    return CHANGED_FLAG, output


def create_vlag(module, name, switch, port, peer_switch, peer_port, CHANGED_FLAG, task, msg):
    """
    Create virtual link aggregation groups.
    :param module: The Ansible module to fetch input parameters.
    :param name: The name of the vlag to create.
    :param switch: Name of the local switch.
    :param port: Name of the trunk on local switch.
    :param peer_switch: Name of the peer switch.
    :param peer_port: Name of the trunk on peer switch.
    :return: String describing if vlag got created or not.
    """
    output = ''

    cli = pn_cli(module)
    cli += ' switch %s vlag-show format name' % switch
    cli += ' no-show-headers '
    vlag_list = run_command(module, cli, task, msg).split()

    if name not in vlag_list:
        cli = pn_cli(module)
        cli += ' switch %s vlag-create name %s port %s ' % (switch, name, port)
        cli += ' peer-switch %s peer-port %s ' % (peer_switch, peer_port)
        cli += ' mode active-active '
        run_command(module, cli, task, msg)
        CHANGED_FLAG.append(True)
        output += '%s: Configured vLag %s\n' % (switch, name)

    return CHANGED_FLAG, output
