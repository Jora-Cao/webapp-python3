#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Michael Liao'

' url handlers '

import re, time, json, logging, hashlib, base64, asyncio

import markdown2

from aiohttp import web

from coroweb import get, post
from apis import Page, APIValueError, APIResourceNotFoundError

from models import User, Comment, Blog, next_id
from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret

def check_admin(request):
  logging.info('============request------------------')
  logging.info(request)
  logging.info('check user: %s %s' % (request.method, request.path))
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = yield from cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  #logging.info('set current user: %s' % request.__user__.email)
  if request.__user__ is None or not request.__user__.admin:
    raise APIPermissionError()

def get_page_index(page_str):
  p = 1
  try:
    p = int(page_str)
  except ValueError as e:
    pass
  if p < 1:
    p = 1
  return p

def user2cookie(user, max_age):
  '''
  Generate cookie str by user.
  '''
  # build cookie string by: id-expires-sha1
  expires = str(int(time.time() + max_age))
  s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
  L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
  return '-'.join(L)

def text2html(text):
  lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
  return ''.join(lines)

@asyncio.coroutine
def cookie2user(cookie_str):
  '''
  Parse cookie and load user if cookie is valid.
  '''
  if not cookie_str:
    return None
  try:
    L = cookie_str.split('-')
    if len(L) != 3:
      return None
    uid, expires, sha1 = L
    if int(expires) < time.time():
      return None
    user = yield from User.find(uid)
    if user is None:
      return None
    s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
    if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
      logging.info('invalid sha1')
      return None
    user.passwd = '******'
    return user
  except Exception as e:
    logging.exception(e)
    return None

@get('/')
async def index(request, *, page='1'):
  page_index = get_page_index(page)
  num = await Blog.findNumber('count(id)')
  page = Page(num,page_index)
  #logging.info("-----------------------------------------------------")
  #logging.info(_COOKIE_KEY)
  #a = auth_factory(request)
  if num == 0:
    blogs = []
  else:
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
  logging.info('check user: %s %s' % (request.method, request.path))
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  return {
    '__template__': 'blogs.html',
    'page': page,
    'blogs': blogs,
    '__user__': request.__user__
  }


# @get('/')
# async def index(request):
#   summary = ''
#   blogs = [
#     Blog(id='1', name='Test Blog', summary=summary, createdat=time.time() - 120),
#     Blog(id='2', name='Something New', summary=summary, createdat=time.time() - 3600),
#     Blog(id='3', name='Learn Swift', summary=summary, createdat=time.time() - 7200)
#   ]
#   logging.info( request)
#   return {
#     'template': 'blogs.html',
#     'blogs': blogs,
#     #'__user__': request.__user__ # 这里要返回去
#   }

@get('/blog/{id}')
async def get_blog(id, request):
  logging.info('check user: %s %s' % (request.method, request.path))
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  blog = await Blog.find(id)
  comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
  for c in comments:
    c.html_content = text2html(c.content)
  blog.html_content = markdown2.markdown(blog.content)
  return {
    '__template__': 'blog.html',
    'blog': blog,
    '__user__': request.__user__,
    'comments': comments
  }

@get('/register')
def register():
  return {
    '__template__': 'register.html'
  }

@get('/signin')
def signin():
  return {
    '__template__': 'signin.html'
  }

@post('/api/authenticate')
async def authenticate(*, email, passwd):
  if not email:
    raise APIValueError('email', 'Invalid email.')
  if not passwd:
    raise APIValueError('passwd', 'Invalid password.')
  users = await User.findAll('email=?', [email])
  logging.info("Jora test")
  logging.info(users)
  if len(users) == 0:
    raise APIValueError('email', 'Email not exist.')
  user = users[0]
  # check passwd:
  sha1 = hashlib.sha1()
  sha1.update(user.id.encode('utf-8'))
  sha1.update(b':')
  sha1.update(passwd.encode('utf-8'))
  if user.passwd != sha1.hexdigest():
    raise APIValueError('passwd', 'Invalid password.')
  # authenticate ok, set cookie:
  r = web.Response()
  r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
  user.passwd = '******'
  r.content_type = 'application/json'
  r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
  #logging.info(r.body.email)
  return r

@asyncio.coroutine
def auth_factory(app, handler):
  @asyncio.coroutine
  def auth(request):
    logging.info('check user: %s %s' % (request.method, request.path))
    request.__user__ = None
    cookie_str = request.cookies.get(COOKIE_NAME)
    if cookie_str:
      user = yield from cookie2user(cookie_str)
      if user:
        logging.info('set current user: %s' % user.email)
        request.__user__ = user
    return (yield from handler(request))
  return auth

@get('/signout')
def signout(request):
  referer = request.headers.get('Referer')
  r = web.HTTPFound(referer or '/')
  r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
  logging.info('user signed out.')
  return r

@get('/manage/')
def manage():
  return 'redirect:/manage/comments'

