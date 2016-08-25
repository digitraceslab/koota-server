from base64 import urlsafe_b64encode
import collections
import csv
from datetime import timedelta
from hashlib import sha256
import importlib
import itertools
import json
from json import dumps, loads
import os
import time
import six
from six import StringIO as IO

import django.db.models
import django.forms

from . import models

import logging
logger = logging.getLogger(__name__)


def import_by_name(name, default=None, raise_if_none=False):
    """Import a name from a module.  Return object.


    name: name of class to import and return
    default: if name not found, return this as default.
    raise_if_none: if name not found, return this by default."""
    if not isinstance(name, str):
        raise ValueError("name must be string: %s"%name)
    if not name:
        return default
    if '.' not in name:
        # If desired, don't let errors pass silently
        logger.error("Custom class import failed: %s"%name)
        if raise_if_none:
            raise ValueError("import_by_name: can not import `%s`"%name)
        return default
    modname, objname = name.rsplit('.', 1)
    try:
        mod = importlib.import_module(modname)
    except ImportError:
        logger.error("Custom class import failed: %s (%s)"%(name, modname))
        if raise_if_none:
            raise ValueError("import_by_name: can not import `%s`"%name)
        return default
    try:
        obj = getattr(mod, objname)
    except AttributeError:
        logger.error("Custom class import failed: %s (%s)"%(name, objname))
        if raise_if_none:
            raise ValueError("import_by_name: can not import `%s`"%name)
        return default
    return obj


from django.conf import settings
SALT = settings.SALT
def safe_hash(data):
    """Make a safe hash function for identifiers."""
    if not isinstance(data, bytes):
        data = data.encode('utf8')
    return urlsafe_b64encode(sha256(SALT+data).digest()[:9]).decode('ascii')

def random_salt_b64(nbytes=18):
    """Random """
    return urlsafe_b64encode(os.urandom(nbytes))

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
          for _ in range(10):
            row = next(rows)
            #print row
            csv_writer.writerow(row)
        except StopIteration:
            fo.seek(0)
            yield fo.read()
            del fo
            break
        fo.seek(0)
        data = fo.read()
        fo.seek(0)
        fo.truncate()
        yield data
    if converter and converter.errors:
        yield 'The following errors were found at unspecified points in processing:\n'
        for error in converter.errors:
            yield str(error)+'\n'
def csv_aligned_iter(table, converter=None, header=None):
    """Yields CSV lines, but try to align them.

    This is a bit of a hack, just useful for human reading.  It makes
    CSV lines, and each field is aligned to the length of longest
    field in that column seen so far.  It also includes a bottom header.
    """
    # Header
    yield ','.join(str(x) for x in header)+'\n'
    # Data
    widths = collections.defaultdict(int)
    for row in table:
        row2 = [ ]
        for i, x in enumerate(row):
            x = str(x)
            w = widths[i] = max(widths[i], len(x))
            row2.append(x.ljust(w))
        yield ','.join(row2)+'\n'
    # Bottom header, properly aligned to data above.
    yield ','.join(str(x).ljust(widths[i]) for i,x in enumerate(header))+'\n'

def json_lines_iter(table, converter=None, header=None):
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
def json_iter(table, converter=None, header=None):
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



#class queryset_iterator(object):
#    def __init__()
def optimized_queryset_iterator_1(queryset):
    """Wrapper to read queryset.

    This is the primitive version of the one below.  It defers loading
    data, so has to do it for every row.  This is inefficient.

    """
    return queryset.defer('data').iterator()
