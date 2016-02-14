from django.shortcuts import render
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.db.models import Func, F, Q, Sum #, RawSQL
from django.db.models.functions import Length

from math import log
from datetime import timedelta
import json

from . import models
from . import devices
from . import util

def human_bytes(x):
    """Add proper binary prefix to number in bytes, returning string"""
    unit_list = [ 'B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    exponent = int(log(x, 1024))
    quotient = x / 1024**exponent
    return '%6.2f %-3s'%(quotient, unit_list[exponent])

def stats(request):
    """Produce basic stats on database usage.

    TODO: Add caching once this gets used enough.
    """
    #if not (request.user.is_staff):
    #    return HttpResponse(status=403)
    from django.db import connection
    c = connection.cursor()
    stats = [ ]

    # This is a list of time intervals to compute stats for.  Time
    # ranges are (now-startatago) -- (now-startatago-duration)
    for description, duration, startatago in [
             ("Last month",            timedelta(days=28),      timedelta(0)),
             ("Last week",             timedelta(days=7),       timedelta(0)),
             ("Second-to-last day",    timedelta(days=1),       timedelta(1)),
             ("Last day",              timedelta(days=1),       timedelta(0)),
             ("Second-to-last hour",   timedelta(seconds=3600), timedelta(0,3600)),
             ("Last hour",             timedelta(seconds=3600), timedelta(0)),
            ]:
        end = timezone.now()-startatago
        start = end-duration
        def to_per_day(x):
            """Convert a number of bytes in 'duration' to bytes/day"""
            return x / duration.total_seconds() * 60*60*24


        stats.append('='*40)
        stats.append(description)
        stats.append('From %s ago to %s ago (total %s)'%(startatago+duration, startatago, duration))
        stats.append('')
        stats.append('Data packet count: %s'%models.Data.objects.filter(ts__gt=start, ts__lte=end).count())

        # Unique users in time period
        c.execute("SELECT count(distinct user_id) FROM kdata_data LEFT JOIN kdata_device USING (device_id) "
                  "WHERE ts>%s and ts<=%s",
                  [start, end])
        count = c.fetchone()[0]
        stats.append('Unique users: %s'%count)

        # Unique devices in time period
        stats.append('Unique devices: %s'%(models.Data.objects.filter(ts__gt=start, ts__lte=end).distinct('device_id').count()))

        # Devices per type in time period
        c.execute("SELECT type, count(distinct device_id) FROM kdata_data LEFT JOIN kdata_device USING (device_id) "
                  "WHERE ts>%s and ts <=%s GROUP BY type ORDER BY type",
                  [start, end])
        device_counts = { }
        for device_type, count in c:
            stats.append('    %-16s: %s'%(device_type, count))
            device_counts[device_type] = count


        if duration <= timedelta(days=2):

            # Data per day
            size = models.Data.objects.filter(ts__gt=start, ts__lte=end).aggregate(sum=Sum(Length('data')))['sum']
            stats.append('Total data size: %s/day'%human_bytes(to_per_day(size)))

            # Amount of data, per device.
            c.execute("SELECT type, sum(length(data)) FROM kdata_data LEFT JOIN kdata_device USING (device_id) "
                      "WHERE ts>%s and ts <=%s GROUP BY type ORDER BY type",
                      [start, end])
            for device_type, size in c:
                # Have both per day, and per device.  If the device
                # type is not found in device_counts, default to -1.
                # This makes an answer that doesnt' make sense
                # (negative), but a) shouldn't happen b) if it
                # happens, it won't pass undetected.
                stats.append('    %-16s: %s/day    %s/day/device'%(
                    device_type, human_bytes(to_per_day(size)),
                    human_bytes(to_per_day(size/device_counts.get(device_type, -1)))
                ))


        stats.append('')

    return HttpResponse('\n'.join(stats), content_type='text/plain')
