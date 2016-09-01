from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

# Create your views here.

from kdata import models
import kdata.permissions
import kdata.views_data

def device_detail(request, public_id):
    device = models.Device.get_by_id(public_id)
    if not kdata.permissions.has_device_permission(request, device):
        return JsonResponse({}, status=403)

    response = { }
    device_cls = device.get_class()
    device_data = models.Data.objects.filter(device_id=device.device_id)
    response['data_count'] = device_data.count()
    response['data_first_ts'] = device_data.order_by('ts').first().ts
    response['data_last_ts'] = device_data.order_by('-ts').first().ts
    response['converers'] = [ c.name() for c in device_cls.converters]

    return JsonResponse(response)


def device_data(request, public_id, converter, format='json'):
    device = models.Device.get_by_id(public_id)
    if not kdata.permissions.has_device_permission(request, device):
        return JsonResponse({}, status=403)
    return kdata.views_data.device_data(request, public_id=public_id,
                                        converter=converter, format=format)

