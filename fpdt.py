#!/usr/bin/env python3
# Copyright (c) 2023 Viet The Nguyen
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import ast
import copy
import enum
import io
import json
import struct
import sys
import types


def as_json_obj_helper(obj, keys, extended_dict=None):
    attrs = list(
        f'{json.dumps(key)}: {getattr(obj, key).as_json()}'
        for key in keys if hasattr(obj, key))
    if extended_dict:
        attrs.extend(
            f'{json.dumps(key)}: {value}'
            for key, value in extended_dict.items())
    return '{' + ', '.join(attrs) + '}'


# Collection of serializaable types used in processing data for a given
# topology by their name.  If a dictionary is loaded the types defined there in
# will be added to this collection.
fp_types = {}


def register_fp_types(name=None):
    def register_fp_types_decorator(cls):
        fp_types[name or cls.__name__] = cls
        return cls
    return register_fp_types_decorator


# Collection of serializable types defined for processing in this script that
# are not supposed to participate in processing topology types.
fp_types_custom = {}


def register_fp_types_custom(name=None):
    def register_fp_types_custom_decorator(cls):
        fp_types_custom[name or cls.__name__] = cls
        return cls
    return register_fp_types_custom_decorator


# -- F Prime configuration flags ----------------------------------------------


# These are F Prime configuration flags (preprocessor definitions) that affect
# the format of data to be encoded/decoded.
fprime_configurable_flags = (
    # This controls whether the Time type includes the time base.
    ('FW_USE_TIME_BASE', True),
    # This controls whether the Time type includes the time context.
    ('FW_USE_TIME_CONTEXT', True),
    # This controls what the byte representation of a true boolean is.
    ('FW_SERIALIZE_TRUE_VALUE', 0xff.to_bytes(1, 'big')),
    # This controls what the byte representation of a false boolean is.
    ('FW_SERIALIZE_FALSE_VALUE', 0x00.to_bytes(1, 'big')),
)
for name, value in fprime_configurable_flags:
    # Put these flags in the global namespace for convenience.
    globals()[name] = value


# -- Fundamental types --------------------------------------------------------


# Creates a class representing the fundamental type given the name and struct
# format.
def make_fundamental_type(name, struct_format):
    fundamental_struct = struct.Struct(struct_format)

    class FundamentalType():

        def __init__(self, value):
            self.value = value

        def as_json(self):
            return str(self)

        @classmethod
        def decode(cls, istream, fsw_dict=None, length=None):
            data = istream.read(fundamental_struct.size)
            if len(data) == 0:
                raise BrokenPipeError()
            return cls(fundamental_struct.unpack(data)[0])

        def encode(self, ostream):
            ostream.write(fundamental_struct.pack(self.value))

        def __float__(self):
            return float(self.value)

        def __format__(self, spec):
            return format(self.value, spec)

        def __int__(self):
            return int(self.value)

        def __repr__(self):
            return repr(self.value)

        def __str__(self):
            return str(self.value)

    FundamentalType.__name__ = name

    return FundamentalType


# Specification for fundamental types (other than bool).  Instead of manually
# writing out the types we construct them from this specification which is a
# tuple of name and struct format.
fundamental_type_specs = (
    ('I8', '>b'),
    ('U8', '>B'),
    ('I16', '>h'),
    ('U16', '>H'),
    ('I32', '>i'),
    ('U32', '>I'),
    ('I64', '>q'),
    ('U64', '>Q'),
    ('F32', '>f'),
    ('F64', '>d'),
    ('I8BE', '>b'),
    ('U8BE', '>B'),
    ('I16BE', '>h'),
    ('U16BE', '>H'),
    ('I32BE', '>i'),
    ('U32BE', '>I'),
    ('I64BE', '>q'),
    ('U64BE', '>Q'),
    ('F32BE', '>f'),
    ('F64BE', '>d'),
    ('I8LE', '<b'),
    ('U8LE', '<B'),
    ('I16LE', '<h'),
    ('U16LE', '<H'),
    ('I32LE', '<i'),
    ('U32LE', '<I'),
    ('I64LE', '<q'),
    ('U64LE', '<Q'),
    ('F32LE', '<f'),
    ('F64LE', '<d'),
    ('I8N', 'b'),
    ('U8N', 'B'),
    ('I16N', 'h'),
    ('U16N', 'H'),
    ('I32N', 'i'),
    ('U32N', 'I'),
    ('I64N', 'q'),
    ('U64N', 'Q'),
    ('F32N', 'f'),
    ('F64N', 'd'),
)
fptypes_fundamental = {}
for name, struct_format in fundamental_type_specs:
    # Create the fundamental type and register it in fp_types.
    fp_types[name] = make_fundamental_type(name, struct_format)
    # Also collect the fundamental_types into their own collection.
    fptypes_fundamental[name] = fp_types[name]
    # Also put the fundamental_types into the global namespace for convenience.
    globals()[name] = fp_types[name]


# Using make_fundamental_type() works for everything except F Prime booleans
# because F Prime booleans explicitly make true equal to
# FW_SERIALIZE_TRUE_VALUE and false equal to FW_SERIALIZE_FALSE_VALUE.  This
# class supports that on encode.  On decode the class supports
# FW_SERIALIZE_FALSE_VALUE as false and any other value as true.
@register_fp_types('bool')
class Bool():

    def __init__(self, value):
        self.value = value

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        data = istream.read(1)
        if len(data) == 0:
            raise BrokenPipeError()
        if data == FW_SERIALIZE_FALSE_VALUE:  # noqa: F821
            return cls(False)
        else:
            return cls(True)

    def encode(self, ostream):
        if self.value:
            ostream.write(FW_SERIALIZE_TRUE_VALUE)  # noqa: F821
        else:
            ostream.write(FW_SERIALIZE_FALSE_VALUE)  # noqa: F821

    def as_json(self):
        return 'true' if self.value else 'false'

    @classmethod
    def from_object(cls, o):
        return cls(bool(o))

    @classmethod
    def from_string(cls, s):
        assert isinstance(s, str)
        if s.lower() == 'true':
            return cls(True)
        if s.lower() == 'false':
            return cls(False)
        return cls(bool(ast.literal_eval(s)))

    def __bytes__(self):
        buf = io.BytesIO()
        self.encode(buf)
        return buf.getvalue()

    def __format__(self, spec):
        return format(str(self.value), spec)

    def __int__(self):
        return int(self.value)

    def __repr__(self):
        return repr(self.value)

    def __str__(self):
        return 'true' if self.value else 'false'


# Register it as a type and fundamental type
fp_types['bool'] = Bool
fptypes_fundamental['bool'] = Bool


# -- F Prime configurable types -----------------------------------------------


# Another part of F Prime configuration is defining what fundamental types
# represent various things.  The following are the default type definitions.
# We also use this list to allow users to override using command line
# arguments.
fprime_configurable_types = (
    ('FwBuffSizeType', U16),  # noqa: F821
    ('FwChanIdType', U32),  # noqa: F821
    ('FwEnumStoreType', I32),  # noqa: F821
    ('FwEventIdType', U32),  # noqa: F821
    ('FwOpcodeType', U32),  # noqa: F821
    ('FwPacketDescriptorType', U32),  # noqa: F821
    ('FwPrmIdType', U32),  # noqa: F821
    ('FwTimeBaseStoreType', U16),  # noqa: F821
    ('FwTimeContextStoreType', U8),  # noqa: F821
    ('FwTlmPacketizeIdType', U16),  # noqa: F821
)
for name, value in fprime_configurable_types:
    # Define these types aliases in fp_types so they can be retrieved by name.
    fp_types[name] = value
    # Also put the type alias into the global namespace for convenience.
    globals()[name] = value


