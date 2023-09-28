import fpdt
import sys


class EventArgumentsRawPrinter():

    def __init__(self, fsw_dict=None):
        self._d = fsw_dict

    def print_header(self):
        pass

    def print_record(self, item):
        if not item.packet.type == fpdt.Packet.Type.LOG:
            return
        sys.stdout.write(item.packet.payload.arguments_raw.data.hex())
        sys.stdout.write('\n')

    def print_footer(self):
        pass

