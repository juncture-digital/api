#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = SCRIPT_DIR
while not os.path.exists(f'{BASEDIR}/static'):
  BASEDIR = os.path.dirname(BASEDIR)
STATICDIR = f'{BASEDIR}/static'

import re
from time import time as now
from collections import namedtuple
from urllib.parse import quote

from mdrender.generators import default

from bs4 import BeautifulSoup

import markdown

from mdrender.gh import has_gh_repo_prefix, get_gh_file, gh_dirlist, get_default_branch
from mdrender import gcs
from mdrender import s3

STORE = 'gc' if 'K_CONFIGURATION' in os.environ else 'aws'

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

css_cache = {}
def fetch_css(url, refresh=False):
  logger.debug(f'fetch_css: url={url} refresh={refresh}')
  if refresh or url not in css_cache:
    resp = requests.get(url)
    if resp.status_code == 200:
      css_cache[url] = resp.text
  return css_cache.get(url)

def convert_urls(soup, md_source, prefix, ref, base_url, ghp=False):
  logger.debug(f'convert_urls: prefix={prefix} ref={ref} base_url={base_url} ghp={ghp}')
  
  # remove Github badges
  for img in soup.find_all('img'):
    if 've-button.png' in img.attrs['src']:
      img.parent.decompose()
  
  # convert absolute links
  for elem in soup.find_all(href=True):
    if md_source.source == 'github':
      orig = elem.attrs['href']
      if elem.attrs['href'].startswith('/'):
        if ghp:
          base = f'/{md_source.repo}/'
        else:
          base_elems = [elem for elem in base_url.split('/') if elem]
          if len(base_elems) >= 2 and base_elems[0] == md_source.acct and base_elems[1] == md_source.repo:
            base = f'/{md_source.acct}/{md_source.repo}/'
          else:
            base = '/'
            # base = base_url
        converted = base + elem.attrs['href'][1:] + (f'?ref={ref}' if ref else '')
        elem.attrs['href'] = converted
      else:
        if ref:
          elem.attrs['href'] += f'?ref={ref}'
      logger.debug(f'orig={orig} base={base_url} converted={elem.attrs["href"]}')
  
  # convert image URLs
  for elem in soup.find_all(src=True):
    if elem.attrs['src'].startswith('http') or elem.name.startswith('ve-'): continue
    if md_source.source == 'github': # create github content url 
      base_url_path_elems = base_url.split('/')[6:-1]
      src_elems = [pe for pe in re.sub(r'^\.\/', '', elem.attrs['src']).split('/') if pe]
      up = src_elems.count('..')
      gh_path = '/'.join(base_url_path_elems[:-up] + src_elems[up:])
      elem.attrs['src'] = f'https://raw.githubusercontent.com/{md_source.acct}/{md_source.repo}/{md_source.ref}/{gh_path}'
    elif elem.attrs['src'].startswith('/'):
      elem.attrs['src'] = f'{base_url}{elem.attrs["src"][1:]}'
  
  param_elems = soup.find_all('param')
  if param_elems:
    gh_acct = md_source.acct if md_source.source == 'github' else prefix.split('/')[0]
    gh_repo = md_source.repo if md_source.source == 'github' else prefix.split('/')[1]
    gh_ref = md_source.ref if md_source.source == 'github' else get_default_branch(gh_acct, gh_repo)
    for elem in param_elems:
      for fld in ('url', 'banner'):
        if fld in elem.attrs and not elem.attrs[fld].startswith('http'):
          orig = elem.attrs[fld]
          gh_path = elem.attrs[fld]
          base = f'/{gh_acct}/{gh_repo}/{gh_ref}'
          if gh_path.startswith('/'):
            gh_path = f'{base}{gh_path}'
          else:
            elems = [elem for elem in base_url.split('/') if elem]
            elems = elems[2:-1] if len(elems) >= 2 and elems[0] == gh_acct and elems[1] == gh_repo else elems[:-1]
            gh_path = f'{base}/' + '/'.join(elems) + ('/' if elems else '') + gh_path
          elem.attrs[fld] = f'https://raw.githubusercontent.com{gh_path}'
          logger.debug(f'orig={orig} base_url={base_url} new={elem.attrs[fld]}')

  return soup

