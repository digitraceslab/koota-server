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
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from requests_oauthlib import OAuth1Session

from . import converter
from . import devices
from . import logs
from . import models
from . import permissions
from . import views



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
        converter.JsonPrettyHtmlData,
                 ]
    config_instructions_template = """
Current state: {{device.oauthdevice.state}}.
<ul>
    {% if device.oauthdevice.state != 'linked' %}
      <li>Please link this
        <form method="post" style="display: inline" action="{% url 'twitter-link' public_id=device.public_id %}">{%csrf_token%}
        <button type="submit" class="btn btn-xs">here</button>
        </form>
    </li>
    {% endif %}
    {% if device.oauthdevice.state == 'linked' %}
      <li>If desired, you may unlink the device here:
      <form method="post" style="display: inline" action="{% url 'twitter-unlink' public_id=device.public_id %}">{%csrf_token%}
      <button type="submit" class="btn btn-xs">here</button>
      </form>
    </li>
    {% endif %}
</ul>
"""
    @classmethod
    def create_hook(cls, instance, user):
        super(Twitter, cls).create_hook(instance, user)
        instance.state = 'unlinked'
        instance.save()


@login_required
@require_http_methods(["POST"])
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
    logs.log(request, 'Twitter: begin linking',
             obj=device.public_id, op='link_begin')


    authorization_url = session.authorization_url(base_authorization_url)
    #print 'Please go here and authorize,', authorization_url
    return HttpResponseRedirect(authorization_url)

@login_required
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
    logs.log(request, 'Twitter: done linking',
             obj=device.public_id, op='link_done')
    return HttpResponseRedirect(reverse('device-config', kwargs=dict(public_id=device.public_id)))


@login_required
@require_http_methods(["POST"])
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
    logs.log(request, 'Twitter: unlink',
             obj=device.public_id, op='unlink')
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



def scrape_device(device_id, save_data=False, debug=False):
    # Get basic parameters
    device = models.OauthDevice.get_by_id(device_id)
    # Check token expiry
    if device.ts_refresh < timezone.now() + timedelta(seconds=60):
        logger.error('Facebook token expired')
        return
    # Avoid scraping again if already done, and if we are in save_data mode.
    if save_data:
        if (device.ts_last_fetch
             and (timezone.now() - device.ts_last_fetch < timedelta(hours=1))):
            return
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
    if debug:
        print(j)
    screen_name = j['screen_name']

    def get_twitter(endpoint, params, filter_json=lambda j: j):
        url = API_BASE%endpoint
        all_data = [ ]
        count = 0
        # Loop for paging
        while True:
            r = session.get(url, params=params)
            body = r.text
            j = r.json()
            if debug:
                print("{} {} len={}".format(r.status_code, r.reason, len(r.content)))
                print('  Rate limit:', r.headers['X-Rate-Limit-Limit'],
                      r.headers['X-Rate-Limit-Remaining'])
                print(dumps(j, indent=4, sort_keys=True, separators=(',', ': ')))
            # Rate limiting?
            if r.status_code == 429:
                print('RATE LIMIT EXCEEDED: %s: twitter %s: %s'%(r.status_code, endpoint, body))
                raise RuntimeError('Twitter rate limit exceeded')
            # Other errors
            if not r.ok:
                print("Error: {}".format(j['error']))
                print('%s: twitter %s: %s'%(r.status_code, endpoint, body))
                return



            # Handle privacy-preserving functions
            j = filter_json(j)
            all_data.append(j)
            if remove_fields is not None:
                for field in remove_fields:
                    j.pop(j, None)
            # Create our data storage object and do the storage
            data = dict(endpoint=endpoint,
                        url=url,
                        data=dumps(j),
                        params=params,
                        status_code=r.status_code,
                        reason=r.reason,
                        timestamp=time.time(),
                        version=1,
                    )
            if save_data:
                views.save_data(dumps(data), device.device_id, )
            # Page (start the loop again) if necessary.
            if 'next_cursor' in j and j['next_cursor'] != 0:
                params['cursor'] = j['next_cursor']
                continue
            break
        return all_data

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
                      {'screen_name':'false'},
                      {'since_id':1442259804},
                      {'include_rts':'false'},
                      j=['created_at','favorite_count','id','in_reply_to_user_id','retweet_count',
                      'favourites_count','follow_request_sent','followers_count','friends_count', 
                      'listed_count','protected','statuses_count',  #in user{}
                      'user_mentions','id' #of the user mentions 
                      ])
    print(ret, '\n')

    ret = get_twitter('statuses/mentions_timeline',
                      {'since_id':1442260740},
                      {'trim_user':1},                  
                      j=['created_at','favorite_count','id','in_reply_to_status_id',
                      'in_reply_to_user_id','retweet_count','user','endpoint','params:{"since_id"}','timestamp'])
    
    print(ret, '\n')

    ret = get_twitter('statuses/retweets_of_me',
                      {'since_id':1442260740},
                      {'trim_user':1}, 
                      {'include_entities':'false'},
                      {'include_user_entities':'false'},                 
                      j=['id','retweet_count','favorite_count','endpoint','timestamp'])
    print(ret, '\n')

    ret = get_twitter('direct_messages/sent',
                      {'since_id':1442260740},
                      {'include_entities':'false'}, #j: TODO define
                      )
    
    print(ret, '\n')

    ret = get_twitter('direct_messages',
                      {'since_id':1442260740},
                      {'include_entities':'false'},   
                      {'skip_status':1}, #j: TODO define         
                      filter_keys)
    
    print(ret, '\n')

    ret = get_twitter('friendships/no_retweets/ids',
                      {'stringify_ids':'true'} , #j: TODO define. Not needed for Oxford.                          
                      filter_keys)
    
    print(ret, '\n')

    ret = get_twitter('friends/ids',
                       {'stringify_ids':'true'},
                       {'count':5000},            
                       j=['ids','endpoint','timestamp'])
    
    print(ret, '\n')

    ret = get_twitter('followers/ids',
                       {'stringify_ids':'true'},
                       {'count':5000},            
                       j=['ids','endpoint','timestamp'])
    
    print(ret, '\n')

    ret = get_twitter('friendships/incoming',
                       {'stringify_ids':'true'}, #j TODO define
                       filter_keys)
    
    print(ret, '\n')

    ret = get_twitter('friendships/outgoing',
                        {'stringify_ids':'true'}, #j TODO define
                        filter_keys)
    
    print(ret, '\n')

    ret = get_twitter('blocks/ids',
                       {'stringify_ids':'true'}, #j TODO define
                       filter_keys)
    
    print(ret, '\n')

    ret = get_twitter('lists/ownerships',
                        j=['created_at','id','member_count','mode','subscriber_count','endpoint','timestamp'])
    
    print(ret, '\n')

    ret = get_twitter('lists/subscriptions',
                        j=['lists','endpoint','timestamp'])
    
    print(ret, '\n')




    #import IPython ; IPython.embed()


def scrape_all(save_data=False, debug=False):
    devices = Twitter.dbmodel.objects.filter(type=Twitter.pyclass_name(),
                                             state='linked')
    for device in devices:
        print(device)
        scrape_device(device.device_id, save_data=False, debug=True)

Twitter.scrape_one_function = staticmethod(scrape_device)
Twitter.scrape_all_function = staticmethod(scrape_all)




urlpatterns = [
    url(r'^link/(?P<public_id>[0-9a-f]+)$', link, name='twitter-link'),
    url(r'^done/$', done, name='twitter-done'),
    url(r'^unlink/(?P<public_id>[0-9a-f]+)$', unlink, name='twitter-unlink'),
]
