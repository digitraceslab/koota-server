import collections
from datetime import datetime, timedelta, time
import itertools
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kdata.models import Device, Data, Group
from koota_e3000_2016 import TZ

class Command(BaseCommand):
    help = 'Fix the Purple Robot json-evaled bug'

    def add_arguments(self, parser):
        #parser.add_argument('device_id', nargs='*')
        pass

    def handle(self, *args, **options):
        #print(options)

        G = Group.objects.filter(slug='TrackingExp1')
        #G.subjects

        now = timezone.now().astimezone(TZ)
        daystart = TZ.localize(datetime.combine(now.date(), time()))
        #daystart = datetime.combine(now.date(), time()).localize(TZ)
        weekstart = daystart - timedelta(days=now.isoweekday()-1) # monday 00:00

        devices = Device.objects.filter(
            user__subject_of_groups=G,
            label__name='Primary personal device',
        )


        # Weekly surveys.
        print('Weekly surveys')
        weekly = devices.filter(type='koota_e3000_2016.WeeklySurvey')
        print("  N = %s"%len(weekly))

        # How many were submitted in last week
        counts = collections.defaultdict(int)
        for D in weekly:
            data = Data.objects.filter(device_id=D.device_id,
                                       ts__gt=weekstart-timedelta(hours=(24+5)),
                                       ts__lt=weekstart,
                                       )
            counts[len(data)] += 1
            #print(D.public_id, len(data))
        print(sorted(counts.items()))


        # Morning surveys
        print('Morning surveys')
        morning = devices.filter(type='koota_e3000_2016.MorningSurvey')
        for days_ago in range(0, 7):
            daystart2 = daystart - timedelta(days=days_ago)
            print('   ', daystart2.date(), end='  ')
            print("N morning surveys: %s"%len(morning), end='  ')
            counts = collections.defaultdict(int)
            for D in morning:
                data = Data.objects.filter(device_id=D.device_id,
                                           ts__gt=daystart2,
                                           ts__lt=daystart2+timedelta(days=1),
                                           )
                counts[len(data)] += 1
                #print(now, daystart, daystart2)
                if (len(data) == 0
                    and daystart2+timedelta(hours=14) < now
                    and now < daystart2+timedelta(hours=16)
                   ):
                    print(D.user.email)

            print(sorted(counts.items()))


        # Evening surveys
        print('Evening surveys')
        morning = devices.filter(type='koota_e3000_2016.EveningSurvey')
        for days_ago in range(0, 7):
            daystart2 = daystart - timedelta(days=days_ago)
            print('   ', daystart2.date(), end='  ')
            print("N=%s"%len(morning), end='  ')
            counts = collections.defaultdict(int)
            for D in morning:
                data = Data.objects.filter(device_id=D.device_id,
                                           ts__gt=daystart2+timedelta(hours=18),
                                           ts__lt=daystart2+timedelta(hours=42),
                                           )
                counts[len(data)] += 1
            print(sorted(counts.items()))