def get_gcs_file(path):
  essays = gcs.Bucket(bucket='visual-essays')
  _user, _essay_path = path.split('/',1)
  match = None
  for key in essays.keys(_user):
    if key.split('/',1)[1] == _essay_path:
      match = key
      break
  if match:
    md = essays.get(match)
    source = {'markdown': md if md else '', 'source': 'google-cloud-storage', 'path': path}
    return namedtuple('ObjectName', source.keys())(*source.values())

def get_s3_file(path):
  essays = s3.Bucket(bucket='visual-essays')
  _user, _essay_path = path.split('/',1)
  match = None
  for key in essays.keys(_user):
    if key.split('/',1)[1] == _essay_path:
      match = key
      break
  if match:
    md = essays.get(match)
    source = {'markdown': md.decode('utf-8') if md else '', 'source': 's3', 'path': path}
    return namedtuple('ObjectName', source.keys())(*source.values())

def source_path(path, prefix):
  is_gh = False
  if path:
    path = path[:-1] if path[-1] == '/' else path
    if re.match(r'^[0-9a-f]{7,64}$', path):
      path = f'{path}/default'
    else:
      if '/' not in path: path = f'{prefix}/{path}'
      if not re.match(r'^[0-9a-f]{7,64}\/', path):
        if has_gh_repo_prefix(path):
         is_gh = True
        else:
          path = f'{prefix}/{path}'
          if not re.match(r'^[0-9a-f]{7,64}\/', prefix):
            is_gh = True
  elif prefix:
    path = prefix
    if re.match(r'^[0-9a-f]{7,64}$', prefix):
      path = f'{path}/default'
    elif not re.match(r'^[0-9a-f]{7,64}\/.+', prefix):
      is_gh = True
  logger.debug(f'is_gh={is_gh} prefix={prefix} path={path}')
  has_extension = '.' in path
  if not is_gh and not has_extension: path = f'{path}.md'
  return is_gh, path

def load_remote(url):
  markdown = ''
  resp = requests.get(url)
  if resp.status_code == 200:
    markdown = resp.text
  logger.debug(f'load_remote: url={url} status={resp.status_code} markdown_size={len(markdown)}')
  source = {'markdown': markdown, 'source': 'url', 'url': url}
  return namedtuple('ObjectName', source.keys())(*source.values())

def add_link(soup, href, attrs=None):
  link = soup.new_tag('link')
  link.attrs = {**{'href':href}, **(attrs if attrs else {})}
  soup.head.append(link)

def add_script(soup, src, attrs=None):
  script = soup.new_tag('script')
  script.attrs = {**{'src':src}, **(attrs if attrs else {})}
  soup.body.append(script)

def add_meta(soup, attrs=None):
  meta = soup.new_tag('meta')
  meta.attrs = attrs
  soup.head.append(meta)

def merge_entities(tag, qids=None):
  qids = qids or []
  qids = qids + [qid for qid in tag.attrs.get('entities','').split() if qid not in qids]
  return merge_entities(tag.parent, qids) if tag.parent else qids

def find_qids(text):
  return re.findall(r'\b(Q[0-9]+)\b', text) if text else []

def set_entities(soup):
  for p in soup.find_all('p'):
    qids = find_qids(p.string)
    if qids:
      p.string = re.sub(r'\b(Q[0-9]+)\b', '', p.string).rstrip()
      if p.string:
        p.attrs['entities'] = ' '.join(qids)
      else:
        p.parent.attrs['entities'] = ' '.join(qids)
        p.decompose()
    
    if p.string:
      lines = [line.strip() for line in p.string.split('\n')]
      if len(lines) > 1:
        match = re.match(r'\d{2}:\d{2}:\d{2}', lines[0])
        if match:
          new_p = BeautifulSoup(f'<p data-start={match[0]} entities="{" ".join(qids)}"><mark start="{match[0]}"><b>{lines[0]}</b></mark></br>{" ".join(lines[1:])}</p>', 'html5lib')
          p.replace_with(new_p.find('p'))
  
  for tag in ('p', 'section', 'main'):
    for el in soup.find_all(tag):
      qids = merge_entities(el)
      if qids:
        el.attrs['entities'] = ' '.join(qids)
        for child in el.find_all(recursive=False):
          if child.name.startswith('ve-'):
            child.attrs['entities'] = ' '.join(qids)

  '''
  for tag in ('main', 'section'):
    for el in soup.find_all(tag):
      if 'entities' in el.attrs:
        del el.attrs['entities']
  if 'entities' in soup.body.attrs:
    del soup.body.attrs['entities']
  '''