def optimized_queryset_iterator(queryset):
    """Queryset wrapper that optimizes lots of data access.

    Reading django queries is a balance.  If we do nothing, django
    reads in all data at once, using all memory.  If we
    .defer('data').iterator(), it will make a new DB query for every
    row, which is very inefficient and slow.

    This uses different heurestics in order to break up one query into
    a lot of different parts.  First, it has to use the time index to
    extract daily our hourly periods.  Then, we use offset within that
    to not get too many rows at once.  There is no single good way to
    make sure that don't query too much and get too many rows at once
    (blowing up memory).

    There are a lot of different parameters here, mainly chunk_size
    and dt.  They will have to be tuned as time goes on and we learn
    more.
    """
    # Parameters
    dt = timedelta(hours=1)
    default_chunk_size = 50
    #
    if not queryset.exists():
        return
    ts_start = queryset[0].ts
    ts_end = queryset.reverse()[0].ts
    ts = ts_start
    while ts <= ts_end:  # ts_end is a closed interval point
        ts_next = ts + dt
        #yield from queryset.filter(ts__gte=ts, ts__lt=ts_next)
        # Filter for time range
        qs2 = queryset.filter(ts__gte=ts, ts__lt=ts_next)
        # Get some aggregate data, in order to possibly better adjust
        # the heuristics.
        agg = qs2.aggregate(#bytes=django.db.models.Sum('data_length'),
                            count=django.db.models.Count('device_id'))
        #bytes = agg['bytes']
        count = agg['count']
        # no rows
        if not count:
            ts = ts_next
            continue
        # Find optimal chunk size
        #chunk_size = int(round(default_chunk_size / (bytes/5000000.)))
        #chunk_size = min(chunk_size, default_chunk_size)
        chunk_size = default_chunk_size
        # Go through the chunks.  Yield from each of them.
        for i in itertools.count():
            qs3 = qs2[i*chunk_size : chunk_size*(i+1)]
            if not qs3.exists(): break  # infinite iterator, break here
            yield from qs3
        ts = ts_next


def time_slice_iterator(it, maxduration):
    """Time iterator ending after a certain number of seconds.

    This was made so that we could limit the time it takes to render
    HTML pages with certain data.  The problem is that this only can
    break after a row is emitted.  In the cases that no rows are
    emitted (the case it was first made for), it can never break.
    """
    time_func = time.time
    end_time = time_func() + maxduration
    while True:
        yield next(it)
        if time_func() >= end_time:
            break



# For Mosquitto server passwords
from django.contrib.auth.hashers import PBKDF2PasswordHasher
import base64
def hash_mosquitto_password(passwd):
    salt = base64.b64encode(os.urandom(15)).decode('ascii')
    passwd = PBKDF2PasswordHasher().encode(passwd, salt, iterations=50000)
    # Following two lines to put it in MQTT format
    passwd = passwd.replace('_', '$', 1)
    passwd = passwd.replace('pbkdf2', 'PBKDF2')
    return passwd



class JsonConfigFormField(django.forms.Field):
    def __init__(self, *args, **kwargs):
        # Somehow max_length gets added again, and we have to remove it.
        kwargs.pop('max_length', None)
        return super(JsonConfigFormField, self).__init__(*args, **kwargs)
    def to_python(self, value):
        if not value.strip(): return ''
        try:
            value = loads(value)
        except json.JSONDecodeError as e:
            raise django.forms.ValidationError("Invalid JSON: "+str(e))
            #raise django.forms.ValidationError("Invalid JSON")
        return value
    def prepare_value(self, value):
        try:
            value = loads(value)
        except json.JSONDecodeError:
            return value
        return dumps(value, sort_keys=True,
                     indent=4, separators=(',', ': '))
# database field
class JsonConfigField(django.db.models.TextField):
    def formfield(self, **kwargs):
        defaults = {'form_class': JsonConfigFormField}
        defaults.update(kwargs)
        return super(JsonConfigField, self).formfield(**defaults)
    # convert python object to query value
    def get_prep_value(self, value):
        if value is '':   return ''
        value = dumps(value, separators=(',', ':'))
        # return should always be string
        return value
    # deserialization (from DB) and .clean() by forms
    def to_python(self, value):
        if value is None: return None
        if not isinstance(value, str): return value
        try:
            value = loads(value)
        except json.JSONDecodeError:
            raise django.forms.ValidationError("Invalid JSON")
        return value



def merge_dicts(*dicts):
    result = { }
    for d in dicts:
        recursive_update_dicts(d, result)
    return result
def recursive_update_dicts(src, dest):
    for k, v in src.items():
        if k in dest and isinstance(v, dict):
            recursive_update_dicts(src[k], dest[k])
        else:
            result[k] = copy.deepcopy(v)



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
