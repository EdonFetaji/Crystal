import aiohttp
import pandas as pd
import requests
from bs4 import BeautifulSoup
import asyncio
import boto3
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.common.by import By
import selenium
from django.conf import settings
from django.core.management.base import BaseCommand


# Set up options for headless mode


def scrape_data():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")  # Disable GPU acceleration (optional but recommended)

    def extract_name_link(driver, selector):
        data = []
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for e in elements:
            row = {}
            row['name'] = e.find_element(By.CSS_SELECTOR, '.sorting_1 > a').get_attribute('innerHTML')
            row['mse_link'] = e.find_element(By.CSS_SELECTOR, '.sorting_1 > a').get_attribute('href')
            data.append(row)
        return data

    # Initialize the Chrome WebDriver in headless mode
    driver = webdriver.Chrome(options=options)
    stock_info = []
    driver.get('https://www.mse.mk/en/issuers/shares-listing')
    stock_info += extract_name_link(driver, 'table > tbody > tr')

    for s in stock_info:
        driver.get(s['mse_link'])
        code = driver.find_element(By.CSS_SELECTOR, '#symbols > li > a').get_attribute('innerHTML')
        s['code'] = code

    driver.quit()
    
    stocks_from_mse = get_stock_names()

    # Add missing stock codes to stock_info
    for mse_code in stocks_from_mse:
        if not any(s['code'] == mse_code for s in stock_info):
            stock_info.append({'code': mse_code})

    return stock_info


s3 = boto3.client('s3',
                  endpoint_url='https://s3.eu-central-2.wasabisys.com',
                  region_name='eu-central-2',
                  aws_access_key_id=settings.WASABI_ACCESS_KEY,
                  aws_secret_access_key=settings.WASABI_SECRET_KEY)


# Function to get stock names from the website
def get_stock_names():
    response = requests.get("https://www.mse.mk/en/stats/symbolhistory/ALK")
    soup = BeautifulSoup(response.text, 'html.parser')
    codes = map(lambda x: x.text.strip(), soup.select("#Code option"))
    return [
        s for s in codes
        if not (s.startswith('E') or any(char.isdigit() for char in s))
    ]


# Asynchronous function to download CSV
async def fetch_csv(stock, session):
    url = f"https://raw.githubusercontent.com/EdonFetaji/DAS-MSE-Project/refs/heads/main/Homework_1/MSE_project/Processed_Data/{stock['code']}.csv"
    async with session.get(url) as response:
        if response.status == 200:
            csv_data = await response.text()
            return stock['code'], csv_data
        else:
            print(f"File {stock['code']}.csv not found on GitHub (HTTP {response.status}).")
            return stock['code'], None


# Function to upload CSV to Wasabi (run in a thread)
def upload_to_wasabi(stock_code, csv_data):
    try:
        if csv_data:
            # Upload the CSV data to Wasabi S3
            s3.put_object(
                Bucket=settings.WASABI_bucket_name,
                Key=f"Stock_Data/{stock_code}.csv",  # Save under a folder in Wasabi
                Body=csv_data,
                ContentType='text/csv'
            )
            print(f"Uploaded file {stock_code}.csv to Wasabi bucket '{settings.WASABI_bucket_name}'.")
    except Exception as e:
        print(f"Failed to upload {stock_code}.csv: {e}")


# Main asynchronous function
async def process_stocks():
    # Get additional stock codes from MSE

    stock_info = scrape_data()
    # Download stock data as CSV
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_csv(stock, session) for stock in stock_info]
        responses = await asyncio.gather(*tasks)

    # Upload CSV files to Wasabi using ThreadPoolExecutor
    with ThreadPoolExecutor() as executor:
        loop = asyncio.get_event_loop()
        upload_tasks = [
            loop.run_in_executor(executor, upload_to_wasabi, stock_code, csv_data)
            for stock_code, csv_data in responses if csv_data
        ]
        await asyncio.gather(*upload_tasks)

    return stock_info


class Command(BaseCommand):
    help = 'Upload stocks data to cloud storage'

    def handle(self, *args, **options):
        try:
            # Get stock information from website
            stock_info = asyncio.run(process_stocks())

            # Return the stock_info list
            return stock_info

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            return None