# -- Basic non-fundamental type factories -------------------------------------


# Class decorator factory for extending an enum.IntEnum based class with an
# decode class function and encode method based on the provided underlying
# type.
def enum_represented_as(enum_underlying_type):
    def decorator(type):
        def decode(cls, istream, fsw_dict=None, length=None):
            untyped = enum_underlying_type.decode(istream, fsw_dict)
            return cls(untyped.value)
        type.decode = classmethod(decode)

        def encode(self, ostream):
            untyped = enum_underlying_type(self.value)
            untyped.encode(ostream)
        type.encode = encode

        def as_json(self):
            return f'{json.dumps(self.name)}'
        type.as_json = as_json

        def __str__(self):
            return self.name
        type.__str__ = __str__

        return type

    return decorator


def make_array_type(name, element_type, size):
    _element_type = element_type
    _size = size

    class Array():
        element_type = _element_type
        size = _size

        def __init__(self, elements):
            self.elements = elements
            assert len(self.elements) == type(self).size
            for element in self.elements:
                assert type(element) == type(self).element_type

        def as_json(self):
            return '[' + ', '.join(x.as_json() for x in self.elements) + ']'

        @classmethod
        def decode(cls, istream, fsw_dict=None, length=None):
            elements = [
                cls.element_type.decode(istream, fsw_dict)
                for i in range(cls.size)
            ]
            self = cls(elements)
            return self

        def encode(self, ostream):
            assert type(self.elements) is list
            assert len(self.elements) == type(self).size
            for element in self.elements:
                assert type(element) == type(self).element_type
                element.encode(ostream)

        def __getitem__(self, index):
            return self.elements[index]

        def __iter__(self):
            return iter(self)

        def __len__(self):
            return len(self.elements)

        def __repr__(self):
            return repr(self.elements)

        def __setitem__(self, index, value):
            self.elements[index].value = value

        def __str__(self):
            return str(self.elements)

    Array.__name__ = name

    return Array


def make_serializable_type(name, member_defs):
    _member_defs = member_defs

    class Serializable():
        member_defs = _member_defs

        def as_json(self):
            return (
                '{'
                + ', '.join(
                    '{}: {}'.format(
                        json.dumps(member_name),
                        getattr(self, member_name).as_json())
                    for member_name, _ in type(self).member_defs)
                + '}'
            )

        @classmethod
        def decode(cls, istream, fsw_dict=None, length=None):
            self = cls()
            for member_name, member_type in type(self).member_defs:
                setattr(
                    self,
                    member_name,
                    member_type.decode(istream, fsw_dict))
            return self

        def encode(self, ostream):
            for member_name, member_type in type(self).member_defs:
                member_value = getattr(self, member_name)
                assert type(member_value) is member_type
                member_value.encode(ostream)

    Serializable.__name__ = name

    return Serializable


# -- Basic non-fundamental types ----------------------------------------------


@register_fp_types_custom()
class Buffer():

    def __init__(self, data=b''):
        self.data = data

    def as_json(self):
        return f'"0x{self.data.hex()}"'

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=-1):
        '''
        Decodes a buffer object from the binary input stream by simply reading
        the data from the input stream as a bytes object and storing it in the
        `data` member.  If `length` is not specified then all of the remaining
        bytes in the binary input stream are read into the Buffer object.  This
        is "read the rest" behavior.  If length is specified then only that
        many bytes are read from the input stream.
        '''
        self = cls()
        if length == 0:
            self.data = b''
        else:
            self.data = istream.read(length)
        return self

    def encode(self, ostream):
        assert type(self.data) is bytes
        ostream.write(self.data)

    def __bytes__(self):
        return bytes(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return repr(self.data)

    def __str__(self):
        return str(self.data)


@register_fp_types_custom()
class AsciiBuffer():

    def __init__(self, string=b''):
        self.string = string

    def as_json(self):
        return json.dumps(self.string)

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=-1):
        '''
        Decodes an ASCII buffer object from the binary input stream by simply
        reading the string from the input stream as a bytes object, decoding it
        as an ASCII string, and storing it in the `string` member.  If `length`
        is not specified then all of the remaining bytes in the binary input
        stream are read into the AsciiBuffer object.  This is "read the rest"
        behavior.  If length is specified then only that many bytes are read
        from the input stream.  Note that no length information is decoded from
        the input stream!
        '''
        self = cls()
        if length == 0:
            self.string_raw = b''
        else:
            self.string_raw = istream.read(length)
        self.string = self.string_raw.decode('ascii')
        return self

    def encode(self, ostream):
        '''
        Writes the buffer to the output stream WITHOUT any length information.
        '''
        assert type(self.string) is str
        ostream.write(self.string.encode('ascii'))

    def __bytes__(self):
        return bytes(self.string)

    def __len__(self):
        return len(self.string)

    def __repr__(self):
        return repr(self.string)

    def __str__(self):
        return str(self.string)


@register_fp_types('string')
class String():
    '''
    Represents a string as a length (FwBuffSizeType) and a buffer of that
    length of ASCII characters.
    '''

    def __init__(self, string=b''):
        self.string = string

    def as_json(self):
        return (
            '{'
            f'"length": {self.length}'
            f', "string": {json.dumps(self.string)}'
            '}'
        )

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=-1):
        self = cls()
        self.length = FwBuffSizeType.decode(istream, fsw_dict)  # noqa: F821
        if length == 0:
            self.string_raw = b''
        else:
            self.string_raw = istream.read(self.length.value)
        self.string = self.string_raw.decode('ascii')
        return self

    def encode(self, ostream):
        assert type(self.length) is FwBuffSizeType  # noqa: F821
        assert type(self.string) is str
        self.length.encode(ostream)
        ostream.write(self.string.encode('ascii'))

    def __bytes__(self):
        return bytes(self.string)

    def __len__(self):
        return len(self.string)

    def __repr__(self):
        return repr(self.string)

    def __str__(self):
        return str(self.string)

    # All of the other fundamental types can get their value using the `value`
    # attribute so we mimic that here with string.
    value = property(
        fget=lambda self: self.string
    )


