"""
Classes and utilities that represents Xena XenaManager-2G port.

:author: yoram@ignissoft.com
"""

import os
import re
import math

from collections import OrderedDict
from enum import Enum

from xenavalkyrie.api.xena_socket import XenaCommandError
from xenavalkyrie.xena_object import XenaObject, XenaObject21
from xenavalkyrie.xena_stream import XenaStream, XenaStreamState
from xenavalkyrie.xena_filter import XenaFilterState, XenaFilter, XenaMatch, XenaLength


class XenaCaptureBufferType(Enum):
    raw = 0
    text = 1
    pcap = 2


class XenaBasePort(XenaObject):
    """ Represents Xena port. """

    cli_prefix = 'p'

    _info_config_commands = ['p_info', 'p_config', 'p_receivesync', 'ps_indices', 'pr_tplds']

    stats_captions = {'pr_pfcstats': ['total', 'CoS 0', 'CoS 1', 'CoS 2', 'CoS 3', 'CoS 4', 'CoS 5', 'CoS 6', 'CoS 7'],
                      'pr_total': ['bps', 'pps', 'bytes', 'packets'],
                      'pr_notpld': ['bps', 'pps', 'bytes', 'packets'],
                      'pr_extra': ['fcserrors', 'pauseframes', 'arprequests', 'arpreplies', 'pingrequests',
                                   'pingreplies', 'gapcount', 'gapduration'],
                      'pt_total': ['bps', 'pps', 'bytes', 'packets'],
                      'pt_extra': ['arprequests', 'arpreplies', 'pingrequests', 'pingreplies', 'injectedfcs',
                                   'injectedseq', 'injectedmis', 'injectedint', 'injectedtid', 'training'],
                      'pt_notpld': ['bps', 'pps', 'bytes', 'packets']}

    def __init__(self, parent, index):
        """ Create port object.

        Note that port can be child of chassis or module objects.

        :param parent: parent module or chassis.
        :param index: port index in format module/port (both 0 based)
        """

        if 'module' in parent.ref:
            objRef = '{}/port/{}'.format(parent.ref, index.split('/')[-1])
        else:
            objRef = '{}/module/{}/port/{}'.format(parent.ref, *index.split('/'))
        super(XenaBasePort, self).__init__(objType='port', index=index, parent=parent, objRef=objRef)
        self._data['name'] = '{}/{}'.format(parent.name, index)
        self.p_info = None
        self._capabilities = None

    def inventory(self):
        self.p_info = self.get_attributes()

    def reset(self):
        """ Reset port-level parameters to standard values, and delete all streams, filters, capture,
            and dataset definitions.
        """
        self.objects = OrderedDict()
        return self.send_command('p_reset')

    def wait_for_up(self, timeout=40):
        self.wait_for_states('p_receivesync', timeout, 'IN_SYNC')

    #
    # Configurations.
    #

    def load_config(self, config_file_name):
        """ Load configuration file from xpc file.

        :param config_file_name: full path to the configuration file.
        """

        with open(config_file_name) as f:
            commands = f.read().splitlines()

        for command in commands:
            if not command.startswith(';'):
                try:
                    self.send_command(command)
                except XenaCommandError as e:
                    self.logger.warning(str(e))

    def save_config(self, config_file_name, file_mode='w+'):
        """ Save configuration file to xpc file.

        :param config_file_name: full path to the configuration file.
        :param file_mode: w+ for port configuration file, a+ for module configuration.
        """

        with open(config_file_name, file_mode) as f:
            f.write(';Port: {}\n'.format(self.index))
            f.write('P_RESET\n')
            for line in self.send_command_return_multilines('p_fullconfig', '?'):
                f.write(line.split(' ', 1)[1].lstrip())

    def add_stream(self, name=None, tpld_id=None, state=XenaStreamState.enabled):
        """ Add stream.

        :param name: stream description.
        :param tpld_id: TPLD ID. If None the a unique value will be set.
        :param state: new stream state.
        :type state: xenavalkyrie.xena_stream.XenaStreamState
        :return: newly created stream.
        :rtype: xenavalkyrie.xena_stream.XenaStream
        """

        stream = XenaStream(parent=self, index='{}/{}'.format(self.index, len(self.streams)), name=name)
        stream._create()
        tpld_id = tpld_id if tpld_id != None else XenaStream.next_tpld_id
        stream.set_attributes(ps_comment='"{}"'.format(stream.name), ps_tpldid=tpld_id)
        XenaStream.next_tpld_id = max(XenaStream.next_tpld_id + 1, tpld_id + 1)
        stream.set_state(state)
        return stream

    def remove_stream(self, index):
        """ Remove stream.

        :param index: index of stream to remove.
        """

        self.streams[index].del_object_from_parent()

    def add_filter(self, comment=None):
        """ Add filter.

        We cannot set state before we set condition so it is the test responsibility.

        :param comment: filter description.
        :return: newly created filter.
        :rtype: xenavalkyrie.xena_filter.XenaFilter
        """

        filter = XenaFilter(parent=self, index='{}/{}'.format(self.index, len(self.filters)), name=comment)
        filter._create()
        filter.set_attributes(pf_comment='"{}"'.format(filter.name))
        return filter

    def remove_filter(self, index):
        """ Remove filter.

        :param index: index of filter to remove.
        """

        self.filters[index].del_object_from_parent()

    def add_match(self):
        """ Add match.

        :return: newly created match.
        :rtype: xenavalkyrie.xena_filter.XenaMatch
        """

        match = XenaMatch(parent=self, index='{}/{}'.format(self.index, len(self.matches)))
        match._create()
        return match

    def remove_match(self, index):
        """ Remove match.

        :param index: index of match to remove.
        """

        self.matches[index].del_object_from_parent()

    def add_length(self):
        """ Add match.

        :return: newly created match.
        :rtype: xenavalkyrie.xena_filter.XenaMatch
        """

        length = XenaLength(parent=self, index='{}/{}'.format(self.index, len(self.lengthes)))
        length._create()
        return length

    def remove_length(self, index):
        """ Remove length.

        :param index: index of length to remove.
        """

        self.lengthes[index].del_object_from_parent()

    #
    # Operations.
    #

    def start_traffic(self, blocking=False):
        """ Start port traffic.

        Port -> Start Traffic

        :param blocking: True - start traffic and wait until traffic ends, False - start traffic and return.
        """
        self.session.start_traffic(blocking, self)

    def stop_traffic(self):
        """ Stop port traffic.

        Port -> Stop Traffic
        """
        self.session.stop_traffic(self)

    def start_capture(self):
        """ Start capture on port.

        Capture -> Start Capture
        """
        self.del_objects_by_type('capture')
        self.send_command('p_capture', 'on')

    def stop_capture(self):
        """ Stop capture on port.

        Capture -> Stop Capture
        """
        self.send_command('p_capture', 'off')

    #
    # Statistics.
    #

    def clear_stats(self):
        """ Clear att TX and RX statistics counter.

        Port Statistics -> Clear TX Counters, Clear RX Counters
        """
        self.send_command('pt_clear')
        self.send_command('pr_clear')

    def read_port_stats(self):
        """
        :return: dictionary {group name {stat name: value}}.
            Sea XenaBasePort.stats_captions.
        """

        stats_with_captions = OrderedDict()
        for stat_name in self.stats_captions.keys():
            stats_with_captions[stat_name] = self.read_stat(self.stats_captions[stat_name], stat_name)
        return stats_with_captions

    def read_stream_stats(self):
        """
        :return: dictionary {stream index {stat name: value}}.
            Sea XenaStream.stats_captions.
        """
        stream_stats = OrderedDict()
        for stream in self.streams.values():
            stream_stats[stream] = stream.read_stats()
        return stream_stats

    def read_tpld_stats(self):
        """
        :return: dictionary {tpld index {group name {stat name: value}}}.
            Sea XenaTpld.stats_captions.
        """
        payloads_stats = OrderedDict()
        for tpld in self.tplds.values():
            payloads_stats[tpld] = tpld.read_stats()
        return payloads_stats

    #
    # Properties.
    #

    @property
    def streams(self):
        """
        :return: dictionary {id: object} of all streams.
        :rtype: dict of (int, xenavalkyrie.xena_stream.XenaStream)
        """

        if not self.get_objects_by_type('stream'):
            tpld_ids = []
            for index in self.get_attribute('ps_indices').split():
                stream = XenaStream(parent=self, index='{}/{}'.format(self.index, index), name=None)
                ps_comment = stream.get_attribute('ps_comment')
                if ps_comment:
                    stream._data['name'] = ps_comment
                tpld_ids.append(stream.get_attribute('ps_tpldid'))
            if tpld_ids:
                XenaStream.next_tpld_id = max([XenaStream.next_tpld_id] + [int(t) for t in tpld_ids]) + 1
        return {s.id: s for s in self.get_objects_by_type('stream')}

    @property
    def tplds(self):
        """
        :return: dictionary {id: object} of all current tplds.
        :rtype: dict of (int, xenavalkyrie.xena_port.XenaTpld)
        """

        # As TPLDs are dynamic we must re-read them each time from the port.
        self.parent.del_objects_by_type('tpld')
        for tpld in self.get_attribute('pr_tplds').split():
            XenaTpld(parent=self, index='{}/{}'.format(self.index, tpld))
        return {t.id: t for t in self.get_objects_by_type('tpld')}

    @property
    def capture(self):
        """
        :return: capture object.
        :rtype: XenaCapture
        """

        if not self.get_object_by_type('capture'):
            XenaCapture(parent=self)
        return self.get_object_by_type('capture')

    @property
    def filters(self):
        """
        :return: dictionary {id: object} of all filters.
        :rtype: dict of (int, xenavalkyrie.xena_filter.XenaFilter)
        """

        if not self.get_objects_by_type('filter'):
            for index in self.get_attribute('pf_indices').split():
                filter = XenaFilter(parent=self, index='{}/{}'.format(self.index, index), name=None)
                pf_comment = filter.get_attribute('pf_comment')
                if pf_comment:
                    filter._data['name'] = pf_comment
        return {f.id: f for f in self.get_objects_by_type('filter')}

    @property
    def matches(self):
        """
        :return: dictionary {id: object} of all matches.
        :rtype: dict of (int, xenavalkyrie.xena_filter.XenaMatch)
        """

        if not self.get_objects_by_type('match'):
            for index in self.get_attribute('pm_indices').split():
                XenaMatch(parent=self, index='{}/{}'.format(self.index, index))
        return {m.id: m for m in self.get_objects_by_type('match')}

    @property
    def lengthes(self):
        """
        :return: dictionary {id: object} of all lengthes.
        :rtype: dict of (int, xenavalkyrie.xena_filter.XenaLength)
        """

        if not self.get_objects_by_type('length'):
            for index in self.get_attribute('pl_indices').split():
                XenaLength(parent=self, index='{}/{}'.format(self.index, index))
        return {l.id: l for l in self.get_objects_by_type('length')}

    @property
    def capabilities(self):

        if self._capabilities == None:
            self._capabilities = XenaPortCapabilities()


        ptr = 0
        capabilities_lst = self.get_attribute('p_capabilities').split() 

        for k,v in self._capabilities.values.items():
            if hasattr(v, "__iter__") :
                self._capabilities.values[k] = [int(x) for x in capabilities_lst[ptr:ptr+len(v)]]
                ptr += len(v)
            else:
                self._capabilities.values[k] = int(capabilities_lst[ptr])
                ptr += 1

        return self._capabilities
    

