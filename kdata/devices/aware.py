"""AWARE devices

http://www.awareframework.com/
"""

from datetime import timedelta
from hashlib import sha256
import json  # use stdlib json for pretty formatting
from json import loads, dumps
import logging
import textwrap
from six.moves.urllib import parse as urlparse

from django.conf import settings
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, UnreadablePostError
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .. import devices
from .. import converter
from .. import exceptions
from .. import group
from .. import logs
from .. import models
from .. import permissions
from .. import util
from .. import views as kviews

LOGGER = logging.getLogger(__name__)

AWARE_DOMAIN = getattr(settings, 'AWARE_DOMAIN', 'https://aware.koota.zgib.net')
AWARE_DOMAIN_SIGNED = getattr(settings, 'AWARE_DOMAIN_signed', 'https://data.koota.cs.aalto.fi')
PACKET_CHUNK_SIZE = 1000
AWARE_QRCODE_FORMAT = getattr(settings, 'AWARE_QRCODE_FORMAT', 'basic')
AWARE_CRT_URL = getattr(settings, 'AWARE_CRT_URL', "https://data.koota.cs.aalto.fi/static/server-aware.crt")
AWARE_CRT_PATH = getattr(settings, 'AWARE_CRT_PATH', "/srv/koota/static/server.crt")


from django.utils.html import escape
from django.utils.safestring import mark_safe

@devices.register_device(default=True, alias="Aware",
                         aliases=['kdata.devices.aware.Aware'])
class Aware(devices.BaseDevice):
    """Basic Python class handling Aware devices"""
    desc = 'Aware device'
    AWARE_DOMAIN = AWARE_DOMAIN
    converters = devices.BaseDevice.converters + [
        converter.AwareUploads,
        converter.AwareTimestamps,
        converter.AwareTableData,
        converter.AwarePacketTimeRange,
        converter.AwareDataSize,
        converter.AwareRecentDataCounts,
        converter.JsonPrettyHtmlData,

        converter.AwareAccelerometer,
        converter.AwareAmbientNoise,
        converter.AwareAppNotifications,
        converter.AwareApplicationCrashes,
        converter.AwareApplicationNotifications,
        converter.AwareBattery,
        converter.AwareBluetooth,
        converter.AwareCalls,
        converter.AwareGravity,
        converter.AwareGyroscope,
        converter.AwareLight,
        converter.AwareLinearAccelerometer,
        converter.AwareLocation,
        converter.AwareMagnetometer,
        converter.AwareMessages,
        converter.AwareNetwork,
        converter.AwareNetworkTraffic,
        converter.AwareRotation,
        converter.AwareScreen,
        converter.AwareSensorWifi,
        converter.AwareTelephony,
        converter.AwareWifi,
    ]
    config_instructions_template = textwrap.dedent("""\
    <ol>
    <li><a href="{{install_url}}">Install the AWERE app from here</a>.</li>
    <li>See the <a href="https://github.com/CxAalto/koota-server/wiki/Aware">instructions on the github wiki</a>.
    <li>URL is {{study_url}}</li>
    </ol>

    <img src="{{qrcode_img_path}}"></img>

    {% if pretty_aware_config %}
    <p>Your raw config is:
    {{ pretty_aware_config }}</p>
    {% endif %}

    """)
    install_url = 'http://play.google.com/store/apps/details?id=com.aware.phone'
    def config_context(self):
        url_ = self.qrcode_url()
        qrcode_img_path = reverse('aware-register-qr',
                                  kwargs=dict(public_id=self.dbrow.public_id))
        config = get_user_config(self)
        # pylint: disable=redefined-variable-type
        config = json.dumps(config, sort_keys=True, indent=1, separators=(',',': '))
        config = mark_safe('<pre>'+escape(config)+'</pre>')
        context = dict(study_url=url_,
                       qrcode_img_path=qrcode_img_path,
                       pretty_aware_config=config,
                       install_url=self.install_url)
        return context
    def webservice_url(self):
        """URL for webservice."""
        secret_id = self.data.secret_id
        url_ = reverse('aware-register', kwargs=dict(indexphp='index.php',
                                                    secret_id=secret_id,
                                                    ))
        url_ = self.AWARE_DOMAIN+url_
        return url_
    def qrcode_url(self):
        """Return the data contained in the QRcode.

        This is the data used for registration."""
        url_ = self.webservice_url()
        url_ = urlparse.urlparse(url_)
        queryparams = { }
        if AWARE_QRCODE_FORMAT == 'embed':
            crt = open(AWARE_CRT_PATH, 'rb').read()
            crt_sha256 = sha256(crt).hexdigest()
            queryparams = dict(crt=crt,
                               crt_sha256=crt_sha256)
        elif AWARE_QRCODE_FORMAT == 'url':
            crt = open(AWARE_CRT_PATH, 'rb').read()
            crt_url = AWARE_CRT_URL
            crt_sha256 = sha256(crt).hexdigest()
            queryparams = dict(crt_url=crt_url,
                               crt_sha256=crt_sha256)
        url_ = url_._replace(query=urlparse.urlencode(queryparams))
        url_ = url_.geturl()
        return url_

