
from calendar import timegm
import csv
from datetime import datetime
from json import loads, dumps
import time

import logging
log = logging.getLogger(__name__)


class _Converter(object):
    per_page = 10
    header = [ ]
    @classmethod
    def name(cls):
        return cls.__name__
    pass

class Raw(_Converter):
    header = ['time', 'data']

    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            yield ts, data

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
            if isinstance(data, buffer):
                log.info(('buffer: ', ts, data))
                continue
            try:
                data = loads(data)
            except ValueError: #ValueError:
                import ast
                try:
                    data = ast.literal_eval(data)
                except:
                    log.critical(type(data), data)
            for probe in data:
                yield (time(probe['TIMESTAMP']),
                       probe['PROBE'].split('.')[-1],
                       dumps(probe))

class PRBattery(_Converter):
    header = ['time', 'level', 'plugged']
    def convert(self, queryset, time=lambda x:x):
        for ts, data in queryset:
            if isinstance(data, buffer):
                log.info(data)
                continue
            try:
                data = loads(data)
            except ValueError: #ValueError:
                import ast
                try:
                    data = ast.literal_eval(data)
                except:
                    log.critical(type(data), data)
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
            if isinstance(data, buffer):
                log.info(data)
                continue
            try:
                data = loads(data)
            except ValueError: #ValueError:
                import ast
                try:
                    data = ast.literal_eval(data)
                except:
                    log.critical(type(data), data)
            for probe in data:
                if probe['PROBE'] == 'edu.northwestern.cbits.purple_robot_manager.probes.builtin.ScreenProbe':
                    yield (time(probe['TIMESTAMP']),
                           int(probe['SCREEN_ACTIVE']),
                          )
