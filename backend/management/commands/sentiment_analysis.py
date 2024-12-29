import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from datetime import datetime
import threading
from queue import Queue
import os
import django
from utils import WasabiClient

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Crystal.settings')
django.setup()
from backend.models import Stock
from transformers import MarianMTModel, MarianTokenizer, pipeline, AutoTokenizer, AutoModelForSequenceClassification


def getStockName_db():
    names = Stock.objects.all().values("name")  # replace dolgorocno suspendirano od kotacija with "" aswell
    return [x['name'] for x in names if x['name'] is not None]


def getStockCode_db():
    codes = Stock.objects.all().values("code")
    return [x['code'] for x in codes if x['name'] is not None]


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(options=options)


class SeleniumDriverPool:
    def __init__(self, max_size=5):
        self.pool = Queue(maxsize=max_size)
        self.lock = threading.Lock()
        for _ in range(max_size):
            driver = create_driver()
            self.pool.put(driver)

    def acquire_driver(self):
        with self.lock:
            return self.pool.get()

    def release_driver(self, driver):
        with self.lock:
            self.pool.put(driver)

    def close_all_drivers(self):
        while not self.pool.empty():
            driver = self.pool.get()
            driver.quit()


pool1 = SeleniumDriverPool(max_size=20)
pool2 = SeleniumDriverPool(max_size=20)

stocks = ["Komercijalna banka AD Skopje", "Alkaloid AD Skopje", "DS Smith AD Skopje", "Fersped AD Skopje",
          "Granit AD Skopje", "Hoteli Metropol Ohrid", "Internesnel Hotels AD Skopje", "Makedonijaturist AD Skopje",
          "Makosped AD Skopje", "Makoteks AD Skopje", "Makpetrol AD Skopje", "Makstil AD Skopje", "Replek AD Skopje",
          "RZ Inter-Transsped AD Skopje", "RZ Uslugi AD Skopje", "Skopski Pazar AD Skopje", "Stopanska banka AD Bitola",
          "Teteks AD Tetovo", "TTK Banka AD Skopje", "Tutunski kombinat AD Prilep", "Vitaminka AD Prilep",
          "VV Tikves AD Kavadarci", "Zito Luks AD Skopje", "ZK Pelagonija AD Bitola", "Ading AD Skopje",
          "Agromehanika AD Skopje", "Angropromet Tikvesanka AD Kavadarci",
          "ArcelorMittal (HRM) AD Skopje", "Automakedonija AD Skopje",
          "BIM AD Sveti Nikole", "Blagoj Tufanov AD Radovis",
          "Cementarnica USJE AD Skopje", "Centralna kooperativna banka AD Skopje", "Debarski Bani –Capa AD Debar",
          "Dimko Mitrev AD Veles", "Evropa AD Skopje", "Fabrika Karpos AD Skopje", "FAKOM AD Skopje",
          "Fruktal Mak AD Skopje", "Fustelarko Borec AD Bitola", "FZC 11-ti OKTOMVRI AD Kumanovo",
          "GD-TIKVES AD Kavadarci", "Geras Cunev Konfekcija AD Strumica", "Geras Cunev Trgovija AD Strumica",
          "Grozd AD Strumica", "GTC AD Skopje", "Interpromet AD Tetovo", "Klanica so ladilnik AD Strumica",
          "Kristal 1923 AD Veles", "Liberti AD Skopje", "Lotarija na Makedonija AD Skopje",
          "Makedonija osiguruvane AD Skopje - Viena Insurens Grup", "Makedonski Telekom AD – Skopje",
          "Makpromet AD Stip", "Mermeren kombinat AD Prilep", "Moda AD Sveti Nikole", "MZT Pumpi AD Skopje",
          "Nemetali Ograzden AD Strumica", "NLB Banka AD Skopje", "Nova Stokovna kuka AD Strumica", "OILKO KDA Skopje",
          "OKTA AD Skopje", "Oranzerii Hamzali Strumica", "Patnicki soobrakaj Transkop AD Bitola",
          "Pekabesko AD Kadino Ilinden", "Pelisterka AD Skopje", "Popova Kula AD Demir Kapija",
          "Prilepska pivarnica AD Prilep", "Rade Koncar- Aparatna tehnika AD Skopje", "Rudnici Banani AD Skopje",
          "RZ Ekonomika AD Skopje", "RZ Tehnicka Kontrola AD Skopje", "Sigurnosno staklo AD Prilep",
          "Sileks AD Kratovo", "Slavej AD Skopje", "Sovremen dom AD Prilep", "Stokopromet AD Skopje",
          "Stopanska banka AD Skopje", "Strumicko pole s. Vasilevo",
          "Tajmiste AD Kicevo", "TEAL AD Tetovo", "Tehnokomerc AD Skopje",
          "Trgotekstil Maloprodazba AD Skopje", "Triglav Osiguruvane AD Skopje",
          "Trudbenik AD Ohrid", "Ugotur AD Skopje", "UNI Banka AD Skopje",
          "Vabtek MZT AD Skopje", "Veteks AD Veles", "ZAS AD Skopje", "Zito Karaorman AD Kicevo",
          "Zito Polog AD Tetovo"]


def filter_stockname():
    stock_names = []
    for company in stocks:
        parts = company.split()
        # get rid of city names for better search
        filtered = [part for part in parts if
                    part not in {"AD", "Skopje", "Bitola", "Tetovo", "Prilep", "Kavadarci", "Ohrid", "Veles",
                                 "Kumanovo", "Sveti", "Nikole", "Debar", "Radovis", "Stip", "Ilinden", "Kicevo",
                                 "Strumica", " - dolgorocno suspendirano od kotacija"}]
        stock_names.append(" ".join(filtered))

    return stock_names


def scrape_kapitalMK():
    stock_dataframes = {}
    filtered_stocks = filter_stockname()
    stock_codes = getStockCode_db()

    while True:
        for stock_name, stock_code in zip(filtered_stocks, stock_codes):
            data = []

            try:
                driver = pool1.acquire_driver()
                i = 1

                while True:
                    driver.get(f'https://kapital.mk/page/{i}/?s={stock_name}')
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
                            nd.get(link)
                            date = nd.find_element(By.CSS_SELECTOR, 'time')
                            date_published = datetime.fromisoformat(date.get_attribute('datetime')).strftime("%d.%m.%Y")
                            print()
                            print(date_published)
                            print()
                            post = nd.find_element(By.CSS_SELECTOR, ".mvp-post-soc-out").text

                            actual_post = post.split('ПОВРЗАНИ ТЕМИ:')[0]
                            print(actual_post)

                            title = a_tag.text
                            data.append({'date': date_published, 'title': title, 'text': actual_post, 'link': link,
                                         'from': 'kapital.mk'})

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
        break

    pool1.close_all_drivers()

    return stock_dataframes


def scrape_biznisinfoMK():
    stock_dataframes = {}
    filtered_stocks = filter_stockname()
    stock_codes = getStockCode_db()

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