@get('/manage/comments')
def manage_comments(*, page='1'):
  return {
    '__template__': 'manage_comments.html',
    'page_index': get_page_index(page)
  }

@get('/manage/blogs')
async def manage_blogs(request,*, page='1'):
  logging.info('check user: %s %s' % (request.method, request.path))
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  return {
    '__template__': 'manage_blogs.html',
    'page_index': get_page_index(page),
    '__user__': request.__user__
  }

@get('/manage/blogs/create')
async def manage_create_blog(request):
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  return {
    '__template__': 'manage_blog_edit.html',
    'id': '',
    'action': '/api/blogs',
    '__user__': request.__user__
  }

@get('/manage/blogs/edit')
async def manage_edit_blog(request, *, id):
  #request.__user__ = None
  logging.info('-------------------')
  cookie_str = request.cookies.get(COOKIE_NAME)
  logging.info('==========================')
  logging.info(cookie_str)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  return {
    '__template__': 'manage_blog_edit.html',
    'id': id,
    'action': '/api/blogs/%s' % id,
    '__user__': request.__user__
  }

@get('/manage/users')
def manage_users(*, page='1'):
  return {
    '__template__': 'manage_users.html',
    'page_index': get_page_index(page)
  }

@get('/api/comments')
def api_comments(*, page='1'):
  page_index = get_page_index(page)
  num = yield from Comment.findNumber('count(id)')
  p = Page(num, page_index)
  if num == 0:
    return dict(page=p, comments=())
  comments = yield from Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
  return dict(page=p, comments=comments)

@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
  logging.info('check user: %s %s' % (request.method, request.path))
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  if user is None:
    raise APIPermissionError('Please signin first.')
  if not content or not content.strip():
    raise APIValueError('content')
  blog = await Blog.find(id)
  if blog is None:
    raise APIResourceNotFoundError('Blog')
  comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
  await comment.save()
  return comment

@post('/api/comments/{id}/delete')
def api_delete_comments(id, request):
  check_admin(request)
  c = yield from Comment.find(id)
  if c is None:
    raise APIResourceNotFoundError('Comment')
  yield from c.remove()
  return dict(id=id)

@get('/api/users')
async def api_get_users(*, page='1'):
  page_index = get_page_index(page)
  num = await User.findNumber('count(id)')
  p = Page(num, page_index)
  if num == 0:
    return dict(page=p, users=())
  users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
  for u in users:
    u.passwd = '******'
  return dict(page=p, users=users)

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

@post('/api/users')
def api_register_user(*, email, name, passwd):
  if not name or not name.strip():
    raise APIValueError('name')
  if not email or not _RE_EMAIL.match(email):
    raise APIValueError('email')
  if not passwd or not _RE_SHA1.match(passwd):
    raise APIValueError('passwd')
  users = yield from User.findAll('email=?', [email])
  if len(users) > 0:
    raise APIError('register:failed', 'email', 'Email is already in use.')
  uid = next_id()
  sha1_passwd = '%s:%s' % (uid, passwd)
  user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
  yield from user.save()
  # make session cookie:
  r = web.Response()
  r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
  user.passwd = '******'
  r.content_type = 'application/json'
  r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
  return r

@get('/api/blogs')
async def api_blogs(*, page='1'):
  page_index = get_page_index(page)
  num = await Blog.findNumber('count(id)')
  p = Page(num, page_index)
  if num == 0:
    return dict(page=p, blogs=())
  blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
  return dict(page=p, blogs=blogs)

@get('/api/blogs/{id}')
def api_get_blog(*, id):
  blog = yield from Blog.find(id)
  return blog

@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
  logging.info('check user: %s %s' % (request.method, request.path))
  request.__user__ = None
  cookie_str = request.cookies.get(COOKIE_NAME)
  if cookie_str:
    user = await cookie2user(cookie_str)
    if user:
      logging.info('set current user: %s' % user.email)
      request.__user__ = user
  check_admin(request)
  if not name or not name.strip():
    raise APIValueError('name', 'name cannot be empty.')
  if not summary or not summary.strip():
    raise APIValueError('summary', 'summary cannot be empty.')
  if not content or not content.strip():
    raise APIValueError('content', 'content cannot be empty.')
  blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
  await blog.save()
  return blog

@post('/api/blogs/{id}')
def api_update_blog(id, request, *, name, summary, content):
  check_admin(request)
  blog = yield from Blog.find(id)
  if not name or not name.strip():
    raise APIValueError('name', 'name cannot be empty.')
  if not summary or not summary.strip():
    raise APIValueError('summary', 'summary cannot be empty.')
  if not content or not content.strip():
    raise APIValueError('content', 'content cannot be empty.')
  blog.name = name.strip()
  blog.summary = summary.strip()
  blog.content = content.strip()
  yield from blog.update()
  return blog

@post('/api/blogs/{id}/delete')
def api_delete_blog(request, *, id):
  check_admin(request)
  blog = yield from Blog.find(id)
  yield from blog.remove()
  return dict(id=id)