@devices.register_device(default=True, alias='AwareValidCert',
                         aliases=['kdata.devices.aware.AwareValidCert'])
class AwareValidCert(Aware):
    """AWARE device, using a valid cert endpoint"""
    desc = 'Aware device (iOS)'
    AWARE_DOMAIN = AWARE_DOMAIN_SIGNED
    install_url = 'https://itunes.apple.com/us/app/aware-client-ios/id1065978412'




# This is our standard JSON configuration.
# Sensor settings:
# https://github.com/denzilferreira/aware-server/blob/master/aware_dashboard.sql#L298
BASE_CONFIG = dict(
    sensors=dict(
        status_mqtt=False,
        #mqtt_server='aware.koota.zgib.net',
        #mqtt_port=8883,
        #mqtt_keep_alive=600,
        #mqtt_qos=2,
        #mqtt_username='x',         # overridden
        #mqtt_password='y',         # overridden
        study_start=1464728400000,  # 1 june 2016 00:00
        #webservice_server='https://aware.koota.zgib.net/'+xxx,
        status_webservice=True,
        frequency_webservice=15,
        webservice_simple=True,     # don't /create_table
        webservice_remove_data=True,# delete data after uploading, no /latest
        webservice_stateless=True,  # don't /create_table
        webservice_only=True,       # delete data after uploading, no /latest
        webservice_silent=True,
        #database_location="public",
        key_strategy="once",

        # meta-options
        frequency_clean_old_data=4,  # (0 = never, 1 = weekly, 2 = monthly)
        #study_id=1,            # If this is set to anything, not user modifiable
        status_crashes=True,
        status_esm=False,
        #webservice_wifi_only

        # Sensor config
        status_battery=True,
        status_screen=True,
        #status_wifi=False,
        #frequency_wifi=300,
        #status_bluetooth=False,
        #frequency_bluetooth=300,
        #status_light=True,
        status_accelerometer=False,
        frequency_accelerometer=1000000, #microseconds
        #frequency_light=10000000,  # microseconds
        #frequency_timezone=43200  # seconds
    ))
for name in ("accelerometer", "barometer", "gravity", "gyroscope",
                 "light", "linear_accelerometer", "magnetometer",
                 "proximity", "rotation", "temperature"):
    BASE_CONFIG['sensors']['threshold_'+name] = 0.05

def aware_to_string(value):
    """AWARE requires setting values to be string.  Convert them"""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
def get_user_config(device):
    """Get a device's remote configuration.

    return value: Python dict object."""
    import copy
    config = copy.deepcopy(BASE_CONFIG)
    #config['sensors']['mqtt_username'] = device.data.public_id
    #config['sensors']['mqtt_password'] = device.data.secret_id
    if device.data.ts_create is not None:
        ts_create = device.data.ts_create.timestamp()
    else:
        ts_create = (timezone.now()-timedelta(days=1)).timestamp()
    # AWARE parses study_start as int!
    config['sensors']['study_start'] = int(ts_create*1000)
    config['sensors']['webservice_server'] = device.webservice_url()
    config['sensors']['status_webservice'] = True

    # This is the difference between a user being able to edit a
    # config themselves and not.
    #config['sensors']['study_id'] = 1

    # Site-global config
    if hasattr(settings, 'AWARE_CONFIG'):
        util.recursive_copy_dict(settings.AWARE_CONFIG, config)

    # Get the user's group config
    user = device.data.user
    user_config = group.user_merged_group_config(user)
    if 'aware_config' in user_config:
        util.recursive_copy_dict(user_config['aware_config'], config)

    # Device-specific config
    if 'aware-config' in device.data.attrs:
        util.recursive_copy_dict(json.loads(device.data.attrs['aware-config']), config)

    # Aware requires it as a list of dicts.
    sensors = [dict(setting=k, value=aware_to_string(v))
               for k,v in config['sensors'].items()]

    config = [{'sensors': sensors}]
    return config



