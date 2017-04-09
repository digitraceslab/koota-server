"""Various converters for raw data.

This module provides for postprocessing of raw data.  Basically, it
provides classes that take an iterator of raw data ((datetime, str)
tuples), and returns iterators over preprocessed data in some sort of
tabular format.  Each converter has these methods:

Converter(iterator[, time])
    New method of usage.

converter.run()
    New method of usage.  Instantiating an object as above and running
    like this has the same effect as Converter.convert() (below), but
    will handle errors.  Error messages are placed in converter.errors
    and converter.error_dict.  TODO: finish documenting this.  TODO:
    more flexible error handling in in this method.

Converter.convert(iterator[, time])
    The argument to this function should be an iterator over
    (datetime, str) tuples.  The datetime.datetime is the raw data
    packet time (when data was recceived by the server).  The str
    is the raw string data which the device has sent to the server.
    The return value is an iterator over tuples, each tuple
    represents one row of output as Python objects.

    This is the core logic of this module.  Each converter class
    should overwrite this function to implement its logic.
    Typically, it would be something like: json decode the string
    data, extract info, yield one or more lines.

Converter.header2()
    Returns the output column names, list of strings.  Used in csv, for
    example.  The default implementation just returns self.header.
    (It's a bit hackish to have both header attribute and header2 method,
    but things changed and a quick hack was introduced pending a final
    solution).

Converter.name()
    Returns the human-readable name of the converter.

Converter.desc
    Human-readable description of the converter.

To make a new converter, you would basically:

- Look to find a similar converter (for example, all of the Purple
  Robot ones are similar)
- Build on (copy or subclass) that.
- Change the convert() method
- Change the header (header attribute)


This file, when run a a script, provides a simple command line interface
(at the bottom).

To access data from Python code, there is no shortcut method right now,
you should do this.  There is an example script at the bottom of this
file.:

- import converter
- converter_class = converter.PRScreen  # for example
- header = converter_class.header2()
- Without error handling (run this if you want to handle them yourself):
  for row in converter_class.convert(rows):
      ... # do something with each row
- There is a second option with error handling:
  converter = converter_class(rows)
  for row in converter.run():
      ... # do something with each row
  # At the end
  converter.errors
  converter.errors_dict
"""

from __future__ import print_function

from six import iteritems, itervalues, string_types
from six.moves import zip

from base64 import urlsafe_b64encode
from calendar import timegm
import collections
import csv
from datetime import datetime, timedelta
from hashlib import sha256
import itertools
import json  # needed for pretty json
try:
    from ujson import dumps, loads
except:
    from json import loads, dumps
from math import cos, log, pi, sin, sqrt
import time
import time as mod_time
from time import localtime
import re
import sys

import logging
logger = logging.getLogger(__name__)


# Make a safe-hash function.  This can be used to hide identifiers.
# This currently uses sha256 + a random secret salt for security.  We
# go through thees steps to a) ensure that we never use a hard-coded
# salt, and b) not depend on django.
try:
    from django.conf import settings
    SALT_KEY = settings.SALT_KEY
    del settings
except:
    # Make a random salt that changes on every invocation.  This is
    # not stable (changes every time the process runs), but is the
    # safest option until there is some way to specify things.  So far
    # there is no point where comparing across invocations is
    # important.
    import random
    SALT_KEY = bytes(bytearray((random.randint(0, 255) for _ in range(32))))
def safe_hash(data):
    """Make a safe hash function for identifiers."""
    if not isinstance(data, bytes):
        data = data.encode('utf8')
    return urlsafe_b64encode(sha256(SALT_KEY+data).digest()[:9]).decode('ascii')



# This is defined in kdata/views_admin.py.  Copied here so that there are no dependencies.
def human_bytes(x):
    """Add proper binary prefix to number in bytes, returning string"""
    if x <= 0:
        return '%6.2f %-3s'%(x, 'B')
    unit_list = [ 'B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    exponent = int(log(x, 1024))
    quotient = x / 1024**exponent
    return '%6.2f %-3s'%(quotient, unit_list[exponent])


class _Converter(object):
    per_page = 25
    header = [ ]
    desc = ""
    @classmethod
    def name(cls):
        """Shortcut to return class name on either object or instance"""
        return cls.__name__
    @classmethod
    def header2(cls):
        """Return header, either dynamic or static."""
        if hasattr(cls, 'header') and cls.header:
            return cls.header
        return ['time'] + [x[0].lower() for x in cls.fields]
    def __init__(self, rows=None, time=lambda x: x):
        # Warning: during template rendering this is used in a variable as "_Converter.name"
        pass
        self.rows = rows
        self.time = time
        self.errors = [ ]
        self.errors_dict = collections.defaultdict(int)
    def run(self):
        """Run through the conversion.

        If any errors are raised during conversion, do not fail.
        Instead, log those errors and continue.  This is a wrapper
        around the direct "convert" statements.  When this method is
        being used, the converter class must be instantiated with the
        rows/time arguments that .convert() takes.
        """
        # Convert the rows into an iterator explicitely here.  For
        # objects like querysets or generators, this has no effect.
        # But for lists/tuples, if we don't do this, every repitition
        # of the while loop *restarts*, which is not what we want.  By
        # making the iterator here, each repitition in the loop below
        # starts where the previous left off.
        rows = iter(self.rows)
        # Until we are exhausted (we get to the break)
        while True:
            try:
                # Iterate through yielding everything.
                for x in self.convert(rows, self.time):
                    yield x
                # If we manage to finish, break loop and we are done.
                # Everything is simple.
                break
            # If there was exception, do something with it, then
            # restart the while loop.  It will break when iterator
            # exhausted.  The handling colud be improved later.
            except Exception as e:
                if len(self.errors) < 100:
                    logger.error("Exception in %s", self.__class__.__name__)
                    import traceback
                    logger.error(e)
                    logger.error(traceback.format_exc())
                    self.errors.append(e)
                self.errors_dict[str(e)] += 1
                #self.errors_emit_error(e)
                # Possibly we need to prevent each next traceback from
                # storing the previous traceback, too.
                del e
    def run_queryset(self, queryset, device,
                     time_converter=lambda x: x,
                     catch_errors=False):
        """Generic function to handle converting querysets"""
        from . import util
        queryset = util.optimized_queryset_iterator(queryset)
        if catch_errors:
            converter = cls(((x.ts, x.data) for x in data),
                            time=time_converter)
            table = converter.run()
        else:
            converter = converter_class()
            table = converter.convert(((x.ts, x.data) for x in data),
                                      time=time_converter)
        return table


class Raw(_Converter):
    header = ['packet_time', 'data']
    desc = "Raw data packets"

    def convert(self, queryset, time=lambda x:x):
        for dt, data in queryset:
            yield (time(timegm(dt.utctimetuple())),
                   data,
                  )

class PacketSize(_Converter):
    header = ['packet_time', 'data_length']
    desc = "Data packet sizes"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            yield (time(timegm(ts.utctimetuple())),
                   len(data),
                  )


class BaseDataSize(_Converter):
    """Thas class can be subclassed to get """
    device_class = 'PurpleRobot'
    per_page = None
    header = ['probe', 'count', 'bytes', 'human_bytes', 'bytes/day']
    desc = "Total bytes taken by each separate probe (warning: takes a long time to compute)"
    days_ago = None
    @classmethod
    def query(cls, queryset):
        """"Limit to the number of days ago, if cls.days_ago is given."""
        if not cls.days_ago:
            return queryset
        from django.utils import timezone
        now = timezone.now()
        return queryset.filter(ts__gt=now-timedelta(days=cls.days_ago))
    def convert(self, queryset, time=lambda x:x):
        if self.days_ago is not None:
            start_time = mod_time.time() - self.days_ago * (24*3600)
            total_days = self.days_ago
        else:
            start_time = 0
            total_days = None
        sizes = collections.defaultdict(int)
        counts = collections.defaultdict(int)
        total_days = self.do_queryset_iteration(queryset, sizes, counts, total_days)
        for probe, size in sorted(iteritems(sizes), key=lambda x: x[1], reverse=True):
            yield (probe,
                   counts[probe],
                   size,
                   human_bytes(size),
                   human_bytes(size/float(total_days)))
        yield ('total',
               sum(itervalues(counts)),
               sum(itervalues(sizes)),
               human_bytes(sum(itervalues(sizes))),
               human_bytes(sum(itervalues(sizes))/float(total_days)))
    # Following methods can be overridden in subclasses to allow us to
    # use the other logic.  This should be copied and pasted to make
    # it work.  This is an example for Purple Robot.
    #def do_queryset_iteration(self, queryset, sizes, counts, total_days):
    #    for ts, data in queryset:
    #        data = loads(data)
    #        for probe in data:
    #            if total_days is None:
    #                total_days = self.figure_total_days(ts)
    #            # Actual body:
    #            sizes[probe['PROBE']] += len(dumps(probe))
    #            counts[probe['PROBE']] += 1
    #    return total_days
    # This method is used by each iterator, does not need to be changed.
    def figure_total_days(self, ts):
        # Figure out the total days.  If we are in django,
        # this is an aware datetime.  Otherwise, it is
        # _probably_ a naive one, which we assume to be
        # UTC.  This hackish stuff also allows us to not
        # depend on django.  TODO: improve this.
        try:
            total_days = (datetime.utcfromtimestamp(mod_time.time())-ts).total_seconds() / (3600*24)
        except TypeError:
            from django.utils import timezone
            now = timezone.now()
            total_days = (now-ts).total_seconds() / (3600*24)
        return total_days
class BaseDataCounts(_Converter):
    per_page = None
    header = ['']
    desc = "Data points per day, for the last 7 days (slow calculation)"
    days_ago = 7
    midnight_offset = 3600*4  # Seconds after midnight at which to start the new day.
    @classmethod
    def query(cls, queryset):
        """Do necessary filtering on the django QuerySet.

        In this case, restrict to the last N days."""
        # This method depends on django, but that is OK since it used
        # Queryset semantics, which itself depend on django.  This
        # method only makes sent to call in the server itself.
        from django.utils import timezone
        now = timezone.now()
        return queryset.filter(ts__gt=now-timedelta(days=cls.days_ago))
    def __init__(self, *args, **kwargs):
        super(BaseDataCounts, self).__init__(*args, **kwargs)
        self.counts = collections.defaultdict(int)
    def convert(self, rows, time=lambda x:x):
        import pytz
        from django.conf import settings
        TZ = pytz.timezone(settings.TIME_ZONE)
        #import IPython ; IPython.embed()

        counts = self.counts
        midnight_offset = self.midnight_offset
        # Operating like PRMissingData
        for ts in self.timestamp_converter(rows).run():
            ts = ts[0]
            if ts < 100000000: continue  # skip bad timestamps
            ts = datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.utc)
            #ts = TZ.normalize(ts.astimezone(TZ))
            ts = TZ.normalize(ts-midnight_offset)
            date = ts.strftime('%Y-%m-%d')
            counts[date] += 1

        all_dates = self.dates()
        day_counts = tuple( counts[date] for date in all_dates )
        day_counts = tuple( (x if x else '_') for x in day_counts )

        yield day_counts
        del self.counts, counts
    @classmethod
    def dates(cls):
        """List of dates we are analyzing"""
        from django.utils import timezone
        now = timezone.now()
        dates = [ (now-timedelta(days=x)).strftime('%Y-%m-%d') for x in range(cls.days_ago-1, -1, -1)]
        return dates
    @classmethod
    def header2(cls):
        return cls.dates()

