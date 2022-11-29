#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s', level=logging.INFO)
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

import sys
import getopt
import traceback
import json
from datetime import datetime, timedelta
from dateutil.parser import parse

DEFAULT_PROJECT_NAME = 'visual-essays'
DEFAULT_BUCKET_NAME = 'visual-essays'
DEFAULT_CREDS_PATH = os.path.join(BASEDIR, 'gcreds.json')

from google.oauth2 import service_account
from google.cloud import storage

class Bucket(object):

    def __init__(self, bucket=DEFAULT_PROJECT_NAME, **kwargs):
        self.project_name = kwargs.get('project', DEFAULT_PROJECT_NAME)
        self.bucket_name = bucket
        self.creds_path = kwargs.get('creds_path', DEFAULT_CREDS_PATH)
        logger.debug(f'gcs.init: project={self.project_name} bucket={self.bucket_name} creds={self.creds_path} creds_exists={os.path.exists(self.creds_path)}')
        credentials = service_account.Credentials.from_service_account_file(self.creds_path)
        self.client = storage.Client(self.project_name, credentials)
        self.bucket = self.client.get_bucket(self.bucket_name)
        logger.debug(f'gcrs: project={self.project_name} bucket={self.bucket_name}')

    def __contains__(self, key):
        logger.debug(f'{key} local={key in self.local} gc={self.bucket.blob(key).exists()}')
        return self.bucket.blob(key).exists()

    def __setitem__(self, key, value):
        blob = self.bucket.blob(key)
        blob.upload_from_string(value)

    def __getitem__(self, key):
        logger.debug(f'__getitem__: key={key}')
        item = None
        blob = self.bucket.blob(key)
        try:
            item = blob.download_as_string().decode('utf-8')
        except Exception as ex:
            if ex.response.status_code == 404:
                raise KeyError
        return item

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __delitem__(self, key):
        blob = self.bucket.blob(key)
        if blob:
            blob.delete()

    def __iter__(self, prefix=None):
        return self.client.list_blobs(self.bucket, prefix=prefix)._items_iter()

    def items(self, prefix=None):
        for blob in self.__iter__(prefix):
            yield blob.name, self[blob.name]

    def iteritems(self):
        for blob in self.__iter__():
            yield blob.name, self[blob.name]

    def keys(self, prefix=None):
        for blob in self.__iter__(prefix):
            yield blob.name

    def rename_object(self, key, new_key):
        obj = self.get(key)
        if obj:
            self.__setitem__(new_key, obj)
            self.__delitem__(key)

    def dir(self, prefix):
        prefix = prefix[:-1] if prefix.endswith('/') else prefix
        dir = set()
        for key in self.keys(prefix):
            key = key[len(prefix)+1:]
            dir.add(key if '/' not in key else key[:key.find('/')+1])
        return sorted(dir)

def usage():
    print('%s [hl:b:exup:rd] [keys]' % sys.argv[0])
    print('   -h --help            Print help message')
    print('   -l --loglevel        Logging level (default=warning)')
    print('   -b --bucket          Bucket name')
    print('   -e --exists          Check if item exists')
    print('   -x --delete          Delete item from database')
    print('   -u --upload          Upload file contents')
    print('   -p --prefix          Prefix for list filtering')
    print('   -r --rename          Rename S3 object')
    print('   -d --dirlist         Directory list')

if __name__ == '__main__':
    kwargs = {}
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hl:b:exup:rd', ['help', 'loglevel', 'bucket', 'exists', 'delete', 'upload', 'prefix', 'rename', 'dirlist'])
    except getopt.GetoptError as err:
        # print help information and exit:
        print(str(err)) # will print something like "option -a not recognized"
        usage()
        sys.exit(2)

    for o, a in opts:
        if o in ('-l', '--loglevel'):
            loglevel = a.lower()
            if loglevel in ('error',): logger.setLevel(logging.ERROR)
            elif loglevel in ('warn','warning'): logger.setLevel(logging.INFO)
            elif loglevel in ('info',): logger.setLevel(logging.INFO)
            elif loglevel in ('debug',): logger.setLevel(logging.DEBUG)
        elif o in ('-b', '--name'):
            kwargs['name'] = a
        elif o in ('-e', '--exists'):
            kwargs['exists'] = True
        elif o in ('-x', '--delete'):
            kwargs['delete'] = True
        elif o in ('-u', '--upload'):
            kwargs['upload'] = True
        elif o in ('-p', '--prefix'):
            kwargs['prefix'] = a
        elif o in ('-r', '--rename'):
            kwargs['rename'] = True
        elif o in ('-d', '--dirlist'):
            kwargs['dirlist'] = True
        elif o in ('-h', '--help'):
            usage()
            sys.exit()
        else:
            assert False, 'unhandled option'

    bucket = Bucket(**kwargs)
    if sys.stdin.isatty():
        if args:
            if len(args) == 1:
                if kwargs.get('upload', False):
                    path = args[0]
                    object_key = '/'.join(path.split('/')[-2:])
                    with open(path, 'rb') as fp:
                        bucket[object_key] = fp.read()
                if kwargs.get('delete', False):
                    del bucket[args[0]]
                elif kwargs.get('exists', False):
                    print(args[0] in bucket)
                elif kwargs.get('dirlist', False):
                    for key in bucket.dir(args[0]):
                        print(key)
                else:
                    print(bucket.get(args[0]).decode('utf-8'))
            elif len(args) == 2:
                if kwargs.get('rename', False):
                    key, new_key = args
                    bucket.rename_object(key, new_key)
                else: # copy local file to s3
                    object_key, path = args
                    with open(path, 'rb') as fp:
                        bucket[object_key] = fp.read()
        elif 'prefix' in kwargs:
            for key in bucket.keys(kwargs['prefix']):
                print(key)    
        else:
            for key in bucket:
                print(key)
    else:
        if args:
            obj = sys.stdin.read()
            bucket[args[0]] = obj
