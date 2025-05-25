import scrapy
from urllib.parse import urlparse, quote_plus, urljoin
import json
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup


# Helper function to safely get text or attribute
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
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36',
        'ROBOTSTXT_OBEY': False,
        'LOG_LEVEL': 'INFO',
        # Add CONCURRENT_REQUESTS_PER_DOMAIN if needed, but Selenium part is sequential per keyword/site.
    }

    def __init__(self, *args, **kwargs):
        super(MainSpider, self).__init__(*args, **kwargs)
        self.config_path = os.path.join(os.path.dirname(__file__), '..', 'scraper_config.json')
        self.config = self._load_config()
        
        self.allowed_domains = self._get_allowed_domains()
        self.base_keywords_to_search = self.config.get('base_keywords', [])
        self.selenium_timeout = self.config.get('selenium_wait_timeout', 10)

        options = webdriver.FirefoxOptions()
        options.add_argument('--headless') # Run headless
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--window-size=1920x1080')
        options.add_argument(f"user-agent={self.custom_settings.get('USER_AGENT')}")
        

        # Define the chrome driver path
        webdriver_path = self.config.get('selenium_webdriver_path')
        
        if webdriver_path and os.path.exists(webdriver_path):
            driver_dir = os.path.dirname(webdriver_path)
            os.environ['PATH'] = f"{driver_dir}{os.pathsep}{os.environ.get('PATH', '')}"
            service = FirefoxService(executable_path=webdriver_path)
            self.driver = webdriver.Firefox(service=service, options=options)
        elif webdriver_path:
            self.logger.warning(f"WebDriver path '{webdriver_path}' provided but not found. Trying system PATH.")
            self.driver = webdriver.Firefox(options=options)
        else:
            self.driver = webdriver.Firefox(options=options)
            
        self.logger.info("Selenium WebDriver initialized.")


    def _load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.logger.info(f"Loading configuration from: {self.config_path}")
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"CRITICAL: Config file not found at {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            self.logger.error(f"CRITICAL: Error decoding JSON from {self.config_path}: {e}")
            return {}

    def _get_allowed_domains(self):
        if not self.config or 'sites' not in self.config: return []
        domains = [urlparse(s_data['base_url']).netloc for s_key, s_data in self.config['sites'].items() if 'base_url' in s_data]
        return list(set(d for d in domains if d))

    def start_requests(self):
        if not self.config or not self.base_keywords_to_search or not hasattr(self, 'driver'):
            self.logger.error("Config/keywords missing or WebDriver not initialized. Stopping.")
            return

        for base_keyword in self.base_keywords_to_search:
            for site_key, site_config in self.config.get('sites', {}).items():
                self.logger.info(f"Fetching suggestions for keyword '{base_keyword}' on site '{site_key}'")
                
                autocomplete_html = self._fetch_autocomplete_html_with_selenium(site_config, base_keyword)
                if not autocomplete_html:
                    self.logger.warning(f"No autocomplete HTML for '{base_keyword}' on '{site_key}'.")
                    continue

                parsed_suggestions = self._parse_autocomplete_suggestions(
                    autocomplete_html, 
                    site_config.get('autocomplete_parser_type'),
                    site_config # Pass full site_config for context if parser needs it
                )
                self.logger.info(f"Found {len(parsed_suggestions)} suggestions for '{base_keyword}' on '{site_key}'.")

                for suggestion in parsed_suggestions:
                    search_term = suggestion.get('search_term')
                    cat_name = suggestion.get('category_name')
                    cat_id = suggestion.get('category_id') # eBay specific

                    if not search_term:
                        continue

                    # --- Category Filtering Logic ---
                    is_suggestion_valid = False
                    final_cat_name_for_url = None
                    final_cat_id_for_url = None

                    allowed_kw_list = site_config.get('allowed_category_keywords', [])
                    
                    if cat_name: # Suggestion included a category
                        category_passes_filter = True # Assume pass if allowed_kw_list is empty
                        if allowed_kw_list: # Only filter if keywords are specified
                            category_passes_filter = any(kw.lower() in cat_name.lower() for kw in allowed_kw_list)
                        
                        if category_passes_filter:
                            is_suggestion_valid = True
                            final_cat_name_for_url = cat_name
                            final_cat_id_for_url = cat_id
                        else:
                            # Category name present but did not match filter - discard this specific term+category combo
                            self.logger.debug(f"Discarding suggestion '{search_term}' in category '{cat_name}' (filter mismatch).")
                            continue 
                    else: # Suggestion had NO category information
                        if site_config.get('allow_search_without_category_if_suggestion_had_no_category', False):
                            is_suggestion_valid = True
                            # final_cat_name/id remain None
                        else:
                            self.logger.debug(f"Discarding suggestion '{search_term}' (no category, and not allowed).")
                            continue
                    
                    if not is_suggestion_valid:
                        continue

                    # --- Site-Specific URL Construction ---
                    scrapy_url = None
                    if site_key == 'ebay_us':
                        if final_cat_id_for_url: # Includes valid category ID
                            template = site_config.get('search_url_template_with_category')
                            if template:
                                scrapy_url = template.format(search_term=quote_plus(search_term), category_id=final_cat_id_for_url)
                        else: # No valid category ID from suggestion (either it had no cat, or cat had no ID)
                            template = site_config.get('search_url_template_no_category')
                            if template:
                                scrapy_url = template.format(search_term=quote_plus(search_term))
                    
                    elif site_key == 'olx_eg':
                        if final_cat_name_for_url:
                            cat_path_map = site_config.get('category_name_to_path_mapping', {})
                            cat_path = cat_path_map.get(final_cat_name_for_url)
                            template = site_config.get('search_url_template_with_category_path')
                            if cat_path and template:
                                slug = search_term.replace(' ', '-').lower() # Simple slug
                                scrapy_url = template.format(base_url=site_config['base_url'].rstrip('/'), 
                                                             category_path=cat_path, search_term_slug=slug)
                        else:
                            template = site_config.get('search_url_template_no_category')
                            if template:
                                scrapy_url = template.format(base_url=site_config['base_url'].rstrip('/'), 
                                                             search_term_query=quote_plus(search_term))
                    
                    if scrapy_url:
                        self.logger.info(f"Yielding Scrapy request for: {scrapy_url}")
                        yield scrapy.Request(scrapy_url, callback=self.parse_search_results,
                                             meta={'search_term': search_term, 'category_name': final_cat_name_for_url, 
                                                   'site': site_key, 'base_keyword': base_keyword})
        
        # No more keywords to process with Selenium for this spider run
        # Driver will be closed by spider_closed signal


    def _fetch_autocomplete_html_with_selenium(self, site_config, keyword):
        try:
            self.driver.get(site_config['base_url'])
            search_bar = WebDriverWait(self.driver, self.selenium_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, site_config['search_bar_selector']))
            )
            search_bar.clear()
            search_bar.send_keys(keyword)
            
            # Wait for autocomplete container to be visible and have children
            # This wait might need adjustment based on how quickly suggestions appear
            time.sleep(2) # Simple wait; a more robust JS-based wait would be better if possible

            autocomplete_container = WebDriverWait(self.driver, self.selenium_timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, site_config['autocomplete_container_selector']))
            )
            # Ensure children are loaded if container appears empty initially
            WebDriverWait(self.driver, self.selenium_timeout).until(
                lambda d: d.find_element(By.CSS_SELECTOR, site_config['autocomplete_container_selector']).get_attribute('innerHTML').strip() != ""
            )
            
            return autocomplete_container.get_attribute('outerHTML')
        except TimeoutException:
            self.logger.warning(f"Timeout waiting for elements for '{keyword}' on {site_config['base_url']}")
        except NoSuchElementException:
            self.logger.warning(f"Search bar or autocomplete container not found for '{keyword}' on {site_config['base_url']}")
        except Exception as e:
            self.logger.error(f"Selenium error fetching suggestions for '{keyword}' on {site_config['base_url']}: {e}")
        return None

    def _parse_autocomplete_suggestions(self, html_content, parser_type, site_config):
        if parser_type == 'ebay_list':
            return self._parse_ebay_autocomplete(html_content, site_config)
        elif parser_type == 'olx_buttons':
            return self._parse_olx_autocomplete(html_content, site_config)
        self.logger.warning(f"Unknown autocomplete_parser_type: {parser_type}")
        return []

    def _parse_ebay_autocomplete(self, ul_html_content, site_config):
        suggestions = []
        soup = BeautifulSoup(ul_html_content, 'html.parser')
        for li in soup.find_all('li', role='option'):
            search_term = safe_get(li, 'attr', 'data-value')
            cat_name_div = li.find('div', class_='ebay-autocomplete-cat')
            cat_name = safe_get(cat_name_div, 'text')
            if cat_name and cat_name.lower().startswith('in '):
                 cat_name = cat_name[3:].strip() # Remove "in " prefix
            cat_id = safe_get(li, 'attr', 'data-cat-id')
            
            if search_term:
                suggestions.append({
                    'search_term': search_term,
                    'category_name': cat_name,
                    'category_id': cat_id
                })
        return suggestions

    def _parse_olx_autocomplete(self, div_html_content, site_config):
        suggestions = []
        soup = BeautifulSoup(div_html_content, 'html.parser')
        # OLX HTML: <button aria-label="Suggestion: macbook pro m1" class="d6b0411e"><span class="b4b1a434"><em>macbook pro</em> m1</span></button>
        # Or: <button aria-label="Suggestion: macbook pro" class="d6b0411e"><span class="b4b1a434"><em> macbook pro </em> في لاب توب</span></button>
        for button in soup.find_all('button', class_=lambda x: x and 'd6b0411e' in x.split()): # More robust class check
            aria_label = safe_get(button, 'attr', 'aria-label')
            span = button.find('span') # , class_=lambda x: x and 'b4b1a434' in x.split())
            span_text = safe_get(span, 'text') if span else ''

            if not aria_label or not aria_label.lower().startswith('suggestion: '):
                continue # Skip if no valid aria-label

            full_suggestion_text_from_aria = aria_label[len('suggestion: '):].strip()
            search_term_to_use = full_suggestion_text_from_aria
            category_name = None

            if ' في ' in span_text: # "search term in category_arabic"
                try:
                    # The search term part in span might be different from aria-label, prioritize aria-label for term
                    _term_in_span, cat_in_span = span_text.split(' في ', 1)
                    category_name = cat_in_span.strip()
                except ValueError:
                    self.logger.warning(f"Could not split OLX category from span: {span_text}")
            
            # If aria-label contained the " في " part, it's complex. For now, assume search term is the whole aria label
            # and category_name is parsed from span if present.
            # This might lead to search_term like "macbook pro في لاب توب" if category parsing from aria-label isn't done.
            # Let's refine: if cat_name found, then the full_suggestion_text_from_aria might be just the item part.
            # This is tricky. Assume for now: aria-label provides the primary search term. Span provides category.
            # A more robust method would be to parse the specific structure if available.
            # The example aria-label="Suggestion: macbook pro" for the "macbook pro في لاب توب" case suggests the aria-label might be cleaner for the base term.
            # Let's try to clean the search term if a category was found.
            if category_name and f" في {category_name}" in full_suggestion_text_from_aria:
                 search_term_to_use = full_suggestion_text_from_aria.replace(f" في {category_name}", "").strip()

            suggestions.append({
                'search_term': search_term_to_use,
                'category_name': category_name,
                'category_id': None # OLX doesn't give IDs here
            })
        return suggestions

    def parse_search_results(self, response):
        # This is where you'd parse the actual search results page from eBay/OLX
        # For Phase 1: Extract Title, description, price, seller name/location, All listing images
        # Store metadata and links in a structured format (CSV or JSON)
        # Save image files
        site = response.meta.get('site', 'N/A')
        search_term = response.meta.get('search_term', 'N/A')
        category_name = response.meta.get('category_name', 'N/A')
        base_keyword = response.meta.get('base_keyword', 'N/A')

        self.logger.info(f"Parsing results from {response.url} for '{search_term}' (cat: {category_name}, base kw: {base_keyword})")
        
        # Example: (replace with actual selectors for each site)
        # for listing in response.css('li.s-item'): # Example eBay selector
        #     yield {
        #         'title': listing.css('h3.s-item__title::text').get(),
        #         'price': listing.css('span.s-item__price::text').get(),
        #         'listing_url': response.urljoin(listing.css('a.s-item__link::attr(href)').get()),
        #         'scraped_from_url': response.url,
        #         'search_term_used': search_term,
        #         'derived_from_keyword': base_keyword,
        #         'category_context': category_name
        #     }
        # For now, just log
        with open(f"{site}_{base_keyword.replace(' ','_')}_{search_term.replace(' ','_')}.html", 'wb') as f:
             f.write(response.body)
        self.logger.info(f"DUMPED HTML for {response.url}")


    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(MainSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=scrapy.signals.spider_closed)
        return spider

    def spider_closed(self, spider):
        if hasattr(self, 'driver'):
            self.driver.quit()
        self.logger.info('Spider closed and WebDriver quit.')