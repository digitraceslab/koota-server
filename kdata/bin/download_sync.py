import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import time
try:
    # python3
    import requests
    from urllib.request import Request, urlopen
    import urllib.parse as parse
except:
    from urllib2 import Request, urlopen
    import urllib2.parse as parse

usage = """\
Koota data download.  Download data, storing in directories organized
by day.  When re-run, only downloads new data.

Required arguments are "base_url", "converter", and "output_dir".  You
must set the environment variable "session_id" before running this.


"""

parser = argparse.ArgumentParser(description=usage)
parser.add_argument("base_url", help="URL to the device (e.g. https://domain.tld/devices/abcdef) or group (e.g. https://domain.tld/group/GroupName)")
parser.add_argument("converter", help="Converter name (e.g. AwareTimestamps)")
parser.add_argument("output_dir", help="")
#parser.add_argument("--session-id")
#parser.add_argument("--device")
parser.add_argument("-f", "--format", default='sqlite3dump', help="format to download")
parser.add_argument("--out-db", default=None, help="if download format is sqlite3dump, location of database to create.  Default: db.sqlite in output_dir.")
parser.add_argument("--group", default=None, action='store_true', help="If true, treate base_url as a group.  Required for group downloads.")
parser.add_argument("-v", "--verbose", default=None, action='store_true')

args = parser.parse_args()

baseurl = args.base_url
baseurl_p = parse.urlparse(args.base_url)
VERBOSE = args.verbose

if 'session_id' not in os.environ:
    print("You must set session_id first!")
    exit(2)

#class auth(requests.auth.AuthBase):
#    def __call__(self, r):
#        r.cookies = dict(sessionid=args['session_id'])
#        import IPython ; IPython.embed()
#        return r


def get(url, params={}):
    #R = Request(url, headers={'Cookie': 'sessionid='+os.environ['session_id']})

    r = requests.get(url, params=params, headers={'Cookie': 'sessionid='+os.environ['session_id']})
    if 'Please login to' in r.text:
        print("session_id invalid or can't log in")
        exit(2)
    if r.status_code != 200:
        print(url, params)
        raise Exception("requests failure: %s %s"%(r.status_code, r.reason))
    return r.text

format = args.format
today = datetime.date.today()

# Get data
if not args.group:
    R = get(os.path.join(baseurl, 'json'))
else:
    R = get(os.path.join(baseurl, args.converter, 'json'))
print(R)
data = json.loads(R)
if data['data_exists']:
    earliest_ts = data['data_earliest']
    latest_ts = data['data_latest']
    earliest = datetime.datetime.fromtimestamp(earliest_ts)
    latest = datetime.datetime.fromtimestamp(latest_ts)
    current_day = earliest.date() - datetime.timedelta(days=1)


    while current_day < latest.date():
        # process [current_date, current_date+1)
        current_day += datetime.timedelta(days=1)

        outfile = current_day.strftime(args.converter+'.%Y-%m-%d'+'.'+format)
        outfile = os.path.join(args.output_dir, outfile)
        if os.path.exists(outfile+'.partial') and current_day != today:
            os.unlink(outfile+'.partial')
        if current_day == today:
            outfile = outfile + '.partial'

        #print('  '+outfile, end='  ', flush=True)

        redownload_today = True  # remove .partial from today, too?
        if os.path.exists(outfile) and (current_day != today or not redownload_today):
            #print()
            if VERBOSE: print('  '+outfile)
            continue

        # download data
        print('  '+outfile, end='  ', flush=True)
        t1 = time.time()
        R = get(os.path.join(baseurl, args.converter)+'.'+format,
                             params=dict(start=current_day.strftime('%Y-%m-%d'),
                                         end=(current_day+datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                                        ))
        dt = time.time() - t1
        print('%8d  %4.1fs   %4.1f'%(len(R), dt, len(R)/dt))
        f = open(outfile+'.tmp', 'w')
        f.write(R) ; f.close()
        os.rename(outfile+'.tmp', outfile)

    if format == 'sqlite3dump':
        current_files = glob.glob(os.path.join(args.output_dir, args.converter+'.*.sqlite3dump'))
        current_files += glob.glob(os.path.join(args.output_dir, args.converter+'.*.sqlite3dump.partial'))
        current_files.sort()
        if args.out_db is None:
            dbfiles = [os.path.join(args.output_dir, 'db.sqlite3')]
        else:
            dbfiles = args.out_db.split(',')
        for dbfile in dbfiles:
            dbfile, *dbfile_args = dbfile.split(':')
            recreate_db = 'updateonly' not in dbfile_args
            print("Importing to DB:", dbfile)
            print("  recreate_db=%s"%recreate_db)

            dbfile_new = dbfile
            if recreate_db:
                dbfile_new = dbfile+'.new'
            else:
                # Delete the existing table
                subprocess.check_call(['sqlite3', dbfile, 'DROP TABLE IF EXISTS %s;'%args.converter])

            t1 = time.time()
            # Import the database
            sql_proc = subprocess.Popen(['sqlite3', dbfile_new, '-batch'], stdin=subprocess.PIPE)
            sql_proc.stdin.write(b'.bail ON\n')
            #sql_proc.stdin.write(b'.echo ON\n')
            sql_proc.stdin.write(b'PRAGMA journal_mode = OFF;\n')
            sql_proc.stdin.write(b'PRAGMA synchronous = OFF;\n')
            for filename in current_files:
                cmd = '.read %s'%filename
                if VERBOSE: print('  '+cmd)
                sql_proc.stdin.write(cmd.encode()+b'\n')
            sql_proc.stdin.write(b'PRAGMA synchronous = NORMAL;\n')
            sql_proc.stdin.close()
            sql_proc.wait()
            dt = time.time() - t1
            if recreate_db:
                os.rename(dbfile_new, dbfile)
            print('Import done: %12d  %4.1fs'%(os.stat(dbfile).st_size, dt))
