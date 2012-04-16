
import hashlib, time

from binascii import hexlify, unhexlify
from collections import OrderedDict
from datetime import datetime
from io import BytesIO, SEEK_END



PDF_VERSION = '1.4'


# TODO: max line length (not streams)


class Object(object):
    def __init__(self, indirect=False):
        self.indirect = indirect

    def bytes(self, document):
        if self.indirect:
            reference = document._by_object_id[id(self)]
            out = reference.bytes(document)
        else:
            out = self._bytes(document)
        return out

    @property
    def r(self):
        return repr(self)

    def delete(self, document):
        try:
            reference = document._by_object_id[self]
            reference.delete()
        except KeyError:
            pass

    def register_indirect(self, document):
        if self.indirect:
            document.register(self)


class Reference(object):
    def __init__(self, document, identifier, generation):
        self.document = document
        self.identifier = identifier
        self.generation = generation

    def bytes(self, document):
        return '{} {} R'.format(self.identifier,
                                self.generation).encode('utf_8')

    @property
    def target(self):
        return self.document[self.identifier][0]

    def delete(self, document=None):
        if document == self.document:
            del self.document[self.identifier]

    def __repr__(self):
        return '{}<{} {}>'.format(self.target.__class__.__name__,
                                  self.identifier, self.generation)

    @property
    def r(self):
        return repr(self.target)

    def __getitem__(self, name):
        return self.target[name]

    def __setitem__(self, key, value):
        self.target[key] = value

    def __getattr__(self, name):
        return getattr(self.target, name)

    def __contains__(self, item):
        return item in self.target

    def register_indirect(self, document):
        self.target.register_indirect(document)


class Boolean(Object):
    def __init__(self, value, indirect=False):
        super().__init__(indirect)
        self.value = value

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.value)

    def _bytes(self, document):
        return b'true' if self.value else b'false'


class Integer(Object, int):
    def __new__(cls, value, base=10, indirect=False):
        try:
            return int.__new__(cls, value, base)
        except TypeError:
            return int.__new__(cls, value)

    def __init__(self, value, base=10, indirect=False):
        Object.__init__(self, indirect)

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, int.__repr__(self))

    def _bytes(self, document):
        return int.__str__(self).encode('utf_8')


class Real(Object, float):
    def __new__(cls, value, indirect=False):
        return float.__new__(cls, value)

    def __init__(self, value, indirect=False):
        Object.__init__(self, indirect)

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, float.__repr__(self))

    def _bytes(self, document):
        return float.__str__(self).encode('utf_8')


class String(Object):
    def __init__(self, string, indirect=False):
        super().__init__(indirect)
        self.string = string

    def __repr__(self):
        return "{}('{}')".format(self.__class__.__name__, self.string)

    def _bytes(self, document):
        escaped = self.string.replace('\n', r'\n')
        escaped = escaped.replace('\r', r'\r')
        escaped = escaped.replace('\t', r'\t')
        escaped = escaped.replace('\b', r'\b')
        escaped = escaped.replace('\f', r'\f')
        for char in '\\()':
            escaped = escaped.replace(char, '\\{}'.format(char))
        out = '({})'.format(escaped)
        return out.encode('utf_8')


class HexString(Object):
    def __init__(self, byte_string, indirect=False):
        super().__init__(indirect)
        self.byte_string = byte_string

    def __repr__(self):
        return "{}('{}')".format(self.__class__.__name__,
                                 hexlify(self.byte_string).decode())

    def _bytes(self, document):
        return b'<' + hexlify(self.byte_string) + b'>'


class Date(String):
    def __init__(self, timestamp, indirect=False):
        local_time = datetime.fromtimestamp(timestamp)
        utc_time = datetime.utcfromtimestamp(timestamp)
        utc_offset = local_time - utc_time
        utc_offset_minutes, utc_offset_seconds = divmod(utc_offset.seconds, 60)
        utc_offset_hours, utc_offset_minutes = divmod(utc_offset_minutes, 60)
        string = local_time.strftime('D:%Y%m%d%H%M%S')
        string += "{:+03d}'{:02d}'".format(utc_offset_hours, utc_offset_minutes)
        super().__init__(string, indirect)


class Name(Object):
    # TODO: names should be unique (per document), so check
    def __init__(self, name, indirect=False):
        super().__init__(indirect)
        self.name = name

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.name)

    def _bytes(self, document):
        # TODO: # escaping
        return '/{}'.format(self.name).encode('utf_8')


class Array(Object, list):
    # TODO: not all methods of list are overridden, so funny
    # behavior is to be expected
    def __init__(self, items=[], indirect=False):
        Object.__init__(self, indirect)
        list.__init__(self, items)

    def __repr__(self):
        return '{}{}'.format(self.__class__.__name__, list.__repr__(self))

    def _bytes(self, document):
        return b'[' + b' '.join([elem.bytes(document) for elem in self]) + b']'

    def register_indirect(self, document):
        register_children = True
        if self.indirect:
            register_children = id(self) not in document._by_object_id
            document.register(self)
        if register_children:
            for item in self:
                item.register_indirect(document)


