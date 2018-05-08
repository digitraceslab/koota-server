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
    help = 'Delete a device'

    def add_arguments(self, parser):
        parser.add_argument('devices', nargs='+',
                            help="Device to delete.")
        parser.add_argument('--delete-data', action='store_true',
                            help="Delete data as well?")
        parser.add_argument('--delete', action='store_true',
                            help="Actually do deletions?")

    def handle(self, *args, **options):

        for device_id in options['devices']:
            device = Device.get_by_id(device_id)
            print('Deleting: %s'%device.public_id)
            be = device.backend
            if be.exists():
                print("  device has data, not deleting yet...")
                if options['delete_data']:
                    #be.delete()
                    raise NotImplementedError("we don't delete data yet...")
                continue
            if options['delete']:
                device.delete()
