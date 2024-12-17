import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from backend.models import Stock
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
import os
import django


# Set up Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Crystal.settings')  # Replace 'Crystal' with your project name
django.setup()


def scrape_data():
    """
    Scrape the Macedonian Stock Exchange website and return a list of dictionaries
    with stock code, name and link to the MSE page for that stock.
    """
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
        try:
            driver.get(str(s['mse_link']))
            code = driver.find_element(By.CSS_SELECTOR, '#symbols > li > a').get_attribute('innerHTML')
            s['code'] = code
        except Exception:
            s['code'] = None

    driver.quit()

    # Simulate getting stock codes from another source
    stocks_from_mse = get_stock_names()

    # Add missing stock codes to stock_info
    for mse_code in stocks_from_mse:
        if not any(s['code'] == mse_code for s in stock_info):
            stock_info.append({'code': mse_code, 'name': None, 'mse_link': None})

    return stock_info


def get_stock_names():
    response = requests.get("https://www.mse.mk/en/stats/symbolhistory/ALK")
    soup = BeautifulSoup(response.text, 'html.parser')
    codes = map(lambda x: x.text.strip(), soup.select("#Code option"))
    return [
        s for s in codes
        if not ((s.startswith('E') and any(char.isdigit() for char in s)) or any(char.isdigit() for char in s))
    ]


class Command(BaseCommand):
    help = 'Populate stocks table with data from scraping the MSE website'

    def handle(self, *args, **options):
        self.stdout.write("Starting stock scraping and database population process...")
        stocks_not_processed_from_hw1 = (
            'EUMK', 'AMBR', 'ELMA', 'EUHA', 'INDI', 'ELNC', 'EVRO', 'ENER', 'ENSA', 'KKFI', 'INEK', 'EDST', 'JULI',
            'TIGA')

        try:
            # Scrape stock data
            stock_info = scrape_data()

            # Populate the database with the retrieved stock_info
            for stock in stock_info:
                try:
                    code = stock.get('code',None)
                    name = stock.get('name', 'N/A')
                    mse_link = stock.get('mse_link', 'N/A')
                    cloud_key = f"Stock_Data/{code}.csv" if code else None
                    last_modified = '2014-01-01' if code in stocks_not_processed_from_hw1 else "2024-11-8"

                    if not code:
                        self.stdout.write(self.style.WARNING(f"Skipping entry without code: {stock}"))
                        continue

                    stock_obj, created = Stock.objects.update_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'mse_url': mse_link,
                            'cloud_key': cloud_key,
                            'last_modified': last_modified,
                        }
                    )

                    action = 'Created' if created else 'Updated'
                    self.stdout.write(self.style.SUCCESS(f"{action} stock: {code}, Name: {name}, MSE URL: {mse_link}"))

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error processing stock {stock.get('code')}: {str(e)}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during stock scraping or population: {str(e)}"))
            return

        self.stdout.write(self.style.SUCCESS("Stock database population completed!"))
