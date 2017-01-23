#!/usr/bin/env python3
# -*- coding:utf-9 -*-

import asyncio, os, inspect, logging, functools

from urllib import parse
from aiohttp import web
from apis import APIError

'''
Step1:
@asyncio.coroutine
def handle_url_xxx(request):
    pass


Step2:
url_param = request.match_info['key']
query_params = parse_qs(request.query_string)

Step3:
text = render('template', data)
return web.Response(text.encode('utf-8'))

'''