from django.utils.html import escape
from django.utils.safestring import mark_safe
class JsonPrettyHtml(_Converter):
    """Encode each data packet as pretty JSON

    This consideres HTML-escaping and can decode certain keys which
    contain JSON as strings.
    """
    desc = "Pretty-print JSON for web pages"
    header = ['packet_time', 'json']
    json_keys = [ ]
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            try:
                data = loads(data)
                for key in self.json_keys:
                    if not key in data: pass
                    data[key+'[jsondecoded]'] = loads(data[key])
                    del data[key]
                data = json.dumps(data, sort_keys=True, indent=1, separators=(',',': '))
                data = mark_safe('<pre>'+escape(data)+'</pre>')
            except:
                # If any errors, use regular data.  This is *not*
                # escaped, but also not marked as escaped.
                pass
            yield (time(timegm(ts.utctimetuple())),
                   data,
                  )
class JsonPrettyHtmlData(JsonPrettyHtml):
    desc = "Pretty-print JSON for web pages (including data key)"
    header = ['packet_time', 'json']
    json_keys = ['data']





class MurataBSN(_Converter):
    _header = ['time',
              'hr', 'rr', 'sv', 'hrv', 'ss',
              'status', 'bbt0', 'bbt1', 'bbt2',
              'time2',
             ]
    _header_debug = ['row_i', 'delta_i', 'time_packet', 'offset_s',
                     'xml_start_time',]
    device_class = 'MurataBSN'
    @classmethod
    def header2(cls):
        if cls.debug:
            return cls._header + cls._header_debug
        return cls._header
    desc = "Murata sleep sensors, basic information."
    debug = False
    safe = False
    def convert(self, rows, time=lambda x:x):
        from defusedxml.ElementTree import fromstring as xml_fromstring
        from dateutil import parser as date_parser
        count = 0
        for ts_packet, data in rows:
            if not data.startswith('<'):
                continue
            unixtime_packet = timegm(ts_packet.timetuple())
            # Do various XML parsing
            doc = xml_fromstring(data)
            node = doc[0][0]
            device_id = node.attrib['id']
            start_time = doc[0][0][0][0].attrib['time']
            ts = date_parser.parse(start_time)
            values = doc[0][0][0][0][9]
            # This is O(n_rows) in memory here.  n_rows is supposed to
            # be always small (~90 max).  Should this assumption be
            # violated, we need a two-pass method.  Just save
            # last_row_i on the first pass, then do second pass.
            rows = [ ]
            reader = csv.reader(values.text.split('\n'))
            for row in reader:
                if not row: continue
                rows.append(row)
            last_time_i = int(rows[-1][0])
            for row in rows:
                #count += 1 ; print count
                unixtime = timegm(ts.timetuple()) + int(row[0])
                # The actual data.  In safe mode, replace everything
                # with null strings.
                data_values = tuple(row[1:])
                if self.safe:
                    data_values = tuple( "" for _ in data_values )
                # These values are used for debuging.  In debug mode,
                # include a bunch of extra data.  In normal mode,
                # include the field time2, which is the time as
                # calcultaed from the packet.
                unixtime_from_packet = unixtime_packet - ( last_time_i - int(row[0]))
                if not self.debug:
                    extra_data = (time(unixtime_from_packet), )
                else:
                    extra_data = (
                        time(unixtime_from_packet),
                        int(row[0]),
                        last_time_i - int(row[0]),
                        time(unixtime_packet),
                        unixtime_from_packet-unixtime,
                        start_time,
                    )
                # Compose and return columns
                yield (time(unixtime), ) + data_values + extra_data
class MurataBSNDebug(MurataBSN):
    desc = "Murata sleep sensors with extra debugging info."
    debug = True
class MurataBSNSafe(MurataBSN):
    desc = "Murata sleep sensors with debugging info and data removed."
    safe = True
    debug = True



class PRProbes(_Converter):
    header = ['time', 'packet_time', 'probe', 'data']
    desc = "Raw JSON data, divided into each probe"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                yield (time(probe['TIMESTAMP']),
                       time(timegm(ts.utctimetuple())),
                       probe['PROBE'].split('.')[-1],
                       dumps(probe))

class PRBattery(_Converter):
    header = ['time', 'level', 'plugged']
    desc = "Battery level"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.BatteryProbe':
                    yield (time(probe['TIMESTAMP']),
                           int(probe['level']),
                           int(probe['plugged']),
                          )
class PRScreen(_Converter):
    header = ['time', 'onoff']
    desc = "Screen on/off times"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.ScreenProbe':
                    yield (time(probe['TIMESTAMP']),
                           int(probe['SCREEN_ACTIVE']),
                          )
class PRWifi(_Converter):
    """WifiAccessPointsProbe converter.

    This is a bit complex because we handle several cases (and handle
    them twice).
    - Current network is handled differently from the list of all
      networks.
    - hash if the class attribute "safe" is set.
    """
    header = ['time', 'essid', 'bssid', 'current', 'strength']
    desc = "Wifi networks found"
    device_class = 'PurpleRobot'
    safe = False
    def convert(self, queryset, time=lambda x:x):
        safe = self.safe
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.WifiAccessPointsProbe':
                    ts = time(probe['TIMESTAMP'])
                    # Emit a special row for CURRENT_SSID
                    if 'CURRENT_BSSID' in probe \
                       and probe['CURRENT_BSSID'] != '00:00:00:00:00:00':
                        current_ssid = probe['CURRENT_SSID']
                        # On some devices the current SSID is quoted.
                        # Json decode it in that case.
                        if current_ssid.startswith('"'):
                            current_ssid = loads(current_ssid)
                        # Handle hashing if we are in safe mode.  In
                        # safe mode, hash the things, but *only* if it
                        # is non-null.  So, this is actually two
                        # levels of conditional.
                        if safe:
                            current_ssid = (safe_hash(current_ssid)
                                            if current_ssid else current_ssid)
                            current_bssid = (safe_hash(probe['CURRENT_BSSID'])
                                             if safe else probe['CURRENT_BSSID'])
                        yield (ts,
                               current_ssid,
                               current_bssid,
                               1,
                               probe['CURRENT_RSSI'],
                           )
                    for ap_info in probe['ACCESS_POINTS']:
                        # Again, two layers of conditionals because we
                        # only hash if non-null.
                        ssid = ap_info['SSID']
                        bssid = ap_info['BSSID']
                        if safe:
                            ssid  = safe_hash(ssid)  if ssid else ssid
                            bssid = safe_hash(bssid) if bssid else bssid
                        yield (ts,
                               ssid,
                               bssid,
                               0,
                               ap_info['LEVEL'],
                               )
class PRWifiSafe(PRWifi):
    safe = True
