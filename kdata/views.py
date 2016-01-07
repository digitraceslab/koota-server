from django.shortcuts import render
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView

import json
from . import models
from . import devices
from . import util

import logging
log = logging.getLogger(__name__)

# Create your views here.


@csrf_exempt
def post(request, device_class=None):
    #import IPython ; IPython.embed()
    if request.method != "POST":
        return JsonResponse(dict(ok=False, message="invalid HTTP method"),
                            status=403)
    # Custom device code, if available.
    results = { }
    if device_class is not None:
        results = device_class.post(request)

    # Find device_id.  Try different things until found.
    if 'device_id' in results:  # results from custom device code
        device_id = results['device_id']
    elif 'HTTP_DEVICE_ID' in request.META:
        device_id = request.META['HTTP_DEVICE_ID']
    elif 'device_id' in request.GET:
        device_id = request.GET['device_id']
    elif 'device_id' in request.POST:
        device_id = request.POST['device_id']
    else:
        return JsonResponse(dict(ok=False, error="No device_id provided"),
                            status=400, reason="No device_id provided")
    try:
        int(device_id, 16)
    except:
        logging.info("Invalid device_id: %r"%device_id)
        return JsonResponse(dict(ok=False, error="Invalid device_id",
                                 device_id=device_id),
                            status=400, reason="Invalid device_id")
    # Return an error if device checkdigits do not work out.  Since
    # the server may not have a complete list of all registered
    # devices, we need some way early-reject invalid device IDs.
    # Purpose is to protect against user misentering it, but not
    # attacks.
    if not util.check_checkdigits(device_id):
        return JsonResponse(dict(ok=False, error='Invalid device_id checkdigits',
                                 device_id=device_id),
                            status=400, reason="Invalid device_id checkdigits")

    # Find the data to store
    if 'data' in results:  # results from custom device code
        json_data = results['data']
    elif 'data' in request.POST:
        json_data = request.POST['data']
    else:
        json_data = request.body

    # Store data in DB.  (Uses django models for now, but should
    # be made more efficient later).
    row = models.Data(device_id=device_id, ip=request.META['REMOTE_ADDR'], data=json_data)
    row.save()
    logging.info("Saved data from device_id=%r"%device_id)

    # HTTP response
    if 'response' in results:
        return results['response']
    return JsonResponse(dict(ok=True))

@csrf_exempt
def config(request, device_class=None):
    """Config dict data.

    This is a dummy URL that has no content, but at least will not 404.
    """
    from django.conf import settings
    cert_der = open(settings.KOOTA_SSL_KEY).read().encode('base64')
    return JsonResponse(dict(cert_der=cert_der))

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
        """Get device model object, testing permissions"""
        obj = self.model.objects.get(device_id=self.kwargs['device_id'])
        if self.request.user.is_superuser:
            return obj
        if obj.user != self.request.user:
            raise Http404
        return obj
    def get_context_data(self, **kwargs):
        """Override template context data with special instructions from the DeviceType object."""
        context = super(DeviceDetail, self).get_context_data(**kwargs)
        try:
            context.update(devices.get_class(self.object.type).configure(device=self.object))
        except devices.NoDeviceTypeError:
            pass
        device_data = models.Data.objects.filter(device_id=self.kwargs['device_id'])
        context['data_number'] = device_data.count()
        if context['data_number'] > 0:
            context['data_earliest'] = device_data.order_by('ts').first().ts
            context['data_latest'] = device_data.order_by('-ts').first().ts
            context['data_latest_data'] = device_data.order_by('-ts').first().data
        return context

import qrcode
import io
import urllib2
from django.conf import settings
def device_qrcode(request, device_id):
    device = models.Device.objects.get(device_id=device_id)
    #device_class = devices.get_class(self.object.type).qr_data(device=device)
    url_base = "{0}://{1}".format(request.scheme, settings.POST_DOMAIN)
    data = [('post', url_base+reverse('post')),
            ('config', url_base+'/config'),
            ('device_id', device.device_id),
            ('device_type', device.type),
            ('cert_der_sha256', settings.KOOTA_SSL_KEY_SHA256)
             ]
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
        id_ = ''.join(random.choice(string.hexdigits[:16]) for _ in range(14))
        id_ = util.add_checkdigits(id_)
        form.instance.device_id = id_
        return super(DeviceCreate, self).form_valid(form)
    def get_success_url(self):
        self.object.save()
        self.object.refresh_from_db()
        print 'id'*5, self.object.device_id
        return reverse('device-detail', kwargs=dict(device_id=self.object.device_id))