#
# AWARE API
#
@csrf_exempt
def register(request, secret_id, indexphp=None):
    """Initial URL that a device hits to register."""
    # pylint: disable=unused-argument
    device = models.Device.get_by_secret_id(secret_id)
    device_cls = device.get_class()
    config = get_user_config(device_cls)

    LOGGER.info("aware register: %s %s", request.POST, secret_id)
    # We have no other operation, basic study configuration.
    data = request.POST
    if 'device_id' in data:
        passwd = util.hash_mosquitto_password(device.secret_id)
        device.attrs['aware-device-uuid'] = data['device_id']
        device.attrs['aware-device-passwd_pbkdf2'] = passwd
        logs.log(request, 'AWARE device registration',
                 obj=device.public_id, op='register')

        # Save registration data
        data_to_save = dict(table="register",
                            data=json.dumps(request.POST),
                            version=1)
        data_to_save = dumps(data_to_save)
        kviews.save_data(data_to_save, device_id=device.device_id, request=request)
        device.attrs['aware-last-ts-%s'%"register"] = timezone.now().timestamp()*1000

        return JsonResponse(config, safe=False)
    # error return.
    return JsonResponse(dict(error="You should scan this with the Aware app.",
                             config=config),
                        status=400, reason="Scan with app")

@csrf_exempt
def create_table(request, secret_id, table, indexphp=None):
    """AWARE client creating table.  This is nullop for us."""
    # pylint: disable=unused-argument
    # {'device_id': ['2e66087d-4afb-4a64-9316-67d737e21998'],
    #  'fields': ["_id integer primary key autoincrement,timestamp real default 0,device_id text default '',topic text default '',message text default '',status integer default 0,UNIQUE(timestamp,device_id)"]}
    #data = request.POST
    return HttpResponse(status=200, reason="We don't sync tables")

@csrf_exempt
def latest(request, secret_id, table, indexphp=None):
    """AWARE client getting most recent data point.

    Unlike the AWARE server, we don't return the latest row (that
    would send data out), but we get the stored timestamp of latest
    data and return that.
    """
    # pylint: disable=unused-argument
    device = models.Device.get_by_secret_id(secret_id)

    # Return the latest timestamp in our database.  Aware uses
    # this to know what data needs to be sent.
    ts = device.attrs.get('aware-last-ts-%s'%table, 0)
    if ts == 0:
        return JsonResponse([], safe=False)
    ts = float(ts)
    response = [dict(timestamp=ts,
                     double_end_timestamp=ts,
                     double_esm_user_answer_timestamp=ts)]
    if 'nonce' in request.POST:
        response[0]['nonce'] = request.POST['nonce']
    return JsonResponse(response, safe=False)

from django.db import transaction
@csrf_exempt
def insert(request, secret_id, table, indexphp=None):
    """AWARE client requesting data to be saved.

    TODO: this function is slowed down by
    urllib.parse.unquote_to_bytes.  When creating request.POST, it has
    to call that, and JSON urlencoded has lots of %nn in it, so this
    is slow.
    """
    # pylint: disable=unused-argument
   # Here is the profile.  This is for about 2MB of data, for the
    # 'accelerometer' sensor:
    #    ncalls  tottime  percall  cumtime  percall filename:lineno(function)
    #     1    0.000    0.000    1.439    1.439 {built-in method builtins.exec}
    #     1    0.000    0.000    1.439    1.439 <string>:1(<module>)
    #     1    0.009    0.009    1.439    1.439 aware.py:270(insert2)
    #     2    0.000    0.000    1.232    0.616 wsgi.py:126(_get_post)
    #     1    0.000    0.000    1.232    1.232 request.py:282(_load_post_and_files)
    #     1    0.000    0.000    1.205    1.205 request.py:374(__init__)
    #     1    0.000    0.000    1.199    1.199 http.py:322(limited_parse_qsl)
    #     4    0.019    0.005    1.105    0.276 parse.py:527(unquote)
    #     1    0.539    0.539    1.062    1.062 parse.py:495(unquote_to_bytes)
    #720914    0.310    0.000    0.310    0.000 {method 'append' of 'list' objects}
    #     1    0.135    0.135    0.135    0.135 {method 'join' of 'bytes' objects}
    #     2    0.109    0.054    0.109    0.054 {method 'split' of '_sre.SRE_Pattern' objects}
    #    21    0.000    0.000    0.098    0.005 manager.py:84(manager_method)
    #    10    0.000    0.000    0.082    0.008 views.py:109(save_data)

    device = models.Device.get_by_secret_id(secret_id)
    # We do *not* check permissions here, since we are only POSTing
    # and no data can come out.  Unlike most devices, we must update
    # some internal state on POSTing, thus an unauthenticated getting
    # of a device class.

    #device_uuid = request.POST['device_id']
    try:
        POST = request.POST
    except UnreadablePostError:
        return JsonResponse(status_code=400, reason_phrase="Data not received")
    data = POST['data']
    data_decoded = loads(data)
    data_sha256 = sha256(data.encode('utf8')).hexdigest()

    timestamp_column_name = 'timestamp'
    if 'double_end_timestamp' in data_decoded[0]:
        timestamp_column_name = 'double_end_timestamp'
    if 'double_esm_user_answer_timestamp' in data_decoded[0]:
        timestamp_column_name = 'double_esm_user_answer_timestamp'

    max_ts = max(float(row[timestamp_column_name]) for row in data_decoded)

    # Using this section, store all data in one packet.
    #data_with_probe = dumps(dict(table=table, data=data))
    #kviews.save_data(data_with_probe, device_id=device.device_id, request=request)

    # In this section, store data in chunks of size 500-1000.
    chunk_size = PACKET_CHUNK_SIZE
    data_separated = ( data_decoded[x:x+chunk_size]
                       for x in range(0, len(data_decoded), chunk_size) )
    with transaction.atomic():
        for data_chunk in data_separated:
            max_ts = max(float(row[timestamp_column_name]) for row in data_chunk)
            data_chunk = dumps(data_chunk)
            # pylint: disable=redefined-variable-type
            data_to_save = dict(table=table,
                                data=data_chunk,
                                version=1)
            data_to_save = dumps(data_to_save)
            #max_ts = max(float(row[timestamp_column_name]) for row in data_chunk)
            kviews.save_data(data_to_save, device_id=device.device_id, request=request)
            device.attrs['aware-last-ts-%s'%table] = max_ts

    # Important conclusion: we must store the last timestamp.  Really
    # this and the section above should be an atomic operation!
    response = [dict(timestamp=max_ts,
                     double_end_timestamp=max_ts,
                     double_esm_user_answer_timestamp=max_ts,
                     data_sha256=data_sha256),]
    if 'nonce' in POST:
        response[0]['nonce'] = POST['nonce']
    #device.attrs['aware-last-ts-%s'%table] = max_ts
    return JsonResponse(response, safe=False)

