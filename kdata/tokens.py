
from datetime import datetime, timedelta

from django.utils import timezone

from . import models

def get_user_anon_id_token(user):
    """Return a token used to identify this user to admins"""
    qs = models.Token.objects.filter(user=user, type="anon_id").order_by('-ts_expire')
    # Get latest token if it exists.
    token = None
    if qs.exists():
        token = qs[0]
    # If token does not exist or is too old, then make new.
    if token is None or token.t_remaining() < timedelta(days=2):
        token = models.Token.create(user=user, type="anon_id", data='',
                                    t_remaining=timedelta(days=3))
    return token

def clean_tokens():
    qs = models.Token.objects.filter(ts_expire__gt=timezone.now(), delete_permanently=True)
    qs.delete()

