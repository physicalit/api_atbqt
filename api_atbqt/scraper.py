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
function getPublicIP() {
    fetch('https://api.bigdatacloud.net/data/client-ip')  // Or your chosen service
        .then(response => response.json())
        .then(data => {
            const ipAddress = data.ipString;
            console.log("Node's Public IP Address:", ipAddress);
            // Optionally, return the IP address back to your Python code
            return ipAddress; 
        })
        .catch(error => console.error("Error fetching IP:", error));
}

return getPublicIP(); 
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
                status_code = driver.execute_async_script(status_code_script)
                logging.info(f'{status_code} First tab: {url} - Title: {driver.title}')
            else:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[index])
                driver.get(url)
                status_code = driver.execute_async_script(status_code_script)
                # status_code = WebDriverWait(driver, 10).until(lambda d: d.execute_async_script(status_code_script))
                logging.info(f' {status_code} Tab: {index} {url} - Title: {driver.title}')
            if status_code != 200:
                # public_ip = driver.execute_script(script_ip)
                public_ip = WebDriverWait(driver, 10).until(lambda d: d.execute_async_script(script_ip))
                logging.error(f'{status_code} for {url} - Title: {driver.title}')
                logging.error(f'My IP: {public_ip}')
                logging.warning(f'{driver.get_log('browser')}')
                for entry in driver.get_log('browser'):
                    logging.warning(entry['message'])
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
            redis_con.set(f'finished:{id}', 1)    
    driver.quit()