"""AWARE devices

http://www.awareframework.com/
"""

import copy
import datetime
from datetime import timedelta
from hashlib import sha256
import json  # use stdlib json for pretty formatting
from json import loads, dumps, JSONDecodeError
import logging
import textwrap
import time
from six.moves.urllib import parse as urlparse

from django.conf import settings
from django import forms
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
from . import aware_esm

LOGGER = logging.getLogger(__name__)

AWARE_DOMAIN = getattr(settings, 'AWARE_DOMAIN', 'https://aware.koota.zgib.net')
AWARE_DOMAIN_SIGNED = getattr(settings, 'AWARE_DOMAIN_signed', 'https://data.koota.cs.aalto.fi')
AWARE_QRCODE_FORMAT = getattr(settings, 'AWARE_QRCODE_FORMAT', 'url') # embed, url
AWARE_CRT_URL = getattr(settings, 'AWARE_CRT_URL', "https://data.koota.cs.aalto.fi/static/server-aware.crt")
AWARE_CRT_PATH = getattr(settings, 'AWARE_CRT_PATH', "/srv/koota/static/server.crt")

PACKET_CHUNK_SIZE = 1000


# Aware config forms
class AwareConfigForm(forms.Form):
    is_locked = forms.NullBooleanField(help_text="Is user blocked from making changes?")
    extra = util.JsonConfigFormField(help_text="Extra data?", required=False, widget=forms.Textarea(attrs={'style': 'font-family: monospace; width: 1000px; height: 500px'}))
    use_default_sensors = forms.BooleanField(initial=True, help_text="Sent some default config when registering?", required=False)
    frequency_update = forms.IntegerField(help_text="Schedule periodically updating config?  (min)", required=False)


from django.utils.html import escape
from django.utils.safestring import mark_safe

@devices.register_device(default=True, alias="Aware",
                         aliases=['kdata.devices.aware.Aware'])
class Aware(devices.BaseDevice):
    """Basic Python class handling Aware devices"""
    desc = 'Aware device'
    AWARE_DOMAIN = AWARE_DOMAIN
    USABLE_QRCODE_METHODS = {'embed', 'url'}
    #USABLE_QRCODE_METHODS = {}
    config_forms = [{'form':AwareConfigForm, 'key': 'aware_config'}]
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
        converter.AwareDeviceInfo,
        converter.AwareDeviceInfo2,
        converter.AwareEsms,
        converter.AwareGravity,
        converter.AwareGyroscope,
        converter.AwareLight,
        converter.AwareLinearAccelerometer,
        converter.AwareLog,
        converter.AwareLocation,
        converter.AwareLocationDay,
        converter.AwareMagnetometer,
        converter.AwareMessages,
        converter.AwareNetwork,
        converter.AwareNetworkTraffic,
        converter.AwareRotation,
        converter.AwareScreen,
        converter.AwareSensorWifi,
        converter.AwareSigMotion,
        converter.AwareTelephony,
        converter.AwareWifi,
    ]
    config_instructions_template = textwrap.dedent("""\
    <ol>
    <li>Install the AWARE app from <a href="{{install_url_local}}">here (koota version)</a> or <a href="{{install_url}}">here (upstream version)</a>.</li>
    <li>If you are viewing this on your device, you can click <a href="{{study_url_aware_scheme}}" class="btn-xs btn-info">here to link directly</a>.</li>
    <li>See the <a href="https://github.com/CxAalto/koota-server/wiki/Aware">instructions on the github wiki</a>.
    <li>URL for linking is <a href="{{study_url}}">{{study_url}}</a></li>
    </ol>

    <img src="{{qrcode_img_path}}">

    {% if pretty_aware_config %}
    <p>Your raw config is:
    {{ pretty_aware_config }}</p>
    {% endif %}

    """)
    install_url = 'http://play.google.com/store/apps/details?id=com.aware.phone'
    install_url_local = 'https://koota.cs.aalto.fi/a/niima.apk'
    def config_context(self):
        url_ = self.qrcode_url()
        qrcode_img_path = reverse('aware-register-qr',
                                  kwargs=dict(public_id=self.dbrow.public_id))
        config = self.aware_config()
        # pylint: disable=redefined-variable-type
        config = json.dumps(config, sort_keys=True, indent=1, separators=(',',': '))
        config = mark_safe('<pre>'+escape(config)+'</pre>')
        context = dict(study_url=url_,
                       study_url_aware_scheme=url_.replace('https:', 'aware-ssl:'),
                       qrcode_img_path=qrcode_img_path,
                       pretty_aware_config=config,
                       install_url=self.install_url,
                       install_url_local=self.install_url_local,
                           )
        return context
    def webservice_url(self):
        """URL for webservice."""
        secret_id = self.dbrow.secret_id
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
        if AWARE_QRCODE_FORMAT == 'embed' and 'embed' in self.USABLE_QRCODE_METHODS:
            crt = open(AWARE_CRT_PATH, 'rb').read()
            crt_sha256 = sha256(crt).hexdigest()
            queryparams = dict(crt=crt,
                               crt_sha256=crt_sha256)
        elif AWARE_QRCODE_FORMAT == 'url' and 'url' in self.USABLE_QRCODE_METHODS:
            crt = open(AWARE_CRT_PATH, 'rb').read()
            crt_url = AWARE_CRT_URL
            crt_sha256 = sha256(crt).hexdigest()
            queryparams = dict(crt_url=crt_url,
                               crt_sha256=crt_sha256)
        url_ = url_._replace(query=urlparse.urlencode(queryparams))
        url_ = url_.geturl()
        return url_

    def aware_config(self, extra_config=None):
        """Final config to send to Aware.

        The extra_config attribute can be a config dictionary which
        takes precedence over the default config provided by this base
        class.
        """
        config = get_user_config(self)
        if extra_config:
            config = util.merge_dicts(config, extra_config)
        config = finalize_config(config, self)
        return config


