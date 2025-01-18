import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException
from datetime import datetime, time
import threading
from queue import Queue
import os
import django
from utils import WasabiClient

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Crystal.settings')
django.setup()
from backend.models import Stock
from transformers import MarianMTModel, MarianTokenizer, pipeline, AutoTokenizer, AutoModelForSequenceClassification
from backend.models import Stock
from utils.SeleniumHelpers import SeleniumDriverPool


def getStockName_db():
    names = Stock.objects.all().values("name")  # replace dolgorocno suspendirano od kotacija with "" aswell
    return [x['name'] for x in names if x['name'] is not None]


def getStockCode_db():
    codes = Stock.objects.all().values("code")
    return [x['code'] for x in codes if x['name'] is not None]


stocks = getStockName_db()


def scrape_kapitalMK():
    stock_dataframes = {}

    try:
        filtered_stocks = Stock.get_filtered_stock_names()
        stock_codes = getStockCode_db()
    except NameError:
        print("Error: Required functions (filter_stockname, getStockCode_db) are not defined.")
        return {}

    try:
        pool1 = SeleniumDriverPool(max_size=20)
    except NameError:
        print("Error: SeleniumDriverPool is not defined.")
        return {}

    for stock_name, stock_code in zip(filtered_stocks, stock_codes):
        data = []
        try:
            driver = pool1.acquire_driver()
            i = 1

            while True:
                driver.get(f'https://kapital.mk/page/{i}/?s={stock_name}')
                time.sleep(2)  # Ensures page loads completely
                html_content = driver.page_source

                if 'Error 404!' in html_content or 'Sorry, your search did not match any entries.' in html_content:
                    break

                article_list = driver.find_elements(By.CSS_SELECTOR, ".mvp-blog-story-list li")

                for tag in article_list:
                    a_tag = tag.find_element(By.CSS_SELECTOR, "a:nth-child(1)")
                    link = a_tag.get_attribute('href')
                    print(link)

                    try:
                        nd = pool1.acquire_driver()
                        nd.set_page_load_timeout(15)  # Increase timeout to 15 seconds
                        nd.get(link)
                        time.sleep(2)

                        date = nd.find_element(By.CSS_SELECTOR, 'time')
                        date_published = datetime.fromisoformat(date.get_attribute('datetime')).strftime("%d.%m.%Y")
                        print(date_published)

                        title = nd.find_element(By.CSS_SELECTOR, "h1.entry-title").text
                        print(title)

                        post = nd.find_element(By.CSS_SELECTOR, ".mvp-post-soc-out").text
                        actual_post = post.split('ПОВРЗАНИ ТЕМИ:')[0]

                        if len(actual_post) < 5000:  # Skip long reads
                            data.append({'date': date_published, 'title': title, 'text': actual_post, 'link': link,
                                         'from': 'kapital.mk'})
                        else:
                            print(f"Skipping article {link} due to excessive length.")

                    except TimeoutException:
                        print(f"Timeout occurred while processing link {link}, skipping article.")
                    except WebDriverException as e:
                        print(f"Error occurred while processing link {link}: {e}")
                    finally:
                        pool1.release_driver(nd)

                i += 1

        except WebDriverException as e:
            print(f"Error occurred for stock {stock_name} on page {i}: {e}")
        finally:
            pool1.release_driver(driver)

        stock_dataframes[stock_code] = pd.DataFrame(data)

    pool1.close_all_drivers()
    return stock_dataframes


