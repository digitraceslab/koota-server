from datetime import datetime, timedelta
import itertools
import json
from six.moves import input
import subprocess
import tempfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ...models import Device, Data
from ... import devices
from ... import util

class Command(BaseCommand):
    help = 'Edit the raw (string value, timestamp)'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs=None,
                            help="Device id to scrape")
        parser.add_argument('scrape_function', nargs='?',
                            help="Function to use for scraping")

    def handle(self, *args, **options):
        # Scrape for a class
        if options['device_id'] in devices.device_class_lookup:
            return self.scrape_all(self, *args, **options)

        # Scrape for a single device
        self.scrape_one(*args, **options)

    def scrape_one(self, *args, **options):
        module, func = options['scrape_function'].rsplit('.', 1)
        module = util.import_by_name(module)
        func = getattr(module, func)

        print(func(options['device_id']))

    def scrape_all(self, *args, **options):
        cls = devices.get_class(options['device_id'])
        cls.scrape_all_function()
