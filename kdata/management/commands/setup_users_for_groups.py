from datetime import datetime, timedelta
import itertools
import json
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import converter as kconverter
from ... import group as kdata_group
from ... import models
from ...models import Device, Data
from ... import util

TZ = timezone.get_current_timezone()

class Command(BaseCommand):
    help = 'Run Group.setup_user for users/groups.  Idempotent group setup.'

    def add_arguments(self, parser):
        parser.add_argument('--user', '-u', nargs=None)
        parser.add_argument('--group', '-g', nargs=None)
        parser.add_argument('--dry-run', '-n', action='store_true')

    def handle(self, *args, **options):
        user = None
        group = None
        # Find user by username and id
        if options['user']:
            qs = User.objects.filter(username=options['user'])
            if qs.exists():
                user = qs.get()
            elif options['user'].isdigit():
                qs = User.objects.filter(id=int(options['user']))
                if qs.exists():
                    user = qs.get()
        # Find gorup by slug
        if options['group']:
            group = models.Group.objects.get(slug=options['group'])
        # Error messages if nothing found
        if options['user'] and not user:
            print("No user found: %s"%options['user'])
        if options['group'] and not group:
            print("No group found: %s"%options['group'])

        # Actual setup, for user/group
        if user:
            groups = models.Group.objects.filter(groupsubject__user=user)
            for g in groups:
                print("seting up: (%-15s)->(%s)"%(user, g))
                if not options['dry_run']:
                    g.get_class().setup_user(user)
        if group:
            cls = group.get_class()
            for gsubj in group.groupsubject_set.all():
                print("seting up: (%-15s)->(%s)"%(gsubj.user, group))
                if not options['dry_run']:
                    cls.setup_user(gsubj.user)
