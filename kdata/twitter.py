"""Twitter scraping support for Koota.


API terms: https://dev.twitter.com/overview/terms/agreement-and-policy

TODO:
- unlink
- handle invalid tokens
- handle rate limit exceeded

"""

from datetime import timedelta
from json import dumps, loads
import time

from django.conf import settings
from django.conf.urls import url, include
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone

from requests_oauthlib import OAuth1Session

from . import converter
from . import devices
from . import models
from . import permissions
from .views import save_data



import logging
logger = logging.getLogger(__name__)



client_key = settings.TWITTER_KEY
client_secret = settings.TWITTER_SECRET
request_token_url = 'https://api.twitter.com/oauth/request_token'
base_authorization_url = 'https://api.twitter.com/oauth/authorize'
access_token_url = 'https://api.twitter.com/oauth/access_token'
API_BASE = 'https://api.twitter.com/1.1/%s.json'

@devices.register_device_decorator(default=False)
class Twitter(devices.BaseDevice):
    dbmodel = models.OauthDevice
    converters = devices.BaseDevice.converters + [
                 ]
    config_instructions_template = (
        """Current state: {{device.oauthdevice.state}}.
        <ul>
          {% if device.oauthdevice.state != 'linked' %}<li>Please link this <a href="{% url 'twitter-link' public_id=device.public_id %}">here</a>.</li>{% endif %}
          {% if device.oauthdevice.state == 'linked' %}<li>If desired, you may unlink the device here: <a href="{% url 'twitter-unlink' public_id=device.public_id%}">here</a>.</li> {% endif %}
        </ul>
        """)
    @classmethod
    def create_hook(cls, instance, user):
        super(Twitter, cls).create_hook(instance, user)
        instance.state = 'unlinked'
        instance.save()



def link(request, public_id):
    """Step one of linking the device
    """
    device = models.OauthDevice.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    # TODO: error handling
    callback_uri = request.build_absolute_uri(reverse(done))

    # 1: Request tokens
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            callback_uri=callback_uri,
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
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
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
    return HttpResponseRedirect(reverse('device-config', kwargs=dict(public_id=device.public_id)))


def unlink(request, public_id):
    # Destroy the auth tokens
    device = models.OauthDevice.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    device.state = 'unlinked'
    device.resource_key = ''
    device.resource_secret = ''
    device.data = dumps(dict(unlinked=time.ctime()))
    device.save()
    return HttpResponseRedirect(reverse('device-config',
                                        kwargs=dict(public_id=device.public_id)))





def cursor_get(func, params):
    i = 0
    next_cursor = None
    while True:
        data = func(params)
        yield data
        if data['next_cursor'] == 0:
            break
        # Two tests to ensure we don't go go too far/overload
        if data['next_cursor'] == next_cursor:
            raise
        if i > 15:
            raise
        params['cursor'] = next_cursor = data['next_cursor']



def scrape_device(device_id, do_save_data=False):
    # Get basic parameters
    device = models.OauthDevice.get_by_id(device_id)
    if (device.ts_last_fetch
        and (timezone.now() - device.ts_last_fetch < timedelta(hours=1))):
        pass
    device.ts_last_fetch = timezone.now()
    device.save()
    resource_owner_key = device.resource_key
    resource_owner_secret = device.resource_secret

    # Create base OAuth session to use for everything
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            resource_owner_key=resource_owner_key,
                            resource_owner_secret=resource_owner_secret)

    # Get settings to get screen name
    settings_url = API_BASE%'account/settings'
    r = session.get(settings_url)
    j = r.json()
    print(j)
    screen_name = j['screen_name']

    def get_twitter(endpoint, params, filter_keys=lambda j: j):
        url = 'https://api.twitter.com/1.1/%s.json'%endpoint
        r = session.get(url, params=params)
        body = r.text
        print('Rate limit:', r.headers['X-Rate-Limit-Limit'],
              r.headers['X-Rate-Limit-Remaining'])

        if r.status_code == 429:
            print('RATE LIMIT EXCEEDED: %s: twitter %s: %s'%(r.status_code, endpoint, body))
            raise RuntimeError('Twitter rate limit exceeded')
        if r.status_code != 200:
            print('%s: twitter %s: %s'%(r.status_code, endpoint, body))
            return
        j = r.json()
        #if 'next_cursor' in j:
        #    print("Twitter needs cursoring")
        j = filter_keys(j)
        print(j)
        data = dict(endpoint=endpoint,
                    url=url,
                    data=dumps(j),
                    params=params,
                    timestamp=time.time(),
                    version=1,
                )
        if do_save_data:
            save_data(data, device_id, )
        return j, data

    def filter_keys(j):
        if not isinstance(j, list):
            return j
        for row in j:
            if 'text' in row:
                row['text_len'] = len(row['text'])
                row['text'] = None
        return j


    #r = session.get('https://api.twitter.com/1.1/statuses/user_timeline.json',
    #                params=dict(screen_name=screen_name))
    #j = r.json()
    # TODO: since_id,
    ret = get_twitter('statuses/user_timeline',
                      {'screen_name':screen_name},
                      filter_keys)
    print(ret, '\n')

    ret = get_twitter('statuses/mentions_timeline',
                      {'screen_name':screen_name},
                      filter_keys)
    print(ret, '\n')

    ret = get_twitter('statuses/retweets_of_me',
                      {'screen_name':screen_name},
                      filter_keys)
    print(ret, '\n')

    ret = get_twitter('friends/list',
                      {'screen_name':screen_name},
                     )
    print(ret, '\n')

    ret = get_twitter('followers/list',
                      {'screen_name':screen_name},
                     )
    print(ret, '\n')


    #import IPython ; IPython.embed()


def scrape_all():
    devices = Twitter.dbmodel.objects.filter(type=Twitter.pyclass_name(),
                                             state='linked')
    for device in devices:
        print(device)
        scrape_device(device.device_id, True)

Twitter.scrape_one_function = scrape_device
Twitter.scrape_all_function = scrape_all




urlpatterns = [
    url(r'^link/(?P<public_id>[0-9a-f]+)$', link, name='twitter-link'),
    url(r'^done/$', done, name='twitter-done'),
    url(r'^unlink/(?P<public_id>[0-9a-f]+)$', unlink, name='twitter-unlink'),
]