@devices.register_device(default=True, alias='AwareValidCert',
                         aliases=['kdata.devices.aware.AwareValidCert'])
class AwareValidCert(Aware):
    """AWARE device, using a valid cert endpoint"""
    desc = 'Aware device (iOS)'
    AWARE_DOMAIN = AWARE_DOMAIN_SIGNED
    install_url = 'https://itunes.apple.com/us/app/aware-client-ios/id1065978412'
    # iOS devices only work with
    USABLE_QRCODE_METHODS = { }



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

    ))
DEFAULT_SENSORS = dict(
    sensors=dict(
        # Sensor config
        status_battery=True,
        status_screen=True,
        #status_wifi=False,
        #frequency_wifi=300,
        #status_bluetooth=False,
        #frequency_bluetooth=300,
        #status_light=True,
        #status_accelerometer=False,
        #frequency_accelerometer=1000000, #microseconds
        #frequency_light=10000000,  # microseconds
        #frequency_timezone=43200  # seconds
        #location_geofence="60.166616,24.943245,300 rect,60.168959,24.947429,60.166457,24.952528",
        #location_geofence="60.185222,24.821330,700 rect,60.171101,24.914507,60.160396,24.821774",
    )
)
for name in ("accelerometer", "barometer", "gravity", "gyroscope",
                 "light", "linear_accelerometer", "magnetometer",
                 "proximity", "rotation", "temperature"):
    DEFAULT_SENSORS['sensors']['threshold_'+name] = 0.05

def aware_to_string(value):
    """AWARE requires setting values to be string.  Convert them."""
    if isinstance(value, str):
        return str(value)
    return json.dumps(value)
def dict_to_settings(config, key_name='setting', value_name='value'):
    """Dict to aware's [{setting:xxx value:xxx}, ...] format.

    {"aaa":xxx, "bbb":yyy} -> [{"setting":"aaa", "value":"xxx"},
                               {"setting":"bbb", "value":"yyy"}]
    """
    cfg = [ {key_name:k, value_name:aware_to_string(v)}
            for k,v in config.items() ]
    cfg.sort(key=lambda x: x.get(key_name, ''))
    return cfg