@register_fp_types('Fw::Time')
class Time():

    def as_json(self):
        import datetime
        unix_seconds = float(self.seconds) + float(self.microseconds) * 1e-6
        utc_datetime = datetime.datetime.utcfromtimestamp(unix_seconds)
        local_tzinfo = datetime.datetime.now().astimezone().tzinfo
        local_datetime = \
            datetime.datetime.fromtimestamp(unix_seconds, local_tzinfo)
        extended_dict = {
            'value': f'{unix_seconds}',
            'utc_year': f'{json.dumps(utc_datetime.year)}',
            'utc_month': f'{json.dumps(utc_datetime.month)}',
            'utc_day': f'{json.dumps(utc_datetime.day)}',
            'utc_hour': f'{json.dumps(utc_datetime.hour)}',
            'utc_minute': f'{json.dumps(utc_datetime.minute)}',
            'utc_second': f'{json.dumps(utc_datetime.second)}',
            'utc_microsecond': f'{json.dumps(utc_datetime.microsecond)}',
            'utc_iso8601': f'{json.dumps(utc_datetime.isoformat())}',
            'local_year': f'{json.dumps(local_datetime.year)}',
            'local_month': f'{json.dumps(local_datetime.month)}',
            'local_day': f'{json.dumps(local_datetime.day)}',
            'local_hour': f'{json.dumps(local_datetime.hour)}',
            'local_minute': f'{json.dumps(local_datetime.minute)}',
            'local_second': f'{json.dumps(local_datetime.second)}',
            'local_microsecond': f'{json.dumps(local_datetime.microsecond)}',
            'local_iso8601': f'{json.dumps(local_datetime.isoformat())}',
        }
        return as_json_obj_helper(
            self,
            ('base', 'context', 'seconds', 'microseconds'),
            extended_dict)

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        if FW_USE_TIME_BASE:  # noqa: F821
            self.base = \
                FwTimeBaseStoreType.decode(istream, fsw_dict)  # noqa: F821
        if FW_USE_TIME_CONTEXT:  # noqa: F821
            self.context = \
                FwTimeContextStoreType.decode(istream, fsw_dict)  # noqa: F821
        self.seconds = U32.decode(istream, fsw_dict)  # noqa: F821
        self.microseconds = U32.decode(istream, fsw_dict)  # noqa: F821
        return self

    def encode(self, ostream):
        if FW_USE_TIME_BASE:  # noqa: F821
            assert type(self.base) is FwTimeBaseStoreType  # noqa: F821
        if FW_USE_TIME_CONTEXT:  # noqa: F821
            assert type(self.context) is FwTimeContextStoreType  # noqa: F821
        assert type(self.seconds) is U32  # noqa: F821
        assert type(self.microseconds) is U32  # noqa: F821
        if FW_USE_TIME_BASE:  # noqa: F821
            self.base.encode(ostream)
        if FW_USE_TIME_CONTEXT:  # noqa: F821
            self.context.encode(ostream)
        self.seconds = U32.decode(ostream, fsw_dict)  # noqa: F821
        self.microseconds = U32.decode(ostream, fsw_dict)  # noqa: F821

    def __str__(self):
        return str(float(self.seconds) + float(self.microseconds) * 1e-6)


# -- Record types -------------------------------------------------------------


def read_until_sync_word(istream, sync_word):
    sync_word_index = 0
    read_next = True
    while sync_word_index < len(sync_word):
        if read_next:
            buf = istream.read(1)
            if len(buf) == 0:
                raise BrokenPipeError()
        if buf[0] == sync_word[sync_word_index]:
            sync_word_index += 1
            read_next = True
            continue
        if sync_word_index > 0:
            sync_word_index = 0
            read_next = False
            continue
        read_next = True
        continue


def create_record_class(name, packet_size_type):
    _packet_size_type = packet_size_type

    @register_fp_types_custom(name)
    class Record():

        packet_size_type = _packet_size_type

        def as_json(self):
            return as_json_obj_helper(
                self,
                ('packet_size', 'packet'),
                extended_dict={
                    "offset": json.dumps(self.offset)
                })

        @classmethod
        def decode(cls, istream, fsw_dict=None, length=None):
            self = cls()
            self.offset = istream.tell() if istream.seekable() else None
            self.packet_size = cls.packet_size_type.decode(istream, fsw_dict)

            # We slice off the input stream into a buffer and create a new
            # input stream backed by that buffer to pass to the Packet parser.
            # We do this because some parsers nested underneath the Packet
            # parser will "read the rest" but without the size context here.
            # For example, the event and telemetry packet parsers do this. We
            # use the size context here to limit the rest of the record so that
            # "read the rest" behavior underneath works as expected and doesn't
            # read the rest of the input stream.
            packet_buffer = istream.read(self.packet_size.value)
            self.packet = Packet.decode(io.BytesIO(packet_buffer), fsw_dict)

            return self

        def encode(self, ostream):
            assert type(self.packet_size) is packet_size_type
            # TODO (vnguyen): Be smart about automatically calculating this.
            self.packet_size.encode(ostream)
            self.packet.encode(ostream)

    Record.__name__ = name
    return Record


ComLoggerRecord = create_record_class("ComLoggerRecord", U16)  # noqa: F821
FprimeGdsRecord = create_record_class("FprimeGdsRecord", U32)  # noqa: F821


@register_fp_types_custom
class FprimeGdsStream():

    sync_word = bytes.fromhex('deadbeef')

    def __init__(self):
        self.record = None

    def as_json(self):
        if self.record is None:
            return '{}'
        assert isinstance(self.record, FprimeGdsRecord)
        return self.record.as_json()

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        read_until_sync_word(istream, cls.sync_word)
        self = cls()
        self.record = FprimeGdsRecord.decode(istream, fsw_dict)
        return self

    def encode(self, ostream):
        if self.record is None:
            return
        assert isinstance(self.record, FprimeGdsRecord)
        ostream.write(type(self).sync_word)
        self.record.encode(ostream)


@register_fp_types_custom()
class PrmDbRecord():

    sync_word = bytes.fromhex('a5')

    def as_json(self):
        extended_dict = {
            'id_hex': f'{json.dumps(hex(self.id.value))}',
            "offset": json.dumps(self.offset)
        }

        if self.parameter is not None:
            extended_dict['topology_name'] = \
                f'{json.dumps(self.parameter.topology_name)}'
            extended_dict['component'] = \
                f'{json.dumps(self.parameter.component)}'
            extended_dict['type'] = \
                f'{json.dumps(self.parameter.type_str)}'
            extended_dict['name'] = f'{json.dumps(self.parameter.name)}'

        if self.value is not None:
            extended_dict['value'] = self.value.as_json()

        return as_json_obj_helper(
            self,
            ('sync_marker', 'size', 'id', 'value_raw'),
            extended_dict)

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.offset = istream.tell() if istream.seekable() else None
        read_until_sync_word(istream, cls.sync_word)
        self.size = U32.decode(istream, fsw_dict)  # noqa: F821
        self.id = FwPrmIdType.decode(istream, fsw_dict)  # noqa: F821
        self.value_raw = \
            Buffer.decode(istream, fsw_dict, self.size.value - 4)  # noqa: F821

        self.parameter = None
        self.value = None

        if fsw_dict:
            self.parameter = fsw_dict.parameters_by_id.get(self.id.value, None)
            if self.parameter is None:
                sys.stderr.write(
                    f'WARNING: Could not find parameter ID "{self.id.value}" '
                    'in FSW dictionary. This indicates that the '
                    'dictionary and the input data are not compatible.\n')

        if self.parameter is not None and self.parameter.type is not None:
            value_raw_istream = io.BytesIO(self.value_raw.data)
            self.value = \
                self.parameter.type.decode(value_raw_istream, fsw_dict)

        return self

    def encode(self, ostream):
        assert type(self.type) is type(self).Type
        self.type.encode(ostream)


# -- F Prime packet types -----------------------------------------------------