class PRBluetooth(_Converter):
    header = ['time',
              'bluetooth_name',
              'bluetooth_address',
              'major_class',
              'minor_class',
              ]
    desc = "Bluetooth devices found"
    device_class = 'PurpleRobot'
    safe = False
    def convert(self, queryset, time=lambda x:x):
        safe = self.safe
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.BluetoothDevicesProbe':
                    ts = time(probe['TIMESTAMP'])
                    for dev_info in probe['DEVICES']:
                        # available keys:
                        # {"BLUETOOTH_NAME":"2a1327a019948590cccc3ff20fe3dbdb",
                        #  "BOND_STATE":"Not Paired",
                        #  "DEVICE MAJOR CLASS":"0x00000100 Computer",
                        #  "BLUETOOTH_ADDRESS":"6841398ddc6f2cee644a3bcf39b894d2",
                        #  "DEVICE MINOR CLASS":"0x0000010c Laptop"}
                        name = dev_info.get('BLUETOOTH_NAME', '')
                        address = dev_info.get('BLUETOOTH_ADDRESS', '')
                        if safe:
                            name = safe_hash(name)
                            address = safe_hash(address)
                        yield (ts,
                               name,
                               address,
                               dev_info.get('DEVICE MAJOR CLASS',''),
                               dev_info.get('DEVICE MINOR CLASS',''),
                               )
class PRBluetoothSafe(PRBluetooth):
    safe = True
class PRStepCounter(_Converter):
    header = ['time', 'step_count', 'last_boot']
    desc = "Step counter"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        last_boot = 0
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.RobotHealthProbe':
                    last_boot = probe['LAST_BOOT']/1000
                    yield (time(probe['TIMESTAMP']), '', time(last_boot))
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.StepCounterProbe':
                    yield (time(probe['TIMESTAMP']+last_boot),
                           probe['STEP_COUNT'],
                           )
class PRDeviceInUse(_Converter):
    header = ['time', 'in_use']
    desc = "Purple Robot DeviceInUseFeature"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.features.DeviceInUseFeature':
                    yield (time(probe['TIMESTAMP']),
                           int(probe['DEVICE_ACTIVE']))
class PRLocation(_Converter):
    desc = 'Purple Robot location probe (builtin.LocationProbe)'
    header = ['time', 'provider', 'lat', 'lon', 'accuracy']
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.LocationProbe':
                    yield (time(probe['TIMESTAMP']),
                           probe['PROVIDER'],
                           probe['LATITUDE'],
                           probe['LONGITUDE'],
                           probe['ACCURACY'],
                           )
class PRAccelerometer(_Converter):
    desc = 'Purple Robot Accelerometer (builtin.AccelerometerProbe).  Some metadata is not yet included here.'
    header = ['event_timestamp', 'normalized_timestamp', 'x', 'y', 'z', 'accuracy']
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.AccelerometerProbe':
                    #yield probe['MAXIMUM_RANGE']
                    #probe['RESOLUTION']
                    for t1, t2, x, y, z, a in zip(probe['EVENT_TIMESTAMP'],
                                                  probe['NORMALIZED_TIMESTAMP'],
                                                  probe['X'],
                                                  probe['Y'],
                                                  probe['Z'],
                                                  probe['ACCURACY'],
                                              ):
                        yield time(t1), time(t2), x, y, z, a
class PRLightProbe(_Converter):
    desc = 'Purple Robot Light Probe (builtin.LightProbe).  Some metadata is not yet included here.'
    header = ['event_timestamp', 'lux', 'accuracy']
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.LightProbe':
                    for t, l, a in zip(probe['EVENT_TIMESTAMP'],
                                       probe['LUX'],
                                       probe['ACCURACY'],
                                       ):
                        yield time(t), l, a


class PRTimestamps(_Converter):
    desc = 'All actual data timestamps of all PR probes'
    header = ['time',
              'packet_time',
              'probe',]
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                yield (time(probe['TIMESTAMP']),
                       time(timegm(ts.utctimetuple())),
                       probe['PROBE'].rsplit('.',1)[-1])
class PRRunningSoftware(_Converter):
    header = ['time', 'package_name', 'task_stack_index', 'package_category', ]
    desc = "All software currently running"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.RunningSoftwareProbe':
                    probe_ts = time(probe['TIMESTAMP'])
                    for software in probe['RUNNING_TASKS']:
                        yield (probe_ts,
                               software['PACKAGE_NAME'],
                               software['TASK_STACK_INDEX'],
                               software['PACKAGE_CATEGORY'],
                              )
class PRSoftwareInformation(_Converter):
    header = ['time',
              'package_name',
              'app_name',
              'package_version_name',
              'package_version_code',]
    desc = "All software installed"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.SoftwareInformationProbe':
                    probe_ts = time(probe['TIMESTAMP'])
                    for software in probe['INSTALLED_APPS']:
                        yield (probe_ts,
                               software['PACKAGE_NAME'],
                               software['APP_NAME'],
                               software.get('PACKAGE_VERSION_NAME'),
                               software['PACKAGE_VERSION_CODE'],
                              )
class PRCallHistoryFeature(_Converter):
    header = ['time', 'window_index',
              'window_size', 'total', 'new_count', 'min_duration',
              'max_duration', 'avg_duration', 'total_duration',
              'std_deviation', 'incoming_count', 'outgoing_count',
              'incoming_ratio', 'ack_ratio', 'ack_count', 'stranger_count',
              'acquiantance_count', 'acquaintance_ratio', ]
    desc = "Aggregated call info"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.features.CallHistoryFeature':
                    ts = time(probe['TIMESTAMP'])
                    for i, window in enumerate(probe['WINDOWS']):
                        yield (ts,
                               i,
                               window['WINDOW_SIZE'],
                               window['TOTAL'],
                               window['NEW_COUNT'],
                               window['MIN_DURATION'],
                               window['MAX_DURATION'],
                               window['AVG_DURATION'],
                               window['TOTAL_DURATION'],
                               window['STD_DEVIATION'],
                               window['INCOMING_COUNT'],
                               window['OUTGOING_COUNT'],
                               window['INCOMING_RATIO'],
                               window['ACK_RATIO'],
                               window['ACK_COUNT'],
                               window['STRANGER_COUNT'],
                               window['ACQUIANTANCE_COUNT'],
                               window['ACQUAINTANCE_RATIO'],
                              )
class PRSunriseSunsetFeature(_Converter):
    header = ['time', 'is_day', 'sunrise', 'sunset', 'day_duration']
    desc = "Sunrise and sunset info at current location"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.features.SunriseSunsetFeature':
                    yield (time(probe['TIMESTAMP']),
                           probe['IS_DAY'],
                           time(probe['SUNRISE']/1000.),
                           time(probe['SUNSET']/1000.),
                           probe['DAY_DURATION']/1000.,
                    )
class PRCommunicationEventProbe(_Converter):
    desc = 'Purple Robot Communication Event Probe'
    header = ['time',
              'communication_type',
              'communication_direction',
              'number',
              'duration']
    desc = "Communication Event Probe"
    device_class = 'PurpleRobot'
    no_number = False
    def convert(self, queryset, time=lambda x:x):
        no_number = self.no_number
        for ts, data in queryset:
            if 'CommunicationEventProbe' not in data:
                continue
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.CommunicationEventProbe':
                    duration = probe.get('DURATION', 0)
                    yield (time(probe['COMM_TIMESTAMP']/1000.),
                           probe['COMMUNICATION_DIRECTION'],
                           probe['COMMUNICATION_TYPE'],
                           '' if no_number else safe_hash(probe['NORMALIZED_HASH']),
                           duration,
                    )
class PRCommunicationEventProbeNoNumber(PRCommunicationEventProbe):
    no_number = True

import requests
class PRApplicationLaunchesSafe(_Converter):
    """ApplicationLaunchEvents - only top apps, others hashed."""
    header = ['time', 'current_app_pkg']
    desc = "ApplicationLaunchProbe, when software is started"
    device_class = 'PurpleRobot'
    def convert(self, queryset, time=lambda x:x):
        # TODO: make this configurable
        link = "https://koota.cs.aalto.fi/static/softinfo.txt"
        f = requests.get(link).text
        AppList = f.split('\n')
        AppList = [k.split(',')[0] for k in AppList]
        AppList = set(AppList)

        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.ApplicationLaunchProbe':
                    if probe['CURRENT_APP_PKG'] not in AppList:
                        #print(time(probe['TIMESTAMP']),
                        #   safe_hash(probe['CURRENT_APP_PKG']))
                        yield (time(probe['TIMESTAMP']),
                           safe_hash(probe['CURRENT_APP_PKG']))
                    else:
                        #print(time(probe['TIMESTAMP']),
                        #   probe['CURRENT_APP_PKG'])
                        yield (time(probe['TIMESTAMP']),
                            probe['CURRENT_APP_PKG'])




