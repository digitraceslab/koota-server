from datetime import datetime, timedelta
import json
from json import dumps, loads

from django.utils import timezone
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import models
from ...models import Device, Data

class DataEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S.%f')
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)




class Command(BaseCommand):
    help = 'Export and import raw data'

    def add_arguments(self, parser):
        parser.add_argument('--import', action='store_true', help_text='load data')
        parser.add_argument('--db-device',
                            help="Device id to scrape OR device class name for scraping all of a class.")
        parser.add_argument('--encoded-device',
                            help="device_id to encode in the output")
        parser.add_argument('--ts-start', help="start timestamp")
        parser.add_argument('--ts-end', help="end timestamp")
        parser.add_argument('--include-ip', action='store_true', help="include IP addresses?")

    def handle(self, *args, **options):
        print(options)

        if options['import']:
            self.import_(*args, **options)
        else:
            self.export(*args, **options)

    def import_(self, *args, **options):
        device = models.Device.get_by_id(options['db_device'])
        device_id = device.device_id

        rows = Data.objects.filter(device_id=device_id).order_by('ts')

        import itertools
        for row in itertools.islice(rows, 10):
            data = dict(device_id=row.device_id,
                        ts=row.ts,
                        ts_received=row.ts_received,
                        ip=row.ip if options['include_ip'] else None,
                        data_length=row.data_length,
                        #data=row.data,
            )
            print(json.dumps(data, cls=DataEncoder))

    def import_(self, *args, **options):
        pass
