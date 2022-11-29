#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os, sys, json, yaml, re
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(SCRIPT_DIR)

from typing import List, Optional

from pydantic import BaseModel

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware

from starlette.responses import RedirectResponse

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

from search import SearchClient
search_client = SearchClient()

from mdrender import get_file, get_html, dir_list
from image_info import ImageInfo
from annotations import Annotations as AnnotationsClient
annos = AnnotationsClient()

from email_server import sendmail

from essays import Essays as EssaysClient

from prezi_upgrader import Upgrader

app = FastAPI(title='Juncture API', root_path='/')

app.mount('/static', StaticFiles(directory='static'), name='static')

CONFIG = yaml.load(open(f'{SCRIPT_DIR}/creds.yaml', 'r').read(), Loader=yaml.FullLoader)

web_components_source = 'https://unpkg.com/visual-essays/dist/visual-essays/visual-essays.esm.js'
local_web_components_source = 'http://localhost:3333/build/visual-essays.esm.js'

default_prefix = 'visual-essays/content'
# default_prefix = 'a3b5125'

app.add_middleware(
  CORSMiddleware,
  allow_origins=['*'],
  allow_methods=['*'],
  allow_headers=['*'],
  allow_credentials=True,
)

class Depicts(BaseModel):
  id: str
  label: Optional[str]
  prominent: Optional[bool]

class ResultsDoc(BaseModel):
  seq: int
  id: str
  title: str
  description: Optional[str] = None
  url: Optional[str] = None
  depicts: List[Depicts] = []
  tags: List[str] = []
  digital_representation_of: Optional[Depicts] = None
  thumbnail: Optional[str] = None
  owner: Optional[str] = None
  rights: Optional[str] = None
  weight: Optional[int] = 1

class SearchResults(BaseModel):
  total: int
  qtime: Optional[float] = None
  docs: List[ResultsDoc] = []
  
@app.get('/docs/')
@app.get('/')
def main():
  return RedirectResponse(url='/docs')

@app.get('/search/{qid}/', response_model=SearchResults, response_model_exclude_unset=True)
def search(
    qid: str,
    source: Optional[str] = 'commons,jstor',
    offset: Optional[int] = 0,
    limit: Optional[int] = 10,
    language: Optional[str] = 'en',
    refresh: Optional[bool] = False,
  ):
  
  logger.debug(f'search: qid={qid} source={source} limit={limit} language={language}')
  return search_client.search(
    qid=qid,
    source=source,
    offset=offset,
    limit=limit,
    language=language,
    refresh=refresh
  )

@app.get('/image-info/')
def image_info(url: str):
  status_code, info = ImageInfo()(url=url)
  return Response(
    status_code=status_code,
    content=json.dumps(info),
    media_type='application/json')

@app.get('/html/{path:path}/')
@app.get('/html/{path:path}')
@app.get('/html/')
@app.get('/html')
async def html(
  request: Request,
  path: Optional[str] = None,
  url: Optional[str] = None,
  base: Optional[str] = None,
  prefix: Optional[str] = default_prefix,
  ref: Optional[str] = None,
  inline: Optional[bool] = False,
  ghp: Optional[bool] = False
):
  ENV = 'DEV' if request.client.host in ('127.0.0.1', 'localhost') or request.client.host.startswith('192.168.') else 'PROD'
  referrer = request.headers.get('referer')
  base_url = base if base else referrer if referrer else '/'
  logger.debug(f'html: path={path} url={url} base_url={base_url} prefix={prefix} ENV={ENV} inline={inline} referrer={referrer}')
  html = get_html(
    path=path,
    url=url,
    base_url=base_url,
    prefix=prefix,
    ref=ref,
    inline=inline,
    env=ENV,
    host=request.client.host,
    ghp=ghp,
    web_components_source = local_web_components_source if ENV == 'DEV' else web_components_source
  )
  if html is None:
    raise HTTPException(status_code=404, detail='Not found')
  return Response(content=html, media_type='text/html')

@app.post('/html/')
async def markdown_to_html(
  request: Request,
  base: Optional[str] = None,
  inline: Optional[bool] = False
):
  ENV = 'DEV' if request.client.host in ('127.0.0.1', 'localhost') or request.client.host.startswith('192.168.') else 'PROD'
  payload = await request.body()
  payload = json.loads(payload.decode('utf-8'))
  markdown = payload['markdown']
  prefix = payload['prefix']
  referrer = request.headers.get('referer')
  base_url = base if base else referrer if referrer else '/'
  logger.debug(f'html: base_url={base_url} referrer={referrer} markdown_size={len(markdown)}')
  html = get_html(
    path=payload['path'],
    markdown=markdown,
    prefix=prefix,
    base_url=base_url, 
    inline=inline,
    env=ENV,
    host=request.client.host,
    web_components_source = local_web_components_source if ENV == 'DEV' else web_components_source
  )
  if html is None:
    raise HTTPException(status_code=404, detail='Not found')
  return Response(content=html, media_type='text/html')

