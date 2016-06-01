"""Twitter scraping support for Koota.


API terms: https://dev.twitter.com/overview/terms/agreement-and-policy

"""

from django.conf.urls import url, include
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone


from requests_oauthlib import OAuth1Session

from . import devices
from . import models
from . import converter



client_key = 'OJFgYQuVOuXSs5ebdFH3ycvWr'
client_secret = '9qqKOCXw7OvO30wW5ksvaNbKwMGNSKqQFiIICgxGsLmq0pkB3j'
request_token_url = 'https://api.twitter.com/oauth/request_token'
base_authorization_url = 'https://api.twitter.com/oauth/authorize'
access_token_url = 'https://api.twitter.com/oauth/access_token'

@devices.register_device_decorator(default=False)
class Twitter(devices.BaseDevice):
    dbmodel = models.OauthDevice
    converters = devices.BaseDevice.converters + [
                 ]
    raw_instructions = (
        """Current state: {device.oauthdevice.state}.  Please link this """
        """<a href="{link_url}">here</a>.<br><br>""")
    @classmethod
    def configure(cls, device):
        """Information for the device configure page."""
        instructions = cls.raw_instructions.format(
            link_url=reverse('twitter-link', kwargs=dict(device_id=device.device_id)),
            device=device,
            )
        return dict(raw_instructions=instructions)
    @classmethod
    def create_hook(cls, instance, user):
        instance.state = 'unlinked'
        instance.save()



def link(request, device_id):
    """Step one of linking the device
    """
    device = models.OauthDevice.get_by_id(device_id)
    # TODO: error handling

    # 1: Request tokens
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            #callback_uri="http://localhost:8002/twitter/done/"
    )
    fetch_response = session.fetch_request_token(request_token_url,
                                           )
    #{
    #    "oauth_token": "Z6eEdO8MOmk394WozF5oKyuAv855l4Mlqo7hhlSLik",
    #    "oauth_token_secret": "Kd75W4OQfb2oJTV0vzGzeXftVAwgMnEK9MumzYcM"
    #}
    # These are the request tokens.
    resource_owner_key = fetch_response.get('oauth_token')
    resource_owner_secret = fetch_response.get('oauth_token_secret')

    device.request_key = resource_owner_key
    device.request_secret = resource_owner_secret
    device.save()


    authorization_url = session.authorization_url(base_authorization_url)
    #print 'Please go here and authorize,', authorization_url
    return HttpResponseRedirect(authorization_url)


def done(request):
    # Same as in link function above.
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            #callback_uri="http://localhost:8002/twitter/done/"
    )


    #redirect_response = raw_input('Paste the full redirect URL here: ')
    #oauth_response = oauth.parse_authorization_response(redirect_response)
    redirect_response = request.build_absolute_uri()
    # http://127.0.0.1/twitter/done/?oauth_token=iTy7NwAAAAAAvEjNAAABVMVlcmo&oauth_verifier=kdPz02n5sFqryMfco0dI2i02P1HOyT2v
    oauth_response = session.parse_authorization_response(redirect_response)
    #{
    #    "oauth_token": "Z6eEdO8MOmk394WozF5oKyuAv855l4Mlqo7hhlSLik",
    #    "oauth_verifier": "sdflk3450FASDLJasd2349dfs"
    #}
    verifier = oauth_response.get('oauth_verifier')

    device = models.OauthDevice.objects.get(request_key=oauth_response['oauth_token'])
    resource_owner_key = device.request_key
    resource_owner_secret = device.request_secret

    # 3: get access tokens
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            resource_owner_key=resource_owner_key,
                            resource_owner_secret=resource_owner_secret,
                            verifier=verifier)
    oauth_tokens = session.fetch_access_token(access_token_url)
    #{
    #    "oauth_token": "6253282-eWudHldSbIaelX7swmsiHImEL4KinwaGloHANdrY",
    #    "oauth_token_secret": "2EEfA6BG3ly3sR3RjE0IBSnlQu4ZrUzPiYKmrkVU"
    #}
    resource_owner_key = oauth_tokens.get('oauth_token')
    resource_owner_secret = oauth_tokens.get('oauth_token_secret')

    # save these
    device.resource_key = resource_owner_key
    device.resource_secret = resource_owner_secret
    device.ts_linked = timezone.now()
    device.state = 'linked'
    device.save()
    return HttpResponseRedirect(reverse('device-config', kwargs=dict(device_id=device.public_id)))

def get_data(device_id):
    settings_url = 'https://api.twitter.com/1.1/account/settings.json'

    device = models.OauthDevice.get_by_id(device_id)
    resource_owner_key = device.resource_key
    resource_owner_secret = device.resource_secret
    device.ts_last_fetch = timezone.now()
    device.save()

    # Using OAuth1Session
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            resource_owner_key=resource_owner_key,
                            resource_owner_secret=resource_owner_secret)

    r = session.get(settings_url)
    j = r.json()
    print(j)
    screen_name = j['screen_name']

    r = session.get('https://api.twitter.com/1.1/statuses/user_timeline.json',
                    params=dict(screen_name=screen_name))
    j = r.json()
    print(j)

    r = session.get('https://api.twitter.com/1.1/statuses/home_timeline.json',
                    params=dict(screen_name=screen_name))
    j = r.json()
    print(j)

    r = session.get('https://api.twitter.com/1.1/statuses/mentions_timeline.json',
                    params=dict(screen_name=screen_name))
    j = r.json()
    print(j)


    import IPython ; IPython.embed()



def unlink():
    # Destroy the auth tokens
    pass




urlpatterns = [
    url(r'^(?P<device_id>[0-9a-f]+)$', link, name='twitter-link'),
    url(r'^done/$', done, name='twitter-done'),
]
