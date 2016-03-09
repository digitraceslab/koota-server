from django.shortcuts import render
from django.core.exceptions import PermissionDenied
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
def post(request, device_id=None, device_class=None):
    #import IPython ; IPython.embed()
    if request.method != "POST":
        return JsonResponse(dict(ok=False, message="invalid HTTP method (must POST)"),
                            status=405)
    # Custom device code, if available.
    results = { }
    if device_class is not None:
        results = device_class.post(request)

    # Find device_id.  Try different things until found.
    if device_id is not None:
        pass
    elif 'device_id' in results:  # results from custom device code
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
        logging.warning("Invalid device_id: %r"%device_id)
        return JsonResponse(dict(ok=False, error="Invalid device_id",
                                 device_id=device_id),
                            status=400, reason="Invalid device_id")
    # Return an error if device checkdigits do not work out.  Since
    # the server may not have a complete list of all registered
    # devices, we need some way early-reject invalid device IDs.
    # Purpose is to protect against user misentering it, but not
    # attacks.
    if not util.check_checkdigits(device_id):
        logging.warning("Invalid device_id checkdigits: %r"%device_id)
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
    row.data_length = len(json_data)
    row.save()
    logging.debug("Saved data from device_id=%r"%device_id)

    # HTTP response
    if 'response' in results:
        return results['response']
    return JsonResponse(dict(ok=True))
def save_data(data, device_id, request=None):
    """Save data programatically, as in not in a HTTP request.

    This is a stripped down copy of POST."""
    if not util.check_checkdigits(device_id):
        raise ValueError("Invalid device ID: checkdigits invalid.")
    remote_ip = '127.0.0.1'
    if request is not None:
        remote_ip = request.META['REMOTE_ADDR']
    row = models.Data(device_id=device_id, ip=remote_ip, data=data)
    row.data_length = len(data)
    row.save()

@csrf_exempt
def log(request, device_id=None, device_class=None):
    return JsonResponse(dict(status='success'))

@csrf_exempt
def config(request, device_class=None):
    """Config dict data.

    This is a dummy URL that has no content, but at least will not 404.
    """
    from django.conf import settings
    from codecs import encode
    cert_der = encode(open(settings.KOOTA_SSL_CERT_DER,'rb').read(), 'base64')
    cert_pem = encode(open(settings.KOOTA_SSL_CERT_PEM,'rb').read(), 'base64')
    return JsonResponse(dict(selfsigned_cert_der=cert_der.decode('ascii'),
                             selfsigned_cert_pem=cert_pem.decode('ascii'),
                         ))

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

    def dispatch(self, request, *args, **kwargs):
        """Handle anonymous users by redirecting to main"""
        if request.user.is_anonymous():
            return HttpResponseRedirect(reverse('main'))
        return super(DeviceListView, self).dispatch(request, *args, **kwargs)
    def get_queryset(self):
        # fixme: return "not possible" if not logged in
        if self.request.user.is_superuser:
            queryset = self.model.objects.all().order_by('_public_id')
        else:
            queryset = self.model.objects.filter(user=self.request.user).order_by('_public_id')
        return queryset

class DeviceConfig(UpdateView):
    template_name = 'koota/device_config.html'
    model = models.Device
    fields = ['name', 'type', 'label', 'comment']

    def get_object(self):
        """Get device model object, testing permissions"""
        obj = self.model.get_by_id(self.kwargs['public_id'])
        if not util.has_device_perm(self.request, obj):
            raise PermissionDenied("No permission for device")
        return obj
    def get_context_data(self, **kwargs):
        """Override template context data with special instructions from the DeviceType object."""
        context = super(DeviceConfig, self).get_context_data(**kwargs)
        device_class = context['device_class'] = self.object.get_class()
        context.update(device_class.configure(device=self.object))
        device_data = models.Data.objects.filter(device_id=self.object.device_id)
        context['data_number'] = device_data.count()
        if context['data_number'] > 0:
            context['data_earliest'] = device_data.order_by('ts').first().ts
            context['data_latest'] = device_data.order_by('-ts').first().ts
            context['data_latest_data'] = device_data.order_by('-ts').first().data
        return context
    def get_success_url(self):
        return reverse('device-config', kwargs=dict(public_id=self.object.public_id))

