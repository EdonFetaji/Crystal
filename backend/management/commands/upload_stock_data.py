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

from celery import shared_task
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Crystal.settings')
import django

django.setup()
from backend.models import Stock

# Access environment variables
access_key = os.getenv("WASABI_ACCESS_KEY")
secret_key = os.getenv("WASABI_SECRET_KEY")
bucket_name = os.getenv("WASABI_BUCKET_NAME")

MAX_WORKERS = 10
s3_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
s3_client_pool = Queue(maxsize=MAX_WORKERS)


def initialize_s3_client_pool():
    for _ in range(MAX_WORKERS):
        s3_client = boto3.client(
            's3',
            endpoint_url='https://s3.eu-central-2.wasabisys.com',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        s3_client_pool.put(s3_client)


async def append_stock_data_to_cloud_async(code, new_df):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(s3_executor, append_stock_data_to_cloud, code, new_df)


def append_stock_data_to_cloud(code, new_df):
    s3 = s3_client_pool.get()  # Acquire an S3 client from the pool
    cloud_key = f"Stock_Data/{code}.csv"
    try:
        try:
            existing_file = s3.get_object(Bucket=bucket_name, Key=cloud_key)
            existing_df = pd.read_csv(StringIO(existing_file['Body'].read().decode('utf-8')))
            print(f"Successfully fetched existing data for {code}.")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"No existing data found for {code}. Creating a new file.")
                existing_df = None
            else:
                print(f"Error fetching existing data: {e}")
                return False

        if existing_df is not None:
            combined_df = pd.concat([new_df, existing_df]).drop_duplicates()
        else:
            combined_df = new_df

        csv_buffer = StringIO()
        combined_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        s3.put_object(
            Bucket=bucket_name,
            Key=cloud_key,
            Body=csv_buffer.getvalue()
        )
        print(f"Successfully appended and uploaded data for {code}.")

    except ClientError as e:
        print(f"Error uploading data: {e}")
    finally:
        s3_client_pool.put(s3)


async def process_data(stock, stock_df: pd.DataFrame):
    def is_valid_date_format(date_string):
        try:
            datetime.strptime(date_string, "%d.%m.%Y")
            return True
        except ValueError:
            return False

    def get_unformatted_data(data):
        mask = data['Date'].apply(lambda x: not is_valid_date_format(x))
        result = data[mask]
        return result

    def format_date_to_european(date_str):
        try:
            date_obj = datetime.strptime(date_str, '%m/%d/%Y')
            return date_obj.strftime('%d.%m.%Y')

        except (ValueError, TypeError):
            return date_str

    def format_price(value):
        if isinstance(value, str):
            parts = re.split(r'\D', value)
            if len(parts[-1]) <= 2:
                decimal_part = parts.pop()
                integer_part = ''.join(parts)
                cleaned_value = f"{integer_part}.{decimal_part}"
            else:
                cleaned_value = ''.join(parts)

            try:
                cleaned_float = float(cleaned_value)
                return f"{cleaned_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except ValueError:
                return "Invalid input format"

        elif isinstance(value, (int, float)):
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        return "Invalid input format"

    def format_data(stock_df):
        if stock_df is not None:
            df = get_unformatted_data(stock_df)
            if "Date" in df.columns:
                df["Date"] = df["Date"].apply(format_date_to_european)
            for col in df.columns:
                if col != 'Date':
                    df[col] = df[col].apply(format_price)

            return df
        else:
            return None

    formatted_data = format_data(stock_df)
    await append_stock_data_to_cloud_async(stock, formatted_data)


