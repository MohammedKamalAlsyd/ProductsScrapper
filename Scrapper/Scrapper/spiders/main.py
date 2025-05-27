import scrapy
from urllib.parse import urlparse, quote_plus
import json
import os
import time
import re # For sanitizing filenames
import random # For random delays

# Selenium and WebDriver Manager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile # Correct import for profile
from webdriver_manager.firefox import GeckoDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from bs4 import BeautifulSoup
from Scrapper.items import ScrapperItem
from scrapy.http import HtmlResponse 

# Helper function to sanitize filenames
def sanitize_filename(name):
  if not name:
    return "unknown_filename"
  name_str = str(name)
  name_str = re.sub(r'[<>:"/\\|?*]', '_', name_str)
  name_str = re.sub(r'\s+', '_', name_str)
  return name_str[:100]

def safe_get(element, method, *args, default=None):
  if element is None: return default
  try:
    if method == 'text':
      return element.text.strip()
    elif method == 'attr':
      return element.get(args[0])
    else:
      return default
  except AttributeError:
    return default

class MainSpider(scrapy.Spider):
  name = "main"
  custom_settings = {
    'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/90.0', # Use the defined constant
    'ROBOTSTXT_OBEY': False,
    'LOG_LEVEL': 'INFO',
    'DOWNLOAD_DELAY': 3,
    'AUTOTHROTTLE_ENABLED': True,
    'AUTOTHROTTLE_START_DELAY': 5,
    'AUTOTHROTTLE_MAX_DELAY': 60,
    'AUTOTHROTTLE_TARGET_CONCURRENCY': 0.2,
    'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
    'CONCURRENT_REQUESTS' : 1,
  }

  def __init__(self, *args, **kwargs):
    super(MainSpider, self).__init__(*args, **kwargs)
    self.config_path = os.path.join(os.path.dirname(__file__), '..', 'scraper_config.json')
    self.config = self._load_config()
    
    self.allowed_domains = self._get_allowed_domains()
    self.base_keywords_to_search = self.config.get('base_keywords', [])
    self.selenium_timeout = self.config.get('selenium_wait_timeout', 25) # Increased
    self.max_srp_pages = self.config.get("max_srp_pages_to_scrape_per_search", 1) # Keep low for testing

    options = FirefoxOptions()
    
    if self.config.get('headless', False): # Default headless to False for easier debugging of bot pages
      options.add_argument('--headless')
      self.logger.info("Selenium Firefox configured to run in headless mode.")
    else:
      self.logger.info("Selenium Firefox configured to run with a visible browser window.")

    # --- Enhanced Stealth Attempts for Firefox ---
    profile = FirefoxProfile()
    # General privacy and anti-fingerprinting
    profile.set_preference("dom.webdriver.enabled", False)
    profile.set_preference('useAutomationExtension', False)
    profile.set_preference("general.useragent.override", self.custom_settings.get('USER_AGENT'))
    profile.set_preference("browser.privatebrowsing.autostart", True)
    profile.set_preference("privacy.trackingprotection.enabled", True)
    profile.set_preference("privacy.trackingprotection.pbmode.enabled", True)
    profile.set_preference("privacy.resistFingerprinting", self.config.get("selenium_resist_fingerprinting", False)) # Can break sites
    profile.set_preference("extensions.screenshots.disabled", True) # Minor, but less for site to query
    profile.set_preference("media.peerconnection.enabled", False) # Disable WebRTC
    profile.set_preference("geo.enabled", False) # Disable geolocation unless needed

    # Spoof screen resolution (adjust if needed, or make configurable)
    # screen_width = self.config.get("selenium_screen_width", 1920)
    # screen_height = self.config.get("selenium_screen_height", 1080)
    # options.add_argument(f"--width={screen_width}")
    # options.add_argument(f"--height={screen_height}")
    # Note: Setting window size via options.add_argument('--window-size=W,H') is often more reliable.

    options.profile = profile # This is the correct way for modern Selenium with FirefoxOptions
    # ------

    options.add_argument('--disable-gpu') 
    options.add_argument('--no-sandbox') 
    options.add_argument(f'--window-size={self.config.get("selenium_window_width", 1920)},{self.config.get("selenium_window_height", 1080)}')
    
    if self.config.get('use_tor', False): 
      # (Tor config remains the same)
      tor_port = self.config.get('tor_socks_port', 9150)
      options.set_preference('network.proxy.type', 1)
      options.set_preference('network.proxy.socks', '127.0.0.1')
      options.set_preference('network.proxy.socks_port', tor_port)
      options.set_preference('network.proxy.socks_version', 5)
      options.set_preference("network.proxy.socks_remote_dns", True)
      self.logger.info(f"Selenium Firefox configured to use Tor SOCKS proxy on 127.0.0.1:{tor_port}.")
    else:
      self.logger.info("Selenium Firefox will NOT use Tor proxy.")

    try:
      self.logger.info("Initializing Selenium WebDriver with GeckoDriverManager...")
      os.environ['WDM_LOG_LEVEL'] = '0' 
      os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
      
      # Give a path hints for GeckoDriver if webdriver_manager has issues sometimes
      # geckodriver_path = GeckoDriverManager(path=self.config.get("geckodriver_path_hint", ".")).install()
      geckodriver_path = GeckoDriverManager().install()
      self.logger.info(f"GeckoDriver installed/found at: {geckodriver_path}")
      
      service = FirefoxService(executable_path=geckodriver_path)
      self.driver = webdriver.Firefox(service=service, options=options)
      
      # Try to further hide webdriver flag after driver initialization
      self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
      self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
      self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]})") # Fake some plugins

      # Set a common screen resolution via JS if arguments don't stick
      # self.driver.execute_script(f"window.screen.availWidth = {screen_width}; window.screen.availHeight = {screen_height}; window.screen.width = {screen_width}; window.screen.height = {screen_height};")
      # self.driver.execute_script(f"window.outerWidth = {screen_width}; window.outerHeight = {screen_height}; window.innerWidth = {screen_width}; window.innerHeight = {screen_height};")


      self.logger.info("Selenium Firefox WebDriver initialized successfully.")
    except WebDriverException as e:
      self.logger.error(f"CRITICAL: WebDriverException during Selenium initialization: {e}")
      self.logger.error("Check Firefox/GeckoDriver compatibility, versions, permissions, or if display is needed (if not headless).")
      self.driver = None
    except Exception as e:
      self.logger.error(f"CRITICAL: Failed to initialize Selenium WebDriver: {e}")
      self.logger.error("Please ensure Firefox is installed. If using Tor, ensure Tor Browser is running and configured.")
      self.driver = None

  def _is_bot_challenge_page(self, current_driver: webdriver.Firefox):
      """Checks if the current page is a bot challenge page."""
      title = current_driver.title.lower()
      url = current_driver.current_url.lower()
      page_source = current_driver.page_source.lower()

      challenge_keywords_title = ["pardon our interruption", "access denied", "are you a human", "checking your browser", "Distil", "Incapsula", "Akamai"]
      challenge_keywords_url = ["challenge", "captcha", "distil_", "incap_"]
      challenge_keywords_body = ["reference id:", "please verify you are human", "enable javascript and cookies", "completing the security check"]

      if any(keyword in title for keyword in challenge_keywords_title):
          return True
      if any(keyword in url for keyword in challenge_keywords_url):
          return True
      if any(keyword in page_source for keyword in challenge_keywords_body):
          # Be careful with body checks as legitimate pages might have "reference id" for other reasons
          if "reference id:" in page_source and "checking your browser" in page_source: # More specific
              return True
      return False

  def _load_config(self): # (Same as before)
    try:
      with open(self.config_path, 'r', encoding='utf-8') as f:
        self.logger.info(f"Loading configuration from: {self.config_path}")
        return json.load(f)
    except FileNotFoundError:
      self.logger.error(f"CRITICAL: Config file not found at {self.config_path}. Please create it.")
      return {}
    except json.JSONDecodeError as e:
      self.logger.error(f"CRITICAL: Error decoding JSON from {self.config_path}: {e}. Check JSON syntax.")
      return {}

  def _get_allowed_domains(self): # (Same as before)
    if not self.config or 'sites' not in self.config: return []
    domains = []
    for site_key, site_data in self.config.get('sites', {}).items():
      if 'base_url' in site_data and site_data.get('base_url'):
        try:
          domains.append(urlparse(site_data['base_url']).netloc)
        except Exception as e:
          self.logger.error(f"Error parsing base_url for site '{site_key}': {site_data.get('base_url')}, Error: {e}")
    return list(set(d for d in domains if d))

  def start_requests(self):
      if not self.driver:
          self.logger.error("Selenium WebDriver not initialized. Spider cannot start.")
          return
      if not self.config.get('sites') or not self.base_keywords_to_search:
          self.logger.error("Configuration for 'sites' or 'base_keywords' missing in scraper_config.json.")
          return

      site_key = 'ebay_us'
      site_config = self.config.get('sites', {}).get(site_key)
      if not site_config:
          self.logger.error(f"Configuration for site '{site_key}' not found in scraper_config.json.")
          return

      for base_keyword in self.base_keywords_to_search:
          self.logger.info(f"Processing base keyword: '{base_keyword}'")
          try:
              self.logger.info(f"Navigating to base URL: {site_config['base_url']} for cookies/session context.")
              self.driver.get(site_config['base_url'])
              time.sleep(random.uniform(self.config.get("selenium_general_delay_min", 1.5), 
                                      self.config.get("selenium_general_delay_max", 3.0)))
              if self._is_bot_challenge_page(self.driver):
                  self.logger.error(f"Bot challenge on initial visit to {site_config['base_url']}. Skipping keyword '{base_keyword}'.")
                  self._save_debug_page(f"initial_visit_bot_challenge_{sanitize_filename(base_keyword)}")
                  continue
          except Exception as e:
              self.logger.warning(f"Error during initial visit to base_url {site_config['base_url']}: {e}. Proceeding with autocomplete.")

          autocomplete_html = self._fetch_autocomplete_html_with_selenium(site_config, base_keyword, site_key)
          if not autocomplete_html:
              self.logger.warning(f"No autocomplete HTML retrieved for '{base_keyword}' on site '{site_key}'. Skipping this base keyword.")
              continue

          parsed_suggestions = self._parse_autocomplete_suggestions(
              autocomplete_html,
              site_config.get('autocomplete_parser_type'),
              site_config
          )
          self.logger.info(f"Found {len(parsed_suggestions)} suggestions for base keyword '{base_keyword}'.")

          for suggestion_idx, suggestion in enumerate(parsed_suggestions):
              search_term = suggestion.get('search_term')
              cat_name = suggestion.get('category_name')
              cat_id = suggestion.get('category_id')

              if not search_term:
                  self.logger.debug(f"Suggestion {suggestion_idx} for '{base_keyword}' has no search_term. Skipping.")
                  continue

              is_suggestion_valid = False
              final_cat_name_for_url = None
              final_cat_id_for_url = None
              allowed_kw_list = site_config.get('allowed_category_keywords', [])

              if cat_name and cat_id:
                  category_passes_filter = not allowed_kw_list or \
                      any(kw.lower() in cat_name.lower() for kw in allowed_kw_list)
                  if category_passes_filter:
                      is_suggestion_valid = True
                      final_cat_name_for_url = cat_name
                      final_cat_id_for_url = cat_id
                      self.logger.debug(f"Using suggestion: '{search_term}' in category '{cat_name} ({cat_id})'")
                  else:
                      self.logger.debug(f"Discarding suggestion '{search_term}' in category '{cat_name}' (did not pass keyword filter).")
                      continue
              else:
                  if site_config.get('allow_search_without_category_if_suggestion_had_no_category', False):
                      is_suggestion_valid = True
                      final_cat_id_for_url = '0'
                      final_cat_name_for_url = "All Categories"
                      self.logger.debug(f"Using suggestion: '{search_term}' (no specific category from autocomplete, searching all).")
                  else:
                      self.logger.debug(f"Discarding suggestion '{search_term}' (no category, and not allowed to search without).")
                      continue

              if not is_suggestion_valid:
                  continue

              srp_url = None
              encoded_search_term = quote_plus(search_term)
              template_with_cat = site_config.get('search_url_template_with_category')
              template_no_cat = site_config.get('search_url_template_no_category')

              if final_cat_id_for_url and final_cat_id_for_url != '0' and template_with_cat:
                  if '{search_term}' in template_with_cat and '{category_id}' in template_with_cat:
                      srp_url = template_with_cat.replace('{search_term}', encoded_search_term).replace('{category_id}', str(final_cat_id_for_url))
                  else:
                      self.logger.warning(f"Template 'search_url_template_with_category' for '{site_key}' is malformed (missing placeholders).")

              if not srp_url and template_no_cat:
                  if '{search_term}' in template_no_cat:
                      srp_url = template_no_cat.replace('{search_term}', encoded_search_term)
                  else:
                      self.logger.warning(f"Template 'search_url_template_no_category' for '{site_key}' is malformed.")

              if not srp_url:
                  self.logger.error(f"Could not construct SRP URL for search term '{search_term}' on site '{site_key}'. Check templates in config.")
                  continue

              if srp_url:
                  self.logger.info(f"Yielding initial SRP request for processing with Selenium: {srp_url} (derived from '{base_keyword}')")
                  meta_for_srp = {
                      'derived_from_keyword': base_keyword,
                      'category_context_from_search': final_cat_name_for_url,
                      'search_term_used_on_srp': search_term,
                      'srp_url': srp_url,
                      'site_key': site_key
                  }
                  yield scrapy.Request(srp_url,
                                      callback=self.process_srp_with_selenium,
                                      meta=meta_for_srp,
                                      dont_filter=True)


  def process_srp_with_selenium(self, response):
    meta = response.meta 
    current_srp_url = meta['srp_url'] # Use the URL passed in meta for the first page
    
    page_count = 0

    while current_srp_url and page_count < self.max_srp_pages:
      page_count += 1
      self.logger.info(f"Selenium navigating to SRP page {page_count}/{self.max_srp_pages}: {current_srp_url}")
      
      try:
        time.sleep(random.uniform(self.config.get("selenium_srp_delay_min", 2.0), 
                                 self.config.get("selenium_srp_delay_max", 4.5)))
        self.driver.get(current_srp_url)
        
        if self._is_bot_challenge_page(self.driver):
            self.logger.error(f"BOT DETECTION on SRP: {self.driver.current_url}. Title: '{self.driver.title}'. Stopping this search.")
            self._save_debug_page(f"srp_bot_detection_{sanitize_filename(meta.get('search_term_used_on_srp'))}_{page_count}")
            return 

        WebDriverWait(self.driver, self.selenium_timeout).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.srp-results > li.s-item, div.srp-river-results > ul.srp-list > li.s-item")),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".srp-save-null-search__heading, .s-no-outline")), 
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.pagination__next, nav[role='navigation'] ul[class*='pagination']")) 
            )
        )
        time.sleep(random.uniform(self.config.get("srp_selenium_post_load_delay_min", 0.8), 
                                 self.config.get("srp_selenium_post_load_delay_max", 1.8)))

      except TimeoutException:
        self.logger.warning(f"Timeout on SRP {self.driver.current_url}. Incomplete page or structure change.")
        self._save_debug_page(f"srp_timeout_{sanitize_filename(meta.get('search_term_used_on_srp'))}_{page_count}")
        break 
      except Exception as e:
        self.logger.error(f"Error during Selenium SRP nav to {current_srp_url}: {e}")
        self._save_debug_page(f"srp_error_{sanitize_filename(meta.get('search_term_used_on_srp'))}_{page_count}")
        break

      selenium_rendered_response = HtmlResponse(
          url=self.driver.current_url, 
          body=self.driver.page_source,
          encoding='utf-8',
          request=response.request 
      )
      selenium_rendered_response.meta.update(meta)

      item_url_metas, next_page_srp_url_from_parser = self._extract_item_urls_and_next_srp(selenium_rendered_response)
      
      for item_meta_dict in item_url_metas:
          yield scrapy.Request(item_meta_dict['url'], # URL for Scrapy tracking
                               callback=self.process_item_page_with_selenium,
                               meta=item_meta_dict['meta'], 
                               dont_filter=True)

      if next_page_srp_url_from_parser:
          current_srp_url = next_page_srp_url_from_parser 
          self.logger.info(f"Next SRP page identified: {current_srp_url}")
      else:
          self.logger.info(f"No 'Next Page' link found on {selenium_rendered_response.url}. Ending pagination.")
          current_srp_url = None 
    
    if page_count >= self.max_srp_pages:
        self.logger.info(f"Reached max SRP pages ({self.max_srp_pages}) for '{meta.get('search_term_used_on_srp')}'.")

  def process_item_page_with_selenium(self, response):
      meta_for_item_page = response.meta 
      item_url = meta_for_item_page['item_url_to_load_with_selenium']

      self.logger.info(f"Selenium navigating to ITEM page: {item_url}")
      try:
          time.sleep(random.uniform(self.config.get("selenium_item_page_delay_min", 2.5), 
                                   self.config.get("selenium_item_page_delay_max", 5.5)))
          self.driver.get(item_url)

          if self._is_bot_challenge_page(self.driver):
              self.logger.error(f"BOT DETECTION on ITEM page: {self.driver.current_url}. Title: '{self.driver.title}'. Skipping item.")
              self._save_debug_page(f"item_bot_detection_{sanitize_filename(meta_for_item_page.get('title_from_srp', 'unknown_item'))}")
              return 

          WebDriverWait(self.driver, self.selenium_timeout).until(
              EC.any_of(
                  EC.presence_of_element_located((By.CSS_SELECTOR, "h1.x-item-title__mainTitle, h1#itemTitle")),
                  EC.presence_of_element_located((By.CSS_SELECTOR, "div.x-price-primary, span#prcIsum")),
                  EC.presence_of_element_located((By.ID, "desc_ifr")) # Description iframe
              )
          )
          time.sleep(random.uniform(self.config.get("item_page_selenium_post_load_delay_min", 1.0), 
                                   self.config.get("item_page_selenium_post_load_delay_max", 2.0)))

      except TimeoutException:
          self.logger.warning(f"Timeout on ITEM page {item_url}. Skipping.")
          self._save_debug_page(f"item_timeout_{sanitize_filename(meta_for_item_page.get('title_from_srp', 'unknown_item'))}")
          return
      except Exception as e:
          self.logger.error(f"Error during Selenium ITEM page nav to {item_url}: {e}")
          self._save_debug_page(f"item_error_{sanitize_filename(meta_for_item_page.get('title_from_srp', 'unknown_item'))}")
          return

      item_page_response = HtmlResponse(
          url=self.driver.current_url,
          body=self.driver.page_source,
          encoding='utf-8',
          request=response.request 
      )
      item_page_response.meta.update(meta_for_item_page) 

      for item in self.parse_item_page(item_page_response):
          yield item

  def _fetch_autocomplete_html_with_selenium(self, site_config, keyword, site_key): 
    # This method should largely remain the same as your last working version,
    # ensuring it uses the random delays from config.
    # For brevity, I'll assume it's still the one you provided.
    # Just make sure self.driver.get(site_config['base_url']) is called *before* this,
    # e.g., in start_requests loop, if you want cookies from base domain.
    try:
      # If not already on base_url (e.g., first call or after an error)
      # current_domain = urlparse(self.driver.current_url).netloc
      # target_domain = urlparse(site_config['base_url']).netloc
      # if current_domain != target_domain:
      #    self.driver.get(site_config['base_url'])
      #    time.sleep(random.uniform(1,2)) # Allow base page to settle if just navigated

      search_bar_selector = site_config['search_bar_selector']
      autocomplete_container_selector = site_config['autocomplete_container_selector']
      search_bar = WebDriverWait(self.driver, self.selenium_timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, search_bar_selector))
      )
      search_bar.clear()
      # search_bar.click() # Sometimes needed if element is obscured or to ensure focus
      # time.sleep(random.uniform(0.2,0.5))

      for char in keyword:
          search_bar.send_keys(char)
          time.sleep(random.uniform(self.config.get("autocomplete_char_min_delay", 0.05), 
                                   self.config.get("autocomplete_char_max_delay", 0.2)))
      
      time.sleep(random.uniform(self.config.get("autocomplete_post_type_delay_min", 1.2), 
                               self.config.get("autocomplete_post_type_delay_max", 2.2)))

      WebDriverWait(self.driver, self.selenium_timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, autocomplete_container_selector))
      )
      WebDriverWait(self.driver, self.selenium_timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f"{autocomplete_container_selector} > li")))
      time.sleep(random.uniform(self.config.get("autocomplete_results_settle_delay_min", 0.4), 
                               self.config.get("autocomplete_results_settle_delay_max", 0.9)))

      autocomplete_container = self.driver.find_element(By.CSS_SELECTOR, autocomplete_container_selector)
      return autocomplete_container.get_attribute('outerHTML')
    except Exception as e:
      self.logger.error(f"Error in _fetch_autocomplete for '{keyword}': {e}")
      self._save_debug_page(f"autocomplete_error_{sanitize_filename(keyword)}")
      return None


  def _parse_autocomplete_suggestions(self, html_content, parser_type, site_config): # (Same as before)
    if not html_content:
        self.logger.warning("No HTML content for _parse_autocomplete_suggestions.")
        return []
    if parser_type == 'ebay_list':
      return self._parse_ebay_autocomplete(html_content, site_config)
    self.logger.warning(f"Unsupported autocomplete_parser_type: {parser_type}")
    return []

  def _parse_ebay_autocomplete(self, ul_html_content, site_config): # (Same as before, ensure it's robust)
    suggestions = []
    soup = BeautifulSoup(ul_html_content, 'html.parser')
    for li in soup.find_all('li', attrs={'role': 'option'}): 
      search_term = li.get('data-value') 
      if not search_term:
          spans = li.select('span.ebayui-ellipsis-3, span[class*="gh-ac"]')
          search_term_parts = [s.get_text(strip=True) for s in spans]
          cat_div_text_el = li.select_one('div.ebay-autocomplete-cat') # Renamed for clarity
          if cat_div_text_el:
              cat_text_to_remove = cat_div_text_el.get_text(strip=True)
              search_term_parts = [p for p in search_term_parts if p != cat_text_to_remove]
          search_term = " ".join(search_term_parts).strip() if search_term_parts else li.get_text(strip=True)

      cat_name_div = li.find('div', class_='ebay-autocomplete-cat') 
      cat_name = cat_name_div.get_text(strip=True) if cat_name_div else None
      if cat_name and cat_name.lower().startswith('in '): 
        cat_name = cat_name[3:].strip()
      
      cat_id = li.get('data-cat-id') 
      
      if search_term: 
        suggestions.append({
          'search_term': search_term.strip(),
          'category_name': cat_name, 
          'category_id': cat_id  
        })
    return suggestions

  def _extract_item_urls_and_next_srp(self, response: HtmlResponse): # (Mostly same, ensure correct variable usage)
    meta = response.meta
    # self.logger.info(...) # Logging is good

    item_url_meta_list = []
    listings = response.css('div.srp-river-results ul.srp-list > li.s-item, ul.srp-results > li.s-item')
    # if not listings ... (debug save) ...

    # self.logger.info(...)

    for i, listing in enumerate(listings):
      item_relative_url = listing.css('a.s-item__link::attr(href)').get()
      if item_relative_url:
        item_url_absolute = response.urljoin(item_relative_url)
        title_from_search = listing.css('div.s-item__title span[role="heading"]::text, h3.s-item__title::text').get()
        # ... (fallbacks for title and price) ...
        title_from_search = title_from_search.strip() if title_from_search else None
        price_from_search = "".join(listing.css('span.s-item__price ::text').getall()).strip()
        price_from_search = price_from_search if price_from_search else None

        meta_for_item_detail_page = {
          'derived_from_keyword': meta.get('derived_from_keyword'),
          'category_context_from_search': meta.get('category_context_from_search'),
          'search_term_used_on_srp': meta.get('search_term_used_on_srp'),
          'title_from_srp': title_from_search,
          'price_from_srp': price_from_search,
          'srp_url': response.url,
          'item_url_to_load_with_selenium': item_url_absolute
        }
        item_url_meta_list.append({'url': item_url_absolute, 'meta': meta_for_item_detail_page})
    
    next_page_srp_url = None
    next_page_href = response.css('a.pagination__next[href]::attr(href), a[rel="next"][href]::attr(href)').get() # Combined selector

    if next_page_href:
      next_page_srp_url = response.urljoin(next_page_href)
      # --- Robust check for same page/fragment (from your previous version) ---
      if next_page_srp_url == response.url or next_page_srp_url.split("?")[0] == response.url.split("?")[0]:
            current_pgn_match = re.search(r'_pgn=(\d+)', response.url)
            next_pgn_match = re.search(r'_pgn=(\d+)', next_page_srp_url)
            is_same_page = False
            if current_pgn_match and next_pgn_match:
                if current_pgn_match.group(1) == next_pgn_match.group(1):
                    is_same_page = True
            elif not next_pgn_match and not current_pgn_match: # Neither has page number explicitly
                 # Could be page 1 if URLs are otherwise identical post-domain
                 if urlparse(response.url).path == urlparse(next_page_srp_url).path:
                     is_same_page = True # Potentially same page if no pgn diff
            
            if is_same_page:
                self.logger.warning(f"Next page URL '{next_page_srp_url}' seems to be the same as current '{response.url}'. Stopping pagination here.")
                next_page_srp_url = None
      #--- End robust check ---
    else: self.logger.info(...) # No next page link found

    return item_url_meta_list, next_page_srp_url


  def _save_debug_page(self, filename_base, response_obj=None):# (Same as before)
    try:
        if self.driver:
            # Ensure directory exists (e.g., Scrapper/Scrapper/debug_pages/)
            debug_dir = os.path.join(os.path.dirname(__file__), 'debug_pages')
            os.makedirs(debug_dir, exist_ok=True)
            full_path_base = os.path.join(debug_dir, filename_base)

            self.driver.save_screenshot(f"{full_path_base}.png")
            with open(f"{full_path_base}.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.logger.info(f"Saved Selenium debug files to {full_path_base}.[png/html]")
        elif response_obj: 
            debug_dir = os.path.join(os.path.dirname(__file__), 'debug_pages')
            os.makedirs(debug_dir, exist_ok=True)
            full_path_base = os.path.join(debug_dir, filename_base)
            with open(f"{full_path_base}_scrapy.html", "wb") as f:
                f.write(response_obj.body)
            self.logger.info(f"Saved Scrapy response body for debug to {full_path_base}_scrapy.html")
    except Exception as e_save:
        self.logger.error(f"Error saving debug files ({filename_base}): {e_save}")


  def parse_item_page(self, response: HtmlResponse): # (Same as before, uses the Selenium rendered response)
    item_data_from_meta = response.meta 
    self.logger.info(f"Parsing item page (rendered by Selenium): {response.url} (From SRP: {item_data_from_meta.get('srp_url')})")

    item = ScrapperItem()
    item['derived_from_keyword'] = item_data_from_meta.get('derived_from_keyword')
    item['category_context_from_search'] = item_data_from_meta.get('category_context_from_search')
    item['link'] = response.url
    
    title_text = response.css('h1.x-item-title__mainTitle span.ux-textspans::text').get()
    if not title_text: 
      title_text = response.css('h1#itemTitle span.ux-textspans--BOLD::text').get()
      if not title_text: title_text = response.css('h1#itemTitle ::text').get() 
      if title_text: title_text = title_text.replace("Details about", "").strip()

    if not title_text: title_text = item_data_from_meta.get('title_from_srp')
    item['title'] = title_text.strip() if title_text else None

    price_text = "".join(response.css('div.x-price-primary span.ux-textspans::text').getall()).strip()
    if not price_text: 
        price_text = response.css('span#prcIsum::text, span#mm-saleDscPrc::text, div[data-testid="item-price"] span.ux-textspans::text').get()
    if not price_text: price_text = item_data_from_meta.get('price_from_srp')
    item['price'] = price_text.strip() if price_text else None

    desc_html_content = response.css('div#desc_module div#ds_div, div#desc_div').get()
    if not desc_html_content: desc_html_content = response.css('div#descriptioncontent, section#description ~ div[class*="vim"], div#viTabs_0_is').get() 

    if desc_html_content:
      soup_desc = BeautifulSoup(desc_html_content, 'html.parser')
      for s_tag in soup_desc(['script', 'style']): s_tag.decompose() # Corrected variable name
      item['description'] = soup_desc.get_text(separator=' ', strip=True)
    else:
      iframe_src = response.css('iframe#desc_ifr::attr(src)').get()
      if iframe_src: 
          # TODO: If iframe content is vital, you need another Selenium navigation step here.
          # For now, just noting the iframe.
          # self.driver.get(response.urljoin(iframe_src))
          # iframe_content = self.driver.page_source
          # soup_iframe_desc = BeautifulSoup(iframe_content, 'html.parser')
          # item['description'] = soup_iframe_desc.get_text(separator=' ', strip=True)
          item['description'] = f"Description in iframe (content not fetched): {response.urljoin(iframe_src)}"
      else: item['description'] = None
    
    image_urls_found = []
    main_img_selectors = [
      'div.ux-image-carousel-item button img::attr(data-zoom-src)', 
      'div.ux-image-carousel-item img::attr(data-zoom-src)', 
      'div.ux-image-carousel-item img::attr(src)', 
      'img#icImg::attr(src)',
      'div.img-figures-viewport ul li img::attr(data-zoom-src)', 
      'div.img-figures-viewport ul li img::attr(src)'
    ]
    for selector in main_img_selectors:
      urls = response.css(selector).getall()
      for url_str in urls: # Renamed url to url_str to avoid conflict
        if url_str and 'gif' not in url_str.lower(): 
            image_urls_found.append(response.urljoin(url_str.split("?")[0]))

    thumb_selectors = [
        'div.ux-image-filmstrip-carousel-item button img::attr(src)',
        'div.ux-image-grid-container button img::attr(src)', 
        'ul.lstTabs li a img::attr(src)' 
    ]
    for selector in thumb_selectors:
      urls = response.css(selector).getall()
      for t_url in urls:
        if t_url and 'gif' not in t_url.lower():
          clean_url = response.urljoin(t_url.split("?")[0])
          if 's-l' in clean_url and ('.jpg' in clean_url or '.png' in clean_url):
            try:
              base_part, size_part_ext = clean_url.rsplit('s-l', 1)
              size_code_match = re.match(r'(\d+)\.(jpg|png|jpeg|gif|webp)', size_part_ext, re.IGNORECASE)
              if size_code_match:
                ext = size_code_match.group(2)
                hires_url = f"{base_part}s-l1600.{ext}" 
                image_urls_found.append(hires_url)
              else: image_urls_found.append(clean_url)
            except ValueError: image_urls_found.append(clean_url)
          else: image_urls_found.append(clean_url)
    
    item['image_urls'] = list(set(u for u in image_urls_found if u and u not in ["", None, "null"]))

    breadcrumbs_texts = response.css('nav[aria-label="breadcrumb"] ol li a span::text, nav.breadcrumbs ul li a::text, nav[aria-label="Breadcrumb"] ol li a span::text').getall()
    if breadcrumbs_texts:
      filtered_breadcrumbs = [b.strip() for b in breadcrumbs_texts if b.strip() and (len(breadcrumbs_texts) <= 2 or b.strip().lower() not in ["home", "electronics"])]
      item['category'] = " > ".join(filtered_breadcrumbs) if filtered_breadcrumbs else " > ".join([b.strip() for b in breadcrumbs_texts if b.strip()])
    else: item['category'] = item_data_from_meta.get('category_context_from_search')

    condition_text = "".join(response.css('div[data-testid="x-item-condition"] div.ux-labels-values__values-content span.ux-textspans::text, div.d-item-condition span.ux-textspans::text').getall()).strip()
    if not condition_text:
        condition_in_specifics = response.xpath("//div[contains(@class, 'ux-labels-values__labels') and (.//span[contains(translate(text(), 'CONDITION', 'condition'), 'condition')] or .//span[contains(translate(text(), 'Condition', 'condition'), 'Condition')])]/following-sibling::div[contains(@class, 'ux-labels-values__values')]//span/text()").getall()
        if condition_in_specifics: condition_text = " ".join(c.strip() for c in condition_in_specifics).strip()
    item['condition'] = condition_text.strip() if condition_text else None

    specifics_dict = {}
    spec_rows_selectors = [
        'div.ux-labels-values__specifications--row',
        'div.ux-layout-section__row--centerized',
        'div.item-details div.ux-labels-values__prop-row',
        'div.x-specs div.x-specs__row' 
    ]
    for row_selector_str in spec_rows_selectors:
        for spec_row_el in response.css(row_selector_str):
            label_sel_text = spec_row_el.css('div.ux-labels-values__labels-content span.ux-textspans--BOLD::text, div.ux-labels-values__labels span.ux-textspans::text, div.ux-labels-values__prop-label span::text, div.x-specs__label span::text').get()
            value_parts_sel_texts = spec_row_el.css('div.ux-labels-values__values-content span.ux-textspans::text, div.ux-labels-values__values span.ux-textspans::text, div.ux-labels-values__prop-value span::text, div.x-specs__value span::text').getall()
            
            label_el_str = label_sel_text.strip().lower().replace(':', '') if label_sel_text else None # Renamed label_el
            value_el_str = " ".join(part.strip() for part in value_parts_sel_texts if part.strip()).strip() # Renamed value_el
            
            if label_el_str and value_el_str and label_el_str not in specifics_dict: 
                specifics_dict[label_el_str] = value_el_str
    
    if not specifics_dict or len(specifics_dict) < 3: 
      for row_selector_el in response.css('div.itemAttr table tr, div.item-specifics table tr, table.vi-ia-tb tr'): # Renamed row_selector
        label_text_from_row_el = row_selector_el.css('td.attrLabels::text, th::text, td.x-item-specifics__label::text').get() # Renamed
        
        value_str = None # Renamed value
        value_nodes_list = row_selector_el.css('td span, td:not([class*="label"])') # Renamed
        if value_nodes_list:
            all_texts = []
            span_texts_list = value_nodes_list.css('span::text').getall() # Renamed
            if span_texts_list and any(s.strip() for s in span_texts_list):
                all_texts = [s.strip() for s in span_texts_list if s.strip()]
            else: 
                for n_sel_el in value_nodes_list: # Renamed
                    node_text = "".join(n_sel_el.xpath(".//text()").getall()).strip() # Renamed
                    if node_text: all_texts.append(node_text)
            processed_val = " ".join(all_texts).strip() # Renamed
            if processed_val: value_str = processed_val
        
        if not value_str:
            fallback_val_text = row_selector_el.css('td:last-child::text').get() # Renamed
            if fallback_val_text: value_str = fallback_val_text.strip()
        
        if label_text_from_row_el and value_str:
            clean_label_str = label_text_from_row_el.strip().lower().replace(':', '').rstrip() # Renamed
            if clean_label_str and clean_label_str not in specifics_dict:
                specifics_dict[clean_label_str] = value_str
    
    item['brand'] = specifics_dict.get('brand')
    item['location'] = specifics_dict.get('item location', specifics_dict.get('location'))
    returns_text_list = response.css('div[data-testid="x-returns-section"] span.ux-textspans::text, span[data-testid="text"]::text, div[data-testid="x-returns-text"] span::text').getall() # Renamed
    returns_text_str = " ".join(p.strip() for p in returns_text_list).lower() # Renamed
    item['free_returns'] = any(phrase in returns_text_str for phrase in ["free returns", "freereturns", "free 30 day returns"])
    
    seller_name_text = response.css('div.x-sellercard-atf__info__about-seller a span.ux-textspans::text, span.ux-seller-section__ μέροςMark span.ux-textspans--PSEUDONYM::text, div.ux-seller-section__item--seller a span.ux-textspans::text, a[data-testid="seller-profile-link"] span span::text, div.ux-seller-section__item--seller span[class*="ux-textspans"]::text').get() # Renamed
    item['seller_name'] = seller_name_text.strip() if seller_name_text else None
    
    feedback_count_str_raw = response.css('div.x-sellercard-atf__info__about-seller a.ux-action[aria-label*="feedback score"] span[aria-hidden="true"]::text, span.ux-seller-section__item--feedbackscore span.ux-textspans::text, a[data-testid="seller-profile-link"] span.ux-textspans--SECONDARY::text, div.ux-seller-section__item--feedbackscore span[class*="ux-textspans"]::text').get() # Renamed
    if feedback_count_str_raw:
        feedback_match_obj = re.search(r'\((\d[\d,]*(?:\.\d+)?)\)', feedback_count_str_raw) # Renamed
        item['seller_feedback_count'] = feedback_match_obj.group(1).strip() if feedback_match_obj else feedback_count_str_raw.strip()
    else: item['seller_feedback_count'] = None

    positive_feedback_text = response.css('div.x-sellercard-atf__info__rating span.ux-textspans--PERCENTAGE, div.ux-seller-section__item--positive-feedback span.ux-textspans--SENTIMENT_POSITIVE::text, div[data-testid="seller-score"] span.ux-textspans--سجل::text, div.ux-seller-section__item--positivefeedback span[class*="ux-textspans"]::text').get() # Renamed
    item['seller_rating'] = positive_feedback_text.strip() if positive_feedback_text else None
    
    seller_link_attr = response.css('div.x-sellercard-atf__info__about-seller a.ux-action[aria-label*="feedback score"]::attr(href), a.ux-seller-section__action[aria-label*="feedback score"]::attr(href), div.ux-seller-section__item--seller a::attr(href), a[data-testid="seller-profile-link"]::attr(href)').get() # Renamed
    item['seller_link'] = response.urljoin(seller_link_attr) if seller_link_attr else None
    
    item['top_rated_seller'] = bool(response.css('span.ux-icon--TOP_RATED_PLUS_SEAL, div.ux-seller-section__item--TOP_RATED_PLUS_PROGRAM span.ux-icon--TOP_RATED_PLUS_PROGRAM, svg[aria-label="Top Rated Seller"], span[title="Top Rated Seller"], span.ux-icon--TRS_PROGRAM_VISUAL_INDICATOR').get())
    item['seller_verified'] = None 
    # ------- End of parse_item_page logic --------
    print("Final A Fckd Item",item)
    yield item

  @classmethod
  def from_crawler(cls, crawler, *args, **kwargs): # (Same as before)
    spider = super(MainSpider, cls).from_crawler(crawler, *args, **kwargs)
    crawler.signals.connect(spider.spider_closed, signal=scrapy.signals.spider_closed)
    return spider

  def spider_closed(self, spider, reason): # (Same as before)
    if hasattr(self, 'driver') and self.driver:
      try:
        self.driver.quit()
        self.logger.info('Selenium WebDriver quit successfully.')
      except Exception as e:
        self.logger.error(f"Error quitting WebDriver: {e}")
    self.logger.info(f"Spider '{spider.name}' closed. Reason: {reason}")