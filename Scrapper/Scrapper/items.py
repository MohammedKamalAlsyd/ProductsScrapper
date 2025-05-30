from scrapy.item import Item, Field

class ScrapperItem(Item):
    # Product information:
    product_id = Field() # eBay Item Number
    title = Field()      # To be populated later from product page
    price = Field()      # To be populated later
    link = Field()       # Will be populated from search results initially, then product page URL
    description = Field()  # To be populated later
    images = Field()     # List of image URLs (used by ImagesPipeline if DOWNLOAD_IMAGES is true)
    image_paths = Field()# List of local paths for downloaded images (populated by ImagesPipeline)
    category_id = Field()  # Category ID used for the search
    condition = Field()    # To be populated later
    brand = Field()        # To be populated later
    location = Field()     # To be populated later
    
    # Seller information
    seller_name = Field()    # To be populated later
    seller_rating = Field()  # To be populated later

    # Meta information for tracking
    source_keyword = Field() # The keyword (original or suggested) that led to this item
    search_page_number = Field() # The page number of search results where this was found
    search_url = Field() # The URL of the search query