@register_fp_types_custom()
class Packet():

    @enum_represented_as(FwPacketDescriptorType)  # noqa: F821
    @register_fp_types_custom('Packet.Type')
    class Type(enum.IntEnum):
        COMMAND = 0
        TELEM = 1
        LOG = 2
        FILE = 3
        PACKETIZED_TLM = 4
        IDLE = 5
        UNKNOWN = 0xFF

    def as_json(self):
        return as_json_obj_helper(self, ('type', 'payload'))

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        '''
        Decodes an F Prime packet (basically a `Fw::ComPacket`) from the given
        binary input stream.  This decoding process has "read the rest"
        behavior since size information is not a part of the packet itself.
        Thus it is important that the binary input stream is confined to the
        actual contents of the packet.  One way to do this is reading the
        packet as a whole (given packet size from a larger context) and
        wrapping that bytes object in a binary input stream using `io.BytesIO`.
        '''
        self = cls()
        try:
            self.type = type(self).Type.decode(istream, fsw_dict)
        except ValueError as e:
            sys.stderr.write(
                'WARNING: F Prime packet parsed with unknown type ('
                + str(e)
                + '). Forging on anyway.\n')
            self.type = types.SimpleNamespace()
            self.type.value = int(e.args[0].split()[0])
            self.type.name = 'INVALID'
            self.type.as_json = lambda: f'{json.dumps(self.type.value)}'

        if self.type == type(self).Type.COMMAND:
            self.payload = CommandPacket.decode(istream, fsw_dict)
        elif self.type == type(self).Type.TELEM:
            self.payload = TelemPacket.decode(istream, fsw_dict)
        elif self.type == type(self).Type.LOG:
            self.payload = EventPacket.decode(istream, fsw_dict)
        elif self.type == type(self).Type.FILE:
            self.payload = FilePacket.decode(istream, fsw_dict)
        else:
            # NOTE: This is "read the rest" behavior so it is important that
            # the input stream be confined to the extents of the packet itself.
            self.payload = Buffer.decode(istream, fsw_dict)
        return self

    def encode(self, ostream):
        assert type(self.type) is type(self).Type
        if self.type == type(self).Type.COMMAND:
            assert isinstance(self.payload, CommandPacket)
        elif self.type == type(self).Type.TELEM:
            assert isinstance(self.payload, TelemPacket)
        elif self.type == type(self).Type.LOG:
            assert isinstance(self.payload, EventPacket)
        elif self.type == type(self).Type.FILE:
            assert isinstance(self.payload, FilePacket)
        else:
            assert isinstance(self.payload, Buffer)
        self.type.encode(ostream)
        self.payload.encode(ostream)


@register_fp_types_custom()
class CommandPacket():

    def as_json(self):
        extended_dict = {
            'opcode_hex': f'{json.dumps(hex(self.opcode.value))}'
        }

        if self.command is not None:
            extended_dict['topology_name'] = \
                f'{json.dumps(self.command.topology_name)}'
            extended_dict['component'] = \
                f'{json.dumps(self.command.component)}'
            extended_dict['mnemonic'] = f'{json.dumps(self.command.mnemonic)}'

        if self.arguments is not None:
            args_as_json = []

            for arg_def, arg in zip(self.command.args, self.arguments):
                arg_as_json = (
                    '{'
                    f'"name": {json.dumps(arg_def.name)}'
                    f', "type": {json.dumps(arg_def.type_str)}'
                    f', "value": {"null" if arg is None else arg.as_json()}'
                    '}'
                )
                args_as_json.append(arg_as_json)

            extended_dict['arguments'] = "[{}]".format(
                ', '.join(args_as_json))

        return as_json_obj_helper(
            self,
            ('opcode', 'arguments_raw'),
            extended_dict=extended_dict)

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.opcode = FwOpcodeType.decode(istream, fsw_dict)  # noqa: F821
        # NOTE: This is "read the rest" behavior so it is important that the
        # input stream be confined to the extents of the packet itself.
        self.arguments_raw = Buffer.decode(istream, fsw_dict)

        self.fsw_dict = fsw_dict
        self.command = None
        self.arguments = None

        if self.fsw_dict:
            self.command = self.fsw_dict.commands_by_opcode.get(
                self.opcode.value,
                None)
            if self.command is None:
                sys.stderr.write(
                    'WARNING: Could not find command opcode '
                    f'"{self.opcode.value}" in FSW dictionary. This indicates '
                    'that the dictionary and the input data are not '
                    'compatible.\n')

        if self.command is not None:
            arguments_raw_istream = io.BytesIO(self.arguments_raw.data)
            self.arguments = []
            for arg in self.command.args:
                if arg.type is None:
                    self.arguments.append(None)
                    continue
                self.arguments.append(
                    arg.type.decode(
                        arguments_raw_istream,
                        self.fsw_dict,
                        length=arg.length))

        return self

    def encode(self, ostream):
        assert type(self.opcode) == FwOpcodeType  # noqa: F821
        assert type(self.arguments_raw) == Buffer
        self.opcode.encode(ostream)
        self.arguments_raw.encode(ostream)


@register_fp_types_custom()
class TelemPacket():

    def as_json(self):
        extended_dict = {
            'id_hex': f'{json.dumps(hex(self.id.value))}'
        }

        if self.channel is not None:
            extended_dict['topology_name'] = \
                f'{json.dumps(self.channel.topology_name)}'
            extended_dict['component'] = \
                f'{json.dumps(self.channel.component)}'
            extended_dict['name'] = f'{json.dumps(self.channel.name)}'
            extended_dict['type'] = f'{json.dumps(self.channel.type_str)}'

        if self.value is not None:
            extended_dict['value'] = self.value.as_json()

        return as_json_obj_helper(
            self,
            ('id', 'time', 'value_raw'),
            extended_dict=extended_dict)

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.id = FwChanIdType.decode(istream, fsw_dict)  # noqa: F821
        self.time = Time.decode(istream, fsw_dict)
        # NOTE: This is "read the rest" behavior so it is important that the
        # input stream be confined to the extents of the packet itself.
        self.value_raw = Buffer.decode(istream, fsw_dict)

        self.channel = None
        self.value = None

        if fsw_dict:
            self.channel = fsw_dict.channels_by_id.get(self.id.value, None)
            if self.channel is None:
                sys.stderr.write(
                    f'WARNING: Could not find channel ID "{self.id.value}" '
                    'in FSW dictionary. This indicates that the '
                    'dictionary and the input data are not compatible.\n')

        if self.channel is not None and self.channel.type is not None:
            value_raw_istream = io.BytesIO(self.value_raw.data)
            self.value = self.channel.type.decode(value_raw_istream, fsw_dict)

        return self

    def encode(self, ostream):
        assert type(self.id) == FwChanIdType  # noqa: F821
        assert type(self.time) == Time
        assert type(self.value_raw) == Buffer
        self.id.encode(ostream)
        self.time.encode(ostream)
        self.value_raw.encode(ostream)