class XenaTpld(XenaObject21):

    stats_captions = {'pr_tpldtraffic': ['bps', 'pps', 'byt', 'pac'],
                      'pr_tplderrors': ['dummy', 'seq', 'mis', 'pld'],
                      'pr_tpldlatency': ['min', 'avg', 'max', 'avg1sec', 'min1sec', 'max1sec'],
                      'pr_tpldjitter': ['min', 'avg', 'max', 'avg1sec', 'min1sec', 'max1sec']}

    def __init__(self, parent, index):
        """
        :param parent: parent port object.
        :param index: TPLD index in format module/port/tpld.
        """
        super(self.__class__, self).__init__(objType='tpld', index=index, parent=parent)

    def read_stats(self):
        """
        :return: dictionary {group name {stat name: value}}.
            Sea XenaTpld.stats_captions.
        """

        stats_with_captions = OrderedDict()
        for stat_name in self.stats_captions.keys():
            stats_with_captions[stat_name] = self.read_stat(self.stats_captions[stat_name], stat_name)
        return stats_with_captions


class XenaCapture(XenaObject):
    """ Represents capture parameters, correspond to the Capture panel of the XenaManager, and deal with configuration
        of the capture criteria and inspection of the captured data from a port.
    """

    _info_config_commands = ['pc_fullconfig']
    stats_captions = ['status', 'packets', 'starttime']

    def __init__(self, parent):
        objRef = '{}/capture'.format(parent.ref)
        super(self.__class__, self).__init__(objType='capture', index=parent.index, parent=parent, objRef=objRef)

    def read_stats(self):
        """
        :return: dictionary {stat name: value}.
            Sea XenaCapture.stats_captions.
        """
        return self.read_stat(XenaCapture.stats_captions, 'pc_stats')

    def get_packets(self, from_index=0, to_index=None, cap_type=XenaCaptureBufferType.text,
                    file_name=None, tshark=None):
        """ Get captured packets from chassis.

        :param from_index: index of first packet to read.
        :param to_index: index of last packet to read. If None - read all packets.
        :param cap_type: returned capture format. If pcap then file name and tshark must be provided.
        :param file_name: if specified, capture will be saved in file.
        :param tshark: tshark object for pcap type only.
        :type: xenavalkyrie.xena_tshark.Tshark
        :return: list of requested packets, None for pcap type.
        """

        to_index = to_index if to_index else len(self.packets)

        raw_packets = []
        for index in range(from_index, to_index):
            raw_packets.append(self.packets[index].get_attribute('pc_packet').split('0x')[1])

        if cap_type == XenaCaptureBufferType.raw:
            self._save_captue(file_name, raw_packets)
            return raw_packets

        text_packets = []
        for raw_packet in raw_packets:
            text_packet = ''
            for c, b in zip(range(len(raw_packet)), raw_packet):
                if c % 32 == 0:
                    text_packet += '\n{:06x} '.format(int(c / 2))
                elif c % 2 == 0:
                    text_packet += ' '
                text_packet += b
            text_packets.append(text_packet)

        if cap_type == XenaCaptureBufferType.text:
            self._save_captue(file_name, text_packets)
            return text_packets

        temp_file_name = file_name + '_'
        self._save_captue(temp_file_name, text_packets)
        tshark.text_to_pcap(temp_file_name, file_name)
        os.remove(temp_file_name)

    #
    # Properties.
    #

    @property
    def packets(self):
        """
        :return: dictionary {id: object} of all packets.
        :rtype: dict of (int, xenavalkyrie.xena_port.XenaCapturePacket)
        """

        if not self.get_object_by_type('cappacket'):
            for index in range(0, self.read_stats()['packets']):
                XenaCapturePacket(parent=self, index='{}/{}'.format(self.index, index))
        return {p.id: p for p in self.get_objects_by_type('cappacket')}

    #
    # Private methods.
    #

    def _save_captue(self, file_name, packets):
        if file_name:
            with open(file_name, 'w+') as f:
                for packet in packets:
                    f.write(packet)


