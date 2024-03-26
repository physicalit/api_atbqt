import redis
import requests
import json
import pandas as pd
from pydantic import BaseModel, Field, HttpUrl
from colorama import Fore, Back, Style
from meilisearch import Client
import time, re
from bs4 import BeautifulSoup
import pandas as pd
from ollama import Client
from sklearn.metrics.pairwise import cosine_similarity

client = Client(host='http://192.168.81.131:11434')

global all_products

class Product(BaseModel):
    nume: str = Field( min_length=1, max_length=200)
    link: str = HttpUrl
    pret: float = Field(ge=0)
    procesor: str = Field( min_length=1, max_length=200)


def check_process_status(request_id):
    redis_con = redis.Redis(host='192.168.81.108', port=6379, password="XJZAT3yjBmo5et3WsNdL", db=0)

    finished_key = f'finished:{request_id}'
    is_finished = redis_con.get(finished_key)

    if is_finished:
        page_sources = redis_con.hgetall(f'page_sources:{request_id}')
        return True, page_sources
    else:
        return False, {}

def get_page_links(html_source):
  soup = BeautifulSoup(html_source, 'html.parser')
  links = soup.find_all('a', class_='css-rc5s2u')
  title = soup.find('title')
  if title:
    return (links) 
  else:
    print(Fore.GREEN + "Error getting page links")
    print(Style.RESET_ALL)

def page_generate(url, page_num):
    return f"{url}/?page={page_num}"

def get_category_pages(page):
    all_pages = []
    for page_num in range(1, 26):
        all_pages.append(page_generate(page, page_num))
    return all_pages      
    
def send_job(pages):
    url = "http://localhost:8080/"
    payload = json.dumps({
    "username": "admin",
    "password": "asdre123"
    })
    headers = {
    'Content-Type': 'application/json'
    }
    token = requests.request("POST", f'{url}login', headers=headers, data=payload)
    payload = json.dumps({
    "links": pages,
    "in_thread_options": {
        "scroll": False}
    })
    headers = {
    'Authorization': token.json()['access_token'],
    'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    return response

def get_pages(response):
    is_finished, page_sources = check_process_status(response)
    global pages
    pages = []
    if is_finished:
        for key, html_source in page_sources.items():
            soup = BeautifulSoup(html_source, 'html.parser')
            ul_element = soup.find('ul', class_='page-numbers')
            a_tags = ul_element.find_all('a')
            for i, a_tag in enumerate(a_tags):
                if i == len(a_tags) - 1:
                    href = key.decode()
                else:
                    href = a_tag.get('href')

                pages.append(href)
    else:
        return True
    return False

def get_prod_links(response):
    is_finished, page_sources = check_process_status(response)
    global pages
    pages = []
    if is_finished:
        for key, html_source in page_sources.items():
            soup = BeautifulSoup(html_source, 'html.parser')
            ul_element = soup.find('ul', class_='products')
            a_tags = ul_element.select('a.woocommerce-loop-product__link')
            for a_tag in a_tags:
                href = a_tag.get('href')
                pages.append(href)
    else:
        return True
    return False

def get_prods(response):
    is_finished, page_sources = check_process_status(response)
    prods = []
    if is_finished:
        for key, html_source in page_sources.items():
            soup = BeautifulSoup(html_source, 'html.parser')
            price = soup.find('span', class_='electro-price').find('span', class_='woocommerce-Price-amount').text.split(',')[0].replace(".", "")
            # print(price)
            title = soup.find('h1', class_='product_title').text
            div_descriere = soup.find('div', class_='electro-description').find('span', text='PROCESOR:')
            processor_name_tag = div_descriere.find_next('span')
            processor_name = processor_name_tag.text.strip('- \n')
            payload = Product(nume=title, link=key, pret=price, procesor=processor_name).model_dump()
            prods.append(payload)
        return prods
    else:
        return False

def get_embeddings(dataframe, column_name):
    texts = dataframe[column_name].tolist()
    embeddings = []
    # Loop through texts and generate embeddings individually
    for text in texts:
        try:
            result = client.embeddings(model='nomic-embed-text', prompt=text)
            embeddings.append(result['embedding'])  # Extract the embedding list
        except Exception as e:
            print(f"Error generating embedding for '{text}': {e}")
            embeddings.append(None)  # Handle potential errors
    return embeddings

def find_best_match(similarities, df2, index):
    best_match_index = similarities[index].argmax()  # Find index of highest similarity
    best_match_proc = df2['procesor'].iloc[best_match_index]
    best_match_benchmark = df2['benchmark'].iloc[best_match_index]  # Assuming you have a 'benchmark' column in df2
    return best_match_proc, best_match_benchmark


all_products = []
categories = ["https://4saleit.ro/categorie-produs/calculatoare-reconditionate/mini-pc/", "https://4saleit.ro/categorie-produs/calculatoare-reconditionate/desktop-pc/"]

for category in categories:
    response = send_job([category])
    # print(response.json())
    while get_pages(response.json()['uuid']):
        time.sleep(5)
    print(pages)
    response = send_job(list(set(pages)))
    # print(response.json())
    while get_prod_links(response.json()['uuid']):
        time.sleep(5)
    response = send_job(list(set(pages)))
    result = None
    while not result:
        result = get_prods(response.json()['uuid'])
        time.sleep(5)

    minipc = pd.DataFrame(result)
    minipc['procesor'] = minipc['procesor'].replace(r' cu .+', '', regex=True)
    minipc['procesor'] = minipc['procesor'].replace(r' de .+', '', regex=True)
    minipc['procesor'] = minipc['procesor'].replace(r'^–', '', regex=True).str.strip()
    all_products.append(minipc)
    
bench = pd.read_csv("./benchmark.csv")
bench = bench.rename(columns={'CPU Name': 'procesor', 'CPU Mark (higher is better)': 'benchmark'})

bench_filtered = bench[~bench['procesor'].str.contains('ARM')].copy()
bench_filtered = bench_filtered[~bench_filtered['procesor'].str.contains('Rockchip')].copy()
bench_filtered['procesor'] = [value.split("@")[0].strip() if "@" in value else value for value in bench_filtered['procesor']]
bench_filtered = bench_filtered[bench_filtered['procesor'].str.contains('AMD') | bench_filtered['procesor'].str.contains('Intel')].copy()

df2_embeddings = get_embeddings(bench_filtered, 'procesor')

sale4it = [] 
for minipc in all_products:
    df1_embeddings = get_embeddings(minipc, 'procesor')
    similarities = cosine_similarity(df1_embeddings, df2_embeddings)

    matched_data = []
    for i, row in minipc.iterrows():
        best_proc, best_bench = find_best_match(similarities, bench_filtered, i)
        matched_data.append({
            'nume': row['nume'],
            'link': row['link'],
            'pret': row['pret'],
            'procesor': row['procesor'],
            'procesor_2': best_proc,
            'benchmark': best_bench
        })
    matched_df = pd.DataFrame(matched_data)

    ram_pattern = r'(\d{1,2}\s?GB\s(?:DDR|LPDDR)[234])'
    storage_pattern = r'((?:SSD|HDD)\s\d+\s?(?:GB|TB))'
    matched_df['Storage'] = matched_df['nume'].str.extract(storage_pattern, flags=re.IGNORECASE)
    matched_df['RAM'] = matched_df['nume'].str.extract(ram_pattern, flags=re.IGNORECASE)
    sale4it.append(matched_df)
    
result_df = pd.concat(sale4it, axis=0).sort_values(by=['benchmark', 'pret'], ascending=[False, True])
result_df.to_excel('../results/4saleit.xlsx', index=False)


