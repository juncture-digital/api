#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
import sys
import json
import getopt
from time import time as now

DEFAULT_CACHE_DIR = '/data'
DEFAULT_CACHE_NAME = 'corpus'

import boto3
from botocore.exceptions import ClientError

DEFAULT_BUCKET_NAME = 'visual-essays'

class Bucket(object):
    
    def __init__(self, bucket=DEFAULT_BUCKET_NAME, **kwargs):
        self.bucket_name = bucket
        if 'AWS_LAMBDA_FUNCTION_NAME' in os.environ:
            self.s3 = boto3.client('s3')
        else:
            self.s3 = boto3.Session(
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
            ).client('s3')
        self.s3_paginator = self.s3.get_paginator('list_objects_v2')

    def __contains__(self, key):
        return self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=key)['KeyCount'] > 0

    def __setitem__(self, key, obj):
        return self.s3.put_object(Bucket=self.bucket_name, Key=key, Body=obj)

    def __getitem__(self, key):
        try:
            return self.s3.get_object(Bucket=self.bucket_name, Key=key)['Body'].read()
        except ClientError as ex:
            if ex.response['Error']['Code'] == 'NoSuchKey':
                raise KeyError

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __delitem__(self, key):
        return self.s3.delete_object(Bucket=self.bucket_name, Key=key)

    def __iter__(self, prefix='/', delimiter='/', start_after=''):
        logger.debug(f'__iter__: prefix={prefix}')
        prefix = prefix[1:] if prefix.startswith(delimiter) else prefix
        start_after = (start_after or prefix) if prefix.endswith(delimiter) else start_after
        for page in self.s3_paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, StartAfter=start_after):
            for content in page.get('Contents', ()):
                yield content['Key']

    def items(self, prefix='/', delimiter='/'):
        for key in self.__iter__(prefix, delimiter):
            yield key, self.get(key)

    def keys(self, prefix='/', delimiter='/'):
        return [key for key in self.__iter__(prefix, delimiter)]

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