@register_fp_types_custom()
class EventPacket():

    def as_json(self):
        extended_dict = {
            'id_hex': f'{json.dumps(hex(self.id.value))}'
        }

        if self.event is not None:
            extended_dict['topology_name'] = \
                f'{json.dumps(self.event.topology_name)}'
            extended_dict['component'] = f'{json.dumps(self.event.component)}'
            try:
                extended_dict['message'] = \
                    json.dumps(
                        self.event.format_string
                        % tuple(arg.value for arg in self.arguments))
            except:  # noqa: E722
                try:
                    extended_dict['message'] = \
                        json.dumps(
                            self.event.format_string.format(
                                *tuple(arg.value for arg in self.arguments)))
                except:  # noqa: E722
                    extended_dict['message'] = \
                        json.dumps(self.event.format_string)
            extended_dict['name'] = f'{json.dumps(self.event.name)}'
            extended_dict['severity'] = \
                f'{json.dumps(self.event.severity_str)}'

        if self.arguments is not None:
            args_as_json = []

            for arg_def, arg in zip(self.event.args, self.arguments):
                arg_as_json = (
                    '{'
                    f'"name": {json.dumps(arg_def.name)}'
                    f', "type": {json.dumps(arg_def.type_str)}'
                    f', "value": {"null" if arg is None else arg.as_json()}'
                )

                # We try to be helpful and automatically look up opcode event
                # arguments for events from the command dispatcher.  The
                # command topology name and opcode in hex format (which is
                # typically is in the XML) are added to the JSON object for the
                # argument.
                if self.event.component == 'cmdDisp' \
                        and arg_def.name == 'Opcode':
                    command_def = self.fsw_dict.commands_by_opcode[arg.value]
                    command_topology_name = command_def.topology_name
                    arg_as_json += \
                        f', "value_hex": {json.dumps(hex(arg.value))}'
                    arg_as_json += \
                        f', "command": {json.dumps(command_topology_name)}'

                arg_as_json += '}'
                args_as_json.append(arg_as_json)

            extended_dict['arguments'] = "[{}]".format(
                ', '.join(args_as_json))

        return as_json_obj_helper(
            self,
            ('id', 'time', 'arguments_raw'),
            extended_dict=extended_dict)

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.id = FwEventIdType.decode(istream, fsw_dict)  # noqa: F821
        self.time = Time.decode(istream, fsw_dict)
        # NOTE: This is "read the rest" behavior so it is important that the
        # input stream be confined to the extents of the packet itself.
        self.arguments_raw = Buffer.decode(istream, fsw_dict)

        self.fsw_dict = fsw_dict
        self.event = None
        self.arguments = None

        if self.fsw_dict:
            self.event = self.fsw_dict.events_by_id.get(
                self.id.value,
                None)
            if self.event is None:
                sys.stderr.write(
                    f'WARNING: Could not find event ID "{self.id.value}" '
                    'in FSW dictionary. This indicates that the '
                    'dictionary and the input data are not compatible.\n')

        if self.event is not None:
            arguments_raw_istream = io.BytesIO(self.arguments_raw.data)
            self.arguments = []
            for arg in self.event.args:
                if arg.type is None:
                    self.arguments.append(None)
                    continue
                self.arguments.append(
                    arg.type.decode(
                        arguments_raw_istream,
                        self.fsw_dict,
                        length=arg.length))

        return self

    def encode(self, ostream):
        assert type(self.id) == FwEventIdType  # noqa: F821
        assert type(self.time) == Time
        assert type(self.arguments_raw) == Buffer
        self.id.encode(ostream)
        self.time.encode(ostream)
        self.arguments_raw.encode(ostream)


@register_fp_types_custom()
class FilePacketPathName():

    def as_json(self):
        return as_json_obj_helper(self, ('length', 'value'))

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.length = U8.decode(istream, fsw_dict)  # noqa: F821
        self.value = AsciiBuffer.decode(istream, fsw_dict, self.length.value)
        return self

    def encode(self, ostream):
        assert type(self.length) == U8  # noqa: F821
        assert type(self.value) == AsciiBuffer
        assert len(self.value) == self.length
        self.length.encode(ostream)
        self.value.encode(ostream)

    def __str__(self):
        return self.value.encode('ascii')


@register_fp_types_custom()
class FilePacket():

    @enum_represented_as(U8)  # noqa: F821
    @register_fp_types_custom('FilePacket.Type')
    class Type(enum.IntEnum):
        START = 0
        DATA = 1
        END = 2
        CANCEL = 3
        NONE = 255

    def as_json(self):
        return as_json_obj_helper(self, ('type', 'sequence_index', 'payload'))

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.type = type(self).Type.decode(istream, fsw_dict)
        self.sequence_index = U32.decode(istream, fsw_dict)  # noqa: F821

        if self.type == type(self).Type.START:
            self.payload = FilePacketStartPayload.decode(istream, fsw_dict)
        elif self.type == type(self).Type.DATA:
            self.payload = FilePacketDataPayload.decode(istream, fsw_dict)
        elif self.type == type(self).Type.END:
            self.payload = FilePacketEndPayload.decode(istream, fsw_dict)
        elif self.type == type(self).Type.CANCEL:
            self.payload = FilePacketCancelPayload.decode(istream, fsw_dict)
        else:
            raise KeyError(f'Encountered unknown FilePacket type: {self.type}')

        return self

    def encode(self, ostream):
        assert type(self.type) is type(self).Type
        assert type(self.sequence_index) is U32  # noqa: F821
        if self.type == type(self).Type.START:
            assert type(self.payload) is FilePacketStartPayload
        elif self.type == type(self).Type.DATA:
            assert type(self.payload) is FilePacketDataPayload
        elif self.type == type(self).Type.END:
            assert type(self.payload) is FilePacketEndPayload
        elif self.type == type(self).Type.CANCEL:
            assert type(self.payload) is FilePacketCancelPayload
        else:
            raise KeyError(f'Encountered unknown FilePacket type: {self.type}')
        self.type.encode(ostream)
        self.sequence_index.encode(ostream)
        self.payload.encode(ostream)


@register_fp_types_custom()
class FilePacketStartPayload():

    def as_json(self):
        return as_json_obj_helper(
            self,
            ('file_size', 'source_path', 'destination_path'))

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.file_size = U32.decode(istream, fsw_dict)  # noqa: F821
        self.source_path = FilePacketPathName.decode(istream, fsw_dict)
        self.destination_path = FilePacketPathName.decode(istream, fsw_dict)
        return self

    def encode(self, ostream):
        self.file_size.encode(ostream)
        self.source_path.encode(ostream)
        self.destination_path.encode(ostream)


@register_fp_types_custom()
class FilePacketDataPayload():

    def as_json(self):
        return as_json_obj_helper(
            self,
            ('byte_offset', 'data_size', 'data'),
            {'data_str': json.dumps(str(self.data.data))})

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.byte_offset = U32.decode(istream, fsw_dict)  # noqa: F821
        self.data_size = U16.decode(istream, fsw_dict)  # noqa: F821
        self.data = Buffer.decode(istream, fsw_dict, self.data_size.value)
        return self

    def encode(self, ostream):
        assert type(self.byte_offset) is U32  # noqa: F821
        assert type(self.data_size) is U16  # noqa: F821
        assert type(self.data) is Buffer
        self.byte_offset.encode(ostream)
        self.data_size.encode(ostream)
        self.data.encode(ostream)


@register_fp_types_custom()
class FilePacketEndPayload():

    def as_json(self):
        return as_json_obj_helper(self, ('checksum',))

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        self.checksum = U32.decode(istream, fsw_dict)  # noqa: F821
        return self

    def encode(self, ostream):
        assert type(self.checksum) is U32  # noqa: F821
        self.checksum.encode(ostream)


@register_fp_types_custom()
class FilePacketCancelPayload():

    def as_json(self):
        return '{}'

    @classmethod
    def decode(cls, istream, fsw_dict=None, length=None):
        self = cls()
        return self

    def encode(self, ostream):
        pass


# -- Dictionary ---------------------------------------------------------------


