BOT_NAME = "Scrapper"

SPIDER_MODULES = ["Scrapper.spiders"]
NEWSPIDER_MODULE = "Scrapper.spiders"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False # Be respectful of site terms

# Configure item pipelines
ITEM_PIPELINES = {
   'scrapy.pipelines.images.ImagesPipeline': 1,
}

# Configure ImagesPipeline
IMAGES_STORE = 'downloaded_images' # Directory where images will be stored


# Enable and configure the AutoThrottle extension (disabled by default)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.5

DOWNLOAD_DELAY = 2 # Start with a reasonable delay

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"