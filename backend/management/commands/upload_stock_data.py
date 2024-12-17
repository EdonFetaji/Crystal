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
    """
    Appends a Pandas DataFrame to an existing CSV in a Wasabi S3 bucket or creates a new one if it doesn't exist.

    Args:
        code (str): Stock code used to identify the corresponding CSV file in the bucket.
        new_df (pd.DataFrame): The new DataFrame to append in front of the existing data.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """

    s3 = s3_client_pool.get()  # Acquire an S3 client from the pool
    cloud_key = f"Stock_Data/{code}.csv"
    try:
        # Try fetching the existing file from the cloud
        try:
            existing_file = s3.get_object(Bucket=bucket_name, Key=cloud_key)
            existing_df = pd.read_csv(StringIO(existing_file['Body'].read().decode('utf-8')))
            print(f"Successfully fetched existing data for {code}.")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"No existing data found for {code}. Creating a new file.")
                existing_df = None  # No data if the file doesn't exist
            else:
                print(f"Error fetching existing data: {e}")
                return False

        # Combine the new data with the old data (new data in front)
        if existing_df is not None:
            combined_df = pd.concat([new_df, existing_df]).drop_duplicates()
        else:
            combined_df = new_df

        # Convert the combined DataFrame to CSV format in memory
        csv_buffer = StringIO()
        combined_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)  # Reset buffer to the start

        # Upload the CSV file back to Wasabi
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

    await append_stock_data_to_cloud_async(stock, format_data(stock_df))


async def run_process_data(stock, combined_df):
    await process_data(stock, combined_df)


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
    modified_stock = {'Code': stock}
    data_array = []

    from_date = datetime.now().date()
    if from_date == last_date:
        print(f"Data for {stock['Code']} is up to date.")
        return None

    until_date = from_date
    while until_date > last_date:

        if until_date - last_date >= timedelta(days=365):
            data_array.append(
                await get_one_year_stock_data(session, stock, until_date - timedelta(days=365), until_date))
            until_date -= timedelta(days=365)
        else:
            data_array.append(await get_one_year_stock_data(session, stock, last_date, until_date))
            break

    data_array = list(filter(lambda x: x is not None, data_array))
    if len(data_array) == 0:
        print(f"No data found for {stock} in {last_date.year}.")
        modified_stock['last_modified'] = last_date
        return modified_stock
    # TODO

    combined_df = pd.concat(data_array, ignore_index=True)  # Combine all DataFrames
    asyncio.create_task(run_process_data(stock, combined_df))

    modified_stock['last_modified'] = datetime.now()
    return modified_stock


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

    # return check_last_date_available(stocks)
    # Prepare the stock objects with last modified date
    stocks_objects = []
    for stock in stocks:
        last_date = stock_last_modified_dict.get(stock, datetime.now().date() - timedelta(days=3650))
        new_stock_entry = {"Code": stock, "Date": last_date}
        stocks_objects.append(new_stock_entry)

    return stocks_objects


from datetime import datetime
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Crystal.settings')
django.setup()

# Now you can import your models
from backend.models import Stock


@sync_to_async
def get_last_modified_date_from_db():
    """
    Fetch the last modified date for each stock code from the Stock model in the database.
    Returns:
        dict: A dictionary with stock codes as keys and their last_modified date as values.
    """
    # Query all Stock objects and retrieve their code and last_modified fields
    stocks = Stock.objects.all().values('code', 'last_modified')

    # Convert the query result to a dictionary {code: last_modified_date}
    stock_last_modified_dict = {
        stock['code']: stock['last_modified']  # Convert datetime to date
        for stock in stocks
    }

    return stock_last_modified_dict


@sync_to_async
def fetch_existing_stocks():
    return {stock.code: stock for stock in Stock.objects.all()}


async def main():
    initialize_s3_client_pool()
    # stocks = await get_stock_names()
    # stock_objects = await get_all_stocks_data(stocks)
    #
    # existing_stocks = await fetch_existing_stocks()
    # new_stocks = []
    # updates = []
    #
    # for s in stock_objects:
    #     db_stock = existing_stocks.get(s['Code'])
    #     if db_stock:
    #         db_stock.last_modified = s['last_modified']
    #         updates.append(db_stock)
    #     else:
    #         new_stocks.append(Stock(**s))
    #
    # Stock.objects.bulk_update(updates, ['last_modified'])
    # Stock.objects.bulk_create(new_stocks)

    stocks = await get_stock_names()
    stock_objects = await get_all_stocks_data(stocks)

    for s in stock_objects:
        Stock.objects.update_or_create(
            code=s['Code'],  # Lookup field
            defaults={
                'last_modified': s.get('last_modified'),
            }
        )


if __name__ == "__main__":
    asyncio.run(main())

    # _______________________________________________________________________
