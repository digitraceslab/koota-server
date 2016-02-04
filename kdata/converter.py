
from six.moves import zip

from calendar import timegm
import collections
import csv
from datetime import datetime
import itertools
from json import loads, dumps
import time

import logging
log = logging.getLogger(__name__)


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
        return ['time'] + [x[0] for x in cls.fields]


class Raw(_Converter):
    header = ['time', 'data']
    desc = "Raw data packets"

    def convert(self, queryset, time=lambda x:x):
        for dt, data in queryset:
            yield time(timegm(dt.utctimetuple())), data

class MurataBSN(_Converter):
    header = ['unixtime', 'hr', 'rr', 'sv', 'hrv', 'ss', 'status', 'bbt0', 'bbt1', 'bbt2']
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
    header = ['time', 'probe', 'data']
    desc = "Purple Robot raw JSON data, divided into each probe"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                yield (time(probe['TIMESTAMP']),
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
    header = ['time', 'step_count']
    desc = "Step counter"
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.StepCounterProbe':
                    yield (time(probe['TIMESTAMP']),
                           probe['STEP_COUNT'],
                           )
class PRDeviceInUse(_Converter):
    header = ['time', 'packet_ts', 'in_use']
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

from six import iteritems
class PRDataSize(_Converter):
    per_page = None
    header = ['probe', 'bytes']
    desc = "Total bytes taken by each separate probe (warning: takes a long time to compute)"
    def convert(self, queryset, time=lambda x:x):
        sizes = collections.defaultdict(int)
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                sizes[probe['PROBE']] += len(dumps(probe))
        for probe, size in sorted(iteritems(sizes), key=lambda x: x[1], reverse=True):
            yield probe, size

class IosLocation(_Converter):
    header = ['time', 'lat', 'lon', 'alt', 'speed']
    desc = "Location data"
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
