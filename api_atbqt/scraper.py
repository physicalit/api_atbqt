from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium import webdriver

import logging.config
import requests
import socket
import redis
import time

logging.config.fileConfig('logging.conf')
logger = logging.getLogger("root")

def setup_options():
        options = Options()
        options.add_argument('--headless')
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        options.page_load_strategy = "normal"
        return options

status_code_script = """
var callback = arguments[arguments.length - 1];
var xhr = new XMLHttpRequest();
xhr.open('GET', window.location.href, true);
xhr.onreadystatechange = function() {
  if (xhr.readyState == 4) {
    callback(xhr.status);
  }
};
xhr.send();
"""

script_ip = """
async function fetchIPAddress() {
  try {
    const response = await fetch('https://api.bigdatacloud.net/data/client-ip');
    const jsonData = await response.json();
    return jsonData.ipString;
  } catch (error) {
    console.error("Error:", error);
    return null;
  }
}

// Expose the fetchIPAddress function to the window object
window.fetchIPAddress = fetchIPAddress;
"""

def read_data(driver, num_of_tabs, redis_con, semaphore_for_redis, parse_options, request_id):
    for tab_index in range(num_of_tabs):
        driver.switch_to.window(driver.window_handles[tab_index])
        if parse_options.slow:
            driver.execute_script("window.scrollBy(0,950)")
            time.sleep(1)
        if parse_options.scroll:
            for _ in range(parse_options.scroll_amount):
                driver.execute_script("window.scrollBy(0,950)")
        result = driver.page_source
        
        with semaphore_for_redis:
            redis_con.hset(f'page_sources:{request_id}', driver.current_url, result)

def get_data(id, parse_options, group_of_tabs, total_num, semaphore_for_driver, semaphore_for_redis, semaphore_for_redis_atfinish): # in thread
    redis_con = redis.Redis(host='192.168.81.108', port=6379, db=0)
    processed_key = f'processed_links:{id}'
    failed_key = f'failed_links:{id}'
    with semaphore_for_driver:
        driver = webdriver.Remote(command_executor="http://192.168.81.101:4444/wd/hub", options=setup_options())
    for index, url in enumerate(group_of_tabs):
        try:
            if index == 0:
                driver.get(url)
                try:
                    status_code = driver.execute_async_script(status_code_script)
                except:
                    alert = WebDriverWait(driver, 10).until(EC.alert_is_present())
                    alert.accept()
                    status_code = driver.execute_async_script(status_code_script)
                    print("except")
                logging.warn(f'{status_code} First tab: {url} - Title: {driver.title}')
            else:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[index])
                driver.get(url)
                try:
                    status_code = driver.execute_async_script(status_code_script)
                except:
                    print("except")
                    alert = WebDriverWait(driver, 10).until(EC.alert_is_present())
                    alert.dismiss()
                    status_code = driver.execute_async_script(status_code_script)
                logging.info(f' {status_code} Tab: {index} {url} - Title: {driver.title}')
            if status_code != 200:
                driver.execute_script(script_ip)
                time.sleep(4)
                public_ip = driver.execute_script("return window.fetchIPAddress().then(ip => { return ip; });")
                logging.warning(f'{status_code} for {url} - Title: {driver.title}')
                logging.warning(f'My IP: {public_ip}')
                for entry in driver.get_log('browser'):
                    logging.info(entry['message'])
            with semaphore_for_redis:
                redis_con.sadd(processed_key, url)
        except WebDriverException as e:
            logging.warning(f"Failed to open {url} - {e}")
            with semaphore_for_redis:
                redis_con.sadd(failed_key, url)
    read_data(driver, len(group_of_tabs), redis_con, semaphore_for_redis, parse_options, id)
    
    with semaphore_for_redis_atfinish:
        num_processed_links = redis_con.scard(processed_key)
        num_failed_links = redis_con.scard(failed_key)
        print(num_processed_links, num_failed_links, total_num)
        if num_processed_links + num_failed_links == total_num:
            redis_con.set(f'finished:{id}', 1)    
    driver.quit()