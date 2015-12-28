from django.shortcuts import render
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView

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

#
# User management
#
from django import forms
from django.contrib.auth.models import User
import django.contrib.auth as auth
class RegisterForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm password')
    email = forms.EmailField()
    def clean(self):
        if self.cleaned_data['password'] != self.cleaned_data['password2']:
            raise forms.ValidationError("Passwords don't match")
        # TODO: test for username alreay existing
        if User.objects.filter(username=self.cleaned_data['username']).exists():
            raise forms.ValidationError("Username already taken")

#from django.views.generic.edit import FormView
class RegisterView(FormView):
    template_name = 'koota/register.html'
    form_class = RegisterForm
    success_url = '/'

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.

        user = User.objects.create_user(form.cleaned_data['username'],
                                        form.cleaned_data['email'],
                                        form.cleaned_data['password'])
        user.save()
        # Log the user in
        user = auth.authenticate(username=form.cleaned_data['username'],
                                                password=form.cleaned_data['password'])
        auth.login(self.request, user)
        return super(RegisterView, self).form_valid(form)


#
# Device management
#
class DeviceListView(ListView):
    template_name = 'koota/device_list.html'
    model = models.Device
    allow_empty = True

    def get_queryset(self):
        if self.request.user.is_superuser:
            queryset = self.model.objects.all()
        else:
            queryset = self.model.objects.filter(user=self.request.user)
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
import urllib2
def device_qrcode(request, id):
    device = models.Device.objects.get(device_id=id)
    data = [('post', 'http://localhost:8000/post'),
            ('config', 'http://localhost:8000/config'),
            ('device_id', device.device_id),
            ('device_type', device.type), ]
    uri = 'koota:?'+'&'.join('%s=%s'%(k, urllib2.quote(v)) for k,v in data)
    img = qrcode.make(uri, border=4, box_size=2,
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
