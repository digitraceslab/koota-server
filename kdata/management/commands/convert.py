from datetime import datetime, timedelta
import itertools
import json
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import converter as kconverter
from ... import group as kdata_group
from ... import models
from ...models import Device, Data
from ... import util

TZ = timezone.get_current_timezone()

class Command(BaseCommand):
    help = 'Run a preprocessor on a device'

    def add_arguments(self, parser):
        parser.add_argument('converter', nargs=None)
        parser.add_argument('device_id', nargs=None)
        parser.add_argument('--output', help="Output filename", default=sys.stdout)
        parser.add_argument('--history', help="Number of past days to use for test.", default=14, type=int)
        parser.add_argument('--textdate', help="Convert unix time?", action='store_true')
        parser.add_argument('--group',
                            help="Run a converter on a group? "
                                 "device_id becomes the group name.",
                            action='store_true')
        parser.add_argument('--full', help="Produce all group data?", action='store_true')
        parser.add_argument('--hash-seed', help="Override hash seed?")
        parser.add_argument('--format', '-f', help="Output format")
        parser.add_argument('--no-handle-errors', action='store_false', default=True,
                            help="Use converter error handing framework.")

    def handle(self, *args, **options):
        #print(options)

        # If textdate is true, then convert time to strings, not
        # unixtime.
        if options['textdate']:
            time_converter = lambda x: datetime.fromtimestamp(x, TZ).strftime('%Y-%m-%d %H:%M:%S')
        else:
            time_converter = lambda x: x

        # Handle groups differently.  Delegate to handle_group and
        # return whatever it has.  In the future these should be more unified.
        if options['group']:
            return self.handle_group(time_converter=time_converter,
                                     **options)

        # Override hash_seed?  None => no effect
        hash_seed = options['hash_seed']
        if hash_seed is not None:
            hash_seed = hash_seed.encode()

        # Get the device we want to convert data from
        device = Device.get_by_id(options['device_id'])
        device_class = device.get_class()

        # Get the converter class list.  We can extra data for one
        # converter, or many at a time.
        if options['converter'] == 'all':
            converter_classes = device_class.converters
        else:
            converter_class = util.import_by_name(options['converter'])
            if not converter_class:
                converter_class = getattr(kconverter, options['converter'])
            converter_classes = [converter_class]

        # For each converter, do the conversion.
        for converter_class in converter_classes:
            # Get the rows of DB objects.
            rows = Data.objects.filter(device_id=device.device_id, )
            rows = rows.order_by('ts')

            # Limit to a certain number of days of history.
            if options['history']:
                rows = rows.filter(ts__gt=(timezone.now()-timedelta(days=options['history'])))

            # Final transformations
            rows = util.optimized_queryset_iterator(rows)
            rows = ((d.ts, d.data) for d in rows)
            # Two options for error handling: handle with warning at
            # end, or immediately raise exception.
            if options['no_handle_errors']:
                converter = converter_class(rows=rows, time=time_converter,
                                            hash_seed=hash_seed)
                table = converter.run()
            else:
                converter = converter_class(rows=rows, time=time_converter,
                                            hash_seed=hash_seed)
                table = converter.convert(rows,
                                          time=time_converter)
            # Set output: stdout or a file.
            if isinstance(options['output'], str):
                output = options['output'].format(device_id=device.public_id,
                                                  converter=converter_class.name(),
                                                  ext=options['format'])
                output = open(output, 'w')
            else:
                output = sys.stdout

            # Do the conversion.  This is a extremely nested iterator
            # that handles all layers at once.
            self.print_rows(table, converter,
                            header=converter.header2(),
                            options=options, output=output)

    def handle_group(self, time_converter, **options):
        group_name = options['device_id']
        group = models.Group.objects.get(slug=group_name)
        group_class = group.get_class()

        hash_seed = options['hash_seed']
        if hash_seed is not None:
            hash_seed = hash_seed.encode()

        group_converter_class = util.import_by_name(options['converter'])
        if not group_converter_class:
            group_converter_class = [ x for x in group_class.converters
                                      if x.name() == options['converter'] ][0]
        group_converter_class = kdata_group.get_group_converter(group_converter_class)
        group_converter_class = group_converter_class

        converter_class = group_converter_class.converter
        converter_for_errors = converter_class(rows=None)

        table = kdata_group.iter_group_data(
            group, group_class,
            group_converter_class, converter_class,
            converter_for_errors=converter_for_errors,
            filter_queryset=None,
            time_converter=time_converter,
            row_limit=None if options['full'] else 50,
            handle_errors=options['no_handle_errors'],
            hash_seed=hash_seed
            )

        header = ['user', 'device', ] + converter_class.header2()
        self.print_rows(table,
                        converter=converter_for_errors,
                        header=header,
                        options=options)

    def print_rows(self, table, converter, header, options, output=sys.stdout):
        import sys
        if options['format']:
            printer = getattr(util, options['format'].replace('-','_')+'_iter')
            for line in printer(table, converter=converter,
                                header=header):
                output.write(line)
        else:
            for line in table:
                print(line, file=output)
        # If we are writing to file, also print problems to stdout
        if isinstance(output, str):
            if converter and converter.errors:
                print('The following errors were found at unspecified points in processing:\n')
                for error in converter.errors:
                    print(str(error))