class FswDictionary():

    class Enum():

        class Item():

            def __init__(self, elem):
                self.name = elem.get('name')
                self.value_str = elem.get('value')
                self.value = int(self.value_str)
                self.description = elem.get('description')

        def __init__(self, elem):
            self.name = elem.get('type')
            self.items = [type(self).Item(x) for x in elem.findall('item')]
            self.type = None

    class Serializable():

        class Member():

            def __init__(self, elem):
                self.name = elem.get('name')
                self.format_specifier = elem.get('format_specifier')
                self.default_str = elem.get('default')
                self.length = int(elem.get('len')) if elem.get('len') else None
                self.type_str = elem.get('type')
                self.type = None

        def __init__(self, elem):
            self.type_str = elem.get('type')
            self.name = self.type_str
            self.members = [
                type(self).Member(x)
                for x in elem.find('members').findall('member')]
            self.type = None

    class Array():

        class Default():

            def __init__(self, elem):
                self.value = elem.get('value')

        def __init__(self, elem):
            self.name = elem.get('name')
            self.element_type_str = elem.get('type')
            self.element_type = None
            self.type_id_str = elem.get('type_id')
            if self.type_id_str is not None:
                self.type_id = int(
                    self.type_id_str,
                    base=16 if self.type_id_str.startswith('0x') else 10)
            self.size_str = elem.get('size')
            self.size = int(self.size_str)
            self.format = elem.get('format')
            if elem.find('defaults'):
                self.defaults = [
                    type(self).Default(x)
                    for x in elem.find('defaults').findall('default')]
            self.type = None

    class Command():

        class Argument():

            def __init__(self, elem):
                self.name = elem.get('name')
                self.description = elem.get('description')
                self.length = int(elem.get('len')) if elem.get('len') else None
                self.type_str = elem.get('type')
                self.type = None

        def __init__(self, elem):
            self.component = elem.get('component')
            self.mnemonic = elem.get('mnemonic')
            self.topology_name = f'{self.component}.{self.mnemonic}'
            self.opcode_str = elem.get('opcode')
            self.opcode = int(
                self.opcode_str,
                base=16 if self.opcode_str.startswith('0x') else 10)
            self.description = elem.get('description')
            # For some reason the PRM_SAVE generated commands don't have an
            # <args> block in the command definition in the dictionary XML so
            # we have to handle that.  Other commands with no arguments still
            # at least have an <args/> block.
            if elem.find('args'):
                self.args = [
                    type(self).Argument(x)
                    for x in elem.find('args').findall('arg')]
            else:
                self.args = []

    class Event():

        class Severity(enum.IntEnum):
            FATAL = 1
            WARNING_HI = 2
            WARNING_LO = 3
            COMMAND = 4
            ACTIVITY_HI = 5
            ACTIVITY_LO = 6
            DIAGNOSTIC = 7

        class Argument():

            def __init__(self, elem):
                self.name = elem.get('name')
                self.description = elem.get('description')
                self.length = int(elem.get('len')) if elem.get('len') else None
                self.type_str = elem.get('type')
                self.type = None

        def __init__(self, elem):
            self.component = elem.get('component')
            self.name = elem.get('name')
            self.topology_name = f'{self.component}.{self.name}'
            self.id_str = elem.get('id')
            self.id = int(
                self.id_str,
                base=16 if self.id_str.startswith('0x') else 10)
            self.severity_str = elem.get('severity')
            self.severity = type(self).Severity[self.severity_str]
            self.description = elem.get('description')
            self.format_string = elem.get('format_string')
            self.args = [
                type(self).Argument(x)
                for x in elem.find('args').findall('arg')]

    class Channel():

        def __init__(self, elem):
            self.component = elem.get('component')
            self.name = elem.get('name')
            self.topology_name = f'{self.component}.{self.name}'
            self.id_str = elem.get('id')
            self.id = int(
                self.id_str,
                base=16 if self.id_str.startswith('0x') else 10)
            self.format_string = elem.get('format_string')
            self.description = elem.get('description')
            self.type_str = elem.get('type')
            self.type = None

    class Parameter():

        def __init__(self, elem):
            self.component = elem.get('component')
            self.name = elem.get('name')
            self.topology_name = f'{self.component}.{self.name}'
            self.id_str = elem.get('id')
            self.id = int(
                self.id_str,
                base=16 if self.id_str.startswith('0x') else 10)
            self.default_str = elem.get('default')

            self.set_command_id = (self.component, f'{self.name}_PRM_SET')
            self.type_str = None
            self.type = None

    def __init__(self, initial_types=fp_types):
        self.enums = {}
        self.serializables = {}
        self.arrays = {}
        self.commands = {}
        self.commands_by_opcode = {}
        self.events = {}
        self.events_by_id = {}
        self.channels = {}
        self.channels_by_id = {}
        self.parameters = {}
        self.parameters_by_id = {}
        self.types = copy.copy(initial_types) if initial_types else {}

    def parse(self, fsw_dict_file_path):
        from xml.etree import ElementTree
        tree = ElementTree.parse(fsw_dict_file_path)
        root = tree.getroot()
        for collection in root:
            if collection.tag == 'enums':
                for elem in collection:
                    if elem.tag == 'enum':
                        enum = type(self).Enum(elem)
                        self.enums[enum.name] = enum
            elif collection.tag == 'serializables':
                for elem in collection:
                    if elem.tag == 'serializable':
                        serializable = type(self).Serializable(elem)
                        self.serializables[serializable.name] = serializable
            elif collection.tag == 'arrays':
                for elem in collection:
                    if elem.tag == 'array':
                        array = type(self).Array(elem)
                        self.arrays[array.name] = array
            elif collection.tag == 'commands':
                for elem in collection:
                    if elem.tag == 'command':
                        command = type(self).Command(elem)
                        command_key = (command.component, command.mnemonic)
                        self.commands[command_key] = command
                        self.commands_by_opcode[command.opcode] = command
            elif collection.tag == 'events':
                for elem in collection:
                    if elem.tag == 'event':
                        event = type(self).Event(elem)
                        self.events[(event.component, event.name)] = event
                        self.events_by_id[event.id] = event
            elif collection.tag == 'channels':
                for elem in collection:
                    if elem.tag == 'channel':
                        channel = type(self).Channel(elem)
                        self.channels[(channel.component, channel.name)] = \
                            channel
                        self.channels_by_id[channel.id] = channel
            elif collection.tag == 'parameters':
                for elem in collection:
                    if elem.tag == 'parameter':
                        parameter = type(self).Parameter(elem)
                        parameter_key = (parameter.component, parameter.name)
                        self.parameters[parameter_key] = parameter
                        self.parameters_by_id[parameter.id] = parameter

        # TODO (vnguyen): Construct and resolve in a recursive descent manner
        # to take care of potential type dependency problems (i.e. type being
        # constructed requires a type that will be constructed later). Memoized
        # depth first traversal should be in topological order.
        self.construct_types(fsw_dict_file_path)
        self.resolve_types()

    def register_type(self, fsw_dict_file_path, type_name, type):
        if type_name in self.types:
            sys.stderr.write(
                f'WARNING: Type named "{type_name}" already exists in type '
                'namespace and is being replaced by type in FSW dictionary '
                f'"{fsw_dict_file_path}".\n')
        self.types[type_name] = type

    def construct_types(self, fsw_dict_file_path):
        for enum_def in self.enums.values():
            if enum_def.type is not None:
                continue

            enum_def.type = enum_represented_as(FwEnumStoreType)(  # noqa: F821
                enum.IntEnum(
                    enum_def.name,
                    [(item.name, item.value) for item in enum_def.items]))

            self.register_type(
                fsw_dict_file_path, enum_def.name, enum_def.type)

        for serializable_def in self.serializables.values():
            if serializable_def.type is not None:
                continue

            # Look up types for each member of the serializable
            for member in serializable_def.members:
                if member.type_str not in self.types:
                    sys.stderr.write(
                        'WARNING: Could not find type '
                        f'"{member.type_str}" for serializable '
                        f'"{serializable_def.name}" in types namespace\n')
                    continue
                member.type = self.types[member.type_str]

            if any(member.type is None for member in serializable_def.members):
                sys.stderr.write(
                    'WARNING: Not all types for serializable '
                    f'"{serializable_def.name}" could be found\n')
                continue

            # Create actual serializable type
            serializable_def.type = make_serializable_type(
                serializable_def.name,
                [
                    (member.name, member.type)
                    for member in serializable_def.members
                ])

            self.register_type(
                fsw_dict_file_path,
                serializable_def.name,
                serializable_def.type)

        for array_def in self.arrays.values():
            if array_def.type is not None:
                continue

            if array_def.element_type_str not in self.types:
                sys.stderr.write(
                    'WARNING: Could not find type '
                    f'"{array_def.element_type_str}" for '
                    f'array "{array_def.name}" in types namespace\n')
                continue

            array_def.type = make_array_type(
                array_def.name,
                self.types[array_def.element_type_str],
                array_def.size)

            self.register_type(
                fsw_dict_file_path,
                array_def.name,
                array_def.type)

    def resolve_types(self):
        for command in self.commands.values():
            for i, arg in enumerate(command.args):
                if arg.type_str not in self.types:
                    sys.stderr.write(
                        f'WARNING: Could not find type "{arg.type_str}" for '
                        f'argument "{arg.name}" of command '
                        f'"{command.topology_name}" in types namespace\n')
                    continue
                arg.type = self.types[arg.type_str]

        for event in self.events.values():
            for i, arg in enumerate(event.args):
                if arg.type_str not in self.types:
                    sys.stderr.write(
                        f'WARNING: Could not find type "{arg.type_str}" for '
                        f'argument "{arg.name}" of event '
                        f'"{event.topology_name}" in types namespace\n')
                    continue
                arg.type = self.types[arg.type_str]

        for channel in self.channels.values():
            if channel.type_str not in self.types:
                sys.stderr.write(
                    f'WARNING: Could not find type "{channel.type_str}" for '
                    f'channel "{channel.topology_name}" in types namespace\n')
                continue
            channel.type = self.types[channel.type_str]

        for parameter in self.parameters.values():
            set_command = self.commands.get(parameter.set_command_id, None)
            if set_command is None:
                sys.stderr.write(
                    'WARNING: Could not find command "'
                    f'{parameter.set_command_id[0]}.'
                    f'{parameter.set_command_id[1]}" for parameter '
                    f'"{parameter.topology_name}"\n')
                continue
            if len(set_command.args) != 1:
                sys.stderr.write(
                    f'WARNING: Command "{set_command.topology_name}" has '
                    f'{len(set_command.args)} argument when it should have '
                    'exactly 1\n')
                continue
            parameter.type_str = set_command.args[0].type_str
            parameter.type = set_command.args[0].type


