"""Data backend for Django
"""

from django.db.models import F, Sum

from .. import models

class Backend(object):
    def __init__(self, device=None):
        if isinstance(device, str):
            self.device_id = device
        else:
            self.device_id = device.device_id
    def count(self):
        return models.Data.objects.filter(device_id=self.device_id).count()
    def bytes_total(self):
        return models.Data.objects.filter(device_id=self.device_id).aggregate(sum=Sum(F('data_length')))['sum']
    def __getitem__(self, slc):
        qs = models.Data.objects.filter(device_id=self.device_id).order_by('ts')
        #import IPython ; IPython.embed()
        if qs.count() == 0:
            return None
        if isinstance(slc, int) and slc < 0:
            idx = -slc - 1   # -1=>0, -2=>1, etc
            return qs.reverse()[idx]
        return qs[slc]