import qrcode
import io
from six.moves.urllib.parse import quote as url_quote
from django.conf import settings
def device_qrcode(request, public_id):
    device = models.Device.get_by_id(public_id)
    if not util.has_device_perm(request, device):
        raise PermissionDenied("No permission for device")
    #device_class = devices.get_class(self.object.type).qr_data(device=device)
    url_base = "{0}://{1}".format(request.scheme, settings.POST_DOMAIN)
    data = [('post', url_base+reverse('post')),
            ('config', url_base+'/config'),
            ('device_id', device.device_id),
            ('public_id', device.public_id),
            ('secret_id', device.secret_id),
            ('device_type', device.type),
            ('selfsigned_post', 'https://'+settings.POST_DOMAIN_SS+reverse('post')),
            ('selfsigned_cert_der_sha256', settings.KOOTA_SSL_CERT_DER_SHA256),
            ('selfsigned_cert_pem_sha256', settings.KOOTA_SSL_CERT_PEM_SHA256),
             ]
    uri = 'koota:?'+'&'.join('%s=%s'%(k, url_quote(v)) for k,v in data)
    img = qrcode.make(uri, border=4, box_size=2,
                     error_correction=qrcode.constants.ERROR_CORRECT_L)
    cimage = io.BytesIO()
    img.save(cimage)
    cimage.seek(0)
    return HttpResponse(cimage.getvalue(), content_type='image/png')



class DeviceCreate(CreateView):
    template_name = 'koota/device_create.html'
    _model = models.Device
    fields = ['name', 'type', 'label', 'comment']

    @property
    def model(self):
        model = self._model
        if self.request.method == 'POST':
            device_class = self.request.POST.get('type', None)
            if device_class is not None:
                dbmodel = devices.get_class(device_class).dbmodel
                if dbmodel is not None:
                    model = dbmodel
        return model
    #def get_form_class(*args, **kwargs):
    #    """Get form class, taking into account different types of db Devices.
    #
    #    The whole point of this is that not every device should be a
    #    models.Device.  For example, surveys are instances of
    #    models.SurveyDevice.  Instead of needing to create this
    #    ourselves in the devices._Device.create_hook, and link them,
    #    we can create from the start.
    #    """
    #    from django.forms import modelform_factory
    #    # Default model
    #    model = self.model
    #    # Override model, if we have been POSTed to, and we know the
    #    # expected device_type, and that class overrides our database
    #    # model.
    #    if self.request.method == 'POST':
    #        device_class = self.request.POST.get('type', None)
    #        if device_class is not None:
    #            dbmodel = devices.get_class(device_class).dbmodel
    #            if dbmodel is not None:
    #                model = dbmodel
    #    # The following two lines are taken from
    #    # ModelFormMixin.get_form_class and FormMixin.get_form.
    #    form_class = modelform_factory(model, fields=self.fields)
    #    form = form_class(**self.get_form_kwargs())
    def get_form(self, *args, **kwargs):
        """Get the form and override device choices based on user.
        """
        form = super(DeviceCreate, self).get_form(*args, **kwargs)

        # This gets only the standard choices, that all users should
        # have.
        choices = devices.get_choices()
        # Extend to extra devices that this user should have.  TODO:
        # make this user-dependent.
        choices.extend([('kdata.survey.TestSurvey1', 'Test Survey #1'),])
        form.fields['type'].choices = choices
        form.fields['type'].widget.choices = choices
        return form
    def form_valid(self, form):
        """Create the device."""
        user = self.request.user
        if user.is_authenticated():
            form.instance.user = user
        else:
            raise Http404   # XXX
        device_class = devices.get_class(form.cleaned_data['type'])
        device_class.create_hook(form.instance, user=user)
        return super(DeviceCreate, self).form_valid(form)
    def get_success_url(self):
        """Redirect to device config page."""
        self.object.save()
        self.object.refresh_from_db()
        #print 'id'*5, self.object.device_id
        return reverse('device-config', kwargs=dict(public_id=self.object.public_id))
