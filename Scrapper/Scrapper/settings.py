BOT_NAME = "Scrapper"

SPIDER_MODULES = ["Scrapper.spiders"]
NEWSPIDER_MODULE = "Scrapper.spiders"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False # Be respectful of site terms

# Configure item pipelines
ITEM_PIPELINES = {
  'scrapy.pipelines.images.ImagesPipeline': 1,
  # 'Scrapper.pipelines.ScrapperPipeline': 300, # If you add custom processing
}

# Configure ImagesPipeline
IMAGES_STORE = 'downloaded_images' # Directory where images will be stored
# Optional: Store images in subdirectories named after a field (e.g., item link or a sanitized title)
IMAGES_URLS_FIELD = 'image_urls'
IMAGES_RESULT_FIELD = 'images'
# IMAGES_EXPIRES = 90 # Optional: days until images are considered expired

# Enable and configure the AutoThrottle extension (disabled by default)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5  # Start with a higher delay
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.2 # Be even more gentle if facing bot detection
# DOWNLOAD_DELAY will also be influenced by AutoThrottle
DOWNLOAD_DELAY = 5 # Increase base delay

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

# FOR INCREMENTAL OUTPUT TO JSON/CSV/XML:
FEED_EXPORT_BATCH_ITEM_COUNT = 1 # Write after every item (good for debugging)

# Reduce Scrapy's own concurrency further when dealing with sensitive sites
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
CONCURRENT_REQUESTS_PER_IP = 1 # If not using rotating IPs

# Optional: Configure a rotating User-Agent middleware if you decide to implement one
# DOWNLOADER_MIDDLEWARES = {
#    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None, # Disable default
#    'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 400, # Example
# }