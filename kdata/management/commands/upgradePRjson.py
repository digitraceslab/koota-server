import itertools
import json

from django.core.management.base import BaseCommand, CommandError
from kdata.models import Device, Data

class Command(BaseCommand):
    help = 'Fix the Purple Robot json-evaled bug'

    #def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    def handle(self, *args, **options):
        for device in Device.objects.all():
            if device.type != 'PurpleRobot':
                continue
            print device, device.device_id, device.user
            rows = Data.objects.filter(device_id=device.device_id).defer('data')
            print 'count:', rows.count()
            count = 0
            for data in rows.iterator():
                count += 1
                data_str = data.data
                if isinstance(data_str, buffer):
                    print 'buffer...'
                #    data_str = str(data_str)
                #    data.data = data_str
                #    data.save()
                #    continue
                #continue
                try:
                    json.loads(data_str)
                    continue
                except ValueError:
                    #print data_str
                    print 'value error in json'
                    pass
                    raise
                    continue
                raise

                #if len(data_str) > 300000:
                #    print len(data_str)
                #continue
                #
                try:
                    dict_data = eval(data_str)
                except ValueError:
                    print "not json and eval failed"
                    continue
                except NameError:
                    print "name error in eval..."
                    #print data_str[:100]
                except TypeError:  # buffer
                    print "buffer?"
                    import IPython; IPython.embed()
                    raise
                new_data = json.dumps(dict_data)
                #if count > 10: break
                #data.data = new_data
                #data.save()
            #break
            