class XenaCapturePacket(XenaObject21):
    """ Represents single captured packet. """

    _info_config_commands = ['pc_info']

    def __init__(self, parent, index):
        obj_ref = '{}/{}'.format(parent.ref, index.split('/')[-1])
        super(self.__class__, self).__init__(objType='cappacket', parent=parent, index=index, objRef=obj_ref)


class XenaPortCapabilities():
    """ Structure that provides the port capabilities """

    _MAXTXEQTAPS = 10

    def __init__(self):
        super(self.__class__, self).__init__()

        self.values = {
           "maxspeed"                   : 0,
           "maxspeedreduction"          : 0,
           "mininterframegap"           : 0,
           "maxinterframegap"           : 0,
           "maxpreamble"                : 0,
           "maxstreams"                 : 0,
           "maxpercent"                 : 0,
           "maxpps"                     : 0,
           "maxmbps"                    : 0,
           "maxseed"                    : 0,
           "maxlimit"                   : 0,
           "maxburstsize"               : 0,
           "minpacketlength"            : 0,
           "maxpacketlength"            : 0,
           "maxheaderlength"            : 0,
           "maxprotocols"               : 0,
           "maxpatternlength"           : 0,
           "maxmodifiers"               : 0,
           "maxmodifierbytes"           : 0,
           "maxrepeat"                  : 0,
           "maxtid"                     : 0,
           "maxmanualpackets"           : 0,
           "maxmatchterms"              : 0,
           "maxlengthterms"             : 0,
           "maxors"                     : 0,
           "maxnots"                    : 0,
           "maxfilters"                 : 0,
           "maxcapturepackets"          : 0,
           "maxtpldstats"               : 0,
           "maxdatasets"                : 0,
           "max32bitmodifiers"          : 0,
           "cansetautoneg"              : 0,
           "cantcpchecksum"             : 0,
           "canudpchecksum"             : 0,
           "caneee"                     : 0,
           "canhwregaccess"             : 0,
           "cantcvrmiiregaccess"        : 0,
           "canadvphyman"               : 0,
           "canmicrotpld"               : 0,
           "canmdimdix"                 : 0,
           "canpayloadmode"             : 0,
           "cancustomdatafields"        : 0,
           "canextpayload"              : 0,
           "candyntrafficchange"        : 0,
           "cansynctrafficstart"        : 0,
           "canpfc"                     : 0,
           "canpcspmaconfig"            : 0,
           "canfec"                     : 0,
           "canfecstats"                : 0,
           "cantxeq"                    : 0,
           "canrxretune"                : 0,
           "prbstypessupported"         : 0,
           "prbsinvertionsupported"     : 0,
           "prbspolyssupported"         : [0 for _ in range(0,5)],
           "numserdes"                  : 0,
           "numlanes"                   : 0,
           "numtxeqtaps"                : 0,
           "txeqtapmaxval"              : [0 for _ in range(0, self._MAXTXEQTAPS)],
           "txeqtapminval"              : [0 for _ in range(0, self._MAXTXEQTAPS)],
           "maxfeccorrectablesymbols"   : 0,
           "maxxmitonepacketlength"     : 0,
           "txruntpacketminlength"      : 0,
           "rxruntpacketminlength"      : 0,
           "canmanipulatepreamble"      : 0,
           "cansetlinktrain"            : 0,
           "canlinkflap"                : 0,
           "canautonegbaser"            : 0,
           "canpmaerrorpulse"           : 0,
           "ischimera"                  : 0
        }