# -- Printers -----------------------------------------------------------------


class JsonPrinter():

    def __init__(self, fsw_dict=None):
        self._d = fsw_dict

    def print_header(self):
        pass

    def print_record(self, item):
        sys.stdout.write(f'{item.as_json()}\n')

    def print_footer(self):
        pass


class TsvPrinter():

    def __init__(self, fsw_dict=None):
        self._d = fsw_dict

    def print_header(self):
        sys.stdout.write(
            'record_index'
            '\trecord_offset'
            '\tpacket_size'
            '\tpacket_type_name'
            '\tpacket_type_value'
            '\tpacket_time'
            '\ttelem_id'
            '\ttelem_id_hex'
            '\ttelem_topology_name'
            '\ttelem_component'
            '\ttelem_name'
            '\ttelem_time'
            '\ttelem_value_raw_size'
            '\ttelem_value_raw'
            '\ttelem_value'
            '\tevent_id'
            '\tevent_id_hex'
            '\tevent_topology_name'
            '\tevent_component'
            '\tevent_name'
            '\tevent_severity'
            '\tevent_time'
            '\tevent_arguments_raw_size'
            '\tevent_arguments_raw'
            '\tpayload'
            '\n')

    def print_record(self, record):
        packet = record.packet
        payload = record.packet.payload
        sys.stdout.write(
            f'{record_index}'
            f'\t{record.offset}'
            f'\t{record.packet_size}'
            f'\t{packet.type.name}'
            f'\t{packet.type.value}')
        if record.packet.type == Packet.Type.TELEM:
            channel = (
                self._d
                and self._d.channels_by_id.get(payload.id.value, None)
            )
            payload_value_as_hex = \
                payload.value_raw.data.hex() if len(payload.value_raw) else ""
            sys.stdout.write(
                f'\t{payload.time}'
                f'\t{payload.id}'
                f'\t{payload.id:#x}'
                f'\t{getattr(channel, "topology_name", "")}'
                f'\t{getattr(channel, "component", "")}'
                f'\t{getattr(channel, "name", "")}'
                f'\t{payload.time}'
                f'\t{len(payload.value_raw)}'
                f'\t{payload_value_as_hex}'
                f'\t{payload.value}'
                '\t\t\t\t\t\t\t\t\t\t')
        elif record.packet.type == Packet.Type.LOG:
            event = \
                self._d and self._d.events_by_id.get(payload.id.value, None)
            payload_args_as_hex = \
                payload.arguments_raw.data.hex() \
                if len(payload.arguments_raw) else ""
            sys.stdout.write(
                f'\t{payload.time}'
                '\t\t\t\t\t\t\t\t\t'
                f'\t{payload.id}'
                f'\t{payload.id:#x}'
                f'\t{getattr(event, "topology_name", "")}'
                f'\t{getattr(event, "component", "")}'
                f'\t{getattr(event, "name", "")}'
                f'\t{getattr(event, "severity_str", "")}'
                f'\t{payload.time}'
                f'\t{len(payload.arguments_raw)}'
                f'\t{payload_args_as_hex}'
                '\t')
        else:
            sys.stdout.write(
                '\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t'
                f'\t{payload.data.hex()}')
        sys.stdout.write('\n')

    def print_footer(self):
        pass