async def get_one_year_stock_data(session, stockname, from_date, until_date):
    data = {
        "FromDate": from_date.strftime("%m/%d/%Y"),
        "ToDate": until_date.strftime("%m/%d/%Y"),
        "Code": stockname
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Referer": f"https://www.mse.mk/en/stats/symbolhistory/{stockname}"
    }
    try:
        async with session.post("https://www.mse.mk/en/stats/symbolhistory/" + stockname, data=data,
                                headers=headers) as response:
            if response.status == 200:
                html_content = await response.text()
                tables = pd.read_html(StringIO(html_content))
                if tables:
                    print(f"Data for {stockname} in {from_date.year} collected.")
                    return tables[0]
                else:
                    print(f"No tables found for {stockname} in {from_date.year}.")

            else:
                print(
                    f"HTTP RESPONSE ERROR: Failed to retrieve data for {stockname} in {from_date.year}, Status: {response.status}")

    except Exception as e:
        print(f"Error fetching data for {stockname} in {from_date.year}: {e}")


async def get_all_data_for_one_stock(session, stock, last_date):
    data_array = []

    from_date = datetime.now().date()
    if from_date == last_date:
        print(f"Data for {stock} is up to date.")
        return None

    until_date = from_date
    while until_date > last_date:
        if until_date - last_date >= timedelta(days=365):
            data = await get_one_year_stock_data(session, stock, until_date - timedelta(days=365), until_date)
            if data is not None:
                data_array.append(data)
            until_date -= timedelta(days=365)
        else:
            data = await get_one_year_stock_data(session, stock, last_date, until_date)
            if data is not None:
                data_array.append(data)
            break

    if len(data_array) == 0:
        print(f"No data found for {stock} in {last_date.year}.")
        return {'Code': stock, 'last_modified': last_date, 'price': None, 'change': None}

    combined_df = pd.concat(data_array, ignore_index=True)
    await process_data(stock, combined_df)

    price = combined_df.iloc[0, 1]
    change = combined_df.iloc[0, 5]

    return {'Code': stock, 'last_modified': datetime.now().date(), 'price': price, 'change': change}


async def get_all_stocks_data(stocks):
    connector = aiohttp.TCPConnector(limit_per_host=50, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [get_all_data_for_one_stock(session, stock['Code'], stock['Date']) for stock in stocks]
        results = await asyncio.gather(*tasks)
        return results


async def get_stock_names():
    response = requests.get("https://www.mse.mk/en/stats/symbolhistory/ALK")
    soup = BeautifulSoup(response.text, 'html.parser')
    codes = map(lambda x: x.text.strip(), soup.select("#Code option"))
    stocks = [
        s for s in codes
        if not ((s.startswith('E') and any(char.isdigit() for char in s)) or any(char.isdigit() for char in s))
    ]
    stock_last_modified_dict = await get_last_modified_date_from_db()

    stocks_objects = []
    for stock in stocks:
        last_date = stock_last_modified_dict.get(stock, datetime.now().date() - timedelta(days=3650))
        new_stock_entry = {"Code": stock, "Date": last_date}
        stocks_objects.append(new_stock_entry)

    return stocks_objects


@sync_to_async
def get_last_modified_date_from_db():
    stocks = Stock.objects.all().values('code', 'last_modified')
    stock_last_modified_dict = {
        stock['code']: stock['last_modified'] for stock in stocks
    }
    return stock_last_modified_dict


@sync_to_async
def update_stock_data(stock_data):
    existing_stock = Stock.objects.filter(code=stock_data['Code']).first()

    defaults = {'last_modified': stock_data.get('last_modified')}

    if stock_data.get('price') is not None:
        defaults['price'] = clean_value(stock_data.get('price'))
    elif existing_stock:
        defaults['price'] = existing_stock.price

    if stock_data.get('change') is not None:
        defaults['change'] = clean_value(stock_data.get('change'))
    elif existing_stock:
        defaults['change'] = existing_stock.change

    # Update or create the stock record
    Stock.objects.update_or_create(
        code=stock_data['Code'],
        defaults=defaults
    )


def clean_value(val):
    if isinstance(val, str):
        return float(val)
    if str(val) == "nan":
        return 0
    return val


async def main():
    initialize_s3_client_pool()
    stocks = await get_stock_names()
    stock_objects = await get_all_stocks_data(stocks)

    for s in stock_objects:
        if s and s.get('Code'):
            await update_stock_data(s)

@shared_task
def run_stock_update():
    asyncio.run(main())

if __name__ == '__main__':
    asyncio.run(main())