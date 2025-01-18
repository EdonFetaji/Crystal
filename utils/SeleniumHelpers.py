import threading
from queue import Queue

from selenium.webdriver.chrome import webdriver


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
