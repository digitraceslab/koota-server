import hashlib
import textwrap
from django.core.urlresolvers import reverse_lazy

class NoDeviceTypeError(Exception):
    pass

device_choices = [
    ('Android', 'Android'),
    ('PurpleRobot', 'Purple Robot (Android)'),
    ('Ios', 'IOS'),
    #('', ''),
    #('', ''),
    #('', ''),
    ]

def get_class(name):
    """Get a device class by (string) name"""
    if name not in globals():
        raise NoDeviceTypeError()
    return globals()[name]



class PurpleRobot(object):
    post_url = reverse_lazy('post-purple')
    config_url = reverse_lazy('config-purple')
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
           </li></ul>
        </li>
        <!-- <li>User ID: {device.device_id}</li> -->
        <li>User ID: anything, not used</li>
        <li>General data upload settings
            <ul>
            <li>Accept all SSL certificates: true</li>
            <li>HTTP upload endpoint: https://{post_domain}{post}?device_id={device.device_id}</li>
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
        store_data = { }
        device_id = UserHash
        data = json.loads(Payload)

        store_data['REMOTE_ADDR'] = request.META['REMOTE_ADDR']

        data_collection.insert_one(store_data)

        # Construct HTTP response that will allow PR to recoginze success.
        status = 'success'
        payload = '{ }'
        checksum = hashlib.md5(status + payload).hexdigest()
        response = HttpResponse(json.dumps(dict(Status='success',
                                                Payload=payload,
                                                Checksum=checksum)),
                                content_type="application/json")

        return dict(data=data,
                    # UserHash is hashed device_id and thus is not
                    # useful to us.  This info must be found some
                    # other way.
                    #device_id=device_id,
                    response=response)
