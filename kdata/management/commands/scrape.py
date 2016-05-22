from datetime import datetime, timedelta
import itertools
import json
from six.moves import input
import subprocess
import tempfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ...models import Device, Data
from ... import util

class Command(BaseCommand):
    help = 'Edit the raw (string value, timestamp)'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs=None,
                            help="Device id to scrape")
        parser.add_argument('scrape_function', nargs=None,
                            help="Function to use for scraping")

    def handle(self, *args, **options):

        module, func = options['scrape_function'].rsplit('.', 1)
        module = util.import_by_name(module)
        func = getattr(module, func)

        print(func(options['device_id']))
