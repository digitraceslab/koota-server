from datetime import datetime, timedelta
import itertools
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction

from kdata import models
from kdata.models import Device, Data

class Command(BaseCommand):
    """List all users in a group, with their hashes.
    """

    def add_arguments(self, parser):
        parser.add_argument('group_slug')
    def handle(self, *args, **options):
        group_slug = options['group_slug']
        print(group_slug)
        print('-'*len(group_slug))
        group = models.Group.objects.get(slug=group_slug)
        group_subjects = models.GroupSubject.objects.filter(group=group)
        for subject in group_subjects:
            print('%s %4d %s'%(subject.hash(), subject.user.id, subject.user.username))

