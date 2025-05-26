import scrapy
from urllib.parse import urlparse, quote_plus, urljoin
import json
import os
import time

# Selenium and WebDriver Manager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager # For auto-installing GeckoDriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from bs4 import BeautifulSoup
from Scrapper.items import ScrapperItem # Import your item definition

# Helper function (keep as is)
def safe_get(element, method, *args, default=None):
    try:
        if method == 'text':
            return element.text.strip()
        elif method == 'attr':
            return element.get(args[0])
    except AttributeError:
        return default
    return default

class MainSpider(scrapy.Spider):
    name = "main"
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/90.0',
        'ROBOTSTXT_OBEY': False,
        'LOG_LEVEL': 'INFO',
        'DOWNLOAD_DELAY': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 3,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 0.5,
    }

    def __init__(self, *args, **kwargs):
        super(MainSpider, self).__init__(*args, **kwargs)
        # Path: Scrapper/Scrapper/spiders/main.py -> Scrapper/Scrapper/scraper_config.json
        self.config_path = os.path.join(os.path.dirname(__file__), '..', 'scraper_config.json')
        self.config = self._load_config()
        
        self.allowed_domains = self._get_allowed_domains()
        self.base_keywords_to_search = self.config.get('base_keywords', [])
        self.selenium_timeout = self.config.get('selenium_wait_timeout', 15)

        options = FirefoxOptions()
        
        if self.config.get('headless', True):
            options.add_argument('--headless')
            self.logger.info("Selenium Firefox configured to run in headless mode.")
        else:
            self.logger.info("Selenium Firefox configured to run with a visible browser window.")

        options.add_argument('--disable-gpu') 
        options.add_argument('--no-sandbox') 
        options.add_argument('--window-size=1920,1080')
        options.set_preference("general.useragent.override", self.custom_settings.get('USER_AGENT'))
        
        if self.config.get('use_tor', True):
            tor_port = self.config.get('tor_socks_port', 9150)
            options.set_preference('network.proxy.type', 1)
            options.set_preference('network.proxy.socks', '127.0.0.1')
            options.set_preference('network.proxy.socks_port', tor_port)
            options.set_preference('network.proxy.socks_version', 5)
            options.set_preference("network.proxy.socks_remote_dns", True)
            self.logger.info(f"Selenium Firefox configured to use Tor SOCKS proxy on 127.0.0.1:{tor_port}.")
        else:
            self.logger.info("Selenium Firefox will NOT use Tor proxy (as per 'use_tor' flag in config).")

        try:
            self.logger.info("Initializing Selenium WebDriver with GeckoDriverManager...")
            geckodriver_path = GeckoDriverManager().install()
            self.logger.info(f"GeckoDriver installed/found at: {geckodriver_path}")
            service = FirefoxService(executable_path=geckodriver_path)
            self.driver = webdriver.Firefox(service=service, options=options)
            self.logger.info("Selenium Firefox WebDriver initialized successfully.")
        except Exception as e:
            self.logger.error(f"CRITICAL: Failed to initialize Selenium WebDriver: {e}")
            self.logger.error("Please ensure Firefox is installed and accessible. If using Tor, ensure it's running.")
            self.driver = None


    def _load_config(self):
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

    def _get_allowed_domains(self):
        if not self.config or 'sites' not in self.config: return []
        domains = []
        for site_key, site_data in self.config.get('sites', {}).items():
            if 'base_url' in site_data and site_data.get('base_url'):
                try:
                    domains.append(urlparse(site_data['base_url']).netloc)
                except Exception as e:
                     self.logger.error(f"Error parsing base_url for {site_key}: {site_data.get('base_url')}, Error: {e}")
        return list(set(d for d in domains if d))


    def start_requests(self):
        if not self.driver:
            self.logger.error("Selenium WebDriver not initialized. Spider cannot start. Check geckodriver/Firefox setup and Tor if enabled.")
            return
        if not self.config.get('sites') or not self.base_keywords_to_search: # Check if sites config exists
            self.logger.error("Configuration for 'sites' or 'base_keywords' missing in scraper_config.json. Spider cannot start requests.")
            return

        site_key = 'ebay_us' # Focusing on eBay only
        site_config = self.config.get('sites', {}).get(site_key)

        if not site_config:
            self.logger.error(f"Configuration for '{site_key}' not found in scraper_config.json. Stopping.")
            return

        for base_keyword in self.base_keywords_to_search:
            self.logger.info(f"Fetching suggestions for keyword '{base_keyword}' on site '{site_key}'")
            
            autocomplete_html = self._fetch_autocomplete_html_with_selenium(site_config, base_keyword)
            if not autocomplete_html:
                self.logger.warning(f"No autocomplete HTML retrieved for '{base_keyword}' on '{site_key}'.")
                continue

            parsed_suggestions = self._parse_autocomplete_suggestions(
                autocomplete_html, 
                site_config.get('autocomplete_parser_type'),
                site_config
            )
            self.logger.info(f"Found {len(parsed_suggestions)} suggestions for '{base_keyword}' on '{site_key}'.")

            for suggestion in parsed_suggestions:
                search_term = suggestion.get('search_term')
                cat_name = suggestion.get('category_name')
                cat_id = suggestion.get('category_id')

                if not search_term: continue

                is_suggestion_valid = False
                final_cat_name_for_url = None
                final_cat_id_for_url = None
                allowed_kw_list = site_config.get('allowed_category_keywords', [])
                
                if cat_name:
                    category_passes_filter = not allowed_kw_list or \
                                             any(kw.lower() in cat_name.lower() for kw in allowed_kw_list)
                    if category_passes_filter:
                        is_suggestion_valid = True
                        final_cat_name_for_url = cat_name
                        final_cat_id_for_url = cat_id
                    else:
                        self.logger.debug(f"Discarding suggestion '{search_term}' in category '{cat_name}' (filter mismatch for '{base_keyword}').")
                        continue 
                else: 
                    if site_config.get('allow_search_without_category_if_suggestion_had_no_category', False):
                        is_suggestion_valid = True
                    else:
                        self.logger.debug(f"Discarding suggestion '{search_term}' (no category, and not allowed for '{base_keyword}').")
                        continue
                
                if not is_suggestion_valid: continue

                scrapy_url = None
                if final_cat_id_for_url:
                    template = site_config.get('search_url_template_with_category')
                    if template:
                        scrapy_url = template.format(search_term=quote_plus(search_term), category_id=final_cat_id_for_url)
                else:
                    template = site_config.get('search_url_template_no_category')
                    if template:
                        scrapy_url = template.format(search_term=quote_plus(search_term))
                
                if scrapy_url:
                    self.logger.info(f"Yielding Scrapy request for: {scrapy_url} (Base KW: {base_keyword})")
                    yield scrapy.Request(scrapy_url, callback=self.parse_search_results,
                                         meta={'derived_from_keyword': base_keyword, 
                                               'category_context_from_search': final_cat_name_for_url,
                                               'search_term_used_on_srp': search_term 
                                              })

    def _fetch_autocomplete_html_with_selenium(self, site_config, keyword):
        try:
            self.driver.get(site_config['base_url'])
            search_bar_selector = site_config['search_bar_selector']
            autocomplete_container_selector = site_config['autocomplete_container_selector']

            search_bar = WebDriverWait(self.driver, self.selenium_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, search_bar_selector))
            )
            search_bar.clear()
            search_bar.send_keys(keyword)
            
            WebDriverWait(self.driver, self.selenium_timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, autocomplete_container_selector))
            )
            WebDriverWait(self.driver, self.selenium_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f"{autocomplete_container_selector} > li")) 
            )
            
            autocomplete_container = self.driver.find_element(By.CSS_SELECTOR, autocomplete_container_selector)
            return autocomplete_container.get_attribute('outerHTML')
        except TimeoutException:
            self.logger.warning(f"Timeout waiting for autocomplete elements for '{keyword}' on {site_config['base_url']}")
        except NoSuchElementException:
            self.logger.warning(f"Search bar or autocomplete container not found for '{keyword}' on {site_config['base_url']}")
        except Exception as e:
            self.logger.error(f"Selenium error fetching suggestions for '{keyword}' on {site_config['base_url']}: {e}")
        return None

    def _parse_autocomplete_suggestions(self, html_content, parser_type, site_config):
        if parser_type == 'ebay_list':
            return self._parse_ebay_autocomplete(html_content, site_config)
        self.logger.warning(f"Unsupported autocomplete_parser_type: {parser_type}")
        return []

    def _parse_ebay_autocomplete(self, ul_html_content, site_config):
        suggestions = []
        soup = BeautifulSoup(ul_html_content, 'html.parser')
        for li in soup.find_all('li', role='option'):
            search_term = safe_get(li, 'attr', 'data-value')
            cat_name_div = li.find('div', class_='ebay-autocomplete-cat')
            cat_name = safe_get(cat_name_div, 'text')
            if cat_name and cat_name.lower().startswith('in '):
                 cat_name = cat_name[3:].strip()
            cat_id = safe_get(li, 'attr', 'data-cat-id')
            
            if search_term:
                suggestions.append({
                    'search_term': search_term.strip(),
                    'category_name': cat_name,
                    'category_id': cat_id
                })
        return suggestions

    def parse_search_results(self, response):
        meta = response.meta
        self.logger.info(f"Parsing search results from {response.url} (Derived from: '{meta.get('derived_from_keyword')}')")

        listings = response.css('ul.srp-results li.s-item, div.s-item__wrapper') 
        if not listings:
            listings = response.css('div.srp-river-results ul.srp-list li.s-item')

        self.logger.info(f"Found {len(listings)} potential listings on page {response.url}")
        
        for i, listing in enumerate(listings):
            item_relative_url = listing.css('a.s-item__link::attr(href)').get()
            
            if item_relative_url:
                item_url = response.urljoin(item_relative_url)
                
                title_texts = listing.css('div.s-item__title span[role="heading"]::text, h3.s-item__title::text').getall()
                title_from_search = " ".join(t.strip() for t in title_texts if t.strip()).strip()
                if not title_from_search:
                     title_from_search = "".join(listing.css('.s-item__title ::text').getall()).strip()

                price_from_search = "".join(listing.css('span.s-item__price ::text').getall()).strip()
                
                request_meta_for_item_page = {
                    'derived_from_keyword': meta.get('derived_from_keyword'),
                    'category_context_from_search': meta.get('category_context_from_search'),
                    'title_from_srp': title_from_search, # Pass along info from SRP
                    'price_from_srp': price_from_search
                }
                yield scrapy.Request(item_url, callback=self.parse_item_page, meta={'item_data': request_meta_for_item_page})
            else:
                self.logger.debug(f"No item URL found for a listing element on {response.url} (index {i})")
        
        next_page_url = response.css('a.pagination__next[href]::attr(href), nav.pagination a[aria-label*="Next page"]::attr(href)').get()
        if next_page_url:
            self.logger.info(f"Found next page: {next_page_url}")
            yield scrapy.Request(response.urljoin(next_page_url),
                                 callback=self.parse_search_results,
                                 meta=meta)
        else:
            self.logger.info(f"No 'Next Page' link found on {response.url}")


    def parse_item_page(self, response):
        # Use .get with a default dictionary to prevent errors if 'item_data' is somehow missing
        item_data_from_srp = response.meta.get('item_data', {}) 
        self.logger.info(f"Parsing item page: {response.url}")

        item = ScrapperItem()

        # Meta Search Info (as per your new item definition)
        item['derived_from_keyword'] = item_data_from_srp.get('derived_from_keyword')
        item['category_context_from_search'] = item_data_from_srp.get('category_context_from_search')
        
        # Product information
        item['link'] = response.url
        item['title'] = response.css('h1.x-item-title__mainTitle span.ux-textspans::text').get()
        if not item['title']: 
            item['title'] = response.css('h1#itemTitle::text').get()
            if item['title']: item['title'] = item['title'].replace("Details about", "").strip()
        if not item['title']: item['title'] = item_data_from_srp.get('title_from_srp') # Fallback

        item['price'] = "".join(response.css('div.x-price-primary span.ux-textspans::text').getall()).strip()
        if not item['price']: 
            item['price'] = response.css('span#prcIsum::text, span#mm-saleDscPrc::text').get()
        if not item['price']: item['price'] = item_data_from_srp.get('price_from_srp') # Fallback

        desc_html_content = response.css('div#desc_module div#ds_div, div#desc_div').get()
        if desc_html_content:
            soup_desc = BeautifulSoup(desc_html_content, 'html.parser')
            item['description'] = soup_desc.get_text(separator=' ', strip=True)
        else:
            iframe_src = response.css('iframe#desc_ifr::attr(src)').get()
            if iframe_src:
                item['description'] = f"Description in iframe, see: {response.urljoin(iframe_src)}"
            else: item['description'] = None
        
        image_urls = []
        main_img_selectors = [
            'div.ux-image-carousel-item img::attr(data-zoom-src)', 
            'div.ux-image-carousel-item img::attr(src)',
            'img#icImg::attr(src)'
        ]
        for selector in main_img_selectors:
            urls = response.css(selector).getall()
            for url in urls:
                if url: image_urls.append(response.urljoin(url.split("?")[0]))

        thumb_selectors = ['div.ux-image-filmstrip-carousel-item button img::attr(src)']
        for selector in thumb_selectors:
            urls = response.css(selector).getall()
            for t_url in urls:
                if t_url:
                    clean_url = response.urljoin(t_url.split("?")[0])
                    if 's-l' in clean_url and ('.jpg' in clean_url or '.png' in clean_url):
                        try:
                            base, ext = clean_url.rsplit('.', 1)
                            parts = base.split('s-l')
                            if len(parts) > 1 and parts[-1].isdigit():
                                hires_url = f"{parts[0]}s-l1600.{ext}"
                                image_urls.append(hires_url)
                            else: image_urls.append(clean_url)
                        except ValueError: image_urls.append(clean_url)
                    else: image_urls.append(clean_url)
        item['image_urls'] = list(set(u for u in image_urls if u))

        breadcrumbs_texts = response.css('nav[aria-label="breadcrumb"] ol li a span::text, nav.breadcrumbs ul li a::text').getall()
        if breadcrumbs_texts:
            item['category'] = " > ".join([b.strip() for b in breadcrumbs_texts if b.strip()])
        else: item['category'] = item_data_from_srp.get('category_context_from_search')

        item['condition'] = "".join(response.css('div[data-testid="x-item-condition"] div.ux-labels-values__values-content span.ux-textspans::text').getall()).strip()

        specifics_dict = {}
        for spec_row_el in response.css('div.ux-labels-values__specifications--row, div.ux-layout-section__row--centerized'): 
            label_el = spec_row_el.css('div.ux-labels-values__labels-content span.ux-textspans--BOLD::text, div.ux-labels-values__labels span.ux-textspans::text').get()
            value_el_parts = spec_row_el.css('div.ux-labels-values__values-content span.ux-textspans::text, div.ux-labels-values__values span.ux-textspans::text').getall()
            value_el = " ".join(part.strip() for part in value_el_parts if part.strip()).strip()
            if label_el and value_el:
                specifics_dict[label_el.strip().lower().replace(':', '')] = value_el.strip()
        
        item['brand'] = specifics_dict.get('brand')
        item['location'] = specifics_dict.get('item location')

        returns_text = "".join(response.css('div[data-testid="x-returns-section"] span.ux-textspans::text').getall()).lower() # Updated selector
        item['free_returns'] = "free returns" in returns_text
        
        item['seller_name'] = response.css('div.x-sellercard-atf__info__about-seller a span.ux-textspans::text, span.ux-seller-section__ μέροςMark span.ux-textspans--PSEUDONYM::text').get()
        
        feedback_count_text = response.css('div.x-sellercard-atf__info__about-seller a.ux-action[aria-label*="feedback score"] span[aria-hidden="true"]::text, span.ux-seller-section__item--feedbackscore span.ux-textspans::text').get()
        item['seller_feedback_count'] = feedback_count_text.strip() if feedback_count_text else None
        
        positive_feedback_text = response.css('div.x-sellercard-atf__info__rating span.ux-textspans--PERCENTAGE, div.ux-seller-section__item--positive-feedback span.ux-textspans--SENTIMENT_POSITIVE::text').get()
        item['seller_rating'] = positive_feedback_text.strip() if positive_feedback_text else None
        
        item['seller_link'] = response.urljoin(response.css('div.x-sellercard-atf__info__about-seller a.ux-action[aria-label*="feedback score"]::attr(href), a.ux-seller-section__action[aria-label*="feedback score"]::attr(href)').get() or "")
        
        item['top_rated_seller'] = bool(response.css('span.ux-icon--TOP_RATED_PLUS_SEAL, div.ux-seller-section__item--TOP_RATED_PLUS_PROGRAM span.ux-icon--TOP_RATED_PLUS_PROGRAM').get()) # Added another selector for TRS
        item['seller_verified'] = None # Typically not a simple flag to scrape easily

        yield item

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(MainSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=scrapy.signals.spider_closed)
        return spider

    def spider_closed(self, spider):
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                self.logger.info('Selenium WebDriver quit successfully.')
            except Exception as e:
                self.logger.error(f"Error quitting WebDriver: {e}")
        self.logger.info(f"Spider '{spider.name}' closed.")