def _config_tabs(soup):
  for el in soup.find_all('section', class_='tabs'):
    # el_heading = next(el.children) 
    # el_heading.decompose()
    for idx, tab in enumerate(el.find_all('section', recursive=False)):
      heading = next(tab.children)
      # tab_id = tab.attrs['id'] if 'id' in tab.attrs else sha256(heading.text.encode('utf-8')).hexdigest()[:8]
      tab_id = f'tab{idx+1}'
      content_id = f'content{idx+1}'
      input = soup.new_tag('input')
      input.attrs = {'type': 'radio', 'name': 'tabs', 'id': tab_id}
      tab.attrs['class'].append('tab')
      if idx == 0:
        input.attrs['checked'] = ''
      label = soup.new_tag('label')
      label.string = heading.text
      label.attrs = {'for': tab_id}
      el.insert(idx*2, input)
      el.insert(idx*2+1, label)
      tab.attrs['class'].append(content_id)
      heading.decompose()

def quote_fname(url):
  parts = url[:-1].split('/') if url.endswith('/') else url.split('/')
  parts[-1] = quote(parts[-1])
  return '/'.join(parts) 
  
def _config_cards(soup):
  for el in soup.find_all('section', class_='cards'):
    cards_wrapper = soup.new_tag('section')
    el.attrs['class'] = [cls for cls in el.attrs['class'] if cls != 'cards']
    cards_wrapper.attrs['class'] = ['cards', 'wrapper']
    for card in el.find_all('section', recursive=False):
      
      heading = next(card.children)
      if 'href' in card.attrs:
        card_title = soup.new_tag('a')
        card_title.attrs['href'] = card.attrs['href']
      else:
        card_title = soup.new_tag('span')
      card_title.attrs['class'] = 'card-title'
      card_title.string = heading.text
      card.insert(0,card_title)
      heading.decompose()

      if card.p.img:
        
        img_style = {
          'background-image': f"url('{quote_fname(card.p.img.attrs['src'])}')",
          'background-repeat': 'no-repeat',
          'background-size': 'cover',
          'background-position': 'center'
        }
        style = '; '.join([f'{key}:{value}' for key,value in img_style.items()]) + ';'
        img = soup.new_tag('div')
        img.attrs['class'] = 'card-image'
        img.attrs['style'] = style
        card.insert(1,img)
        card.p.decompose()

      if card.ul:
        card.ul.attrs['class'] = 'card-metadata'
        for li in card.ul.find_all('li'):
          if li.text.split(':')[0].lower() in ('coords', 'eid', 'qid'):
            li.attrs['class'] = 'hide'
  
      if card.p:
        card.p.attrs['class'] = 'card-abstract'

      card.attrs['class'].append('card')
      cards_wrapper.append(card)
    el.append(cards_wrapper)

_default_footer_md = '''
.ve-footer
    - Brought to you by:  [![](https://raw.githubusercontent.com/jstor-labs/juncture-digital/c7d73fb/images/Labs_logo_knockout.svg)](https://labs.jstor.org)
    - [About]()
    - [Terms and conditions]()
'''
_default_footer = None
def get_default_footer():
  global _default_footer
  if _default_footer is None:
    _default_footer = BeautifulSoup(
      markdown.markdown(
        _default_footer_md,
        extensions=['customblocks',],
        extension_configs={'customblocks': {'fallback': default, 'generators': {'default': 'md.generators:default'}}}
      ),
    'html5lib').find('ve-footer')
  return _default_footer
  
