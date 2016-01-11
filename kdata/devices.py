import hashlib
import json
import textwrap
from django.core.urlresolvers import reverse_lazy
from django.http import JsonResponse
import logging
log = logging.getLogger(__name__)

from . import converter

class NoDeviceTypeError(Exception):
    pass

device_choices = [
    ('Android', 'Android'),
    ('PurpleRobot', 'Purple Robot (Android)'),
    ('Ios', 'IOS'),
    ('MurataBSN', 'Murata Bed Sensor'),
    #('', ''),
    #('', ''),
    ]

def get_class(name):
    """Get a device class by (string) name"""
    if name not in globals():
        return _Device
        #raise NoDeviceTypeError()
    return globals()[name]

class _Device(object):
    converters = [converter.Raw]
    @classmethod
    def configure(cls, device):
        return { }


class PurpleRobot(_Device):
    post_url = reverse_lazy('post-purple')
    config_url = reverse_lazy('config-purple')
    converters = [converter.Raw,
                  converter.PRProbes,
                  converter.PRScreen,
                  converter.PRBattery,
                  ]
    @classmethod
    def configure(cls, device):
        """Initial device configuration"""
        from django.conf import settings
        raw_instructions = textwrap.dedent("""\
        Please go to settings and set these properties:<p>

        <ul>
        <li>Probes configuration: Enable probes: on, then go through and manually disable every probe, then turn on these:
        <ul><li> Hardware sensor probes: Location (frequency: 30 min), Step counter. </li>
            <li>Device Info&Config: Battery probe, Screen Probe, Device in Use.</li>
            <li>External device probes: Wifi Probe (sampling frequency: every 5 min)</li>
            <li>You may experiment with any other probes you would like, but consider battery usage.</li>
            </ul>
        </li>
        <!-- <li>User ID: {device.device_id}</li> -->
        <li>User ID: anything, not used</li>
        <li>General data upload settings
            <ul>
            <li>Accept all SSL certificates: false</li>
            <li>HTTP upload endpoint: https://{post_domain}{post}/{device.device_id}</li>
            <li>Only use wifi connection: true</li>
            </ul>
        </li>
        <li>JSON uploader settings ==> Enable JSON uploader: on</li>
        <li>User identifier: something random, it is not used</li>
        <li>Configuration URL: blank</li>
        <li>Refresh interval: Never</li>
        </ul>

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
        data = json.loads(Payload)

        # Construct HTTP response that will allow PR to recoginze success.
        status = 'success'
        payload = '{ }'
        checksum = hashlib.md5(status + payload).hexdigest()
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
    @classmethod
    def post(cls, request):
        doc = xml_fromstring(request.body)
        node = doc[0][0]
        device_id = node.attrib['id']

        return dict(device_id=device_id,
                    )
