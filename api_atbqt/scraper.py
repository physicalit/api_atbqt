from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium import webdriver

import logging.config
import redis
import time

logging.config.fileConfig('logging.conf')
logger = logging.getLogger("root")

def setup_options():
        options = Options()
        options.add_argument('--headless')
        options.page_load_strategy = "normal"
        return options

def read_data(driver, num_of_tabs, redis_con, semaphore_for_redis, parse_options, request_id):
    for tab_index in range(num_of_tabs):
        driver.switch_to.window(driver.window_handles[tab_index])
        if parse_options.scroll:
            for _ in range(parse_options.scroll_amount):
                driver.execute_script("window.scrollBy(0,650)")
        result = driver.page_source
        if parse_options.slow:
            time.sleep(2)
        
        with semaphore_for_redis:
            redis_con.hset(f'page_sources:{request_id}', driver.current_url, result)
    # driver.quit()

def get_data(id, parse_options, group_of_tabs, total_num, semaphore_for_driver, semaphore_for_redis): # in thread
    redis_con = redis.Redis(host='192.168.81.108', port=6379, db=0)
    processed_key = f'processed_links:{id}'
    failed_key = f'failed_links:{id}'
    with semaphore_for_driver:
        driver = webdriver.Remote(command_executor="http://192.168.81.101:4444/wd/hub", options=setup_options())
    for index, url in enumerate(group_of_tabs):
        try:
            if index == 0:
                driver.get(url)
                logging.info(f'First tab: {url} - Title: {driver.title}')
            else:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[index])
                driver.get(url)
                logging.info(f'tab: {index} {url} - Title: {driver.title}')
            with semaphore_for_redis:
                redis_con.sadd(processed_key, url)
        except WebDriverException as e:
            logging.warning(f"Failed to open {url} - {e}")
            with semaphore_for_redis:
                redis_con.sadd(failed_key, url)
    read_data(driver, len(group_of_tabs), redis_con, semaphore_for_redis, parse_options, id)
    
    with semaphore_for_redis:
        num_processed_links = redis_con.scard(processed_key)
        num_failed_links = redis_con.scard(failed_key)
        if num_processed_links + num_failed_links == total_num:
            # Set a flag in Redis to indicate the process has finished
            redis_con.set(f'finished:{id}', 1)    
    driver.quit()
    # if parse_options.scroll:
    #     pass
        # logging.warning(url)
    # r.ping()
    # print(id, options, group_of_tabs, total_num)