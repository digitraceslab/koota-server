import itertools
import json

from django.core.management.base import BaseCommand, CommandError
from kdata.models import Device, Data
from django.utils import timezone
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Fix the Purple Robot json-evaled bug'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs='*')
        parser.add_argument('--history', help="Number of past days to use for test.", default=14, type=int)
        parser.add_argument('--min-gap', help="Minimum missing data gap to report (s).", default=3600, type=int)

    def handle(self, *args, **options):
        #print(options)
        min_gap = options['min_gap']

        if options['device_id']:  # if any elements in list
            devices = [ Device.get_by_id(id_) for id_ in options['device_id'] ]
        else:
            devices = Device.objects.filter(type='PurpleRobot')

        for device in devices:
            print(device.public_id, device.user.username, device.type)
            rows = Data.objects.filter(device_id=device.device_id,
                                       ts__gt=timezone.now()-timedelta(days=options['history'])).defer('data')
            print('count:', rows.count())

            from kdata import converter
            ts_list = converter.PRTimestamps().convert(((x.ts, x.data) for x in rows.iterator()))

            ts_list_sorted = sorted(x[0] for x in ts_list if x[0] > 100000000)
            ts_list_sorted = iter(ts_list_sorted)
            time0 = next(ts_list_sorted)
            for time in ts_list_sorted:
                if time > time0 + min_gap:
                    print("  {0}    {1:<5.5}".format(datetime.fromtimestamp(time0), (time-time0)/3600))
                time0 = time