def scrape_biznisinfoMK():
    stock_dataframes = {}
    filtered_stocks = Stock.get_filtered_stock_names()
    stock_codes = getStockCode_db()
    pool2 = SeleniumDriverPool(max_size=20)
    while True:

        for stock_name, stock_code in zip(filtered_stocks, stock_codes):
            data = []

            try:
                driver = pool2.acquire_driver()
                i = 1

                while True:
                    driver.get(f'https://biznisinfo.mk/page/{i}/?s={stock_name}')
                    html_content = driver.page_source

                    if 'Упсссс... Error 404' in html_content or 'Нема резултати за вашето пребарување' in html_content:
                        break

                    article_list = driver.find_elements(By.CSS_SELECTOR, ".td_module_10")
                    print(f'Title: {article_list}')
                    for tag in article_list:
                        a_tag = tag.find_element(By.CSS_SELECTOR, "div:nth-child(1) > a:nth-child(1)")
                        link = a_tag.get_attribute('href')
                        print(link)

                        try:
                            nd = pool2.acquire_driver()
                            nd.get(link)

                            date = nd.find_element(By.CSS_SELECTOR, 'time')
                            date_published = datetime.strptime(date.text, "%d/%m/%Y").strftime("%d.%m.%Y")
                            print()
                            print(date_published)
                            print()

                            title = nd.find_element(By.CSS_SELECTOR, "h1.entry-title").text
                            print(title)

                            post = nd.find_element(By.CSS_SELECTOR, ".td-main-content").text
                            actual_post = post.split('Можеби ќе ве интересира и...')[0]

                            # if stock_name in actual_post:
                            data.append({'date': date_published, 'title': title, 'text': actual_post, 'link': link,
                                         'from': 'biznisinfo.mk'})

                        except WebDriverException as e:
                            print(f"Error occurred while processing link {link}: {e}")

                        finally:
                            pool2.release_driver(nd)

                    i += 1

            except WebDriverException as e:
                print(f"Error occurred for stock {stock_name} on page {i}: {e}")

            finally:
                pool2.release_driver(driver)

            stock_dataframes[stock_code] = pd.DataFrame(data)

        break

    pool2.close_all_drivers()
    return stock_dataframes


# for sentiment
tokenizer_finbert = AutoTokenizer.from_pretrained("yiyanghkust/finbert-tone")
model_finbert = AutoModelForSequenceClassification.from_pretrained("yiyanghkust/finbert-tone",
                                                                   output_hidden_states=False)
sentiment_analyzer = pipeline("sentiment-analysis", model="yiyanghkust/finbert-tone")

# for translation
tokenizer_translator = MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-mk-en')
model_translator = MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-mk-en')


def sentiment_analysis(news):
    def split_text_into_chunks(text, max_length):
        words = text.split()
        chunks = []
        current_chunk = []

        for word in words:
            if len(' '.join(current_chunk + [word])) <= max_length:
                current_chunk.append(word)
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    wasabi_client = WasabiClient()
    # stock_codes = getStockCode_db()

    for stock_name, df in news.items():
        final_rows = []
        for index, row in df.iterrows():

            # Title
            macedonian_title = row['title'].replace('„', '').replace('“', '')
            encoded_input = tokenizer_translator(macedonian_title, return_tensors='pt')
            translated = model_translator.generate(**encoded_input)
            english_title = tokenizer_translator.decode(translated[0], skip_special_tokens=True)

            # Content - can't exceed 512 tokens thats why chunking
            macedonian_content = row['text']
            chunks = split_text_into_chunks(macedonian_content, max_length=512)
            translated_chunks = []
            sentiments = []

            for chunk in chunks:
                encoded_input2 = tokenizer_translator(chunk, return_tensors='pt')
                translated2 = model_translator.generate(**encoded_input2)
                translated_chunk = tokenizer_translator.decode(translated2[0], skip_special_tokens=True)

                result = sentiment_analyzer(translated_chunk)
                sentiments.append(result[0]['label'])

                translated_chunks.append(translated_chunk)

            english_content = ' '.join(translated_chunks)
            sentiment_summary = ', '.join(sentiments)

            # Append the full article as a single row
            final_rows.append({
                'date': row['date'],
                'title': english_title,
                'content': english_content,
                'sentiment_summary': sentiment_summary,
                'link': row['link']
            })

            print(f"Title: {english_title} finished")
            # print(f"Content (English): {english_content}\n")

        final_df = pd.DataFrame(final_rows)
        final_df.set_index('date', inplace=True)

        wasabi_client.update_or_create_articles(stock_name, final_df)


if __name__ == "__main__":
    stock_news1 = scrape_kapitalMK()
    stock_news2 = scrape_biznisinfoMK()

    sentiment_analysis(stock_news1)
    sentiment_analysis(stock_news2)
