from base64 import b64encode
import csv
from hashlib import sha256
import importlib
from json import dumps
from six import StringIO as IO

import six

from . import models

import logging
logger = logging.getLogger(__name__)

def get_device(request, *args, **kwargs):
    raise NotImplemented

def has_device_perm(request, device):
    """Test for user having permissions to access device.
    """
    if isinstance(device, six.string_types):
        device = models.Device.objects.get(device_id=device)
    if request.user.is_superuser and request.user.is_verified():
        return True
    if device.user == request.user:
        return True
    return False

def check_device_permissions(func):
    raise NotImplemented
    def _decorated(request, *args, **kwargs):
        if not has_device_perm(request, kwargs['device_id']):
            return Http404
        return func(request, *args, **kwargs)
    return _decorated

def import_by_name(name):
    """Import a name from a module.  Return object."""
    modname, objname = name.rsplit('.', 1)
    try:
        mod = importlib.import_module(modname)
    except ImportError:
        logger.error("Custom class import failed: %s (%s)"%(name, modname))
        return None
    try:
        obj = getattr(mod, objname)
    except AttributeError:
        logger.error("Custom class import failed: %s (%s)"%(name, objname))
        return None
    return obj


from django.conf import settings
SALT = settings.SALT
def safe_hash(data):
    """Make a safe hash function for identifiers."""
    if not isinstance(data, bytes):
        data = data.encode('utf8')
    return b64encode(sha256(SALT+data).digest()[:9]).decode('ascii')

class IntegerMap(object):
    """Map objects to integers"""
    def __init__(self):
        self.map = { }
    def __call__(self, value):
        return self.map.setdefault(value, len(self.map))


def csv_iter(table, converter=None, header=None):
    rows = iter(table)
    fo = IO()
    csv_writer = csv.writer(fo)
    csv_writer.writerow(header)
    while True:
        try:
          for _ in range(1000):
            row = next(rows)
            #print row
            csv_writer.writerow(row)
        except StopIteration:
            fo.seek(0)
            yield fo.read().encode('utf-8')
            del fo
            break
        fo.seek(0)
        data = fo.read().encode('utf-8')
        fo.seek(0)
        fo.truncate()
        yield data
    if converter and converter.errors:
        yield 'The following errors were found at unspecified points in processing:\n'
        for error in converter.errors:
            yield str(error)+'\n'

def json_lines_iter(table, converter=None):
    rows = iter(table)
    try:
        while True:
            yield dumps(next(rows))+'\n'
    except StopIteration:
        pass
    if converter and converter.errors:
        yield 'The following errors were found at unspecified points in processing:\n'
        for error in converter.errors:
            yield str(error)+'\n'
def json_iter(table, converter=None):
    rows = iter(table)
    yield '[\n'
    try:
        yield dumps(next(rows))  # first one (hope there is no StopIteration now)
        while True:
            row = next(rows)  # raises StopIteration if data exhausted
            yield ',\n'  # finalize the one from before, IF we have a next row
            yield dumps(row)
    except StopIteration:
        pass
    yield '\n]\n'
    if converter and converter.errors:
        yield 'The following errors were found at unspecified points in processing:\n'
        for error in converter.errors:
            yield str(error)+'\n'




#
# The following functions deal with device checkdigits.
#
def luhn1(num, check=False):
    """Luhn algorithm mod 16"""
    factor = 2
    #if check:
    #    factor = 1
    sum = 0
    base = 16
    digits = 2
    base = base**digits

    if check:
        sum = int(num[-digits:], 16)
        num = num[:-digits]
    # Starting from the right, work leftwards
    # Now, the initial "factor" will always be "1"
    # since the last character is the check character
    #for (int i = input.Length - 1; i >= 0; i--) {
    for char in reversed(num):
        addend = factor * int(char, 16)

        # factor alternates between 1 and 2
        factor = 2-factor+1

        # Sum the digits of the "addend" as expressed in base "n"
        addend = (addend // base) + (addend % base);
        sum += addend

    remainder = sum % base
    #print remainder, type(remainder)

    if check:
        return remainder == 0
    else:
        # Computing check digits
        checkCodePoint = (base - remainder) % base
        return '%x'%checkCodePoint

def luhn2(num, check=False):
    factor = 2
    #if check:
    #    factor = 1
    sum = 0
    #base = 16
    #digits = 2
    #base = base**digits

    num = int(num, 16)
    if check:
        #sum = int(num[-digits:], 16)
        #num = num[:-digits]
        sum = num & 255
        num = num >> 8

    #for char in reversed(num):
    while num > 0:
        #addend = factor * int(char, 16)
        addend = factor * (num&15)
        num = num >> 4   # advance to next digits

        # factor alternates between 1 and 2
        factor = 2-factor+1

        # Sum the digits of the "addend" as expressed in base "n"
        #addend = (addend / base) + (addend % base);
        #print addend
        addend = (addend >> 8) + (addend & 255)
        sum += addend
        #print hex(num), sum, addend

    remainder = sum % 256
    #print remainder, type(remainder)

    if check:
        return remainder == 0
    else:
        # Computing check digits
        checkCodePoint = (256 - remainder) % 256
        return '%02x'%checkCodePoint
luhn = luhn2

def add_checkdigits(num):
    return num + luhn(num)
def check_checkdigits(num):
    return luhn(num, check=True)

def test_luhn():
    import random
    random.seed(13)
    for num in ['5146abc5fd2',
                hex(random.randint(0,2**31-1))[2:],
                hex(random.randint(0,2**31-1))[2:],
                hex(random.randint(0,2**31-1))[2:],
                hex(random.randint(0,2**31-1))[2:],
                ]+[hex(random.randint(0,2**31-1))[2:] for _ in range(1000000) ] \
        :
        #
        num_swapped = swap2(num+luhn(num))

        #if num[2]=='0' and num[3]=='f':
        #    print num, luhn(num)
        #    print ('swap2', num, luhn(num), swap2(num), luhn(swap2(num)), )

        assert luhn(num+luhn(num), check=True), \
            (num, luhn(num), )

        assert len(num)<4 or num[2]==num[3] or not luhn(num_swapped, check=True), \
            ('swap2', num, luhn(num), swap2(num), luhn(swap2(num)), )

        num_replaced = replace1(num+luhn(num))
        assert not luhn(num_replaced, check=True), \
            ('swap2', num, luhn(num), replace1(num), luhn(replace1(num)), )

def swap2(num):
    return num[:2]+num[3:4]+num[2:3]+num[4:]
def replace1(num):
    import random, string
    pos = random.randint(0, len(num)-1)
    while True:
        x = random.choice(string.hexdigits[:16])
        if x != num[pos]: break
    return num[:pos] + x + num[pos+1:]
