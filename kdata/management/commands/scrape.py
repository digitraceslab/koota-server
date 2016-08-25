from datetime import datetime, timedelta
import itertools
import json
from six.moves import input
import subprocess
import tempfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import models
from ...models import Device, Data
from ... import devices
from ... import util

class Command(BaseCommand):
    help = 'Edit the raw (string value, timestamp)'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs=None,
                            help="Device id to scrape OR device class name for scraping all of a class.")
        parser.add_argument('--scrape_function', '-f',
                            help="Function to use for scraping")
        parser.add_argument('--debug', '-d', action='store_true',
                            help="Run in debug mode?")
        parser.add_argument('--save-data', action='store_true',
                            help="Actually save scraped data in the database?")

    def handle(self, *args, **options):
        # Scrape for a class
        if options['device_id'] in devices.device_class_lookup:
            return self.scrape_all(self, *args, **options)

        # Scrape for a single device
        self.scrape_one(*args, **options)

    def scrape_one(self, *args, **options):
        if options['scrape_function']:
            func = util.import_by_name(options['scrape_function'])
        else:
            device = models.Device.get_by_id(options['device_id'])
            func = device.get_class().scrape_one_function

        func(device_id=options['device_id'],
             save_data=options['save_data'], debug=options['debug'])

    def scrape_all(self, *args, **options):
        if options['scrape_function']:
            func = util.import_by_name(options['scrape_function'])
        else:
            # device_id is class name, not device ID!
            cls = devices.get_class(options['device_id'])
            func = cls.scrape_all_function

        func(save_data=options['save_data'], debug=options['debug'])