#
# Daily aggregations
#
class DayAggregator(_Converter):
    """Base class for performing server-side aggregation by day.

    This basically provides an on-line sort (actually aggregation)
    that tries to group data by some timestamp key.  Because we can't
    store too much in memory at once, we have to use various
    heurestics and it *will* fail in some cases.  Continued
    development will be needed.

    API:
    - iterates through queryset
    - self.iter_rows(packet_ts, packet_data):
      iterate all of the (ts, ts_bin, row_data) which should be aggregated.
    - self.ts_func(row): -> ts
    - self.process(first_ts, bin_key, all_probe_rows):
      Take (ts_bin, bin_rows), yield things to return.

    Deprecated:
    - self.filter_func(queryset_row)
    - self.filter_func_row(probe_row)
    - self.ts_bin_func(ts) -> bin_key (like (YYYY,MM,DD))
    """
    paging_disabled = True  # Used in HTML browsing
    # Convert timestamp(unixtime) to a tuple used for binning
    ts_bin_func = staticmethod(lambda ts: localtime(ts)[:3]) #Y-M-D.  FIXME: timezone
    # Packet filtering func: should each row be used?
    filter_func = staticmethod(lambda data: True)
    # This is subtracted from timestamp when binning.
    midnight_offset = 3600*4  # four hours after midnight, by default.
    def __init__(self, *args, **kwargs):
        super(DayAggregator, self).__init__(*args, **kwargs)
        self.day_dict = collections.defaultdict(list)
        self.current_day = None
        self.current_day_ts = None
        self.current_i = 0

    def iter_row(self, packet_ts, data):
        """"""
        # This is set up for PR right now.
        if not self.filter_func(data): return
        # Load the row and iterate through all the data within it.
        data = loads(data)
        for probe in data:
            if not self.filter_row_func(probe): continue
            ts = self.ts_func(probe)
            if ts is None: print(probe)
            yield ts, self.ts_bin_func(ts), probe

    def convert(self, queryset, time=lambda x:x):
        day_dict = self.day_dict
        current_day = self.current_day
        current_day_ts = self.current_day_ts
        current_i = self.current_i
        midnight_offset = self.midnight_offset
        # Iterate through all the queryset
        for packet_ts, data in queryset:
            ## Allow filter_func to exclude data right away.
            #if not self.filter_func(data): continue
            ## Load the row and iterate through all the data within it.
            #data = loads(data)
            #for probe in data:
            for ts, day, probe in self.iter_row(packet_ts, data):
                    current_i += 1
                    # Setup in the first loop round.
                    if current_day is None:
                        current_day = day
                        current_day_ts = ts
                    # If we have iterated far enough in the future,
                    # then we assume that we have all data from the
                    # current day.  Yield this.
                    if ts > current_day_ts + 172800: # two days
                        done_day_bin = min(day_dict)
                        done_day_data = day_dict.pop(done_day_bin)
                        for row in self.process(done_day_bin,
                                                done_day_data):
                            yield row
                        if day_dict:
                            # we have new data
                            current_day = self.current_day = min(day_dict)
                            current_day_ts = self.current_day_ts \
                                             = self.ts_func(day_dict[current_day][0])
                        else:
                            current_day = day
                            current_day_ts = ts
                        self.current_i = current_i
                    # Some detection for going backwards.
                    #if ts + 3600 < current_day_ts:
                    #    # This is supposed to be some safety against
                    #    # going backwards too much and ending up using
                    #    # too much memory.  But I think it is not
                    #    # necessary.  In the event that this is not
                    #    # too needed anymore.
                    #    #print("backwards in time:", ts, current_day_ts)
                    #    continue
                    # Save this data in the respective list.
                    day_dict[day].append(probe)
        # finalize by yielding all remaining days.
        while day_dict:
            done_day_bin = min(day_dict)
            done_day_data = day_dict.pop(done_day_bin)
            for row in self.process(done_day_bin, done_day_data):
                yield row
    def process(timestamp, day_tuple, data):
        """Do the processing:

        timestamp is the unixtime timestamp of the first data point.
        day_tuple is the (Y,M,D) tuple or whatever is used for the binning function.
        data is the list of all data rows that have been appended to this time bin.
        """
        raise NotImplementedError("Abstract method")
class PRDayAggregator(DayAggregator):
    device_class = 'PurpleRobot'
    # Extract timestamp (unixtime) from a row
    ts_func = staticmethod(lambda probe: probe['TIMESTAMP'])
    # Should each row within a packet be used?
    # Following must be copied in each subclass (and remove self.)
    filter_row_func = staticmethod(lambda row: row['PROBE'] == self.probe_type)
class IosDay(PRDayAggregator):
    """Day aggregator extended to koota's iOS app."""
    device_class = 'Ios'
    ts_func = staticmethod(lambda probe: probe['timestamp'])
    filter_func = staticmethod(lambda data: True)
    filter_row_func = staticmethod(lambda row: 'probe' not in row)

class AwareDayAggregator(PRDayAggregator):
    """Base class for Aware aggregation"""
    ts_func = staticmethod(lambda probe: probe['timestamp'])
    # Should each row within a packet be used?
    # Following must be copied in each subclass (and remove self.)
    filter_row_func = staticmethod(lambda row: row['table'] == self.probe_type)
    #probe_type = 'locations' # to be filled in
    def iter_row(self, packet_ts, data):
        data = loads(data)
        if data['table'] != self.probe_type: return
        data2 = loads(data['data'])
        for row in data2:
            ts = row['timestamp']/1000
            yield ts, self.ts_bin_func(ts), row


