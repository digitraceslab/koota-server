from datetime import datetime, timedelta
import itertools
import json
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import converter as kconverter
from ... import group as kdata_group
from ... import models
from ...models import Device, Data
from ... import util

TZ = timezone.LocalTimezone()

class Command(BaseCommand):
    help = 'Print AWARE configuration (currently just scheduled timestamps)'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs=None)

    def handle(self, *args, **options):
        pass