@csrf_exempt
def clear_table(request, secret_id, table, indexphp=None):
    """AWARE client requesting to clear a table.  Nullop for us."""
    # pylint: disable=unused-argument
    return HttpResponse(reason="Not handled")




# /index.php/webservice/client_get_study_info/  # supposed to have API key
def study_info(request, secret_id, indexphp=None):
    """Returns "study info" that is presented when QR scanned.

    This function has no effect on config locking."""
    # pylint: disable=unused-argument
    public_id = None
    LOGGER.info("aware get study info: %s %s", request.POST, secret_id)
    if not secret_id:
        return JsonResponse({ }, status_code=400)

    device = models.Device.get_by_secret_id(secret_id)
    public_id = device.public_id

    user = device.user
    user_config = group.user_merged_group_config(user)
    study_config = user_config.get('aware_study',{})
    study_name         = study_config.get('study_name', 'Koota')
    study_description  = study_config.get('study_description',
                                          ('Link to your account '
                                           '(device_id=%s)'%public_id))
    researcher_first   = study_config.get('researcher_first', 'Aalto Complex Systems')
    researcher_last    = study_config.get('researcher_last', '')
    researcher_contact = study_config.get('researcher_contact', 'noreply@koota.cs.aalto.fi')

    logs.log(request, 'AWARE study info requested',
             obj=device.public_id, op='study_info')
    response = dict(study_name=study_name,
                    study_description=study_description,
                    researcher_first=researcher_first,  # researcher name
                    researcher_last=researcher_last,
                    researcher_contact=researcher_contact,
                    device_id='11'
                )
    return JsonResponse(response)



import qrcode
import io
from six.moves.urllib.parse import quote as url_quote
def register_qrcode(request, public_id, indexphp=None):
    """Produce png AWARE qr code."""
    # pylint: disable=unused-argument
    device = models.Device.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission()
    device_class = device.get_class()
    url = device_class.qrcode_url()
    data = url
    img = qrcode.make(data, border=4, box_size=3,
                     error_correction=qrcode.constants.ERROR_CORRECT_L)
    cimage = io.BytesIO()
    img.save(cimage)
    cimage.seek(0)
    return HttpResponse(cimage.getvalue(), content_type='image/png')



from django.conf.urls import url
urlpatterns = [
    url(r'^v1/(?P<public_id>[0-9a-f]+)/qr.png$', register_qrcode,
        name='aware-register-qr'),

    # Main registratioon link
    # AWARE has: 'index.php/webservice/index/$study_id/$api_key
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)/?$', register,
        name='aware-register'),

    # Various table operations
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/create_table$', create_table,
        name='aware-create-table'),
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/latest$', latest,
        name='aware-latest'),
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/insert$', insert,
        name='aware-insert'),
    url(r'^v1/(?:1/)?(?P<table>\w+)/clear_table$', clear_table,
        name='aware-clear-table'),
]

# these urlpatters are hard-coded rooted at /index.php/.* so need to
# be handled specially.
urlpatterns_fixed = [
    # /index.php/webservice/client_get_study_info/  # supposed to have API key
    url(r'^webservice/client_get_study_info/(?P<secret_id>.*)',
        study_info,
        name='aware-study-info'),
]