class PRBatteryDay(PRDayAggregator):
    header = ['day', 'mean_level', ]
    probe_type = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.BatteryProbe'
    desc = "PR battery, daily averages (has error)."
    filter_func = staticmethod(lambda data: 'BatteryProbe' in data)
    filter_row_func = staticmethod(lambda row: row['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.BatteryProbe')
    def process(self, day, probes):
        levels = [ probe['level'] for probe in probes ]
        yield ('%04d-%02d-%02d'%day,
               sum(levels)/len(levels),
        )
class PRCommunicationEventsDay(PRDayAggregator):
    header = ['day', 'n_events', 'n_phone', 'n_sms',
              'n_incoming', 'n_outgoing', 'n_missed',
              'tot_duration', 'min_duration', 'max_duration', 'mean_duration',
              'std_pop_duration',
    ]
    probe_type = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.CommunicationEventProbe'
    desc = "PR commsunication events, aggregate information"
    ts_func = staticmethod(lambda probe: probe['COMM_TIMESTAMP']//1000)
    filter_func = staticmethod(lambda data: 'CommunicationEventProbe' in data)
    filter_row_func = staticmethod(lambda row: row['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.CommunicationEventProbe')
    def process(self, day, probes):
        #for p in probes:
        #    print(p)
        phone_events = [ p for p in probes if p['COMMUNICATION_TYPE']=='PHONE' ]
        sms_events   = [ p for p in probes if p['COMMUNICATION_TYPE']=='SMS' ]
        n_events   = len(probes)
        n_phone    = len(phone_events)
        n_sms      = len(sms_events)
        n_incoming = sum(1 for p in probes if p['COMMUNICATION_DIRECTION']=='INCOMING')
        n_outgoing = sum(1 for p in probes if p['COMMUNICATION_DIRECTION']=='OUTGOING')
        n_missed   = sum(1 for p in probes if p['COMMUNICATION_DIRECTION']=='MISSED')
        tot_duration = sum(p['DURATION'] for p in phone_events)
        if n_phone:
            min_duration = min(p['DURATION'] for p in phone_events)
            max_duration = max(p['DURATION'] for p in phone_events)
            mean_duration = tot_duration/n_phone
        else:
            min_duration = 0
            max_duration = 0
            mean_duration = 0
        var_duration = sum((p['DURATION']-mean_duration)**2 for p in phone_events)
        std_pop_duration = sqrt(var_duration)
        yield ('%04d-%02d-%02d'%day,
               n_events, n_phone, n_sms,
               n_incoming, n_outgoing, n_missed,
               tot_duration, min_duration, max_duration, mean_duration,
               std_pop_duration,
        )

import numpy as np
from geopy.distance import vincenty
#from scipy.cluster.vq import kmeans, vq
class LocationDayAggregator(DayAggregator):
    """Daily movement information.

    This was contributed by students.  For details, you must see code

    - Day
    - Location standard deviation (meters)
    - Number of clusters (using kmeans)
    - Entropy of cluster diversity (-p ln p, p=fraction of time in each cluster)
    - Normalized entropy = entropy / log(num_clusters)
    - transition time between clusters
    - total distance traveled
    """
    header = ['day', 'locstd',
              'numclust', 'entropy', 'normentropy',
              'transtime', 'totdist']
    def process(self, day, probes):
        time_step = 600 # seconds, size of data bins
        speed_th = 0.28 # m/s, moving threshold
        max_dist = 500 # m, maximum radius of cluster
        lat, lon, times = self.get_lat_lon_times(probes)
        time_bins = range(int(min(times)), int(max(times)) + time_step, time_step)
        lat_binned = []
        lon_binned = []
        dists = []

        # bin data
        for i in range(0, len(time_bins)-1):
#            useInd = mlab.find([time >= time_bins[i] and time < time_bins[i + 1] for time in times])
            useInd = np.where([time >= time_bins[i] and time < time_bins[i + 1] for time in times])[0]
            if len(useInd) > 0:
                lat_binned.append(np.mean([lat[j] for j in useInd]))
                lon_binned.append(np.mean([lon[j] for j in useInd]))
            else:
                lat_binned.append(np.nan)
                lon_binned.append(np.nan)

        # calculate distances between coordinates
        for i in range(0, len(lon_binned) - 1):
            if not any(np.isnan([lon_binned[i], lat_binned[i], lon_binned[i + 1], lat_binned[i + 1]])):
                dists.append(vincenty((lat_binned[i], lon_binned[i]), (lat_binned[i + 1], lon_binned[i + 1])).meters)
            else:
                dists.append(np.nan)

        # calculate speeds and categorize points
        speeds = [dist / time_step for dist in dists]
        #is_stationary = mlab.find([speed < speed_th for speed in speeds])
        #is_moving = mlab.find([speed >= speed_th for speed in speeds])
        is_stationary = np.where([speed < speed_th for speed in speeds])[0]
        is_moving = np.where([speed >= speed_th for speed in speeds])[0]
        stat_lat = [lat_binned[j] for j in is_stationary]
        stat_lon = [lon_binned[j] for j in is_stationary]
        if len(is_stationary) > 0:
            mean_lat = np.mean([lat_binned[j] for j in is_stationary])
            LAT_SCALAR = np.cos(np.pi*mean_lat/180)
        else:
            LAT_SCALAR = 0

        # location variance
        loc_std = None  # default if can't compute
        if len(stat_lon) > 0:
            loc_std = EARTH_RADIUS * sqrt(np.var(stat_lat)*LAT_SCALAR**2 + np.var(stat_lon))*pi/180

        # total distance
        total_distance = np.nansum(dists)

        # transition time
        transition_time = 0.0  # default if no data
        if len(is_stationary) + len(is_moving) > 0:
            transition_time = len(is_moving) / float(len(is_stationary) + len(is_moving))

        # number of clusters
        if len(stat_lat) > 0:
            kmeans_dists = [max_dist + 1] # dummy to enter while loop
            k = 0
            while any([x > max_dist for x in kmeans_dists]):
                k += 1
                stat_data = np.transpose(np.array([stat_lat, stat_lon]))
                stat_data *= [LAT_SCALAR, 1]
                [kmeans_cat, kmeans_dists] = kmeans_haversine(stat_data, k,iter=10)
                # prevent infinite loop (shouldn't happen anyway)
                if k > 20:
                    break
            # entropy
            entropy = 0.
            for i in range(0, k):
                cur_inds = np.where([c == i for c in kmeans_cat])[0]
                p = np.double(len(cur_inds)) / np.double(len(stat_lat))
                if p != 0:
                    entropy -= p * np.log(p)

            # normalized entropy
            if k != 1:
                norm_entropy = entropy / np.log(np.double(k))
            else:
                norm_entropy = 0.
        else:
            # No centroids so can't compute these things
            k = 0
            entropy = 0
            norm_entropy = 0

        #if loc_std is not None and loc_std > 30000:
        #    print(day)
        #    print(round(np.mean(stat_lat),4), round(np.std(stat_lat)*EARTH_RADIUS*LAT_SCALAR*pi/180,4))#, stat_lat)
        #    print(round(np.mean(stat_lon),4), round(np.std(stat_lon)*EARTH_RADIUS*pi/180,4))#, stat_lon)
        #    print(stat_lat)
        #    print(stat_lon)
        yield ('%04d-%02d-%02d'%day,
               loc_std,
               k,
               entropy,
               norm_entropy,
               transition_time,
               total_distance
                )
class PRLocationDay(PRDayAggregator, LocationDayAggregator):
    probe_type = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.LocationProbe'
    desc = "PRLocation, daily features"
    filter_func = staticmethod(lambda data: 'LocationProbe' in data)
    filter_row_func = staticmethod(lambda row: row['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.LocationProbe')
    fast_row_limit = 5
    def get_lat_lon_times(self, probes):
        lat = [ probe['LATITUDE'] for probe in probes ]
        lon = [ probe['LONGITUDE'] for probe in probes ]
        times = [ probe['TIMESTAMP'] for probe in probes ]
        return lat, lon, times
class IosLocationDay(IosDay, PRLocationDay):
    def get_lat_lon_times(self, probes):
        lat = [ probe['lat'] for probe in probes ]
        lon = [ probe['lon'] for probe in probes ]
        times = [ probe['timestamp'] for probe in probes ]
        return lat, lon, times
class AwareLocationDay(AwareDayAggregator, LocationDayAggregator):
    def iter_row(self, packet_ts, data):
        data = loads(data)
        if data['table'] != 'locations': return
        #print(data)
        data2 = loads(data['data'])
        for row in data2:
            ts = row['timestamp']/1000
            yield ts, self.ts_bin_func(ts), row
    def get_lat_lon_times(self, probes):
        lat = [ probe['double_latitude'] for probe in probes if probe.get('label')!='disabled' ]
        lon = [ probe['double_longitude'] for probe in probes if probe.get('label')!='disabled' ]
        times = [ probe['timestamp']/1000 for probe in probes if probe.get('label')!='disabled' ]
        return lat, lon, times
# Second implemation of DayConverter - including k-means
def kmeans_haversine(data, k, iter=20, thresh=1e-05):
    """Run k-means on a geographic coordinate system.

    For PRLocationDay.
    """
    # k-means algorithm using the Haversine distance
    obs_len = len(data)
    cat_collection = []
    dists_collection = []
    errors = []

    # no need to run many times if only one cluster
    if k == 1:
        iter = 1

    for j in range(0, iter):
        # random initial centroids
        centroids = data[np.random.permutation(obs_len)[0:k]]
        old_centroids = np.copy(centroids)
        old_centroids[0][0] -= thresh * 10 # fix to enter while loop
        while (np.sum(abs(old_centroids[old_centroids[:,0].argsort()] - centroids[centroids[:,0].argsort()])) > thresh): # arrays are sorted to be able to make a comparison
            cat = np.zeros(obs_len)
            dists = np.zeros(obs_len)
            # calculate distances
            for i in range(0, obs_len):
                dist = [haversine(data[i], x) for x in centroids]
                cat[i] = np.argmin(dist)
                dists[i] = np.min(dist)
            old_centroids = np.copy(centroids)
            # recalculate centroids
            for i in range(0, k):
                use_inds = np.where(cat == i)[0]
                if len(use_inds) > 0:
                    centroids[i] = np.mean(data[use_inds], axis=0)
        dists_collection.append(dists)
        cat_collection.append(cat)
        errors.append(np.sum(dists))

    # choose best result
    best_ind = np.argmin(errors)
    return cat_collection[best_ind], dists_collection[best_ind]
#from math import asin as arcsin, pi, pow as power, sin, cos
EARTH_RADIUS = 6371010.
def haversine(point1, point2):
    """Haversine spherical coordinate distance.  For PRLocationDay."""
    # Calculates the distance between two pairs of latitude-longitude coordinates using the Haversine formula
    lat1 = point1[0] / 180. * np.pi
    lat2 = point2[0] / 180. * np.pi
    lon1 = point1[1] / 180. * np.pi
    lon2 = point2[1] / 180. * np.pi
    return 2. * EARTH_RADIUS * np.arcsin(np.sqrt(np.power(np.sin((lat2-lat1)/2.),2)+np.cos(lat1)*np.cos(lat2)*np.power(np.sin((lon2-lon1)/2.),2)))




#
# Generic probes
#
class _PRGeneric(_Converter):
    """Generic simple probe

    This is an abstract base class for converting any probe into one row.

    Required attribute: 'field', which is tuples of (field_name,
    PROBE_FIELD).  The first is the output field name, the second is
    what is found in the probe object.  If length second is missing,
    use the first for both.
    """
    device_class = 'PurpleRobot'
    @classmethod
    #fields = ['X_MIN', 'X_MAX']
    def convert(self, queryset, time=lambda x:x):
        """Iterate through all data, extract the probes, take the probes we
        want, then yield timestamp+the requested fields.
        """
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == self.probe_name:
                    yield (time(probe['TIMESTAMP']), ) + \
                         tuple(probe[x[-1]] for x in self.fields)
class _PRGenericArray(_Converter):
    """Generic simple probe

    This is an abstract base class for converting any probe into one row.

    Required attribute: 'field', which is tuples of (field_name,
    PROBE_FIELD).  The first is the output field name, the second is
    what is found in the probe object.  If length second is missing,
    use the first for both.
    """
    device_class = 'PurpleRobot'
    @classmethod
    def header2(cls):
        """Return header, either dynamic or static."""
        if hasattr(cls, 'header') and cls.header:
            return cls.header
        return ['time', 'probe_time'] + [x[0].lower() for x in cls.fields] + [x[0].lower() for x in cls.fields_array]
    @classmethod
    def convert(self, queryset, time=lambda x:x):
        """Iterate through all data, extract the probes, take the probes we
        want, then yield timestamp+the requested fields.
        """
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == self.probe_name:
                    row_common = tuple(probe[f[-1]] for f in self.fields)
                    for row in zip(probe[self.ts_field], *(probe[f[-1]] for f in self.fields_array )):
                        ts_event = row[0]
                        yield (time(ts_event),
                               time(probe['TIMESTAMP'])) \
                              + row_common \
                              + row[1:]


class PRAccelerometerBasicStatistics(_PRGeneric):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.features.AccelerometerBasicStatisticsFeature'
    desc = "Purple Robot features.AccelerometerBasicStatisticsFeature"
    fields = [
        ('X_MIN', ),
        ('X_MEAN', ),
        ('X_MAX', ),
        ('X_STD_DEV', ),
        ('X_RMS', ),
        ('Y_MIN', ),
        ('Y_MEAN', ),
        ('Y_MAX', ),
        ('Y_STD_DEV', ),
        ('Y_RMS', ),
        ('Z_MIN', ),
        ('Z_MEAN', ),
        ('Z_MAX', ),
        ('Z_STD_DEV', ),
        ('Z_RMS', ),
        ('DURATION', ),
        ('BUFFER_SIZE', ),
        ('FREQUENCY', ),
        ]
class PRAccelerometerFrequency(_PRGeneric):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.features.AccelerometerFrequencyFeature'
    desc = "Purple Robot features.AccelerometerFrequencyFeature"
    fields = [
        ('WINDOW_TIMESTAMP', ),
        ('POWER_X', ),
        ('FREQ_X', ),
        ('POWER_Y', ),
        ('FREQ_Y', ),
        ('POWER_Z', ),
        ('FREQ_Z', ),
        ]
class PRApplicationLaunches(_PRGeneric):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.ApplicationLaunchProbe'
    desc = "ApplicationLaunchProbe, when software is started"
    fields = [
        ('CURRENT_APP_PKG', ),
        ('CURRENT_APP_NAME', ),
        # These can always be found by looking at previous row, and
        # are missing in the first row.
        #('PREVIOUS_APP_PKG', ),
        #('PREVIOUS_APP_NAME', ),
        #('PREVIOUS_TIMESTAMP', ),
        ]
class PRAudioFeatures(_PRGeneric):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.AudioFeaturesProbe'
    desc = "Audio Features Probe - some signal information on audio"
    fields = [
        ('FREQUENCY', ),
        ('NORMALIZED_AVG_MAGNITUDE', ),
        ('POWER', ),
        ('SAMPLE_BUFFER_SIZE', ),
        ('SAMPLE_RATE', ),
        ('SAMPLES_RECORDED', ),
        ]
class PRCallState(_PRGeneric):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.CallStateProbe'
    desc = "Call state (idle/active)"
    fields = [
        ('CALL_STATE', ),
        ]
class PRTouchEvents(_PRGeneric):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.TouchEventsProbe'
    desc = "Touch events, number of"
    fields = [
        ('TOUCH_COUNT', ),
        ('LAST_TOUCH_DELAY', ),
        ]
class PRProximity(_PRGenericArray):
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.ProximityProbe'
    desc = "Proximity probe"
    ts_field = 'EVENT_TIMESTAMP'
    fields = [ ]
    fields_array = [('ACCURACY',),
                    ('DISTANCE',), ]



class PRDataSize(BaseDataSize):
    device_class = 'PurpleRobot'
    per_page = None
    def do_queryset_iteration(self, queryset, sizes, counts, total_days):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                #if probe['TIMESTAMP'] < start_time:
                #    # TODO: some probes may have wrong timestamps
                #    # (like StepCounterProbe) which makes this
                #    # comparison wrong.
                #    continue
                if total_days is None:
                    total_days = self.figure_total_days(ts)
                # Actual body:
                sizes[probe['PROBE']] += len(dumps(probe))
                counts[probe['PROBE']] += 1
        return total_days

class PRDataSize1Day(PRDataSize):
    desc = "Like PRDataSize, but limited to 1 day.  Use this for most testing."
    days_ago = 1
class PRDataSize1Week(PRDataSize):
    desc = "Like PRDataSize, but limited to 7 days.  Also more efficient."
    days_ago = 7
class PRDataSize1Hour(PRDataSize):
    desc = "Like PRDataSize, but limited to 7 days.  Also more efficient."
    days_ago = 1/24.

class PRMissingData(_Converter):
    """Report time periods of greater than 3600s when no data was recorded.

    This uses the PRTimestamps converter to the timestamps of actual
    data collection, not just when data was uploaded which is expected
    to be intermitent.  This is used for testing Purple Robot
    functioning.
    """
    device_class = 'PurpleRobot'
    per_page = None
    header = ['gap_start', 'gap_end', 'gap_s', 'previous_duration_s']
    desc = "Report gaps of greater than 3600s in last 28 days of Purple Robot data."
    days_ago = 28
    min_gap = 3600
    @classmethod
    def query(cls, queryset):
        """Do necessary filtering on the django QuerySet.

        In this case, restrict to the last 14 days."""
        #now = datetime.utcnow() This method depends on django, but
        # that is OK since it used Queryset semantics, which itself
        # depend on django.  This method only makes sent to call in
        # the server itself.
        if cls.days_ago is not None:
            from django.utils import timezone
            now = timezone.now()
            return queryset.filter(ts__gt=now-timedelta(days=cls.days_ago))
        return queryset
    def __init__(self, *args, **kwargs):
        super(PRMissingData, self).__init__(*args, **kwargs)
        self.ts_list = [ ]
    def convert(self, rows, time=lambda x:x):
        ts_list = self.ts_list
        # Get list of all actual data timestamps (using PRTimestamps converter).
        #
        # Run through all data.  By the way that "extend" works, if
        # there is an error in decoding, the previously appended items
        # will still be tehre.  So, when we restart (from the .run()
        # method that restarts on exceptions), we continue appending
        # to the same list, which is good.
        self.ts_list.extend(x[0] for x in PRTimestamps(rows).run())
        # Avoid all timestamps less than 1e8s (1973).  This avoids
        # times converted from things that weren't unixtimes.
        ts_list_sorted = sorted(t for t in ts_list if t > 100000000)
        ts_list_sorted.append(mod_time.time())
        ts_list_sorted = iter(ts_list_sorted)
        # Simple core: go through, convert all data, any gaps that are
        # greater than self.min_gap seconds, yield that info.
        t_before_gap = next(ts_list_sorted)
        t_active_start = t_before_gap
        t_next = None
        for t_next in ts_list_sorted:
            if t_next > t_before_gap + self.min_gap:
                yield (time(t_before_gap),
                       time(t_next),
                       t_next-t_before_gap,
                       t_before_gap-t_active_start if t_active_start else '',
                )
                t_active_start = t_next
            t_before_gap = t_next
        if t_next is None:
            return
        yield (time(t_before_gap),
               time(t_next),
               t_next-t_before_gap,
               t_before_gap-t_active_start if t_active_start else '',
        )
        del self.ts_list
        del ts_list
class PRMissingData7Days(PRMissingData):
    days_ago = 7
    desc = "Report gaps of greater than 3600s in last 7 days of Purple Robot data."
class PRMissingDataUnlimited(PRMissingData):
    days_ago = None
    desc = "Report gaps of greater than 3600s in last 7 days of Purple Robot data."

class PRRecentDataCounts(BaseDataCounts):
    device_class = 'PurpleRobot'
    timestamp_converter = PRTimestamps


#
# iOS converters (our app)
#
class BaseIosConverter(_Converter):
    device_class = 'Ios'
class IosProbes(BaseIosConverter, PRProbes):
    pass
class IosTimestamps(BaseIosConverter, _Converter):
    desc = 'All actual data timestamps of all iOS probes'
    header = ['time',
              'packet_time',
              'probe',]
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                yield (time(probe['TIMESTAMP'] if 'TIMESTAMP' in probe else probe['timestamp']),
                       time(timegm(ts.utctimetuple())),
                       probe['probe'].rsplit('.',1)[-1])
class IosDataSize(BaseIosConverter, PRDataSize):
    pass
class IosRecentDataCounts(BaseIosConverter, PRRecentDataCounts):
    pass
class _IosGeneric(BaseIosConverter, _PRGeneric):
    pass
# Real data
class IosLocation(BaseIosConverter):
    header = ['time', 'lat', 'lon', 'alt', 'speed']
    desc = "Location data"
    per_page = 1
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for row in data:
                if 'probe' not in row or row['probe'] == 'Location':
                    yield (time(row['timestamp']),
                       float(row['lat']),
                       float(row['lon']),
                       float(row['alt']),
                       float(row['speed']),
                       )
class IosScreen(_IosGeneric):
    header = ['time', 'onoff']
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for row in data:
                if row['probe'] == 'Screen':
                    yield (time(row['timestamp']),
                           row['state'],
                          )




import io
from dateutil.parser import parse as dateutil_parse
class ActiwatchFull(_Converter):
    device_class = 'kdata.devices.actiwatch.Actiwatch'
    desc = "Actiwatch full data"
    header = [#'line',
              'time',
              'time_str',
              'line',
              'activity',
              'marker',
              'white light',
              'sleepwake',
              'intervalstatus',]

    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            if '---- Subject Properties------' not in data:
                continue

            tzoffset = re.search(r'"Time Zone Offset:","([-+\d:]+)","hours:minutes"', data).group(1)
            m = re.search(r'--- Epoch-by-Epoch Data -+"\s+.*?("Line",.*)',
                          data, re.DOTALL)
            f = io.StringIO(m.group(1))
            reader = csv.reader(f)

            for line in reader:
                if not line: continue
                if line[0] == 'Line': continue
                dt = dateutil_parse("%s %s %s"%(line[1], line[2], tzoffset))
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                ts = dt.timestamp()
                #print(line)

                yield (time(ts),
                       time_str,
                       int(line[0]) if line[0] != 'NaN' else float('nan'),
                       int(line[3]) if line[3] != 'NaN' else float('nan'),
                       int(line[4]) if line[4] != 'NaN' else float('nan'),
                       float(line[5]),
                       float(line[6]),
                       line[7],
                       )
class ActiwatchStatistics(_Converter):
    device_class = 'kdata.devices.actiwatch.Actiwatch'
    desc = "Actiwatch intervals"
    header = ['time_start',
              'time_end',
              'interval_type',
              'interval_num',
              'start_date',
              'start_time',
              'end_date',
              'end_time',
              'duration',
              'percent_invalid_sw',
              'efficiency',
              'wake_time',
              'percent_wake',
              'sleep_time',
              'percent_sleep',
              'exposure_white',
              'avg_white',
              'max_white',
              'talt_white',
              'percent_invalid_white']
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            if '---- Subject Properties------' not in data:
                continue

            tzoffset = re.search(r'"Time Zone Offset:","([-+\d:]+)","hours:minutes"', data).group(1)
            m = re.search(r'--- Statistics -+"\s+.*?("Interval Type",.*?)\r\n\r\n\r\n',
                          data, re.DOTALL)
            f = io.StringIO(m.group(1))
            reader = csv.reader(f)

            for line in reader:
                if not line: continue
                if line[0] == 'Interval Type': continue
                if line[0] == '': continue

                if 'Summary' not in line[0]:
                    start_dt = dateutil_parse("%s %s %s"%(line[2], line[3], tzoffset))
                    #start_time_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                    start_ts = time(start_dt.timestamp())
                    end_dt = dateutil_parse("%s %s %s"%(line[4], line[5], tzoffset))
                    #end_time_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
                    end_ts = time(end_dt.timestamp())
                else:
                    start_ts = end_ts = ''

                yield (start_ts, end_ts) + tuple(line[:-1]) # last one is empty
class ActiwatchMarkers(_Converter):
    device_class = 'kdata.devices.actiwatch.Actiwatch'
    desc = "Actiwatch button pushes"
    header = ['time',
              'time_str',
              'line',
              'date',
              'time_of_day',
              'marker',
              'interval Status', '']

    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            if '---- Subject Properties------' not in data:
                continue

            tzoffset = re.search(r'"Time Zone Offset:","([-+\d:]+)","hours:minutes"', data).group(1)
            m = re.search(r'--- Marker/Score List -+"\s+.*?("Line","Date",.*?)\r\n\r\n\r\n',
                          data, re.DOTALL)
            f = io.StringIO(m.group(1))
            reader = csv.reader(f)

            for line in reader:
                if not line: continue
                if line[0] == 'Line': continue
                if line[0] == '': continue
                dt = dateutil_parse("%s %s %s"%(line[1], line[2], tzoffset))
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                ts = dt.timestamp()

                yield (time(ts), time_str,) + tuple(line[:-1]) # last one is empty



class BaseAwareConverter(_Converter):
    device_class = ('Aware', 'AwareValidCert')
    ts_column = 'timestamp'
    #table = 'screen'
    #desc = "Generic Aware converter"
    #fields = ['screen_status',
    #          ]
    @classmethod
    def header2(cls):
        """Return table header"""
        if hasattr(cls, 'header') and cls.header:
            return cls.header
        return ['time', ] + [x.lower() for x in cls.fields]
    def convert(self, queryset, time=lambda x:x):
        table = self.table
        fields = self.fields
        ts_column = self.ts_column

        for ts, data in queryset:
            data = loads(data)
            if not isinstance(data, dict): continue
            if data['table'] != table:
                continue
            table_data = loads(data['data'])
            for row in table_data:
                yield (time(row[ts_column]/1000.),
                       ) + tuple(row.get(colname,'') for colname in fields)
class AwareAuto(BaseAwareConverter):
    header = ['time', 'data']
    def convert(self, queryset, time=lambda x:x):
        table = self.table
        ts_column = self.ts_column

        for ts, data in queryset:
            data = loads(data)
            if not isinstance(data, dict): continue
            if data['table'] != table:
                continue
            table_data = loads(data['data'])
            for row in table_data:
                ts = time(row[ts_column]/1000.)
                row.pop('device_id')
                row.pop(ts_column)
                yield (ts, json.dumps(row, sort_keys=True))
class AwareUploads(BaseAwareConverter):
    header = ['packet_time', 'table', 'len_data']
    desc = "Uploaded tables and times"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            yield (time(timegm(ts.utctimetuple())),
                   data['table'],
                   len(data['data']),
                   )
class AwareTimestamps(BaseAwareConverter):
    header = ['time', 'packet_time', 'table']
    desc = "Timestamps of each collected data point"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            if not isinstance(data, dict): continue
            table_data = loads(data['data'])
            for row in table_data:
                yield (time(row['timestamp']/1000.),
                       time(timegm(ts.utctimetuple())),
                       data['table'],
                       )
class AwareTableData(BaseAwareConverter):
    header = ['packet_time', 'table', 'data']
    desc = "Uploaded data, by table."
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            yield (time(timegm(ts.utctimetuple())),
                   data['table'],
                   data['data'],
                   )
class AwarePacketTimeRange(BaseAwareConverter):
    header = ['packet_time', 'table', 'start_time', 'end_time', 'n_rows',
              'packet_size', 'rows_per_s']
    desc = "Time ranges covered by each data packet."
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            data_decoded = loads(data['data'])
            try:
                time_range = (data_decoded[-1]['timestamp']
                                -data_decoded[0]['timestamp']) / 1000
            except (KeyError, IndexError, ValueError):
                time_range = None
            yield (time(timegm(ts.utctimetuple())),
                   data['table'],
                   time(data_decoded[ 0]['timestamp']/1000) if time_range else '',
                   time(data_decoded[-1]['timestamp']/1000) if time_range else '',
                   len(data_decoded),
                   len(data['data']),
                   len(data_decoded)/float(time_range) if time_range else '',
                   )
class AwareDataSize(BaseDataSize):
    device_class = ('Aware', 'AwareValidCert')
    per_page = None
    def do_queryset_iteration(self, queryset, sizes, counts, total_days):
        for ts, data in queryset:
            data_decoded = loads(data)
            if isinstance(data_decoded, list):
                table = 'unknown'
            else:
                table = data_decoded['table']
            if total_days is None:
                total_days = self.figure_total_days(ts)
            # Actual body:
            sizes[table] += len(data)
            counts[table] += 1
        return total_days
class AwareDeviceInfo(BaseAwareConverter):
    # {"table": "aware_device", "data":
    # "[{\"device\":\"hammerhead\",\"build_id\":\"MOB30H\",\"sdk\":\"23\",\"release_type\":\"user\",\"release\":\"6.0.1\",\"timestamp\":1465242186982,\"board\":\"hammerhead\",\"device_id\":\"UID\",\"brand\":\"google\",\"label\":\"\",\"serial\":\"NNNNNN\",\"manufacturer\":\"LGE\",\"hardware\":\"hammerhead\",\"product\":\"hammerhead\",\"model\":\"Nexus
    # 5\"}]"}
    desc = "Hardware info"
    table = "aware_device"
    fields = ['device', 'release', 'label', 'sdk', 'brand', 'manufacturer',
              'hardware', 'build_id', 'product', 'model']
class AwareDeviceInfo2(AwareAuto):
    desc = "Hardware meta-info."
    table = "aware_device"
class AwareScreen(BaseAwareConverter):
    desc = "Screen on/off"
    table = 'screen'
    fields = ['screen_status',
              ]
class AwareBattery(BaseAwareConverter):
    desc = "Battery"
    table = 'battery'
    fields = ['battery_level',
              'battery_status',
              'battery_health',
              'battery_adaptor',
              ]
class AwareLight(BaseAwareConverter):
    desc = "Light sensor"
    table = 'light'
    fields = ['double_light_lux',
              'accuracy',
              ]
class AwareWifi(BaseAwareConverter):
    desc = "Wifi scans"
    table = 'wifi'
    fields = ['ssid',
              'bssid',
              'mac_address',
              'rssi',
              ]
class AwareSensorWifi(BaseAwareConverter):
    desc = "Wifi scans"
    table = 'sensor_wifi'
    fields = ['ssid',
              'bssid',
              'mac_address',
              ]
class AwareBluetooth(BaseAwareConverter):
    desc = "Bluetooth"
    table = 'bluetooth'
    fields = ['bt_address',
              'bt_rssi',
              'device_id',
              'label',
              ]
class AwareLocation(BaseAwareConverter):
    desc = "Location"
    table = 'locations'
    fields = ['double_latitude',
              'double_longitude',
              'double_altitude',
              'accuracy',
              'double_speed',
              'double_bearing',
              'provider',
              'label',
              ]
class AwareNetwork(BaseAwareConverter):
    desc = "Networks"
    table = 'network'
    fields = ['network_state',
              'network_type',
              'network_subtype',
              ]
class AwareApplicationNotifications(BaseAwareConverter):
    desc = "Notifications"
    table = 'applications_notifications'
    fields = ['application_name',
              'defaults',
              'sound',
              'vibrate',
              ]
class AwareApplicationCrashes(BaseAwareConverter):
    desc = "Notifications"
    table = 'applications_crashes'
    fields = ['error_short',
              'error_long',
              'application_name',
              'package_name',
              'application_version',
              'error_condition',
              ]
class AwareAmbientNoise(BaseAwareConverter):
    desc = "Ambient noise plugin"
    table = 'plugin_ambient_noise'
    fields = ['is_silent',
              'double_decibels',
              'double_silence_threshold',
              'double_rms',
              'double_frequency',
              'blob_raw',
              ]
class AwareAccelerometer(BaseAwareConverter):
    desc = "Accelerometer"
    table = 'accelerometer'
    fields = ['double_values_0',
              'double_values_1',
              'double_values_2',
              ]
class AwareGravity(BaseAwareConverter):
    desc = "gravity"
    table = 'gravity'
    fields = ['double_values_0',
              'double_values_1',
              'double_values_2',
              'accuracy',
              ]
class AwareGyroscope(BaseAwareConverter):
    desc = "gyroscope"
    table = 'gyroscope'
    fields = ['axis_z',
              'axis_y',
              'axis_x',
              'accuracy',
              ]
class AwareLinearAccelerometer(BaseAwareConverter):
    desc = "linear_accelerometer"
    table = 'linear_accelerometer'
    fields = ['double_values_0',
              'double_values_1',
              'double_values_2',
              ]
class AwareMagnetometer(BaseAwareConverter):
    desc = "magnetometer"
    table = 'magnetometer'
    fields = ['double_values_0',
              'double_values_1',
              'double_values_2',
              'accuracy',
              ]
class AwareRotation(BaseAwareConverter):
    desc = "rotation"
    table = 'rotation'
    fields = ['double_values_0',
              'double_values_1',
              'double_values_2',
              'accuracy',
              ]
class AwareProximity(BaseAwareConverter):
    desc = "proximity"
    table = 'sensor_proximity'
    fields = ['double_sensor_power_ma',
              'double_sensor_resolution',
              ]
class AwareNetworkTraffic(BaseAwareConverter):
    desc = "network_traffic"
    table = 'network_traffic'
    fields = ['double_sent_bytes',
              'double_received_bytes',
              'network_type',
              'double_sent_packets',
              'double_received_packets',
              ]
class AwareAppNotifications(BaseAwareConverter):
    desc = "applications_notifications"
    table = 'applications_notifications'
    fields = ['application_name',
              'sound',
              'vibrate',
              'double_sent_packets',
              'double_received_packets',
              ]
class AwareTelephony(BaseAwareConverter):
    desc = "telephony"
    table = 'telephony'
    fields = ['network_type',
              'phone_type',
              'data_enabled',
              'sim_state',
              ]
class AwareSigMotion(BaseAwareConverter):
    desc = "Significant Motion"
    table = 'significant'
    fields = ['is_moving',
              ]
class AwarePHQ9(BaseAwareConverter):
    desc = "PHQ9 answers"
    table = 'questionnaire'
    fields = ['answer',
              ]
    
class AwareLog(BaseAwareConverter):
    desc = "Status log"
    table = 'aware_log'
    fields = ['log_message']
class AwareCalls(BaseAwareConverter):
    desc = "Calls (incoming=1, outgoing=2, missed=3)"
    header = ['time', 'call_type', 'call_duration', 'trace', ]
    def convert(self, queryset, time=lambda x:x):
        types = {"1": "incoming", "2":"outgoing", "3":"missed"}
        for ts, data in queryset:
            data = loads(data)
            if not isinstance(data, dict): continue
            if data['table'] != 'calls': continue
            table_data = loads(data['data'])
            for row in table_data:
                yield (time(row['timestamp']/1000.),
                       types[row.get('call_type', '')],
                       row.get('call_duration', ''),
                       safe_hash(row['trace']) if 'trace' in row else '',
                       )
class AwareMessages(BaseAwareConverter):
    desc = "Messages"
    header = ['time', 'message_type', 'trace', ]
    def convert(self, queryset, time=lambda x:x):
        types = {"1": "incoming", "2":"outgoing"}
        for ts, data in queryset:
            data = loads(data)
            if data['table'] != 'messages': continue
            table_data = loads(data['data'])
            for row in table_data:
                yield (time(row['timestamp']/1000.),
                       types[row.get('message_type', '')],
                       safe_hash(row['trace']) if 'trace' in row else '',
                       )
class AwareRecentDataCounts(BaseDataCounts):
    device_class = ('Aware', 'AwareValidCert')
    timestamp_converter = AwareTimestamps
class AwareEsms(BaseAwareConverter):
    desc = "ESMs"
    header = ['time_asked', 'time_answer', 'user_answer', 'title', 'type', 'instructions', 'submit', 'notification_timeout']
    def convert(self, queryset, time=lambda x:x):
        types = {"1": "incoming", "2":"outgoing"}
        for ts, data in queryset:
            data = loads(data)
            if data['table'] != 'esms': continue
            table_data = loads(data['data'])
            for row in table_data:
                esm_json = loads(row['esm_json'])
                yield (time(row['timestamp']/1000.),
                       time(row['double_esm_user_answer_timestamp']/1000.),
                       row['esm_user_answer'],
                       esm_json.get('esm_type',''),
                       esm_json.get('esm_title',''),
                       esm_json.get('esm_instructions',''),
                       esm_json.get('esm_submit',''),
                       esm_json.get('esm_notification_timeout',''),
                       )







if __name__ == "__main__":
    import argparse
    description = """\
    Command line utility for converting raw data into other forms.

    This converts raw data using the converters defined in this file.
    It is a simple command line version of views_data.py:device_data.
    In the future, the common ground of these two functions should be
    merged.

    So far, the input format must be 'json-lines', that is, one JSON
    object on each line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help="Input filename")
    parser.add_argument('converter', help="Output filename")
    parser.add_argument('-f', '--format', help="Output format [csv,json,py]",
                        default='csv')
    parser.add_argument('-o', '--output', help="Output filename",
                        default=None)
    parser.add_argument('--handle-errors', help="Catch errors and continue",
                        action='store_true', default=False)
    parser.add_argument('--suppress-errors', help="If there were errorrs, do not print "
                                        "anything about them.  Has no effect unless "
                                        "--handle-errors is given.",
                        action='store_true', default=False)
    args = parser.parse_args()

    converter = globals()[args.converter]

    # Open the input file.  We expect it to have one JSON object per
    # line (as separated by \n).  Then, we make an iterator that JSON
    # decodes each line, and give this iterater to the converter.  The
    # converter returns another iterator over the reprocessed data.
    f = open(args.input)
    row_iter = (loads(line) for line in f )
    # Reprocess the row to convert the unixtime to UTC datetime
    row_iter = ((datetime.utcfromtimestamp(ts), data) for (ts, data) in row_iter)
    # First method is new conversion that handles errors
    # semi-intelligently.
    if args.handle_errors:
        converter = converter(row_iter)
        table = converter.run()
    # Second does not handle errors, if an error happens exception is
    # propagated.
    else:
        table = converter().convert(row_iter)  # iterate through lines
    # Output filename
    if args.output is not None:
        f_output = open(args.output, 'w')
    else:
        f_output = sys.stdout

    # Write as python objects (repr)
    if args.format == 'py':
        for row in table:
            print(repr(row), file=f_output)

    # Write as CSV
    elif args.format == 'csv':
        # We have to be a bit convoluted to support both python2 and
        # python3 here.  Maybe there is a better way to do this...
        csv_writer = csv.writer(f_output)
        csv_writer.writerow([x.encode('utf-8') for x in converter.header2()])
        for row in table:
            #csv_writer.writerow(row)
            csv_writer.writerow([x.encode('utf-8') if isinstance(x, string_types) else x
                                 for x in row])

    # Write as JSON
    elif args.format == 'json':
        print('[', file=f_output)
        table = iter(table)
        print(dumps(next(table)), end='', file=f_output)
        for row in table:
            print(',', file=f_output) # makes newline
            print(dumps(row), end='', file=f_output)
        print('\n]', file=f_output)

    else:
        print("Unknown output format: %s"%args.format)
        exit(1)

    # If there were any errors, make a warning about them.
    if args.handle_errors and not args.suppress_errors:
        if converter.errors:
            print("")
            print("The following errors were found:")
            for error in converter.errors:
                print(error)
