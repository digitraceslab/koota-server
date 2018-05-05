"""Data backend for Django
"""

from datetime import datetime, timedelta

from django.db.models import F, Sum

from .. import models

class Backend(object):
    def __init__(self, device=None):
        if isinstance(device, str):
            raise RuntimeError("backends must not be initialized with devices")
        else:
            self.device = device
            self.device_id = device.device_id
    def count(self, slc=None, cache=True):
        """Count of number of rows (optionally within slice)"""
        if slc is None and cache:
            return self.device.n_packets
        if slc is not None:
            qs = self[slc]
            if qs is None: return 0
            return qs.count()
        return models.Data.objects.filter(device_id=self.device_id).count()
    def exists(self, slc=None):
        """Does any data exist?  (optionally within slice)"""
        if slc is not None:
            qs = self[slc]
            if qs is None: return 0
            return qs.exists()
        return models.Data.objects.filter(device_id=self.device_id).exists()
    def bytes_total(self):
        return models.Data.objects.filter(device_id=self.device_id).aggregate(sum=Sum(F('data_length')))['sum']
    def __getitem__(self, slc):
        qs = models.Data.objects.filter(device_id=self.device_id).order_by('ts')
        #import IPython ; IPython.embed()
        if not qs.exists():
            return None
        if isinstance(slc, int):
            if slc < 0:
                idx = -slc - 1   # -1=>0, -2=>1, etc
                return qs.reverse()[idx]
            return qs[slc]
        if isinstance(slc, slice):
            if isinstance(slc.start, datetime):
                qs = qs.filter(ts__gte=slc.start)
            if isinstance(slc.stop, datetime):
                qs = qs.filter(ts__lt=slc.stop)
        return qs
