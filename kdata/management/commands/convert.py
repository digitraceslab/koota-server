from datetime import datetime, timedelta
import itertools
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kdata.models import Device, Data
import kdata.converter

class Command(BaseCommand):
    help = 'Run a preprocessor on a device'

    def add_arguments(self, parser):
        parser.add_argument('converter', nargs=None)
        parser.add_argument('device_id', nargs=None)
        parser.add_argument('--history', help="Number of past days to use for test.", default=14, type=int)

    def handle(self, *args, **options):
        #print(options)
        converter = getattr(kdata.converter, options['converter'])
        if options['device_id'] == 'PR':
            devices = Device.objects.filter(type='PurpleRobot')
            rows = Data.objects.filter(device_id__in=devices)
        elif options['device_id']:
            device = Device.get_by_id(options['device_id'])
            rows = Data.objects.filter(device_id=device.device_id, )
        else:
            raise ValueError()
        rows = rows.filter(ts__gt=(timezone.now()-timedelta(days=options['history']) if options['history'] else 0 )
                           ).defer('data')#.iterator()
        #rows = rows.values_list('ts', 'data')
        rows = ((d.ts, d.data) for d in rows.iterator())
        converter = converter(rows=rows, time=lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
        for line in converter.run():
            print(line)

            
            
