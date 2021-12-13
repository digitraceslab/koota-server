from datetime import datetime, timedelta
import itertools
import json
from six.moves import input
import subprocess
import tempfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ...models import Device, Data

class Command(BaseCommand):
    help = 'List all data from one device'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs=None, help="Device ID.  Always required")
        parser.add_argument('--rowid', nargs=None, help="Print only this rowid, and entire data.")

    def handle(self, *args, **options):
        device = Device.get_by_id(public_id=options['device_id'])

        # Print a single row.
        if options['rowid']:
            data = Data.objects.get(device_id=device.device_id, id=options['rowid'])
            print(data.data)
            return

        queryset = Data.objects.filter(device_id=device.device_id).order_by('ts')
        for row in queryset:
            data = row.data
            data = data[:100]
            data = repr(data)
            print(f"{row.id:10} {row.device_id}  {row.ts}  {data}")




