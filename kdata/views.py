from django.shortcuts import render
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView


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


class DeviceListView(ListView):
    template_name = 'koota/device_list.html'
    model = models.Device
    allow_empty = True

    def get_queryset(self):
        if self.request.user.is_superuser:
            queryset = self.model.objects.all()
        else:
            queryset = self.model.objects.filter(user=self.request.usel)
        return queryset

class DeviceDetail(DetailView):
    template_name = 'koota/device_detail.html'
    model = models.Device
    def get_object(self):
        obj = self.model.objects.get(device_id=self.kwargs['id'])
        if self.request.user.is_superuser:
            return obj
        if obj.user != self.request.user:
            raise Http404
        return obj

import qrcode
import io
def device_qrcode(request, id):
    device = models.Device.objects.get(device_id=id)
    data = ['post=http://localhost:8000/post',
            'config=http://localhost:8000/config',
            'device_id=%s'%device.device_id,
            'device_type=%s'%device.type, ]
    img = qrcode.make('; '.join(data), border=4, box_size=3,
                     error_correction=qrcode.constants.ERROR_CORRECT_L)
    cimage = io.BytesIO()
    img.save(cimage)
    cimage.seek(0)
    return HttpResponse(cimage.getvalue(), content_type='image/png')



class DeviceCreate(CreateView):
    template_name = 'koota/device_create.html'
    model = models.Device
    fields = ['name', 'type']

    def form_valid(self, form):
        user = self.request.user
        if user.is_authenticated():
            form.instance.user = user
        # random device ID
        import random, string
        id_ = ''.join(random.choice(string.hexdigits[:16]) for _ in range(16))
        form.instance.device_id = id_
        return super(DeviceCreate, self).form_valid(form)
    def get_success_url(self):
        self.object.save()
        self.object.refresh_from_db()
        print 'id'*5, self.object.device_id
        return reverse('device-detail', kwargs=dict(id=self.object.device_id))