class XenaPort(XenaBasePort):
    def __init__(self, parent, index):
        super(XenaPort, self).__init__(parent=parent, index=index)

    def read_fec_stats(self):
        """
        :return: list showing how many FEC blocks have been seen with [0, 1, 2, 3....N, > N] symbol errors
        """

        # Note we discard the "dummy" and "num_val" elements returned by pp_rxfecstats
        return [int(val) for val in self.get_attribute('pp_rxfecstats').split()[2:]]


    def read_rx_total_stats(self):
        """
        :return: 
        """

        captions  = ["rx_bits", "codewords", "corr_codewords", "uncorr_codewords", "corr_symbols", "pre_fec_ber", "post_fec_ber"]
        raw_stats = self.get_attribute('pp_rxtotalstats').split()

        return dict(zip(captions, raw_stats))
    
    def set_tx_error_rate(self, rate):
        """
        """
        self.set_attributes(pp_txerrorrate=rate)


    def clear_rx_pcs_stats(self):
        """
        """
        self.send_command('pp_rxclear')

    def set_pma_err_pulse(self, duration, period, repetition, coeff, exp):
        """
        Sets the parameters for the PMA pulse error inject. 

        Period must be bigger than duration, BER will be calculated as coeff * power(10, exp) 

        :param duration  : 0 ms – 5 s; increments of 1 ms; 0 = constant BER
        :param period    : 10 ms – 50 s; number of ms – must be multiple of 10 ms
        :param repetition: 1 – 64K; 0 = continuous
        :param coeff     : (0.01 < coeff < 9.99) * 100
        :param exp       :  -3 < exp < -17
        """
        c = math.trunc(coeff * 100)
        if c < 1 or c > 999:
            raise ValueError("Coefficient value must be between 0.01 and 9.99 : {} ".format(coeff))

        arg = "{} {} {} {} {}".format(duration, period, repetition, c, exp)
        self.set_attributes(pp_pmaerrpul_params=arg)

        return self.get_attribute('pp_pmaerrpul_params')


    def enable_pma_err_pulse(self, enable=True):
        """
        """
        self.set_attributes(pp_pmaerrpul_enable = 1 if enable else 0)        