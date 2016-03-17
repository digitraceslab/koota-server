import hashlib
import importlib
import json
import textwrap
from django.core.urlresolvers import reverse_lazy
from django.http import JsonResponse
import logging
log = logging.getLogger(__name__)

from . import converter
from . import models
from . import util


# Here we define the different types of available devices.  This is
# sort of tricky.  For models.Device, we need Device.type.choices to
# have *all* possible devices, otherwise the DB won't validate.
# However, we need to restrict the types of devices available in
# forms, because sometimes some devices will only be available to
# certain users.
# Standard device choices: What should always be in forms.
standard_device_choices = [
    ('Android', 'Android'),
    ('PurpleRobot', 'Purple Robot (Android)'),
    ('Ios', 'IOS'),
    ('MurataBSN', 'Murata Bed Sensor'),
    #('', ''),
    #('', ''),
    ]
# All device choices: what should validate in DB.
all_device_choices = list(standard_device_choices)

def get_choices(all=False):
    """Get the device classes.

    all=False --> return standard for forms.
    all=True  --> return all for DB."""
    if all:
        return list(x[:2] for x in all_device_choices)
    return list(x[:2] for x in standard_device_choices)
def register_device(cls, desc=None):
    """Allow us to dynamically register devices.

    This dynamically changes the models.Device.type.choices when
    things are registered.  It is a hack but can be improved later...

    If description is not given, use the class methods .name() and
    .pyclass_name() (vi _devicechocies_row()) to automatically find
    the necessary data.
    """
    if desc:
        name = '%s.%s'%(cls.__module__, cls.__name__)
        all_device_choices.append((name, desc))
    else:
        all_device_choices.append(cls._devicechoices_row())
    # This is an epic hack and deserves fixing eventually.  We must
    # extend the model fields, or else updated models won't pass
    # validation.  Eventually, devices should not be a .choices
    # property on a model.
    models.Device._meta.get_field('type').choices \
            = all_device_choices
def get_class(name):
    """Get a device class by (string) name.

    Option 1: from this namespace.
    Option 2: import it, if it contains a '.'.
    Option 3: return generice device _Device.
    """
    if name in globals():
        device = globals()[name]
    elif '.' in name:
        modname, clsname = name.rsplit('.', 1)
        mod = importlib.import_module(modname)
        device = getattr(mod, clsname)
    else:
        device = _Device
    return device



import random, string
class _Device(object):
    """Standard device object."""
    # Converters are special data processors.
    converters = [converter.Raw]
    # If dbmodel is given, this overrides the models.Device model when
    # an object is created.  This has to be used _before_ the DB
    # device is created, so needs some hack kind of things in forms.
    dbmodel = None
    @classmethod
    def name(cls):
        """Human name for this device.

        This is used in select fields and so on."""
        return cls.__name__
    @classmethod
    def pyclass_name(cls):
        """Importable name for this class.

        This is the Python class name corresponding to this device.
        This is used when the server needs to import the object
        corresponding to the device.
        """
        return '%s.%s'%(cls.__module__, cls.__name__)
    @classmethod
    def _devicechoices_row(cls):
        """Helper for adding this to device list.

        This returns (pyclass_name, name) that is used for the choices
        option of the "type" field of the model, and selection
        forms.
        """
        return (cls.pyclass_name(), cls.name())

    @classmethod
    def create_hook(cls, instance, user):
        """Do initial device set-up.

        Create and set the various device_ids.  This was originally in
        kdata/views.py:DeviceCreate, and now other classes can extend
        this.
        """
        # random device ID
        # Loop until we find an ID which does not exist.
        while True:
            id_ = ''.join(random.choice(string.hexdigits[:16]) for _ in range(14))
            id_ = util.add_checkdigits(id_)
            try:
                instance.__class__.get_by_id(id_[:6])
            except instance.DoesNotExist:
                break
        instance.device_id = id_
        instance._public_id = id_[:6]

    @classmethod
    def configure(cls, device):
        """Return any special options for configuration.

        A dict mapping keys to values.  This is used on the
        device_config page.
        """
        return { }
    #def post(self, request):
    #    """Handle special options needed for accepting data.
    #
    #    Returns a dict which controls the functioning of the post() view."""
    #    return { }




class Ios(_Device):
    converters = [converter.Raw,
                  converter.IosLocation]
    pass