@app.post('/annotation/')
async def create_annotation(request: Request):
  payload = await request.body()
  kwargs = json.loads(payload)
  kwargs['token'] = request.headers.get('authorization','').split()[-1]
  status_code, created = annos.create_annotation(**kwargs)
  return Response(
    status_code=status_code,
    content=json.dumps(created),
    media_type='application/json')

@app.get('/annotations/{path:path}/')
async def get_annotations(request: Request, path: str):
  return annos.get_annotations(path, re.sub(r'\/\/$', '/', str(request.base_url)))

@app.get('/annotation/{path:path}/')
async def get_annotation(request: Request, path: str):
  return annos.get_annotation(path, re.sub(r'\/\/$', '/', str(request.base_url)))

@app.put('/annotation/{path:path}/')
async def update_annotation(request: Request, path: str):
  annotation = await request.body()
  token = request.headers.get('authorization','').split()[-1]
  status_code, updated = annos.update_annotation(path, json.loads(annotation), token)
  return Response(status_code=status_code, content=json.dumps(updated))

@app.delete('/annotation/{path:path}/')
async def delete_annotation(request: Request, path: str):
  token = request.headers.get('authorization','').split()[-1]
  return Response(status_code=annos.delete_annotation(path, token))

@app.get('/file/{path:path}/')
@app.get('/file/{path:path}')
@app.get('/markdown/{path:path}/')
@app.get('/markdown/{path:path}')
@app.get('/markdown/')
def file(
  request: Request,
  path: Optional[str] = None,
  url: Optional[str] = None,
  prefix: Optional[str] = default_prefix,
  ref: Optional[str] = None
):
  source = 'gcs' if '/gcs/' in request.url.path else 's3' if '/gcs/' in request.url.path else None
  logger.debug(f'get_file: path={path} url={url} prefix={prefix} ref={ref} source={source}')
  md_source = get_file(path, prefix, url, ref, source)
  if md_source is None:
    raise HTTPException(status_code=404, detail='Not found')
  return Response(content=md_source.markdown, media_type='text/markdown')

@app.get('/dir/{path:path}/')
@app.get('/dir/{path:path}')
async def dir(path: str):
  return dir_list(path)

@app.post('/file/{path:path}/')
@app.post('/markdown/{path:path}/')
async def put_gcs(request: Request, path: str):
  content = await request.body()
  token = request.headers.get('authorization','').split()[-1]
  status_code, content = EssaysClient().put(path, content, token)
  return Response(status_code=status_code, content=content, media_type='text/plain')

@app.delete('/file/{path:path}/')
@app.delete('/markdown/{path:path}/')
async def delete_gcs(request: Request, path: str):
  token = request.headers.get('authorization','').split()[-1]
  return EssaysClient().delete(path, token)

@app.post('/sendmail/')
async def _sendmail(request: Request):
  referrer = request.headers.get('referer')
  body = await request.body()
  content, status_code = sendmail(**{**json.loads(body), **{'referrer': referrer}})
  return Response(status_code=status_code, content=content) 

@app.post('/prezi2to3/')
async def prezi2to3(request: Request):
  body = await request.body()
  v2_manifest = json.loads(body)
  upgrader = Upgrader(flags={
    'crawl': False,        # NOT YET IMPLEMENTED. Crawl to linked resources, such as AnnotationLists from a Manifest
    'desc_2_md': True,     # If true, then the source's `description` properties will be put into a `metadata` pair. If false, they will be put into `summary`.
    'related_2_md': False, # If true, then the `related` resource will go into a `metadata` pair. If false, it will become the `homepage` of the resource.
    'ext_ok': False,       # If true, then extensions are allowed and will be copied across.
    'default_lang': 'en',  # The default language to use when adding values to language maps.
    'deref_links': False,  # If true, the conversion will dereference external content resources to look for format and type.
    'debug': False,        # If true, then go into a more verbose debugging mode.
    'attribution_label': '', # The label to use for requiredStatement mapping from attribution
    'license_label': ''} # The label to use for non-conforming license URIs mapped into metadata
  )
  v3_manifest = upgrader.process_resource(v2_manifest, True) 
  v3_manifest = upgrader.reorder(v3_manifest)
  return v3_manifest

@app.get('/gh-token')
async def gh_token(request: Request, code: Optional[str] = None, hostname: Optional[str] = None):
  token = CONFIG['gh_unscoped_token']
  status_code = 200
  if code:
    if hostname in ('127.0.0.1','localhost') or hostname.startswith('192.168.'):
      token = CONFIG['gh_auth_token']
    elif hostname in CONFIG['gh_secrets']:
      resp = requests.post(
        'https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json'},
        data={
          'client_id': CONFIG['gh_secrets'][hostname]['gh_client_id'],
          'client_secret': CONFIG['gh_secrets'][hostname]['gh_client_secret'],
          'code': code
        }
      )
      status_code = resp.status_code
      token_obj = resp.json()
      token = token_obj['access_token'] if status_code == 200 else ''
  return Response(status_code=status_code, content=token, media_type='text/plain')

if __name__ == '__main__':
  app.run(debug=True, host='0.0.0.0', port=8000)
else:
  from mangum import Mangum
  handler = Mangum(app)
