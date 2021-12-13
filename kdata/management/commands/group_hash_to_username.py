import sys

from django.core.management.base import BaseCommand, CommandError

from kdata import models
from kdata.models import Device, Data

class Command(BaseCommand):
    """Look up users based on their group hashes (from stdin)

    User hashes are passed via stdin, one per line.
    """

    def add_arguments(self, parser):
        parser.add_argument('group_slug', nargs='+')
    def handle(self, *args, **options):
        # Create a map of all hashes -> users
        hash_map = { }
        group_slugs = options['group_slug']
        for group_slug in group_slugs:
            group = models.Group.objects.get(slug=group_slug)
            group_subjects = models.GroupSubject.objects.filter(group=group)
            for subject in group_subjects:
                hash_map[subject.hash()] = subject.user.username
        # For each line in stdin, print the username
        print("Enter hashes to look up, one per line:", file=sys.stderr)
        for row in sys.stdin:
            row = row.strip('\n')
            print(hash_map.get(row.strip('\n'), '-'))