class PurpleRobot(_Device):
    post_url = reverse_lazy('post-purple')
    config_url = reverse_lazy('config-purple')
    converters = [converter.Raw,
                  converter.PRProbes,
                  converter.PRScreen,
                  converter.PRBattery,
                  converter.PRWifi,
                  converter.PRBluetooth,
                  converter.PRStepCounter,
                  converter.PRDeviceInUse,
                  converter.PRLocation,
                  converter.PRAccelerometer,
                  converter.PRAccelerometerBasicStatistics,
                  converter.PRAccelerometerFrequency,
                  converter.PRApplicationLaunches,
                  converter.PRRunningSoftware,
                  converter.PRAudioFeatures,
                  converter.PRProximity,
                  converter.PRCallState,
                  converter.PRCallHistoryFeature,
                  converter.PRSunriseSunsetFeature,
                  converter.PRTouchEvents,
                  converter.PRTimestamps,
                  converter.PRDataSize1Hour,
                  converter.PRDataSize1Day,
                  converter.PRDataSize1Week,
                  converter.PRDataSize,
                  converter.PRMissingData,
                  ]
    @classmethod
    def configure(cls, device):
        """Initial device configuration"""
        from django.conf import settings
        raw_instructions = textwrap.dedent("""\

        <p>See the new instructions at <a href="https://github.com/CxAalto/koota-server/wiki/PurpleRobot">the wiki page</a>.
        Your <tt>device_secret_id</tt> is <tt>{device.secret_id}</tt> and thus your HTTP upload endpoint is <tt>https://{post_domain}{post}/{device.secret_id}</tt> .

        <!--<p>Old instructions are below (see the wiki page instead):</p>

        Please go to settings and set these properties:<p>

        <ul>
        <li>Probes configuration: Enable probes: on, then go through and manually disable every probe, then turn on these:
        <ul><li> Hardware sensor probes: Location (frequency: 30 min), Step counter. </li>
            <li>Device Info&Config: Battery probe, Screen Probe, Device in Use.</li>
            <li>External device probes: Wifi Probe (sampling frequency: every 5 min)</li>
            <li>You may experiment with any other probes you would like, but consider battery usage.</li>
            </ul>
        </li>
        <!-- <li>User ID: {device.device_id}</li> - ->
        <li>User ID: anything, not used</li>
        <li>General data upload settings
            <ul>
            <li>Accept all SSL certificates: false</li>
            <li>HTTP upload endpoint: https://{post_domain}{post}/{device.secret_id}</li>
            <li>Only use wifi connection: true</li>
            </ul>
        </li>
        <li>JSON uploader settings ==> Enable JSON uploader: on</li>
        <li>User identifier: something random, it is not used</li>
        <li>Configuration URL: blank</li>
        <li>Refresh interval: Never</li>
        </ul>-->

        """.format(
            post=str(cls.post_url),
            device=device,
            post_domain=settings.POST_DOMAIN,
            ))
        return dict(post=cls.post_url,
                    config=cls.config,
                    qr=False,
                    raw_instructions=raw_instructions,
                    )
    @classmethod
    def config(cls, request):
        """/config url data"""
        device_id = request.GET['user_id']
        pass
    @classmethod
    def post(cls, request):
        request.encoding = ''
        data = json.loads(request.POST['json'])
        Operation = data['Operation']
        UserHash = data['UserHash']
        Payload = data['Payload']
        # Check the hash
        m = hashlib.md5()
        # This re-encoding to utf-8 is inefficient, when we originally
        # got raw binary data, is inefficient.  However, django is
        # fully unicode aware, and there is no easy way to tell it to
        # "not decode anything".  So, this is the workaround.
        m.update((UserHash+Operation+Payload).encode('utf-8'))
        checksum = m.hexdigest()
        if checksum != data['Checksum']:
            return HttpResponseBadRequest("Checksum mismatch",
                                    content_type="text/plain")
        #
        device_id = UserHash
        #data = json.loads(Payload)
        data = Payload

        # Construct HTTP response that will allow PR to recoginze success.
        status = 'success'
        payload = '{ }'
        checksum = hashlib.md5((status + payload).encode('utf8')).hexdigest()
        response = JsonResponse(dict(Status='success',
                                     Payload=payload,
                                     Checksum=checksum),
                                content_type="application/json")

        return dict(data=data,
                    # UserHash is hashed device_id and thus is not
                    # useful to us.  This info must be found some
                    # other way.
                    #device_id=device_id,
                    response=response)


from defusedxml.ElementTree import fromstring as xml_fromstring
class MurataBSN(_Device):
    converters = [converter.Raw,
                  converter.MurataBSN,
                 ]
    raw_instructions = textwrap.dedent("""\
    See <a href="https://github.com/CxAalto/koota-server/wiki/MurataBSN">the wiki page</a>.
    The <tt>device_secret_id</tt> to use for the "Node ID" on the "Communication Settings" page
    is <tt>{device.secret_id}</tt>.  Do <b>not</b> put in your Koota username and password,
    leave them as <tt>x</tt> or something.
    """)
    @classmethod
    def post(cls, request):
        doc = xml_fromstring(request.body)
        node = doc[0][0]
        device_id = node.attrib['id']

        return dict(device_id=device_id,
                    )
    @classmethod
    def configure(cls, device):
        return dict(qr=False,
                    raw_instructions=cls.raw_instructions.format(device=device),
                    )

