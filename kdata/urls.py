from django.conf.urls import url, include
from django.contrib import admin
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views

from kdata import views as kviews
from kdata import devices

urlpatterns = [
    url(r'^post$', kviews.post, name='post'),
    url(r'^post/purple$', kviews.post, dict(device_class=devices.PurpleRobot),
        name='post-purple'),
    url(r'^config$', kviews.config, name='config'),
    url(r'^devices/$', kviews.DeviceListView.as_view(), name='device-list'),
    url(r'^devices/(?P<id>[0-9a-fA-F]*)/$', kviews.DeviceDetail.as_view(),
        name='device-detail'),
    url(r'^devices/(?P<id>[0-9a-fA-F]*)/qr.png$', kviews.device_qrcode,
        name='device-qr'),
    url(r'^devices/create/$', kviews.DeviceCreate.as_view(),
        name='device-create'),

    url(r'^$', TemplateView.as_view(template_name='koota/main.html')),
    ]