def get_user_config(device):
    """Get an Aware device's configuration.

    This is the main function which creates the configuration for an
    Aware device.  It will take into account many sources of data:
    global config from this module config, global config from django,
    the user's group configuration properties, and configuration on the
    device itself.

    return value: Python object which will be JSON encoded for sending
    to Aware.
    """
    config = copy.deepcopy(BASE_CONFIG)

    # Default sensors?
    if (device.dbrow.attrs.get('aware_config')
        and json.loads(device.dbrow.attrs['aware_config']).get('use_default_sensors')):
        util.recursive_copy_dict(DEFAULT_SENSORS, config)

    # Create some basic info
    #config['sensors']['mqtt_username'] = device.dbrow.public_id
    #config['sensors']['mqtt_password'] = device.dbrow.secret_id
    if device.dbrow.ts_create is not None:
        ts_create = device.dbrow.ts_create.timestamp()
    else:
        ts_create = (timezone.now()-timedelta(days=1)).timestamp()
    # AWARE parses study_start as int!
    config['sensors']['study_start'] = int(ts_create*1000)
    config['sensors']['webservice_server'] = device.webservice_url()
    config['sensors']['status_webservice'] = True
    config['sensors']['device_label'] = device.dbrow.public_id

    # Merge in all our config locations:

    # Config from django settings
    if hasattr(settings, 'AWARE_CONFIG'):
        util.recursive_copy_dict(settings.AWARE_CONFIG, config)

    # Config from a user's groups:
    user = device.dbrow.user
    user_group_config = group.user_merged_group_config(user)
    if 'aware_config' in user_group_config:
        util.recursive_copy_dict(user_group_config['aware_config'], config)

    # Config from this device in particular (device attrs)
    if 'aware_config' in device.dbrow.attrs:
        _data = json.loads(device.dbrow.attrs['aware_config'])
        util.recursive_copy_dict(_data, config)
        # Same as above, but prevents problems in case of wrapped
        # "aware_config" attribute like groups require.
        if 'aware_config' in _data:
            util.recursive_copy_dict(_data['aware_config'], config)

    # Config adjustments that should be done after config merging:
    # Should the study be locked?  Locked by default, see conditions for locking.
    if config.get('study_id', '') or config.get('unlocked', True):
        config['aware_unlocked'] = True

    # Find time to update config
    if (device.dbrow.attrs.get('aware_config')
        and json.loads(device.dbrow.attrs['aware_config']).get('frequency_update')):
        config['sensors']['frequency_update'] = json.loads(device.dbrow.attrs['aware_config']).get('frequency_update')


    return config


