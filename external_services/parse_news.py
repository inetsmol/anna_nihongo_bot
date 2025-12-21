import random
import re
from datetime import datetime
from urllib.parse import urljoin

import gspread
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from openai_services import openai_gpt_translate, openai_gpt_get_phrase_from_text


def fetch_webpage_with_js(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Запуск Chrome в фоновом режиме

    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(url)

        # Ждем, пока не появится контейнер с новостями
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "js-news-list"))
        )

        return driver.page_source
    finally:
        driver.quit()


def get_full_news_text(url):
    response = requests.get(url)
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, 'html.parser')
    article_body = soup.find('div', class_='article-body')

    if article_body:
        # Удаляем все теги, кроме <p>
        for tag in article_body.find_all(['ruby', 'span']):
            tag.unwrap()

        # Извлекаем текст из всех параграфов
        paragraphs = article_body.find_all('p')
        full_text = '\n'.join([p.get_text(strip=True) for p in paragraphs])
        return full_text
    else:
        return "Не удалось получить полный текст новости."


def parse_news(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    news_container = soup.find('section', id='js-news-list')

    if not news_container:
        print("Не удалось найти контейнер с новостями на странице.")
        return []

    news_items = news_container.find_all('article', class_='news-list__item')

    parsed_news = []
    for item in news_items:
        news = {}

        link = item.find('a')
        if link:
            news['link'] = urljoin(base_url, link['href'])
            news['full_text'] = get_full_news_text(news['link'])

        img = item.find('img')
        if img:
            news['image'] = urljoin(base_url, img['src'])

        title = item.find('h2')
        if title:
            news['title'] = re.sub(r'<[^>]+>', '', str(title)).strip()

        date = item.find('time')
        if date:
            news['date'] = date['datetime']

        parsed_news.append(news)

    return parsed_news


def get_random_today_news(news_list):
    today = datetime.now().date()
    today_news = []

    for news in news_list:
        try:
            news_date = datetime.strptime(news.get('date'), "%Y-%m-%d %H:%M:%S").date()
            if news_date == today:
                today_news.append(news)
        except ValueError:
            print(f"Неправильный формат даты: {news.get('date')}")
            continue

    if today_news:
        return random.choice(today_news)
    else:
        return None


def get_news():
    base_url = "https://www3.nhk.or.jp"
    url = f"{base_url}/news/easy/"
    html_content = fetch_webpage_with_js(url)

    if html_content:
        news_list = parse_news(html_content, base_url)

        if news_list:
            random_today_news = get_random_today_news(news_list)
            if random_today_news:
                # Аутентификация в Google Sheets
                scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
                creds = Credentials.from_service_account_file('../anna-nihongo-bot-96c6f518f0cd.json', scopes=scope)
                client = gspread.authorize(creds)

                # Открываем таблицу (замените 'Your Google Sheet Name' на имя вашей таблицы)
                sheet = client.open('news_nhk_or_jp').sheet1
                translated_text = await openai_gpt_translate(random_today_news.get('full_text'))
                dictionary = await openai_gpt_get_phrase_from_text(random_today_news.get('full_text'))
                row = [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    random_today_news.get('title', 'Нет заголовка'),
                    random_today_news.get('link', 'Нет ссылки'),
                    random_today_news.get('image', 'Нет изображения'),
                    random_today_news.get('date', 'Нет даты'),
                    random_today_news.get('full_text', 'Не удалось получить полный текст'),
                    translated_text,
                    dictionary,
                ]
                sheet.append_row(row)
                print(f"Словарь: {dictionary}")
        else:
            print("Новости не найдены. Возможно, структура страницы снова изменилась.")
    else:
        print("Не удалось загрузить страницу. Проверьте подключение к интернету или доступность сайта.")


if __name__ == "__main__":
    get_news()
