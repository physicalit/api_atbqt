from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoAlertPresentException
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
""" # with async option
# status_code_script = """
# let callback = arguments[arguments.length - 1];

# async function handleReadStateChange() {
#     if (document.readyState === 'complete') {
#         try {
#             const response = await fetch(window.location.href, { method: 'HEAD' });
#             const statusCode = response.status;
#             callback(statusCode);
#         } catch (err) {
#             console.error('Error while trying to get status code:', err);
#             // Fallback to GET request if HEAD request fails
#             try {
#                 const response = await fetch(window.location.href, { method: 'GET' });
#                 const statusCode = response.status;
#                 callback(statusCode);
#             } catch (err) {
#                 console.error('Error while trying to get status code with GET request:', err);
#                 callback(0);
#             }
#         }
#     }
# }
# if (document.readyState === 'loading' || document.readyState === 'interactive') {
#     document.addEventListener('readystatechange', handleReadStateChange);
# } else {
#     handleReadStateChange();
# }
# """

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

def get_status(driver):
    try:
        try:
            time.sleep(1)
            alert = driver.switch_to.alert  
            alert.dismiss()
        except NoAlertPresentException:
            logging.info(f'No aelrt box found')
        driver.execute_script("window.scrollBy(0,950)")
        status_code = driver.execute_async_script(status_code_script)
    except:
        try:
            time.sleep(1)
            driver.execute_script("window.scrollBy(0,950)")
            alert = WebDriverWait(driver, 10).until(EC.alert_is_present())
            alert.accept()
            status_code = driver.execute_async_script(status_code_script)
        except:
            logging.info(f'Unable to get status code - giving it one more try')
            try:
                time.sleep(1)
                driver.execute_script("window.scrollBy(0,950)")
                status_code = driver.execute_async_script(status_code_script)
            except:
                logging.error(f'geting status code - Failed')
        return status_code

def get_data(id, parse_options, group_of_tabs, total_num, semaphore_for_driver, semaphore_for_redis, semaphore_for_redis_atfinish): # in thread
    redis_con = redis.Redis(host='192.168.81.108', port=6379, password='XJZAT3yjBmo5et3WsNdL', db=0)
    processed_key = f'processed_links:{id}'
    failed_key = f'failed_links:{id}'
    with semaphore_for_driver:
        driver = webdriver.Remote(command_executor="http://192.168.81.101:4444/wd/hub", options=setup_options())
    for index, url in enumerate(group_of_tabs):
        try:
            if index == 0:
                driver.get(url)
                status_code = get_status(driver)
                logging.info(f'{status_code} First tab: {url} - Title: {driver.title}')
            else:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[index])
                driver.get(url)
                status_code = get_status(driver)
                logging.info(f' {status_code} Tab: {index} {url} - Title: {driver.title}')
            if status_code != 200:
                driver.execute_script(script_ip)
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
        logging.info(f"Success: {num_processed_links}, Failed: {num_failed_links}, Total: {total_num}")
        if num_processed_links + num_failed_links == total_num:
            redis_con.set(f'finished:{id}', 1)    
    driver.quit()