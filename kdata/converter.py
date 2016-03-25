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

from six import iteritems, itervalues
from six.moves import zip

from calendar import timegm
import collections
import csv
from datetime import datetime, timedelta
import itertools
from json import loads, dumps
from math import log
import time
import sys

import logging
logger = logging.getLogger(__name__)

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
                logger.error("Exception in %s", self.__class__.__name__)
                import traceback
                logger.error(e)
                logger.error(traceback.format_exc())
                self.errors.append(e)
                self.errors_dict[str(e)] += 1
                #self.errors_emit_error(e)

class Raw(_Converter):
    header = ['time', 'data']
    desc = "Raw data packets"

    def convert(self, queryset, time=lambda x:x):
        for dt, data in queryset:
            yield time(timegm(dt.utctimetuple())), data

class MurataBSN(_Converter):
    header = ['time', 'hr', 'rr', 'sv', 'hrv', 'ss', 'status', 'bbt0', 'bbt1', 'bbt2']
    desc = "Basic information from Murata bed sensors"
    def convert(self, rows, time=lambda x:x):
        from defusedxml.ElementTree import fromstring as xml_fromstring
        from dateutil import parser as date_parser
        count = 0
        for ts, data in rows:
            doc = xml_fromstring(data)
            node = doc[0][0]
            device_id = node.attrib['id']
            start_time = doc[0][0][0][0].attrib['time']
            ts = date_parser.parse(start_time)
            values = doc[0][0][0][0][9]
            reader = csv.reader(values.text.split('\n'))
            for row in reader:
                #count += 1 ; print count
                if not row: continue
                unixtime = timegm(ts.timetuple()) + int(row[0])
                #yield [unixtime, time.strftime('%H:%M:%S', time.localtime(unixtime))]+ row[1:]
                yield [time(unixtime), ]+ row[1:]


class PRProbes(_Converter):
    header = ['time', 'packet_time', 'probe', 'data']
    desc = "Purple Robot raw JSON data, divided into each probe"
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
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.ScreenProbe':
                    yield (time(probe['TIMESTAMP']),
                           int(probe['SCREEN_ACTIVE']),
                          )
class PRWifi(_Converter):
    header = ['time', 'essid', 'current', 'strength']
    desc = "Wifi networks found"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.WifiAccessPointsProbe':
                    ts = time(probe['TIMESTAMP'])
                    current = probe['CURRENT_BSSID']
                    yield (ts,
                           loads(probe['CURRENT_SSID']),
                           #probe['CURRENT_BSSID'],
                           1,
                           probe['CURRENT_RSSI'],
                           )
                    for ap_info in probe['ACCESS_POINTS']:
                        yield (ts,
                               ap_info['SSID'],
                               #ap_indo['BSSID']
                               0,
                               ap_info['LEVEL'],
                               )
class PRBluetooth(_Converter):
    header = ['time', 'bluetooth_name', 'bluetooth_address']
    desc = "Bluetooth devices found"
    def convert(self, queryset, time=lambda x:x):
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
                        yield (ts,
                               dev_info.get('BLUETOOTH_NAME', ''),
                               dev_info.get('BLUETOOTH_ADDRESS', ''),
                               )
class PRStepCounter(_Converter):
    header = ['time', 'step_count', 'last_boot']
    desc = "Step counter"
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
    header = ['time', 'packet_time', 'in_use']
    desc = "Purple Robot DeviceInUseFeature"
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
class PRTimestamps(_Converter):
    desc = 'All actual data timestamps of all PR probes'
    header = ['time',
              #'packet_time',
              'probe',]
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                yield (time(probe['TIMESTAMP']),
                       #timegm(ts.timetuple())
                       probe['PROBE'].rsplit('.',1)[-1])
class PRRunningSoftware(_Converter):
    header = ['time', 'package_name', 'task_stack_index', 'package_category', ]
    desc = "All software currently running"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.RunningSoftwareProbe':
                    for software in probe['RUNNING_TASKS']:
                        yield (time(probe['TIMESTAMP']),
                               software['PACKAGE_NAME'],
                               software['TASK_STACK_INDEX'],
                               software['PACKAGE_CATEGORY'],
                              )
