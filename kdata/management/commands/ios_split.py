from datetime import datetime, timedelta
import itertools
import json

from django.core.management.base import BaseCommand, CommandError
from kdata.models import Device, Data
from django.utils import timezone
from django.db import transaction

class Command(BaseCommand):
    """This command splits very large iOS device packets.

    Early versions of the iOS app uploaded data packets with sizes
    that could increase without bound.  This would cause memory
    problems for the server, even when processing them inline.  We
    solve this by manually splitting them.

    To run this script you have to manually uncomment a few lines
    before running (for safety).
    """
    help = 'Split very large iOS packets'

    def add_arguments(self, parser):
        parser.add_argument('device_id', nargs='*')
        parser.add_argument('--live_run')

    def handle(self, *args, **options):
        #print(options)
        live_run = False
        if 'live_run' in options:
            if input('Do a live run? [yes/NO] > ') == 'yes':
                live_run = True

        if options['device_id']:  # if any elements in list
            devices = [ Device.get_by_id(id_) for id_ in options['device_id'] ]
        else:
            devices = Device.objects.filter(type='Ios')

        f_log = open('ios_split.log', 'w')

        for device in devices:
          print("\n\nDevice: %s"%device.device_id)

          rows = Data.objects.filter(device_id=device.device_id).defer('data')


          for row in rows.iterator():
            with transaction.atomic():
                if row.data_length <= 2**20:
                    continue
                # Row needs processing
                print()
                print('orig:', len(row.data))
                print('DATA', file=f_log)
                print(row.id, file=f_log)
                print(row.device_id, file=f_log)
                print(row.ts, file=f_log)
                print(row.ip, file=f_log)
                print(repr(row.data), file=f_log)
                print(row.data_length, file=f_log)
                print('-', file=f_log)
                data = json.loads(row.data)
                new_data = [ ]
                i = 0
                n = 1000
                while True:
                    _ = data[i*n:(i+1)*n]
                    if len(_) == 0:
                        break
                    _ = json.dumps(_)
                    new_data.append(_)
                    i += 1
                for data2 in new_data:
                    print(len(data2))
                    if live_run:
                        new_row = Data(device_id=row.device_id,
                                       ts=row.ts,
                                       ip=row.ip,
                                       data=data2,
                                       data_length=len(data2))
                        new_row.save()
                        new_row.ts = row.ts
                        new_row.save()
                if live_run:
                    row.device_id = row.device_id+'_orig1'
                    row.save()
                    print('committed')

                #break
