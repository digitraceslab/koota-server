
from calendar import timegm
import collections
import csv
from datetime import datetime
from json import loads, dumps
import time

import logging
log = logging.getLogger(__name__)


class _Converter(object):
    per_page = 25
    header = [ ]
    @classmethod
    def name(cls):
        return cls.__name__
    pass

class Raw(_Converter):
    header = ['time', 'data']

    def convert(self, queryset, time=lambda x:x):
        for dt, data in queryset:
            yield time(timegm(dt.utctimetuple())), data

class MurataBSN(_Converter):
    header = ['unixtime', 'hr', 'rr', 'sv', 'hrv', 'ss', 'status', 'bbt0', 'bbt1', 'bbt2']
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
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                yield (time(probe['TIMESTAMP']),
                       probe['PROBE'].split('.')[-1],
                       dumps(probe))

class PRBattery(_Converter):
    header = ['time', 'level', 'plugged']
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
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            data = loads(data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.features.DeviceInUseFeature':
                    yield (time(probe['TIMESTAMP']),
                           int(probe['DEVICE_ACTIVE']))

from six import iteritems
class PRDataSize(_Converter):
    per_page = None
    header = ['time', 'onoff']
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
