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
        raw_instructions = textwrap.dedent("""\
        Please go to settings and set these properties:<p>

        <ul>
        <li>Post endpoint: https://data.koota.zgib.net{post}</li>
        <li>User ID: {device.device_id}</li>
        </ul>

        """.format(
            post=str(cls.post_url),
            device=device,
            ))
        return dict(post=cls.post_url,
                    config=cls.config,
                    qr=False,
                    raw_instructions=raw_instructions)
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
                    device_id=device_id,
                    response=response)
