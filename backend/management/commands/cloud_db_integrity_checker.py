import os
import re
import time
import aiohttp
import asyncio

import boto3
import requests
import numpy as np
import pandas as pd
from io import StringIO

from asgiref.sync import sync_to_async
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Crystal.settings')
import django

django.setup()
from backend.models import Stock
from utils.WassabiClient import initialize_wasabi_client

wasabi = initialize_wasabi_client()


def get_stock_db():
    # stocks =  Stock.objects.all().values('code')
    # stock_last_modified_dict = {
    #     stock['code']: stock['last_modified'] for stock in stocks
    # }
    return [x['code'] for x in Stock.objects.all().values('code')]


available_stock_data = {}
for s in get_stock_db():
    try:
        df = wasabi.fetch_data(s)
        date = df.iloc[0, 0]
        # print(s, date)
        if date not in available_stock_data.keys():
            available_stock_data[date] = [s]
        else:
            available_stock_data[date].append(s)
    except Exception as e:
        print(e)

for date in available_stock_data.keys():
    print(date)
    print(tuple(available_stock_data[date]))