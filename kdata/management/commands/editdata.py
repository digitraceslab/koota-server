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
    help = 'Edit the raw (string value, timestamp)'

    def add_arguments(self, parser):
        parser.add_argument('rowid', nargs=None,
                            help="Rowid to edit")
        parser.add_argument('--json', action='store_true',
                            help="Validate new data is valid json.")
        parser.add_argument('--timestamp', type=int,
                            help="Update timestamp of the data, do not edit data.")
        parser.add_argument('--commit', action='store_true',
                            help="Commit the new data (must be given).")

    def handle(self, *args, **options):

        row = Data.objects.get(id=options['rowid'])

        # Update timestamp if --timestamp is given.
        if options['timestamp']:
            print('old timestamp is', row.ts)
            print('old timestamp is', row.ts.timestamp())
            new_ts = float(input('enter new timestamp (unixtime) > '))
            print(new_ts)
            new_ts = timezone.datetime.fromtimestamp(new_ts, tz=timezone.UTC())
            print('new timestamp is', repr(new_ts))
            if options['commit'] and input('Commit new data? [y/N] > ') == 'y':
                row.ts = new_ts
                row.save()
                print("New data committed.")
            return

        # Write data to file, let user edit it, then re-read and
        # possibly update.
        tmpfile = tempfile.NamedTemporaryFile()
        tmpfile.write(row.data.encode('utf8'))
        tmpfile.flush()
        # edit
        subprocess.call(['emacs', tmpfile.name])
        # re-read
        tmpfile.seek(0)
        newdata = tmpfile.read().decode('utf8')

        # Validate JSON data.
        if options['json']:
            json.loads(newdata)
            print("JSON validated")
        if newdata == row.data:
            print("No changes to data...")
            return

        print(newdata)
        if options['commit'] and input('Commit new data? [y/N] > ') == 'y':
            row.data = newdata
            row.save()
            print("New data committed.")
