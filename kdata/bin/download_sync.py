import argparse
import atexit
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
Find your browser cookies, and then run:
    export session_id=THE_COOKIE_VALUE

Example of downloading only csv files, one per day:
    python3 download_sync.py https://koota.tld/devices/abc123 AwareScreen downloaded_data/ --format=csv --start=2018-07-10 --end=2018-07-15

However, perhaps you want all of these files to become one.  In this
case, you would download database dumps and assemble them (the default
format is database dumps).  The rest of this information referrs to this.

Example usage to download one device's data for a certain time period,
and store it in the database Sample.sqlite3.  This also downloads
per-day data, which you should save to avoid re-downloading existing
data:
    python3 download_sync.py https://koota.tld/devices/abc123 AwareScreen tmp_data/ --start=2018-07-10 --end=2018-07-15 --out-db=Sample.sqlite3

Download one's data from several converters (remove Sample.sqlite3
before running), and update all them into the same one database file:
    python3 download_sync.py https://koota.tld/devices/abc123 AwareScreen tmp_data/ --start=2018-07-10 --end=2018-07-15 --out-db=Sample.sqlite3:updateonly
    python3 download_sync.py https://koota.tld/devices/abc123 AwareTimestamps tmp_data/ --start=2018-07-10 --end=2018-07-15 --out-db=Sample.sqlite3:updateonly

To download group-based data, point to the group URL and add --group:
    python3 download_sync.py --group https://koota.tld/group/group_name tmp_data/ --out-db=Group.sqlite3

When using --out-db there are several options:

  a) By default, each database file is removed and re-created on every
     run.  This is perhaps good for initial testing, but not big data.
         --out-db=data.sqlite3

  b) The updateonly option does not delete the database file, but will try to
     reload all data into the database on every run:
         --out-db=data.sqlite3:updateonly

  c) The incremental option will only load the newly downloaded data.
     This is best for massive datasets, but if something goes wrong
     during the process, there is a chance the database may be left in a
     corrupt state (e.g. data missing from it) with no way of knowing.
     To ensure things are consistent, you can run one of the above
     commands:
         --out-db=data.sqlite3:incremental
