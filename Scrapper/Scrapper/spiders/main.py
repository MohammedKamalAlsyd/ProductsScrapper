import scrapy
import json
from urllib.parse import urlencode, urljoin
import re
import html
from pathlib import Path # For robust config path

from Scrapper.items import ScrapperItem

class MainSpider(scrapy.Spider):
    name = "main"
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36',
    }

    def __init__(self, *args, **kwargs):
        super(MainSpider, self).__init__(*args, **kwargs)
        
        config_file_path = Path(__file__).parent.parent / 'scraper_config.json'
        
        try:
            with open(config_file_path, 'r') as f:
                self.scraper_configuration = json.load(f)
            self.logger.info(f"Successfully loaded configuration from {config_file_path}")
        except FileNotFoundError:
            self.logger.error(f"CRITICAL: Configuration file '{config_file_path}' not found. Ensure it exists in the correct location (Scrapper/Scrapper/scraper_config.json).")
            self.scraper_configuration = {} 
        except json.JSONDecodeError:
            self.logger.error(f"CRITICAL: Error decoding JSON from '{config_file_path}'. Please check its format.")
            self.scraper_configuration = {}

        self.base_keywords = self.scraper_configuration.get('base_keywords', [])
        self.use_suggestions_setting = self.scraper_configuration.get('use_suggestions', False)
        self.suggestion_url_template = self.scraper_configuration.get('suggestion_url')
        self.suggestion_base_params = self.scraper_configuration.get('suggestion_base_params', {})
        self.search_base_url_template = self.scraper_configuration.get('search_base_url')
        self.search_params_template = self.scraper_configuration.get('search_base_params', {}).copy()
        self.default_category_id_config = self.scraper_configuration.get('default_category_id', '0')
        
        self.use_tor = self.scraper_configuration.get('use_tor', False)
        self.tor_proxy = self.scraper_configuration.get('tor_proxy_address') if self.use_tor else None
        self.max_pages = self.scraper_configuration.get('max_search_pages_per_keyword', 1)
        
        self.download_images_config = self.scraper_configuration.get('download_product_images', True)
        self.logger.info(f"Image download from JSON config: {self.download_images_config}")

    def _make_request(self, url, callback, meta=None, method='GET', body=None, headers=None):
        if meta is None:
            meta = {}
        if self.use_tor and self.tor_proxy:
            meta['proxy'] = self.tor_proxy
        return scrapy.Request(url, callback=callback, meta=meta, method=method, body=body, headers=headers, errback=self.errback_httpbin)

    def errback_httpbin(self, failure):
        self.logger.error(repr(failure))
        if failure.check(scrapy.spidermiddlewares.httperror.HttpError):
            response = failure.value.response
            self.logger.error('HttpError on %s', response.url)
        elif failure.check(scrapy.resolver.DNSLookupError): # Adjusted for actual Scrapy exception type
            request = failure.request
            self.logger.error('DNSLookupError on %s', request.url)
        elif failure.check(TimeoutError): # Python's built-in TimeoutError, or twisted.internet.error.TimeoutError
            request = failure.request
            self.logger.error('TimeoutError on %s', request.url)

    async def start(self):
        if not self.scraper_configuration:
            self.logger.error("Spider configuration (scraper_config.json) not loaded or empty. Halting spider.")
            return

        if not self.base_keywords:
            self.logger.warning("No 'base_keywords' found in configuration. Spider will not perform any searches.")
            return
        if not self.search_base_url_template:
            self.logger.error("CRITICAL: 'search_base_url' is not configured in scraper_config.json. Searches cannot proceed. Halting spider.")
            return

        for keyword in self.base_keywords:
            if self.use_suggestions_setting and self.suggestion_url_template:
                suggestion_params = self.suggestion_base_params.copy()
                suggestion_params['kwd'] = keyword
                final_suggestion_url = f"{self.suggestion_url_template}?{urlencode(suggestion_params)}"
                self.logger.info(f"Fetching suggestions for '{keyword}' from: {final_suggestion_url}")
                request_meta = {'original_keyword': keyword}
                yield self._make_request(final_suggestion_url, callback=self.parse_suggestions, meta=request_meta)
            else:
                self.logger.info(f"Using base keyword directly (no suggestions or suggestion URL missing): '{keyword}'")
                # FIX: Iterate over the synchronous generator and yield its items
                for request in self._initiate_search(keyword, self.default_category_id_config, original_keyword_info=keyword):
                    yield request

    # parse_suggestions still yields from _initiate_search, so it also needs to be fixed
    def parse_suggestions(self, response): # This remains a synchronous generator
        original_keyword = response.meta['original_keyword']
        self.logger.info(f"Received suggestions for '{original_keyword}' from {response.url}")
        
        try:
            response_text = response.text
            callback_name = self.suggestion_base_params.get("callback", "0")
            if callback_name and response_text.startswith(callback_name + "(") and response_text.endswith(")"):
                 response_text = response_text[len(callback_name)+1:-1]
            data = json.loads(response_text)
        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode JSON from suggestion response for {original_keyword}. Body: {response.text[:300]}")
            # FIX: Iterate over the synchronous generator and yield its items
            for request in self._initiate_search(original_keyword, self.default_category_id_config, original_keyword_info=original_keyword):
                yield request
            return # Explicit return after yielding to avoid "generator didn't yield" if it was an error path

        processed_suggestions = False
        suggestions_sources = [
            data.get("richRes", {}).get("sug", []),
            data.get("rcser", {}).get("sug", []),
            data.get("sug", []) 
        ]

        for sug_list in suggestions_sources:
            if sug_list:
                processed_suggestions = True
                self.logger.info(f"Processing suggestions for '{original_keyword}' from a list of size {len(sug_list)}")
                for sug_item in sug_list:
                    kwd = sug_item.get("kwd")
                    cat_id_to_use = self.default_category_id_config
                    category_info = sug_item.get("category", [])
                    if len(category_info) >= 1 and category_info[0]:
                        cat_id_to_use = str(category_info[0])
                    if kwd:
                        self.logger.info(f"  Suggested keyword: {kwd}, Category ID: {cat_id_to_use}")
                        # FIX: Iterate over the synchronous generator and yield its items
                        for request in self._initiate_search(kwd, cat_id_to_use, original_keyword_info=original_keyword):
                            yield request
                break 
        if not processed_suggestions:
            self.logger.warning(f"No valid suggestions found in response for '{original_keyword}'. Using original keyword for search.")
            # FIX: Iterate over the synchronous generator and yield its items
            for request in self._initiate_search(original_keyword, self.default_category_id_config, original_keyword_info=original_keyword):
                yield request

    # _initiate_search remains a synchronous generator
    def _initiate_search(self, keyword, category_id, original_keyword_info=None):
        if not self.search_base_url_template:
            self.logger.error(f"'search_base_url' not configured. Cannot search for '{keyword}'.")
            return # This will make it an empty generator if this condition is met

        search_params = self.search_params_template.copy()
        search_params['_nkw'] = keyword
        search_params['_sacat'] = category_id if category_id else self.default_category_id_config
        search_params['_pgn'] = 1
        full_search_url = f"{self.search_base_url_template}?{urlencode(search_params)}"
        display_keyword = f"{keyword} (original: {original_keyword_info})" if original_keyword_info and original_keyword_info != keyword else keyword
        self.logger.info(f"Initiating search for '{display_keyword}', Category: {category_id}, Page: 1 at {full_search_url}")

        request_meta = {
            'source_keyword': original_keyword_info if original_keyword_info else keyword,
            'current_keyword': keyword,
            'category_id': category_id,
            'search_page_number': 1,
            'search_url_template': full_search_url
        }
        yield self._make_request(full_search_url, callback=self.parse_search_results, meta=request_meta)

    # parse_search_results remains a synchronous generator
    def parse_search_results(self, response):
        source_keyword = response.meta['source_keyword']
        current_keyword = response.meta['current_keyword']
        category_id = response.meta['category_id']
        current_page_num = response.meta['search_page_number']
        display_keyword_log = f"{current_keyword} (source: {source_keyword})" if source_keyword != current_keyword else current_keyword
        self.logger.info(f"Parsing search results for '{display_keyword_log}', Category: {category_id}, Page: {current_page_num} from {response.url}")

        product_links_xpaths = [
            "//li[contains(@class, 's-item') and not(contains(@class, 's-item--blank'))]//a[contains(@class, 's-item__link') and contains(@href, '/itm/')]/@href",
            "//ul[contains(@class, 'srp-results')]//li[contains(@class, 's-item')]//a[contains(@class, 's-item__link') and contains(@href, '/itm/')]/@href",
            "//div[contains(@class, 's-item__wrapper')]//a[contains(@class, 's-item__link') and contains(@href, '/itm/')]/@href"
        ]
        product_links = []
        for xpath_query in product_links_xpaths:
            product_links = response.xpath(xpath_query).getall()
            if product_links:
                break
        
        if not product_links:
            self.logger.warning(f"No product links found on page {current_page_num} for keyword '{display_keyword_log}'. Check selectors or page content.")
            if "0 results found" in response.text or "s-message__image" in response.text or "kein Ergebnis" in response.text.lower():
                self.logger.info(f"Detected '0 results' or similar message for '{display_keyword_log}' on page {current_page_num}.")
                return
        
        product_count_on_page = 0
        for relative_link in product_links:
            product_count_on_page += 1
            full_product_url = response.urljoin(relative_link)
            product_id_match = re.search(r'/itm/(\d+)', full_product_url)
            product_id_from_link = product_id_match.group(1) if product_id_match else None
            product_page_meta = {
                'source_keyword': source_keyword,
                'current_keyword': current_keyword,
                'category_id': category_id,
                'search_page_number': current_page_num,
                'search_url': response.url,
                'product_id_from_link': product_id_from_link
            }
            self.logger.debug(f"Requesting product page: {full_product_url} (Kwd: '{display_keyword_log}', Page: {current_page_num})")
            yield self._make_request(full_product_url, callback=self.parse_product_page, meta=product_page_meta)
        
        self.logger.info(f"Enqueued {product_count_on_page} product page requests from page {current_page_num} for '{display_keyword_log}'.")

        if current_page_num < self.max_pages:
            next_page_button_xpaths = [
                "//nav[contains(@class, 'pagination')]//a[contains(@class, 'pagination__next') or @rel='next']/@href",
                "//a[contains(@class, 'ebayui-pagination__control') and (@aria-label='Go to next search page' or @aria-label='Nächste Suchseite')]/@href"
            ]
            next_page_button = None
            for xpath_query in next_page_button_xpaths:
                next_page_button = response.xpath(xpath_query).get()
                if next_page_button:
                    break
            
            if next_page_button:
                next_page_url = response.urljoin(next_page_button)
                self.logger.info(f"Found next page link for '{display_keyword_log}': {next_page_url}")
                pagination_meta = response.meta.copy()
                pagination_meta['search_page_number'] = current_page_num + 1
                yield self._make_request(next_page_url, callback=self.parse_search_results, meta=pagination_meta)
            else:
                self.logger.info(f"No 'next page' link found for '{display_keyword_log}' on page {current_page_num}. Reached last page or end of results for this keyword.")
        else:
            self.logger.info(f"Reached max_search_pages_per_keyword ({self.max_pages}) for '{display_keyword_log}'. Stopping pagination.")

    # parse_product_page remains a synchronous generator
    def parse_product_page(self, response):
        item = ScrapperItem()
        product_id = response.meta.get('product_id_from_link')
        if not product_id:
            product_id_match = re.search(r'/itm/(\d+)', response.url)
            product_id = product_id_match.group(1) if product_id_match else None
        if not product_id:
            product_id_page_xpaths = [
                "//div[@id='descItemNumber']/text()",
                "//span[text()='eBay item number:']/following-sibling::span[contains(@class, 'ux-textspans--BOLD')]/text()",
                "//span[contains(text(),'eBay-Artikelnummer:')]/following-sibling::span/text()"
            ]
            for xpath_query in product_id_page_xpaths:
                product_id_page = response.xpath(xpath_query).get()
                if product_id_page:
                    product_id_page_cleaned = re.search(r'(\d+)', product_id_page)
                    if product_id_page_cleaned:
                        product_id = product_id_page_cleaned.group(1).strip()
                        break
        item['product_id'] = product_id
        item['link'] = response.url

        json_ld_data = None
        json_ld_scripts = response.xpath('//script[@type="application/ld+json"]')
        for script_tag in json_ld_scripts:
            script_content = script_tag.xpath('string(.)').get()
            if script_content:
                try:
                    parsed_json = json.loads(script_content)
                    current_schema = None
                    schemas_to_check = []
                    if isinstance(parsed_json, list):
                        schemas_to_check.extend(parsed_json)
                    elif isinstance(parsed_json, dict):
                        schemas_to_check.append(parsed_json)
                    
                    found_matching_product = False
                    for obj in schemas_to_check:
                        if isinstance(obj, dict) and obj.get('@type') == 'Product':
                            offer_url = obj.get('offers', {}).get('url', '') if isinstance(obj.get('offers'), dict) else ''
                            is_match = False
                            if product_id and product_id in offer_url:
                                is_match = True
                            if is_match:
                                json_ld_data = obj
                                found_matching_product = True
                                break 
                            elif not json_ld_data :
                                json_ld_data = obj
                    if found_matching_product:
                        break
                except json.JSONDecodeError:
                    self.logger.debug(f"Failed to parse a JSON-LD script on {response.url}")
                    continue
        
        if json_ld_data:
            self.logger.debug(f"Processing Product JSON-LD for {item.get('product_id','N/A')} from {response.url}")
            item['title'] = html.unescape(json_ld_data.get('name', '')).strip()
            offers_data = json_ld_data.get('offers', {})
            if isinstance(offers_data, list): offers_data = offers_data[0] if offers_data else {}
            if isinstance(offers_data, dict):
                price_val = offers_data.get('price')
                price_curr = offers_data.get('priceCurrency')
                if price_val is not None and price_curr: item['price'] = f"{price_curr} {price_val}"
                elif price_val is not None: item['price'] = str(price_val)
                condition_schema_url = offers_data.get('itemCondition', '')
                if condition_schema_url and isinstance(condition_schema_url, str):
                    condition_name = condition_schema_url.split('/')[-1]
                    item['condition'] = condition_name.replace('Condition', '').strip()
            brand_data = json_ld_data.get('brand', {})
            if isinstance(brand_data, dict): item['brand'] = brand_data.get('name', '').strip()
            elif isinstance(brand_data, str): item['brand'] = brand_data.strip()

            if self.download_images_config:
                images_json = json_ld_data.get('image', [])
                if isinstance(images_json, str): item['images'] = [images_json]
                elif isinstance(images_json, list): item['images'] = images_json
                else: item['images'] = []
            else: item['images'] = []
        else:
            self.logger.info(f"No matching Product JSON-LD found for {item.get('product_id','N/A')} on {response.url}. Using fallbacks.")
            if self.download_images_config:
                img_selectors = [
                    'div.ux-image-carousel-item img::attr(data-zoom-src)',
                    'img#icImg::attr(src)',
                    'div.vim.vi-evo-row-gap img::attr(src)'
                ]
                image_urls_page = []
                for selector in img_selectors:
                    image_urls_page = response.css(selector).getall()
                    if image_urls_page: break
                item['images'] = [url for url in image_urls_page if url and any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])]
            else: item['images'] = []

        if not item.get('title'):
            title_xpaths = [
                "//h1[contains(@class, 'x-item-title__mainTitle')]//span[contains(@class, 'ux-textspans--BOLD')]/text()",
                "//h1[@data-testid='x-item-title']//span[contains(@class,'ux-textspans--BOLD')]/text()",
                "//h1[contains(@class, 'item-title')]//text()[normalize-space()]",
                "//meta[@property='og:title']/@content"
            ]
            for xpath_query in title_xpaths:
                title_text = response.xpath(xpath_query).get()
                if title_text:
                    if "og:title" in xpath_query : title_text = title_text.split('| eBay')[0]
                    item['title'] = html.unescape(title_text.strip())
                    break
        if not item.get('price'):
            price_selectors = [
                "div.x-price-primary span.ux-textspans::text",
                "span[itemprop='price']/@content",
                "span[itemprop='price']::text"
            ]
            for selector in price_selectors:
                price_text = response.css(selector).get() if "::text" in selector or "@" not in selector else response.xpath(selector).get()
                if price_text:
                    item['price'] = price_text.strip()
                    price_currency_symbol = response.css('div.x-price-primary span.ux-textspans-format::text').get()
                    if price_currency_symbol and price_currency_symbol not in item['price']:
                         item['price'] = f"{price_currency_symbol.strip()} {item['price']}"
                    break
        
        condition_selectors = [
            "div.x-item-condition-text span.ux-textspans::text",
            "//div[@id='vi-itm-cond']/text()",
            "//div[contains(@class, 'x-sellercard__ Zustand')]//span[contains(@class, 'ux-textspans--BOLD')]/text()",
            "//span[@data-testid='ux-textual-display' and contains(preceding-sibling::span/text(), 'Condition')]/text()"
        ]
        for selector in condition_selectors:
            condition_text = response.css(selector).get() if "::text" in selector else response.xpath(selector).get()
            if condition_text:
                item['condition'] = html.unescape(condition_text.strip())
                break
        
        seller_notes_xpaths = [
            "//div[contains(@class, 'vi- συνοπτικά στοιχεία-παρουσίασης')]//span[contains(text(), 'Seller Notes') or contains(text(),'Verkäuferhinweise')]/following-sibling::span//text()",
            "//div[@data-testid='ux-labels-values__values-container']//span[contains(text(),'Seller Notes') or contains(text(),'Verkäuferhinweise')]/ancestor::div[contains(@class,'ux-labels-values__labels-values-row')]//div[contains(@class,'ux-labels-values__values')]//span[contains(@class,'ux-textspans')]/text()"
        ]
        full_seller_notes = ""
        for xpath_query in seller_notes_xpaths:
            seller_notes_texts = response.xpath(xpath_query).getall()
            if seller_notes_texts:
                full_seller_notes = "".join(html.unescape(text.strip()) for text in seller_notes_texts).strip()
                full_seller_notes = re.sub(r'Read moreabout the seller notes|Read Lessabout the seller notes|Mehr zum Thema|Weniger zum Thema', '', full_seller_notes, flags=re.IGNORECASE).strip()
                break
        
        if full_seller_notes: item['description'] = full_seller_notes
        elif not item.get('description'):
            meta_desc_xpaths = [
                "//meta[@name='description']/@content",
                "//meta[@property='og:description']/@content"
            ]
            for xpath_query in meta_desc_xpaths:
                desc_text = response.xpath(xpath_query).get()
                if desc_text:
                    item['description'] = html.unescape(desc_text.strip())
                    break
        
        brand_xpaths = [
            "//div[@data-testid='x-item-specifics']//div[.//span[contains(text(),'Brand') or contains(text(),'Marke')]]//div[contains(@class,'ux-labels-values__values')]//span/text()",
            "//div[contains(@class,'ux-labels-values__labels-values')]//span[contains(text(),'Brand') or contains(text(),'Marke')]/ancestor::div[contains(@class,'ux-labels-values__labels-values-row')]//div[contains(@class,'ux-labels-values__values')]//span[contains(@class,'ux-textspans')]/text()"
        ]
        for xpath_query in brand_xpaths:
            brand_text = response.xpath(xpath_query).get()
            if brand_text:
                item['brand'] = brand_text.strip()
                break
        
        if self.download_images_config and not item.get('images'):
            img_fallback_selectors = [
                'div.ux-image-carousel-item img::attr(data-zoom-src)',
                'div.ux-image-filmstrip-carousel-item img::attr(src)',
                'img#icImg::attr(src)'
            ]
            image_urls_page = []
            for selector in img_fallback_selectors:
                current_urls = response.css(selector).getall()
                if current_urls:
                    image_urls_page.extend(current_urls)
            
            valid_images = []
            for url in image_urls_page:
                if url and any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    valid_images.append(response.urljoin(url))
            item['images'] = list(dict.fromkeys(valid_images))

        location_xpaths = [
            "//div[contains(@class, 'd-shipping-minview')]//span[contains(text(), 'Located in:') or contains(text(),'Artikelstandort:')]/text()",
            "//div[@data-testid='delivery-location']//span[contains(@class,'ux-textspans--SECONDARY')]/text()",
            "//div[contains(@class,'ux-labels-values__labels-values')]//span[contains(text(),'Item location') or contains(text(),'Artikelstandort')]/ancestor::div[contains(@class,'ux-labels-values__labels-values-row')]//div[contains(@class,'ux-labels-values__values')]//span[contains(@class,'ux-textspans')]/text()"
        ]
        for xpath_query in location_xpaths:
            location_data = response.xpath(xpath_query).getall()
            if location_data:
                location_text = " ".join(loc.strip() for loc in location_data if loc.strip()).strip()
                location_text = location_text.replace("Located in:", "").replace("Artikelstandort:", "").strip()
                if location_text:
                    item['location'] = location_text
                    break
        
        seller_name_selectors = [
            'div.x-sellercard-atf__info__about-seller a span.ux-textspans--BOLD::text',
            "//span[@class='ux-textspans ux-textspans--BOLD' and (starts-with(@aria-label, 'Seller') or starts-with(@aria-label,'Verkäufer'))]/text()",
            "//div[contains(@class,'x-seller-component')]//a[contains(@href,'usr')]//span/text()"
        ]
        for selector in seller_name_selectors:
            name_text = response.css(selector).get() if "::text" in selector else response.xpath(selector).get()
            if name_text :
                item['seller_name'] = name_text.strip()
                break
        
        seller_rating_percent_css = response.css('div.x-sellercard-atf__data-item button span.ux-textspans--PSEUDOLINK:contains("positive")::text').get()
        seller_feedback_count_css = response.xpath("//div[contains(@class, 'x-sellercard-atf__info__about-seller')]//div[contains(@class, 'x-sellercard-atf__about-seller-item')]/span[contains(@class, 'ux-textspans--SECONDARY') and not(contains(text(),'feedback') or contains(text(),'Bewertungen'))]/text()").get()
        rating_str_parts = []
        if seller_rating_percent_css: rating_str_parts.append(seller_rating_percent_css.strip())
        if seller_feedback_count_css:
            count_cleaned = seller_feedback_count_css.strip()
            if count_cleaned and count_cleaned not in rating_str_parts : rating_str_parts.append(f"({count_cleaned})")
        
        if rating_str_parts: item['seller_rating'] = " ".join(rating_str_parts).replace(" positive feedback", "% positive feedback").replace(" positive Bewertungen", "% positive Bewertungen")
        else:
            seller_rating_store_percent = response.xpath("//div[contains(@class, 'seller-persona')]//li[contains(.,'feedback') or contains(.,'Bewertungen')]/span[contains(@class,'percent')]/text()").get()
            seller_rating_store_count = response.xpath("//div[contains(@class, 'seller-persona')]//li[contains(.,'feedback') or contains(.,'Bewertungen')]/a[contains(@class,'num')]/text()").get()
            store_parts = []
            if seller_rating_store_percent: store_parts.append(seller_rating_store_percent.strip() + (" positive feedback" if "%" in seller_rating_store_percent else ""))
            if seller_rating_store_count: store_parts.append(f"({seller_rating_store_count.strip()})")
            if store_parts: item['seller_rating'] = " ".join(store_parts).strip()
        
        item['source_keyword'] = response.meta.get('source_keyword')
        item['category_id'] = response.meta.get('category_id')
        item['search_page_number'] = response.meta.get('search_page_number')
        item['search_url'] = response.meta.get('search_url')

        if not item.get('title') or not item.get('price') or not item.get('product_id'):
            self.logger.warning(f"Could not extract all core details for URL {response.url}. ProductID: {item.get('product_id','N/A')}, Title: {item.get('title')}, Price: {item.get('price')}")
        yield item