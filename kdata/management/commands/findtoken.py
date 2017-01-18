from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import models

TZ = timezone.LocalTimezone()

class Command(BaseCommand):
    help = 'Run a preprocessor on a device'

    def add_arguments(self, parser):
        parser.add_argument('token', nargs=None)
    def handle(self, *args, **options):
        qs = models.Token.objects.filter(token=options['token'])
        if not qs.exists():
            print("Token not found")
        token = qs.get()
        print("%s: %s"%(token.user.username, token.data))
