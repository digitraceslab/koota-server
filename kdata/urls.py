from django.conf.urls import url, include
from django.contrib import admin
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views

from kdata import views as kviews
from kdata import views_data
from kdata import views_admin
from kdata import views_funf
from kdata import devices
from kdata import survey
from kdata import group
from kdata import twitter

urlpatterns = [
    url(r'^post/purple/?(?P<device_id>\w+)?/?$', kviews.post, dict(device_class=devices.PurpleRobot),
        name='post-purple'),
    url(r'^post/?(?P<device_id>[A-Fa-f0-9]+)?/?$', kviews.post, name='post'),
    # the Murata bed sensor has a hard-coded POST URL.
    url(r'^data/push/$', kviews.post, dict(device_class=devices.MurataBSN),
        name='post-MurataBSN'),
    url(r'^config$', kviews.config, name='config'),
    url(r'^devices/$', kviews.DeviceListView.as_view(), name='device-list'),
    url(r'^devices/create/$', kviews.DeviceCreate.as_view(),
        name='device-create'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/config$', kviews.DeviceConfig.as_view(),
        name='device-config'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/qr.png$', kviews.device_qrcode,
        name='device-qr'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/$', views_data.DeviceDetail.as_view(),
        name='device'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/(?P<converter>\w+)\.?(?P<format>[\w-]+)?',
        views_data.device_data,
        name='device-data'),

    url(r'^log$', kviews.log, name='log'),
    url(r'^stats/', views_admin.stats),

    url(r'^survey/take/(?P<token>[\w]*)', survey.take_survey, name='survey-take'),

    url(r'^group/$', group.group_join, name='group-join'),
    url(r'^group/(?P<group_name>[\w]+)/?$', group.group_view, name='group-view'),
    url(r'^group/(?P<group_name>[\w]+)/(?P<converter>\w+)\.?(?P<format>[\w-]+)?',
        group.group_data, name='group-data'),

    url(r'^funf/config/(?P<device_id>[A-Fa-f0-9]+)?/?$', views_funf.config_funf, name='funf-journal-config'),
    url(r'^funf/post1/(?P<device_id>[A-Fa-f0-9]+)?/?$', kviews.post,
        dict(device_class=views_funf.FunfJournal),
        name='funf-journal-post'),

    url(r'^twitter/', include(twitter.urlpatterns)),

    url(r'^$', TemplateView.as_view(template_name='koota/main.html'), name='main'),
    ]