def to_html(md_source, prefix, ref, base_url, env='PROD', host=None, inline=False, ghp=False, **kwargs):
  logger.info(f'to_html: prefix={prefix} path={md_source.path} base_url={base_url} env={env} host={host} inline={inline}')
  
  def replace_empty_headings(match):
    return re.sub(r'(#+)(.*)', r'\1 &nbsp;\2', match.group(0))
  
  # logger.info(md_source.markdown)
  md = re.sub(r'^#{1,6}(\s+)(\{.*\}\s*)?$', replace_empty_headings, md_source.markdown, flags=re.M)

  html = markdown.markdown(
    md,
    extensions=[
      'customblocks',
      'extra',
      'pymdownx.mark',
      'mdx_outline',
      'codehilite',
      'prependnewline',
      'fenced_code',
      'mdx_breakless_lists',
      'sane_lists'
      # 'mdx_urlize'
    ],
    extension_configs = {
      'customblocks': {
        'fallback': default,
        'generators': {
          'default': 'md.generators:default'
        }
      }
    }
  )
  
  def em_repl(match):
    return match.group(0).replace('<em>','_').replace('</em>','_')

  html = re.sub(r'<h[1-6]>\s*&nbsp;\s*<\/h[1-6]>', '', html)
  html = re.sub(r'(\bwc:\S*<\/?em>.*\b)', em_repl, html)
    
  soup = BeautifulSoup(html, 'html5lib')

  convert_urls(soup, md_source, prefix, ref, base_url, ghp)

  add_hypothesis = soup.find('ve-add-hypothesis')
  custom_style = soup.find('ve-style')
  footer = soup.find('ve-footer')
  first_heading = soup.find(re.compile('^h[1-6]$'))
  
  _config_tabs(soup)
  _config_cards(soup)

  # insert a 'main' wrapper element around the essay content
  main = soup.html.body
  main.attrs = soup.html.body.attrs
  main.name = 'main'
  body = soup.new_tag('body')
  contents = main.replace_with(body)
  body.append(contents)

  footnotes = soup.find('div', class_='footnote')
  if footnotes:
    footnotes.name = 'section'
    contents.append(footnotes)

  if footer: main.append(footer)

  set_entities(soup)

  css = ''
  api_static_root_js = f'http://{host}:8000/static' if env == 'DEV' else 'https://api.juncture-digital.org/static'
  webapp_static_root_js = f'http://{host}:8080/static' if env == 'DEV' else 'https://visual-essays.github.io/web-app/static'
  css_root = f'http://localhost:3333/build' if env == 'DEV' else 'https://unpkg.com/visual-essays/dist/visual-essays'
  
  is_v1 = soup.find('param') is not None
  if is_v1:
    meta = soup.find('param', ve_config='')
    template = open(f'{STATICDIR}/v1/index.html', 'r').read()
    if prefix: template = template.replace('window.PREFIX = null', f"window.PREFIX = '{prefix}';")
    if ref: template = template.replace('window.REF = null', f"window.REF = '{ref}';")
    template = BeautifulSoup(template, 'html5lib')
    for el in template.find_all('component'):
      if 'v-bind:is' in el.attrs and el.attrs['v-bind:is'] == 'mainComponent':
        el.append(contents)
        break
    
    if inline:
      css = open(f'{STATICDIR}/v1/css/main.css', 'r').read()
    else:
      add_link(template, f'{api_static_root_js}/v1/css/main.css', {'rel': 'stylesheet'})

  else: # v2
    meta = soup.find('ve-meta')
    footer = soup.find('ve-footer')
    if prefix:
      for el in soup.find_all('ve-image'):
        el.attrs['anno-base'] = prefix + f'/{md_source.path}' if md_source.path else ''
      for el in soup.find_all('ve-media'):
        el.attrs['anno-base'] = prefix + f'/{md_source.path}' if md_source.path else ''
    template = open(f'{STATICDIR}/v2/index.html', 'r').read()
    if prefix: template = template.replace('window.PREFIX = null', f"window.PREFIX = '{prefix}';")
    if ref: template = template.replace('window.REF = null', f"window.REF = '{ref}';")
    template = BeautifulSoup(template, 'html5lib')
    template.body.insert(0, contents)
    
    if inline:
      # css += '\n' + fetch_css(f'{webapp_static_root_js}/{"base" if custom_style else "all"}.css', refresh=env=='DEV')
      css += '\n' + fetch_css(f'{css_root}/visual-essays.css', refresh=env=='DEV')
    else:
      # add_link(template, f'{webapp_static_root_js}/{"base" if custom_style else "all"}.css', {'rel': 'stylesheet'})
      add_link(template, 'https://unpkg.com/visual-essays/dist/visual-essays/visual-essays.css', {'rel': 'stylesheet'})

    if custom_style:
      if custom_style.attrs.get('href'):
        if custom_style.attrs['href'].startswith('http'):
          if inline:
            css += '\n' + fetch_css(custom_style.attrs['href'])
          else:
            add_link(template, custom_style.attrs['href'], {'rel': 'stylesheet'})
        else:
          store = s3.Bucket (bucket='visual-essays') if STORE == 'aws' else gcs.Bucket(bucket='visual-essays')
          css_path = custom_style.attrs['href'][1:] if custom_style.attrs['href'][0] == '/' else custom_style.attrs['href']
          found = next(iter([key for key in store.keys(prefix) if key.split('/',1)[-1] == css_path]), None)
          if found:
            css += '\n' + store.get(found).decode('utf-8')
      custom_style.decompose()
      
    if add_hypothesis:
      add_hypothesis.decompose()
      add_script(template, 'https://hypothes.is/embed.js', {'async': 'true'})

  base = template.find('base')
  if base:
    base.attrs['href'] = base_url
  
  if css:
    # add css as style tag
    style = soup.new_tag('style')
    style.attrs['data-id'] = 'default'
    style.string = css
    template.head.append(style)

  if inline:
    script = soup.new_tag('script')
    script.attrs['type'] = 'module'
    script.string = open(f'{STATICDIR}/{"v1" if is_v1 else "v2"}/js/main.js', 'r').read()
    template.body.append(script)
  else:
    add_script(template, f'{api_static_root_js}/{"v1" if is_v1 else "v2"}/js/main.js', {'type': 'module'})
  
  if soup.head.style:
    template.head.append(soup.head.style)

  if meta:
    for name in meta.attrs:
      if name == 'title':
        if not template.head.title:
          template.head.append(template.new_tag('title'))
        template.head.title.string = meta.attrs[name]
      elif name not in ('author', 'banner', 'layout'):
        add_meta(template, {'name': name, 'content': meta.attrs[name]})
    if meta.name == 've-meta':
      meta.decompose()
  # else:
    # add_meta(template, {'name': 'robots', 'content': 'noindex'})
  
  if not (template.head.title and template.head.title.string) and first_heading:
    title = soup.new_tag('title')
    title.string = first_heading.text
    template.head.append(title)
    
  if not is_v1 and footer is None:
    template.find('main').append(get_default_footer())
    
  html = str(template)
  html = re.sub(r'\s+<p>\s+<\/p>', '', html) # removes empty paragraphs
  
  return html

