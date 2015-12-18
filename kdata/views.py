from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt


import json
from . import models

# Create your views here.


@csrf_exempt
def post(request):
    #import IPython ; IPython.embed()
    if request.method == "POST":
        print request.META
        if 'HTTP_DEVICE_ID' in request.META:
            device_id = request.META['HTTP_DEVICE_ID']
        elif 'device_id' in request.POST:
            device_id = request.POST['device_id']
        elif 'device_id' in request.GET:
            device_id = request.GET['device_id']
        else:
            raise ValueError('No device ID')

        if 'data' in request.POST:
            json_data = request.POST['data']
        else:
            json_data = request.body

        row = models.Data(device_id=device_id, ip=request.META['REMOTE_ADDR'], data=json_data)
        row.save()

    return HttpResponse(json.dumps(dict(ok=True)),
                        content_type="application/json")
