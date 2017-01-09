from django import forms
from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.db.models import Func, F, Q, Sum #, RawSQL
from django.db.models.functions import Length
from django.template.response import TemplateResponse

from math import log
from datetime import timedelta
import hashlib
import json
import os

from . import models
from . import devices
from . import group
from . import logs
from . import util
from .util import human_bytes

import logging
logger = logging.getLogger(__name__)






#
# User management
#
from django import forms
import django.contrib.auth as auth
class RegisterForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm password')
    email = forms.EmailField()
    def clean(self):
        User = auth.get_user_model()
        if self.cleaned_data['password'] != self.cleaned_data['password2']:
            raise forms.ValidationError("Passwords don't match")
        # TODO: test for username alreay existing
        if User.objects.filter(username=self.cleaned_data['username']).exists():
            raise forms.ValidationError("Username already taken")
        # Do the django standard password validation
        auth.password_validation.validate_password(
            self.cleaned_data.get('password2'))

#from django.views.generic.edit import FormView
class RegisterView(FormView):
    template_name = 'koota/register.html'
    form_class = RegisterForm
    success_url = '/'

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        User = auth.get_user_model()

        user = User.objects.create_user(form.cleaned_data['username'],
                                        form.cleaned_data['email'],
                                        form.cleaned_data['password'])
        user.save()
        logs.log(self.request, 'user registration',
                 obj='user='+user.username,
                 op='register')
        # Log the user in
        user = auth.authenticate(username=form.cleaned_data['username'],
                                                password=form.cleaned_data['password'])
        auth.login(self.request, user)
        return super(RegisterView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super(RegisterView, self).get_context_data(**kwargs)
        User = auth.get_user_model()
        for _ in range(10):
            random_username = hashlib.sha256(os.urandom(32)).hexdigest()[:6]
            if not User.objects.filter(username=random_username).exists():
                context['random_username'] = random_username
                break
        return context




# One-time password (TOTP, one-factor auth) related views.
import django_otp.forms
from django_otp.forms import OTPAuthenticationForm
class KootaOTPAuthenticationForm(OTPAuthenticationForm):
    """OTP auth form that allows auth to be optional.  This is mostly
    taken from the django-otp, with the last part commented out.

    """
    otp_token = forms.CharField(required=False, label="2FA Token (optional)")
    def clean_otp(self, user):
        """Process the otp_* fields

        Like django_otp.forms.OTPAuthenticationForm, but make OTP
        authentication optional.  No error is raised if it is not
        present, but the user is not verified.
        """
        if user is None:
            return

        device = self._chosen_device(user)
        token = self.cleaned_data.get('otp_token')

        user.otp_device = None

        if self.cleaned_data.get('otp_challenge'):
            #error = self._handle_challenge(device)
            pass
        elif token:
            user.otp_device = self._verify_token(user, token, device)
            if not user.otp_device:
                raise forms.ValidationError("2FA token is wrong.")
            messages.add_message(self.request, messages.SUCCESS, '2FA succeeded')


        #if user.otp_device is None:
        #    self._update_form(user)
        #
        #    if error is None:
        #        error = forms.ValidationError(_('Please enter your OTP token'))
        #
        #    raise error


from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache
#from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import login as django_login
@never_cache
@sensitive_post_parameters()
def login(request, *args, **kwargs):
    """Login view redirecting to the subject's expected login page."""
    ret = django_login(request, *args, **kwargs)
    if not request.user.is_anonymous:
        login_view_name = group.user_main_page(request.user)
        if login_view_name is not None:
            request.session['login_view_name'] = login_view_name
            return HttpResponseRedirect(reverse(login_view_name))
    return ret





from django import forms
class OTPVerifyForm(forms.Form):
    otp_token = forms.CharField()
def otp_config(request):
    """View to manage two-factor (OTP) auth.

    - Show QR code if the device is not confirmed.
    - Allow user to confirm their code, if it not confirmed.  Then
      mark the device as confirmed.
    - If device is already confirmed, then don't show the QR code
      since that would risk it being lost.  However, do show it if the
      user has logged in using OTP (user.is_verified) and you have
      just verified your token.
    """
    if request.user.is_anonymous:
        return HttpResponse("Forbidden: must be logged in", status=403)
    context = c = { }
    # Get devices
    devices = list(django_otp.devices_for_user(request.user, confirmed=None)) # conf
    # and unconf If there is more than one device, log an error.
    # FIXME: this does not support one-time passwords and multiple
    # devices yet.
    if len(devices) > 1:
        logger.critical("User has more than one OTP device: %s", request.user.id)
    # If the user has no devices, create one now.
    if len(devices) == 0:
        from django_otp.plugins.otp_totp.models import TOTPDevice
        device = TOTPDevice(user=request.user,
                            confirmed=False,
                            name='Auto device')
        device.save()
    # If everything is normal, then select the user's device.
    else:
        device = devices[0]
        c['confirmed'] = device.confirmed

    # Attempt to verify code or confirm the unconfirmed device.
    if request.method == 'POST':
        form = c['otp_form'] = OTPVerifyForm(request.POST)
        form.is_valid()  # validate form - validation is null op.
        success = c['success'] = device.verify_token(form.cleaned_data['otp_token'])
        # Success: if the device is unconfirmed, then confirm it.  It
        # can then be used for logging in, etc.
        if success:
            # Do device confirmation
            if not device.confirmed:
                device.confirmed = True
                device.save()
                c['confirmed'] = device.confirmed
            message = c['message'] = 'Code verified.'
        else:
            message = c['message'] = 'Code not successful.'
        # Note that there is no other special action on success.

        # Reset the form - don't display code again or anything.
        form = c['otp_form'] = OTPVerifyForm()
    else:
        form = c['otp_form'] = OTPVerifyForm()

    return TemplateResponse(request, 'koota/otp.html', context)


import base64
import qrcode
import io
from six.moves.urllib.parse import quote as url_quote
def otp_qr(request):
    """Produce the HOTP QR code for this user.

    FIXME: this will generate the code if user.is_verified, but does
    not check for valid code on the otp_config page.

    """
    if request.user.is_anonymous:
        return HttpResponse("Forbidden: must be logged in", status=403)
    # Get the right device.  Assume that there is only one per user...
    devices = list(django_otp.devices_for_user(request.user, confirmed=None))
    device = next(iter(devices)) # Assume only one device
    if device.confirmed and not request.user.is_verified():
        return HttpResponse('Can not get QR code (confirmed, login not verified)',
                            status=403, content_type='text/plain')

    # Generate the QR code and return.
    uri = 'otpauth://totp/{0}?secret={1}'.format(
        'Koota-'+request.user.username,
        base64.b32encode(device.bin_key).decode('utf-8'))
    img = qrcode.make(uri, border=4, box_size=2,
                     error_correction=qrcode.constants.ERROR_CORRECT_L)
    cimage = io.BytesIO()
    img.save(cimage)
    cimage.seek(0)
    return HttpResponse(cimage.getvalue(), content_type='image/png')





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
            size = models.Data.objects.filter(ts__gt=start, ts__lte=end).aggregate(sum=Sum(F('data_length')))['sum']
            stats.append('Total data size: %s/day'%human_bytes(to_per_day(size)))

            # Amount of data, per device.
            c.execute("SELECT type, sum(data_length) FROM kdata_data LEFT JOIN kdata_device USING (device_id) "
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
