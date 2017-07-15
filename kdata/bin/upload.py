"""Upload data to koota.

This is a stand-alone command line program which can upload data to
the Koota server.  It should have no dependencies besides straight
Python.

Usage:
    $ python upload.py device_id data_file

Data packets should be split into smaller chuckns (ideally ~100 kb),
and then uploaded separately.  This script should be modified to do
that, and then upload each chuck in sequence.  Be careful to consider
the case of errors, so that each chuck will be uploaded once but no
more than once.

TODO: verify SSL certificates and use the pinned endpoint.  (two
complexities: may need another dependency, may need actual other files
on disk thus making this not a single file.)

"""

from __future__ import print_function

DEFAULT_URL = 'https://data.koota.cs.aalto.fi/post/'

import hashlib
import json
try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import Request, urlopen, HTTPError

def post_data(device_id, data, url):
    data_sha256 = hashlib.sha256(data).hexdigest()
    _r = Request(url=url,
                 data=data,
                 headers={'Device-ID': device_id,
                          'X-Sha256': data_sha256,
                          'X-Rowid': '1'})
    try:
        r = urlopen(_r)
        try:
            response = r.read()
            response = json.loads(response.decode('utf-8'))
            # py3 / py2 comptability
            print('  HTTP status:', r.getcode())
            print('  Response:', response)
            if response.get('ok', False):
                return 0
            if data_sha256 != response.get('data_sha256', ''):
                return 0
            return 1
        finally:
            r.close()
    except HTTPError as e:
        print('  HTTP error:', e.getcode(), e.reason)
        return 1




if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Upload data to koota server")
    parser.add_argument('device_id', help='device id to upload to')
    parser.add_argument('data_filename', help='Data to device id to upload to')
    parser.add_argument('--url', help='URL to post to',
                        default=DEFAULT_URL)
    args = parser.parse_args()

    device_id = args.device_id
    data = open(args.data_filename, 'rb').read()

    # Test the stuff
    #print(device_id)
    #print(data)

    # Do any re-processing of the data here.
    data_packets = [ data ]

    # Upload each packet in sequence.  We have to be careful to make
    # sure that each packet is recorded, and also to send each packet
    # only once.  We do this in a loop.  If there were problems, you
    # would have to manully adjust the program to start from the first
    # broken packet.
    for i, packet in enumerate(data_packets):
        #if i <= ...:
        #    continue
        print("Packet:", i)

        # The following line will post a single data packet.
        status = post_data(args.device_id, data, url=args.url)
        if status:
            print('Packet %s failed'%i)
            exit(1)
            # Abort here.  You should rerun remembering to not upload
            # old packets again.

        print("Packet done:", i)

    exit(status)

