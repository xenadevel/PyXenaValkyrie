
from trafficgenerator.tgn_app import TgnApp
from xenamanager.api.XenaSocket import XenaSocket
from xenamanager.api.KeepAliveThread import KeepAliveThread
from xenamanager.xena_object import XenaObject
from xenamanager.xena_port import XenaPort


def init_xena(logger):
    """ Create Xena manager object.

    :param logger: python logger object
    :return: Xena object
    """

    return XenaApp(logger)


class XenaApp(TgnApp):

    def __init__(self, logger):
        self.logger = logger
        self.session = XenaSession(self.logger)

    def add_chassis(self, chassis, owner, password='xena'):
        self.session.add_chassis(chassis, owner, password)

    def disconnect(self):
        self.session.disconnect()


class XenaSession(XenaObject):

    def __init__(self, logger):
        self.logger = logger
        self.api = None
        super(self.__class__, self).__init__(objType='session', index='', parent=None)

    def add_chassis(self, chassis, owner, password='xena'):
        XenaChassis(chassis, self).logon(owner, password)

    def disconnect(self):
        self.release_ports()
        for chassis in self.get_objects_by_type('chassis'):
            chassis.disconnect()

    def inventory(self):
        for chassis in self.get_objects_by_type('chassis'):
            chassis.inventory()

    def reserve_ports(self, locations, force=False):
        """ Reserve ports and reset factory defaults.

        :param locations: list of ports locations in the form <ip/slot/port> to reserve
        :param force: True - take forcefully, False - fail if port is reserved by other user
        :return: ports dictionary (index: object)
        """

        for location in locations:
            ip, module, port = location.split('/')
            self.chassis_list[ip].reserve_ports(['{}/{}'.format(module, port)], force)

        return self.ports

    def release_ports(self):
        for port in self.ports.values():
            port.release()

    def start_traffic(self, *ports):
        for chassis, chassis_ports in self._per_chassis_ports(*self._get_operation_ports(*ports)).items():
            chassis.start_traffic(*chassis_ports)

    def stop_traffic(self, *ports):
        for chassis, chassis_ports in self._per_chassis_ports(*self._get_operation_ports(*ports)).items():
            chassis.stop_traffic(*chassis_ports)

    def _get_operation_ports(self, *ports):
        return ports if ports else self.ports.values()

    def _per_chassis_ports(self, *ports):
        per_chassis_ports = {}
        for port in ports:
            chassis = self.get_object_by_name(port.name.split('/')[0])
            if chassis not in per_chassis_ports:
                per_chassis_ports[chassis] = []
            per_chassis_ports[chassis].append(port)
        return per_chassis_ports

    @property
    def chassis_list(self):
        """
        :return: dictionary {name: object} of all chassis.
        """

        return {str(c): c for c in self.get_objects_by_type('chassis')}

    @property
    def ports(self):
        """
        :return: dictionary {name: object} of all ports.
        """

        ports = {}
        for chassis in self.chassis_list.values():
            ports.update({str(p): p for p in chassis.get_objects_by_type('port')})
        return ports


class XenaChassis(XenaObject):

    def __init__(self, ip, parent):
        super(self.__class__, self).__init__(objType='chassis', index='', parent=parent, name=ip)

        self.api = XenaSocket(self.logger, ip)
        self.api.connect()
        self.keep_alive_thread = KeepAliveThread(self.api)
        self.keep_alive_thread.start()

    def logon(self, owner, password):
        self.send_command('c_logon', '"{}"'.format(password))
        self.send_command('c_owner', '"{}"'.format(owner))

    def disconnect(self):
        self.api.disconnect()

    def inventory(self):
        self.c_info = self.get_attributes('c_info')
        for m_index, m_portcounts in enumerate(self.c_info['c_portcounts'].split()):
            if int(m_portcounts):
                XenaModule(index=m_index, parent=self).inventory()

    def reserve_ports(self, locations, force=False):
        """ Reserve ports and reset factory defaults.

        :param locations: list of ports locations in the form <slot/port> to reserve
        :param force: True - take forcefully, False - fail if port is reserved by other user
        :return: ports dictionary (index: object)
        """

        for location in locations:
            port = XenaPort(location=location, parent=self)
            port.reserve(force)
            port.reset()

        return self.ports

    def start_traffic(self, *ports):
        self._traffic_command('on')

    def stop_traffic(self, *ports):
        self._traffic_command('off')

    def _traffic_command(self, command, *ports):
        ports = self._get_operation_ports(*ports)
        ports_str = ' '.join([p.ref.replace('/', ' ') for p in ports])
        self.send_command('c_traffic', command, ports_str)
        for port in ports:
            port.wait_for_states('p_traffic', 40, command)

    def _get_operation_ports(self, *ports):
        return ports if ports else self.ports.values()

    @property
    def modules(self):
        """
        :return: dictionary {index: object} of all modules.
        """

        return {int(c.ref): c for c in self.get_objects_by_type('module')}

    @property
    def ports(self):
        """
        :return: dictionary {name: object} of all ports.
        """

        return {str(p): p for p in self.get_objects_by_type('port')}


class XenaModule(XenaObject):

    def __init__(self, index, parent):
        super(self.__class__, self).__init__(objType='module', index=index, parent=parent)

    def inventory(self):
        self.m_info = self.get_attributes('m_info')
        if 'NOTCFP' in self.m_info['m_cfptype']:
            m_portcount = int(self.get_attribute('m_portcount'))
        else:
            m_portcount = int(self.get_attribute('m_cfpconfig').split()[0])
        for p_index in range(m_portcount):
            XenaPort(location='{}/{}'.format(self.ref, p_index), parent=self).inventory()

    @property
    def ports(self):
        """
        :return: dictionary {index: object} of all ports.
        """

        return {int(p.ref.split('/')[1]): p for p in self.get_objects_by_type('port')}