def get_file(path=None, prefix=None, url=None, ref=None, source=None, **kwargs):
  logger.debug(f'get_file: path={path} url={url} prefix={prefix} ref={ref} source={source}')
  if url:
    md_source = load_remote(url)
  else:
    _is_gh, _path = source_path(path, prefix)
    md_source = get_gh_file(_path, ref) if _is_gh else get_gcs_file(_path) if STORE == 'gc' else get_s3_file(_path)
  return md_source

def get_html(path=None, url=None, markdown=None, prefix=None, ref=None, source=None, **kwargs):
  start = now()
  if markdown:
    source = {'markdown': markdown, 'source': 'input', 'path': path}
    md_source = namedtuple('ObjectName', source.keys())(*source.values())
  else:
    md_source = get_file(path, prefix, url, ref, source)
  if md_source:
    if md_source.source == 'github':
      prefix = f'{md_source.acct}/{md_source.repo}'
    html = to_html(md_source, prefix, ref, path=md_source.path, **kwargs) if md_source else None
    logger.debug(f'get_html: path={path} url={url} source={md_source.source if md_source else None} base_url={kwargs.get("base_url")} prefix={prefix} ref={ref} markdown={markdown is not None} elapsed={round(now()-start,3)}')
    return html

def dir_list(path=None, **kwargs):
  if re.match(r'^[0-9a-f]{7,64}', path): # s3 or gcs list
    store = s3.Bucket (bucket='visual-essays') if STORE == 'aws' else gcs.Bucket(bucket='visual-essays')
    return store.dir(prefix=path)
  else: # gh list
    path_elems = [pe for pe in path.split('/') if pe]
    if len(path_elems) >= 2:
      acct = path_elems[0]
      repo = path_elems[1]
      root = '/'.join(path_elems[2:])
      return gh_dirlist(acct, repo, root)
    