def process_schedule(sched):
    """Convert schedule to final form.

    Takes one schedule and returns a list of schedules.  The main thing
    that happens here is converting extras to the right format, and
    possibly adding random times to schedules.
    """

    if 'questions' in sched:
        sched = aware_esm.convert(sched)

    # Do we need to make the {'key':x, 'value':y} format ESM settings
    # for schedules?  This automatically converts dicts to this
    # format.  It will be converted to string (dumps) before sending
    # to the client.
    if ('schedule' in sched
          and 'action' in sched['schedule']
          and 'extras' in sched['schedule']['action']
          and isinstance( sched['schedule']['action']['extras'], dict)):
        # dict_to_settings makes the settings in the right format
        # - with the right key/value names.
        sched['schedule']['action']['extras'] = \
          dict_to_settings(sched['schedule']['action']['extras'],
                           key_name='extra_key', value_name='extra_value')
    # Handle random interval schedules.  Go through all schedules and
    # deplicate the ones that have multiple times.
    schedules_config2 = [ ]

    #print(sched['schedule']['trigger'])
    if 'random_intervals' in sched['schedule']['trigger']:
        now_ts = timezone.now().timestamp()
        # Loop over several days
        today = timezone.now().date()
        params = sched['schedule']['trigger']['random_intervals']
        N = params['N']
        start, end = params['start'], params['end']
        forward_time = params.get('forward_time', 3600*24*2)
        for day_n in range(forward_time//(3600*24) + 1):
            day = today + timedelta(days=day_n)
            start_dt = timezone.get_current_timezone().localize(datetime.datetime(*day.timetuple()[:3], hour=start[0], minute=start[1]))
            end_dt = timezone.get_current_timezone().localize(datetime.datetime(*day.timetuple()[:3], hour=end[0], minute=end[1]))
            start_ts = start_dt.timestamp()
            end_ts   = end_dt.timestamp()
            times = util.random_intervals(start=start_ts, end=end_ts, N=params['N'], min=params.get('min', 0)*60,
                                          max=params['max']*60 if 'max' in params else None,
                                          seed=params.get('seed', 'u436on')+day.strftime('%Y-%m-%d'))
            for ts in times:
                #print(ts, datetime.datetime.fromtimestamp(ts))
                if now_ts > ts or ts > now_ts+forward_time:
                    continue
                sched2 = copy.deepcopy(sched)
                sched2['schedule']['trigger']['timer'] = int(ts*1000)
                sched2['schedule']['trigger']['random_intervals'] = json.dumps(sched2['schedule']['trigger']['random_intervals'])
                sched2['schedule']['schedule_id'] = sched2['schedule']['schedule_id']+'_'+str(int(ts))
                schedules_config2.append(sched2)
    else:
        schedules_config2.append(sched)

    return schedules_config2


def finalize_config(config, device):
    """Do last post-processing on the config dict.

    This takes the config dictionary and turns it into a list of
    dictionaries.  It does any other last-step processing, like
    converting the schedules to their final form, adding random times to
    schedules, and so on.  Any config which should be overrideable
    should be in get_user_config.
    """
    # Schedules
    #schedule_NAME = [ {"package": "xxx", "schedule":{} }, { } ]
    # schedule =
    #  {"schedule_id": "greeting_active",
    #   "action":{"type":"service","class":"com.aware.phone/com.aware.utils.Aware_TTS",
    #             "extras":[{"extra_key":"tts_text",
    #                        "extra_value":"Hello there."},
    #                       {"extra_key":"tts_requester","extra_value":"com.aware.phone"}]},
    #   "trigger":{"condition":[{"condition_uri": "content://com.aware.phone.provider.screen/screen",
    #                            "condition_where":"screen_status=3"}]}}}
    #
    # Example with ESM
    # {"schedule_id": "ask_stars",
    #   "action":{"type":"service","class":"com.aware.phone/com.aware.ESM",
    #             "extras":[{"extra_key":"esms",
    #                        "extra_value":dumps([esm1, esm2, ...])},
    #                       ]},
    #  "schedule": { }
    # }
    # esm1 = {"esm_type": 1=text, 2=radio, 3=checkbox, 4=likert, 5=quickans, 6=scale, 7=num
    #         "esm_title": str
    #         "esm_instructions": str
    #         "esm_submit": str
    #         "esm_expiration_threshold": int,
    #         "esm_notification_timeout": int,
    #         "esm_trigger": str,
    #         ""}
    if 'schedulers' not in config:
        config['schedulers'] = [ ]
    for key in list(config):
        if key.startswith('schedule_'):
            sched = config.pop(key)
            if isinstance(sched, (list,tuple)):
                for sched_inner in sched:
                    config['schedulers'].extend(process_schedule(sched_inner))
            else:
                config['schedulers'].append(process_schedule(sched))

    # If we have ESMs, then turn it on.
    if len(config['schedulers']) > 0:
        config['sensors']['status_esm'] = True

    # Configure updates to config.  This should be last, so that other
    # schedules get triggered before all config is reset.
    #config['frequency_update'] = 5
    if 'frequency_update' in config['sensors']:
        # Periodic updates
        update_config = {
            "package": "com.aware.phone",
            "schedule": {
                "action": {
                    "class": "com.aware.phone/com.aware.utils.StudyUtils",
                    "extras": [
                        {"extra_key": "study_url",
                         "extra_value": device.qrcode_url()},
                        ],
                    "type": "service",
                    },
                "schedule_id": "update_config",
                "trigger": {
                    "interval_delayed": int(float(config['sensors']['frequency_update']))
                    },
                }
            }
        config['schedulers'].append(update_config)

    # Plugins
    # Plugins operate the same as settings, but have a different package name.
    # [ {sensors: [ ] }
    #   {plugins: [{plugin:"package_name", settings:[ {setting:"name", value:"config" }, ... ] } ] }
    plugins_config = [
        { "plugin": plugin_name,
          "settings": dict_to_settings(plugin_settings)}
        for plugin_name, plugin_settings in config.get('plugins', {}).values()
        ]
    config.pop('plugins', None)

    # Make final configuration.  Aware requires it as a list of dicts.
    config = [{'sensors': dict_to_settings(config['sensors']),
              'plugins': plugins_config,
              'schedulers': config['schedulers'],
              }]
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
    config = device_cls.aware_config()

    LOGGER.info("aware register: %s %s", request.POST, secret_id)
    # We have no other operation, basic study configuration.
    data = request.POST
    if 'study_check' in data:
        # A ping when app starts to see if study is still going on.
        # If this is false, then it force-quits the study.
        data_to_save = dict(table="study_check",
                            data=json.dumps(request.POST),
                            timestamp=time.time(),
                            version=1)
        data_to_save = dumps(data_to_save)
        kviews.save_data(data_to_save, device_id=device.device_id, request=request)
        config = [{'status':True, 'config': config[0]}]
        return JsonResponse(config, safe=False)
    if 'device_id' in data:
        passwd = util.hash_mosquitto_password(device.secret_id)
        device.attrs['aware-device-uuid'] = data['device_id']
        device.attrs['aware-device-passwd_pbkdf2'] = passwd
        logs.log(request, 'AWARE device registration',
                 obj=device.public_id, op='register')

        # Save registration data
        data_to_save = dict(table="register",
                            data=json.dumps(request.POST),
                            timestamp=time.time(),
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


# This was test stuff used for more efficient un-urlquoting
import re
FIELDS_MATCH = re.compile('[&;]')
_hexdig = '0123456789ABCDEFabcdef'
_hextostr = {('%'+a+b): chr(int(a + b, 16)) for a in _hexdig for b in _hexdig}
R = re.compile(b'%[0-9A-Fa-f]{2}')
def unquote(s, _h2s=_hextostr):
    #return re.sub('%[0-9A-Fa-f]{2}', lambda x: _hextostr[x.group()], s)
    #return re.sub(b'%[0-9A-Fa-f]{2}', lambda x: _h2s[x.group()], s)
    return R.sub(lambda x: _hextostr[x.group()], s)

import cProfile
from django.db import transaction
# Debugging for urlunquoting speed
#@csrf_exempt
#def insert(request, *args, **kwargs):
#    if 'accel' in request.path:
#        cProfile.runctx('r = insert2(request, *args, **kwargs)', globals(), locals(), sort='cumul')
#        return r
#    else:
#        return insert2(request, *args, **kwargs)
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
        return JsonResponse(dict(error="Data not received"),
                            status=400, reason="Data not received")
    data = POST['data']
    try:
        data_decoded = loads(data)
    except JSONDecodeError as e:
        LOGGER.error("Aware JsonDecodeError 1: (%s) (%s): %s %s",
                     str(e), len(data), device.public_id, data[-10:])
        raise

    #body = request.body.decode().encode().decode() # bytes->str
    #pairs = FIELDS_MATCH.split(body)
    #POST = { }
    #for name_value in pairs:
    #    if not name_value: continue
    #    nv = name_value.split('=', 1)
    #    if len(nv) < 2: continue
    #    name = nv[0].replace('+', ' ')
    #    name = re.sub('%[0-9A-Fa-f]{2}', lambda x: _hextostr[x.group()], name)
    #    value = nv[1].replace('+', ' ')
    #    value = re.sub('%[0-9A-Fa-f]{2}', lambda x: _hextostr[x.group()], value)
    #    POST[name] = value

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
                                timestamp=time.time(),
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
        return JsonResponse(dict(error="No secret_id"), status=400)

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