class PRCallHistoryFeature(_Converter):
    header = ['time', 'window_index',
              'window_size', 'total', 'new_count', 'min_duration',
              'max_duration', 'avg_duration', 'total_duration',
              'std_deviation', 'incoming_count', 'outgoing_count',
              'incoming_ratio', 'ack_ratio', 'ack_count', 'stranger_count',
              'acquiantance_count', 'acquaintance_ratio', ]
    desc = "Aggregated call info"
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




class _PRGeneric(_Converter):
    """Generic simple probe

    This is an abstract base class for converting any probe into one row.

    Required attribute: 'field', which is tuples of (field_name,
    PROBE_FIELD).  The first is the output field name, the second is
    what is found in the probe object.  If length second is missing,
    use the first for both.
    """
    @classmethod
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
    probe_name = 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.CallStateProbe'
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


class PRDataSize(_Converter):
    per_page = None
    header = ['probe', 'count', 'bytes', 'human_bytes', 'bytes/day']
    desc = "Total bytes taken by each separate probe (warning: takes a long time to compute)"
    days_ago = None
    @classmethod
    def query(cls, queryset):
        """"Limit   to the number of days ago, if cls.days_ago is given."""
        if not cls.days_ago:
            return queryset
        from django.utils import timezone
        now = timezone.now()
        return queryset.filter(ts__gt=now-timedelta(days=cls.days_ago))
    def convert(self, queryset, time=lambda x:x):
        sizes = collections.defaultdict(int)
        counts = collections.defaultdict(int)
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                sizes[probe['PROBE']] += len(dumps(probe))
                counts[probe['PROBE']] += 1
        for probe, size in sorted(iteritems(sizes), key=lambda x: x[1], reverse=True):
            yield (probe,
                   counts[probe],
                   size,
                   human_bytes(size),
                   human_bytes(size/float(self.days_ago)))
        yield ('total',
               sum(itervalues(counts)),
               sum(itervalues(sizes)),
               human_bytes(sum(itervalues(sizes))),
               human_bytes(sum(itervalues(sizes))/float(self.days_ago)))
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
    per_page = None
    header = ['time0', 'time1', 'gap_s']
    desc = "Report gaps of greater than 3600s in last 14 days of Purple Robot data."
    days_ago = 14
    min_gap = 3600
    @classmethod
    def query(cls, queryset):
        """Do necessary filtering on the django QuerySet.

        In this case, restrict to the last 14 days."""
        #now = datetime.utcnow() This method depends on django, but
        # that is OK since it used Queryset semantics, which itself
        # depend on django.  This method only makes sent to call in
        # the server itself.
        from django.utils import timezone
        now = timezone.now()
        return queryset.filter(ts__gt=now-timedelta(days=cls.days_ago))
    def convert(self, rows, time=lambda x:x):
        #import IPython ; IPython.embed()
        # Get list of all actual data timestamps (using PRTimestamps converter)
        ts_list = PRTimestamps(rows).run()
        # Avoid all timestamps less than 1e8s (1973).  This avoids
        # times converted from things that weren't unixtimes.
        ts_list_sorted = sorted(x[0] for x in ts_list if x[0] > 100000000)
        ts_list_sorted = iter(ts_list_sorted)
        # Simple core: go through, convert all data, any gaps that are
        # greater than self.min_gap seconds, yield that info.
        time0 = next(ts_list_sorted)
        for time1 in ts_list_sorted:
            if time1 > time0 + self.min_gap:
                yield (time(time0), time(time1), time1-time0)
            time0 = time1



class IosLocation(_Converter):
    header = ['time', 'lat', 'lon', 'alt', 'speed']
    desc = "Location data"
    per_page = 1
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for row in data:
                try:
                    yield (time(row['timestamp']),
                       float(row['lat']),
                       float(row['lon']),
                       float(row['alt']),
                       float(row['speed']),
                       )
                except:
                    pass





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


    # Write as python objects (repr)
    if args.format == 'py':
        for row in table:
            print(repr(row))

    # Write as CSV
    elif args.format == 'csv':
        csv_writer = csv.writer(sys.stdout)
        csv_writer.writerow(converter.header2())
        for row in table:
            csv_writer.writerow(row)

    # Write as JSON
    elif args.format == 'json':
        print('[')
        table = iter(table)
        print(dumps(next(table)), end='')
        for row in table:
            print(',') # makes newline
            print(dumps(row), end='')
        print('\n]')

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
