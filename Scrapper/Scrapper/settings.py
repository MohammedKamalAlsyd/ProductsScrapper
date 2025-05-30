# Scrapy settings for Scrapper project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "Scrapper"

SPIDER_MODULES = ["Scrapper.spiders"]
NEWSPIDER_MODULE = "Scrapper.spiders"

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "Scrapper (+http://www.yourdomain.com)" # Set in spider custom_settings

# Obey robots.txt rules
ROBOTSTXT_OBEY = False # eBay's robots.txt can be restrictive for scraping search

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 1 # Start with 1 or 2 to be polite
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 8 # Default 8
#CONCURRENT_REQUESTS_PER_IP = 0 # If domain is IP

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#   "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "Scrapper.middlewares.ScrapperSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "Scrapper.middlewares.ScrapperDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
   "Scrapper.pipelines.ScrapperPipeline": 300, # Keep your general pipeline
   "Scrapper.pipelines.CustomEbayImagesPipeline": 1, # Add image pipeline, runs first
}

# Image Pipeline Settings
IMAGES_STORE = 'downloaded_ebay_images' # Directory where images will be stored
IMAGES_URLS_FIELD = 'images'         # Item field containing image URLs
IMAGES_RESULT_FIELD = 'image_paths'  # Item field to store download results (paths)

# Custom setting for the spider to enable/disable image downloads
# Can be overridden by spider argument: -a DOWNLOAD_IMAGES=True or -a DOWNLOAD_IMAGES=False
# DOWNLOAD_IMAGES = True

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"