class Dictionary(Object, OrderedDict):
    def __init__(self, indirect=False):
        Object.__init__(self, indirect)
        OrderedDict.__init__(self)

    def __repr__(self):
        return '{}{}'.format(self.__class__.__name__, dict.__repr__(self))

    def _bytes(self, document):
        return b'<< ' + b' '.join([Name(key).bytes(document) + b' ' +
                                   value.bytes(document)
                                   for key, value in self.items()]) + b' >>'

    def register_indirect(self, document):
        register_children = True
        if self.indirect:
            register_children = id(self) not in document._by_object_id
            document.register(self)
        if register_children:
            for item in self.values():
                item.register_indirect(document)


class Stream(Dictionary):
    def __init__(self):
        # (Streams are always indirectly referenced)
        super().__init__(indirect=True)
        self.data = BytesIO()

    def _bytes(self, document):
        if 'Length' in self:
            self['Length'].delete(document)
        self['Length'] = Integer(self.size)
        out = super()._bytes(document)
        out += b'\nstream\n'
        out += self.data.getvalue()
        out += b'\nendstream'
        return out

    def read(self, *args, **kwargs):
        return self.data.read(*args, **kwargs)

    def write(self, *args, **kwargs):
        return self.data.write(*args, **kwargs)

    def tell(self, *args, **kwargs):
        return self.data.tell(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self.data.seek(*args, **kwargs)

    @property
    def size(self):
        restore_pos = self.tell()
        self.seek(0, SEEK_END)
        size = self.tell()
        self.seek(restore_pos)
        return size


class Null(Object):
    def __init__(self, indirect=False):
        super().__init__(indirect)

    def __repr__(self):
        return self.__class__.__name__

    def _bytes(self, document):
        return b'null'



class Document(dict):
    def __init__(self):
        self.catalog = Catalog()
        self.info = Dictionary(indirect=True)
        self.timestamp = time.time()
        self.info['CreationDate'] = Date(self.timestamp)
        self.id = None
        self._by_object_id = {}

    def register(self, obj):
        if id(obj) not in self._by_object_id:
            identifier, generation = self.max_identifier + 1, 0
            reference = Reference(self, identifier, generation)
            self._by_object_id[id(obj)] = reference
            self[identifier] = (obj, generation)

    @property
    def max_identifier(self):
        try:
            identifier = max(self.keys())
        except ValueError:
            identifier = 0
        return identifier

    def _write_xref_table(self, file, addresses):
        def out(string):
            file.write(string + b'\n')

        out(b'xref')
        out('0 {}'.format(self.max_identifier + 1).encode('utf_8'))
        out(b'0000000000 65535 f ')
        last_free = 0
        for identifier in range(1, self.max_identifier + 1):
            try:
                obj, gen = self[identifier]
                address = addresses[identifier]
                out('{:010d} {:05d} n '.format(address, gen).encode('utf_8'))
            except KeyError:
                out(b'0000000000 65535 f ')
                last_free = identifier

    def write(self, file_or_filename):
        def out(string):
            file.write(string + b'\n')

        try:
            file = open(file_or_filename, 'wb')
        except TypeError:
            file = file_or_filename

        self.catalog.register_indirect(self)
        self.info.register_indirect(self)
        if 'Producer' in self.info:
            self.info['Producer'].delete(self)
        if 'ModDate' in self.info:
            self.info['ModDate'].delete(self)
        self.info['Producer'] = String('pyte PDF backend')
        self.info['ModDate'] = Date(self.timestamp)

        out('%PDF-{}'.format(PDF_VERSION).encode('utf_8'))
        file.write(b'%\xDC\xE1\xD8\xB7\n')
        addresses = {}
        for identifier in range(1, self.max_identifier + 1):
            try:
                obj, generation = self[identifier]
                addresses[identifier] = file.tell()
                out('{} 0 obj'.format(identifier, generation).encode('utf_8'))
                out(obj._bytes(self))
                out(b'endobj')
            except KeyError:
                pass
        xref_table_address = file.tell()
        self._write_xref_table(file, addresses)
        out(b'trailer')
        trailer = Dictionary()
        trailer['Size'] = Integer(self.max_identifier + 1)
        trailer['Root'] = self.catalog
        trailer['Info'] = self.info
        md5sum = hashlib.md5()
        md5sum.update(str(self.timestamp).encode())
        md5sum.update(str(file.tell()).encode())
        for value in self.info.values():
            md5sum.update(value._bytes(self))
        new_id = HexString(md5sum.digest())
        if self.id:
            self.id[1] = new_id
        else:
            self.id = Array([new_id, new_id])
        trailer['ID'] = self.id
        out(trailer.bytes(self))
        out(b'startxref')
        out(str(xref_table_address).encode('utf_8'))
        out(b'%%EOF')


class Catalog(Dictionary):
    def __init__(self):
        super().__init__(indirect=True)
        self['Type'] = Name('Catalog')
        self['Pages'] = Pages()


class Pages(Dictionary):
    def __init__(self):
        super().__init__(indirect=True)
        self['Type'] = Name('Pages')
        self['Count'] = Integer(0)
        self['Kids'] = Array()

    def new_page(self, width, height):
        page = Page(self, width, height)
        self['Kids'].append(page)
        self['Count'] = Integer(self['Count'] + 1)
        return page


class Page(Dictionary):
    def __init__(self, parent, width, height):
        super().__init__(indirect=True)
        self['Type'] = Name('Page')
        self['Parent'] = parent
        self['Resources'] = Dictionary()
        self['MediaBox'] = Array([Integer(0), Integer(0),
                                  Real(width), Real(height)])


class Font(Dictionary):
    def __init__(self, indirect):
        super().__init__(indirect)
        self['Type'] = Name('Font')