"""

parser = argparse.ArgumentParser(description=usage)
parser.add_argument("base_url", help="URL to the device (e.g. https://domain.tld/devices/abcdef) or group (e.g. https://domain.tld/group/GroupName)")
parser.add_argument("converter", help="Converter name (e.g. AwareTimestamps)")
parser.add_argument("output_dir", help="")
#parser.add_argument("--session-id")
#parser.add_argument("--device")
parser.add_argument("-f", "--format", default='sqlite3dump', help="format to download")
parser.add_argument("--out-db", default=None, help="if download format is sqlite3dump, location of database to create.  Default: db.sqlite in output_dir.  If you use another format (like csv), you should not use --out-db, but you will end up with a lot of csv files")
parser.add_argument("--group", default=None, action='store_true', help="If true, treate base_url as a group.  Required for group downloads.")
parser.add_argument("-v", "--verbose", default=None, action='store_true')
parser.add_argument("--start", default=None, help="Earliest time to download (expanded to nearest whole day)")
parser.add_argument("--end", default=None, help="Latest time to download (expanded to nearest whole day)")
parser.add_argument("--force-recreate", action='store_true', default=None, help="Force-recreate all databases")
parser.add_argument("--unsafe", action='store_true', default=None, help="Open database in unsafe mode.  May be slightly faster, but could corrupt the database under certain circumstances.")

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
        raise Exception("requests failure: %s %s (on %s %s)"%(r.status_code, r.reason, url, params))
    return r.text

format = args.format
today = datetime.date.today()
os.makedirs(args.output_dir, exist_ok=True)

#for converter in args.converter.split(','):

# Get data
if not args.group:
    R = get(os.path.join(baseurl, 'json'))
else:
    print(os.path.join(baseurl, args.converter, 'json'))
    R = get(os.path.join(baseurl, args.converter, 'json'))
print(R)
data = json.loads(R)
if data['data_exists']:
    has_new_data = False
    earliest_ts = data['data_earliest']
    latest_ts = data['data_latest']
    if args.start:
        import dateutil.parser
        start = dateutil.parser.parse(args.start).timestamp()
        earliest_ts = max(earliest_ts, start)
    if args.end:
        import dateutil.parser
        end = dateutil.parser.parse(args.end).timestamp()
        latest_ts = min(latest_ts, end)
    earliest = datetime.datetime.fromtimestamp(earliest_ts)
    latest = datetime.datetime.fromtimestamp(latest_ts)
    current_day = earliest.date() - datetime.timedelta(days=1)

    new_files = [ ]
    def cleanup_files(files):
        for file_ in files:
            os.unlink(file_)
    atexit.register(cleanup_files, new_files)

    while current_day < latest.date():
        # process [current_date, current_date+1)
        current_day += datetime.timedelta(days=1)

        is_partial = False
        outfile = current_day.strftime(args.converter+'.%Y-%m-%d'+'.'+format)
        outfile = os.path.join(args.output_dir, outfile)
        if os.path.exists(outfile+'.partial') and current_day != today:
            os.unlink(outfile+'.partial')
        if current_day == today:
            outfile = outfile + '.partial'
            is_partial = True

        #print('  '+outfile, end='  ', flush=True)

        redownload_today = True  # remove .partial from today, too?
        if os.path.exists(outfile) and (current_day != today or not redownload_today):
            #print()
            if VERBOSE: print('  '+outfile)
            continue

        # download data
        has_new_data = True
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
        if not is_partial:
            new_files.append(outfile)

    if (has_new_data or args.force_recreate) and format == 'sqlite3dump':
        all_files = glob.glob(os.path.join(args.output_dir, args.converter+'.*.sqlite3dump'))
        all_files += glob.glob(os.path.join(args.output_dir, args.converter+'.*.sqlite3dump.partial'))
        all_files.sort()
        if args.out_db is None:
            dbfiles = [os.path.join(args.output_dir, 'db.sqlite3')]
        else:
            dbfiles = args.out_db.split(',')
        for dbfile in dbfiles:
            print("Importing to DB:", dbfile)
            dbfile, *dbfile_args = dbfile.split(':')
            new_db = 'updateonly' not in dbfile_args
            incremental_update = 'incremental' in dbfile_args
            if incremental_update:
                new_db = False
            print("  new_db=%s"%new_db)

            dbfile_new = dbfile
            if new_db:
                dbfile_new = dbfile+'.new'
                if os.path.exists(dbfile_new): os.unlink(dbfile_new)
            elif incremental_update:
                pass
            else:
                # Delete the existing table
                subprocess.check_call(['sqlite3', dbfile, 'DROP TABLE IF EXISTS %s;'%args.converter])

            t1 = time.time()
            # Import the database
            sql_proc = subprocess.Popen(['sqlite3', dbfile_new, '-batch'], stdin=subprocess.PIPE)
            sql_proc.stdin.write(b'.bail ON\n')
            #sql_proc.stdin.write(b'.echo ON\n')
            if args.unsafe:
                sql_proc.stdin.write(b'PRAGMA journal_mode = OFF;\n')
                sql_proc.stdin.write(b'PRAGMA synchronous = OFF;\n')
            # Do we load all files into the database
            if incremental_update:
                files = new_files
            else:
                files = all_files
            for filename in files:
                cmd = '.read %s'%filename
                if VERBOSE: print('  '+cmd)
                sql_proc.stdin.write(cmd.encode()+b'\n')
                sql_proc.stdin.flush()
                time.sleep(1)
            if args.unsafe:
                sql_proc.stdin.write(b'PRAGMA synchronous = NORMAL;\n')
            sql_proc.stdin.close()
            sql_proc.wait()
            # Make indexes as needed
            import sqlite3
            conn = sqlite3.connect(dbfile_new)
            try:
                idxsql = ('user', 'time')
                conn.execute('CREATE INDEX {table}_{idxid} ON {table} ({columns})'.format(table=args.converter, idxid='_'.join(idxsql), columns=', '.join(idxsql)))
            except sqlite3.OperationalError:
                # Can't make user,time: do (user) only and (time) only if possible.
                try:
                    idxsql = ('user', )
                    conn.execute('CREATE INDEX {table}_{idxid} ON {table} ({columns})'.format(table=args.converter, idxid='_'.join(idxsql), columns=', '.join(idxsql)))
                except sqlite3.OperationalError: pass
                try:
                    idxsql = ('time', )
                    conn.execute('CREATE INDEX {table}_{idxid} ON {table} ({columns})'.format(table=args.converter, idxid='_'.join(idxsql), columns=', '.join(idxsql)))
                except sqlite3.OperationalError: pass
            #for idxsql in [('user', ), ('user', 'time', )]:
            #    sql_proc.stdin.write('CREATE INDEX {table}_{idxid} ON {table} ({columns}) ;\n'.format(table=args.converter, idxid='_'.join(idxsql), columns=', '.join(idxsql)).encode())
            dt = time.time() - t1
            if new_db:
                os.rename(dbfile_new, dbfile)
            print('Import done: %12d  %4.1fs'%(os.stat(dbfile).st_size, dt))

    # Commit files, unmark them as pending
    for file_ in reversed(list(new_files)):
       new_files.remove(file_)