class VnlogPrinter():

    def __init__(self, fsw_dict=None):
        self._d = fsw_dict

    def print_header(self):
        sys.stdout.write(
            '#record_index'
            '\trecord_offset'
            '\tpacket_size'
            '\tpacket_type_name'
            '\tpacket_type_value'
            '\tpacket_time'
            '\ttelem_id'
            '\ttelem_id_hex'
            '\ttelem_topology_name'
            '\ttelem_component'
            '\ttelem_name'
            '\ttelem_time'
            '\ttelem_value_raw_size'
            '\ttelem_value_raw'
            '\ttelem_value'
            '\tevent_id'
            '\tevent_id_hex'
            '\tevent_topology_name'
            '\tevent_component'
            '\tevent_name'
            '\tevent_severity'
            '\tevent_time'
            '\tevent_arguments_raw_size'
            '\tevent_arguments_raw'
            '\tpayload'
            '\n')

    def print_record(self, record):
        packet = record.packet
        payload = record.packet.payload
        sys.stdout.write(
            f'{record_index}'
            f'\t{record.offset}'
            f'\t{record.packet_size}'
            f'\t{packet.type.name}'
            f'\t{packet.type.value}')
        if record.packet.type == Packet.Type.TELEM:
            channel = (
                self._d
                and self._d.channels_by_id.get(payload.id.value, None)
            )
            payload_value_as_hex = \
                payload.value_raw.data.hex() if len(payload.value_raw) else "-"
            sys.stdout.write(
                f'\t{payload.time}'
                f'\t{payload.id}'
                f'\t{payload.id:#x}'
                f'\t{getattr(channel, "topology_name", "-")}'
                f'\t{getattr(channel, "component", "-")}'
                f'\t{getattr(channel, "name", "-")}'
                f'\t{payload.time}'
                f'\t{len(payload.value_raw)}'
                f'\t{payload_value_as_hex}'
                f'\t{payload.value}'
                '\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-')
        elif record.packet.type == Packet.Type.LOG:
            event = \
                self._d and self._d.events_by_id.get(payload.id.value, None)
            payload_args_as_hex = \
                payload.arguments_raw.data.hex() \
                if len(payload.arguments_raw) else "-"
            sys.stdout.write(
                f'\t{payload.time}'
                '\t-\t-\t-\t-\t-\t-\t-\t-\t-'
                f'\t{payload.id}'
                f'\t{payload.id:#x}'
                f'\t{getattr(event, "topology_name", "-")}'
                f'\t{getattr(event, "component", "-")}'
                f'\t{getattr(event, "name", "-")}'
                f'\t{getattr(event, "severity_str", "-")}'
                f'\t{payload.time}'
                f'\t{len(payload.arguments_raw)}'
                f'\t{payload_args_as_hex}'
                '\t-')
        else:
            sys.stdout.write(
                '\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-'
                f'\t{payload.data.hex()}')
        sys.stdout.write('\n')

    def print_footer(self):
        pass


# -- Main program -------------------------------------------------------------


if __name__ == '__main__':
    import argparse
    import pathlib

    parser = argparse.ArgumentParser(description='''
        fprime-data-tool is a command line utility to read F Prime data in
        different formats and configurations and display them in different
        formats.  It can even work without a dictionary which is useful for
        sanity checking at the packet level.  With an F Prime FSW dictionary
        specified it can interpret the data.''')

    parser.add_argument(
        'istream',
        nargs='?',
        type=argparse.FileType('rb'),
        default=sys.stdin.buffer,
        help='''
            input file (default: read from stdin)''')
    parser.add_argument(
        '-F', '--output-format',
        action='store',
        type=str,
        choices=('json', 'tsv', 'vnlog'),
        default='vnlog',
        help='''
            selects the output format; default is vnlog''')
    parser.add_argument(
        '-d', '--dictionary',
        type=pathlib.Path,
        nargs=1,
        action='append',
        default=None,
        required=False,
        help='''
            path to F Prime dictionary used to interpret packet contents;
            default is to use no dictionary and display packet contents as
            binary blobs; this flag can be specified multiple times to load and
            merge multiple dictionaries''')
    parser.add_argument(
        '-I', '--import',
        action='append',
        default=None,
        dest='imports',
        metavar='MODULE',
        nargs=1,
        required=False,
        type=str,
        help='''
            imports a Python module with the given name which may augment the
            types available for parsing; the module should have a top-level
            variable named `types` that is a dictionary mapping type name
            (string) to the type itself; these types get added to
            `fp_types_custom` and can be specified as a top-level type using
            --record-type''')
    parser.add_argument(
        '-R', '--record-type',
        type=str,
        default='ComLoggerRecord',
        help='''
            specifies the top-level type to parse; the parser will treat the
            input as a concatenated sequence of the specified type; for
            ComLogger logs use ComLoggerRecord (this is the default); for
            fprime-gds recv.bin logs use FprimeGdsRecord; for parameter
            database files use PrmDbRecord; to read an fprime-gds uplink or
            downlink stream use FprimeGdsStream; you can also specify types
            that are defined in a loaded dictionary; if you choose a type other
            than ComLoggerRecord and FprimeGdsRecord then the output format
            will revert to JSON; types available: {}
            '''.format(
                ', '.join(
                    f"{name}"
                    for name
                    in list(fp_types.keys()) + list(fp_types_custom.keys()))))

    for name, default in fprime_configurable_flags:
        parser.add_argument(
            f'--{name}',
            metavar='VALUE',
            dest=name,
            action='store',
            type=ast.literal_eval,
            default=default,
            help=f'''
                sets the F Prime configuration for {name}; default is
                {default}''')

    def FundamentalType(type_name):
        if type_name in fptypes_fundamental:
            return fptypes_fundamental[type_name]
        raise KeyError(f'Unknown fundamental_type name "{type_name}"')

    fundamental_types_list = ', '.join(
        f"{name}" for name in fptypes_fundamental.keys())
    for name, default in fprime_configurable_types:
        parser.add_argument(
            f'--{name}',
            metavar='TYPE',
            dest=name,
            action='store',
            type=FundamentalType,
            default=default,
            help=f'''
                sets the F Prime configuration for {name}; must be one of the
                following fundamental_types: {fundamental_types_list}; default
                is {default.__name__}''')

    args = parser.parse_args()

    # Apply configurable flags from CLI options
    for name, _ in fprime_configurable_flags:
        globals()[name] = getattr(args, name)

    # Apply configurable types from CLI options
    for name, _ in fprime_configurable_types:
        fp_types[name] = getattr(args, name)
        globals()[name] = getattr(args, name)

    fsw_dict = None
    if args.dictionary is not None:
        fsw_dict = FswDictionary(fp_types)
        for (fsw_dict_file_path,) in args.dictionary:
            fsw_dict.parse(fsw_dict_file_path)

    if args.imports is not None:
        import importlib
        for (module_name,) in args.imports:
            module = importlib.import_module(module_name)
            for type_name, type_class in module.types.items():
                fp_types_custom[type_name] = type_class

    record_type = None
    if fsw_dict is not None:
        record_type = fsw_dict.types.get(args.record_type, record_type)
    record_type = fp_types_custom.get(args.record_type, record_type)

    if record_type is None:
        sys.stderr.write(
            f'ERROR: Record type "{args.record_type}" does not exist\n')
        sys.exit(1)

    if not hasattr(record_type, 'decode'):
        sys.stderr.write(
            f'ERROR: Record type "{record_type.__name__}" does not have a '
            'decode attribute.  The type must have a decode class function.\n')
        sys.exit(1)

    if record_type is not ComLoggerRecord and \
            record_type is not FprimeGdsRecord:
        sys.stderr.write(
            f'WARNING: Record type "{record_type.__name__}" is not either '
            '"ComLoggerRecord" or "FprimeGdsRecord" so forcing use of JSON '
            'printer\n')
        args.output_format = 'json'

    if args.output_format == 'json':
        printer = JsonPrinter(fsw_dict)
    elif args.output_format == 'tsv':
        printer = TsvPrinter(fsw_dict)
    elif args.output_format == 'vnlog':
        printer = VnlogPrinter(fsw_dict)
    else:
        raise KeyError(f'Unknown printer specified: "{args.output_format}"')

    printer.print_header()

    try:
        record_index = 0
        while True:
            record = record_type.decode(args.istream, fsw_dict)
            if record is None:
                continue
            printer.print_record(record)
            sys.stdout.flush()
            record_index += 1
    except BrokenPipeError:
        pass

    printer.print_footer()
