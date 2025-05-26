from scrapy.item import Item, Field

class ScrapperItem(Item):
    # Product information:
    title = Field()
    price = Field()
    link = Field()
    description = Field()
    image_urls = Field() # For ImagesPipeline: list of image URLs
    images = Field()     # For ImagesPipeline: result (list of dicts with path, url, checksum)
    category = Field()   # Category derived from breadcrumbs or search context
    condition = Field()
    brand = Field()
    location = Field()   # Item location
    # Refurbished = Field() # Can be part of condition or a specific tag
    free_returns = Field()
    
    # Seller information
    seller_name = Field()
    seller_rating = Field() # e.g. "99.5% Positive feedback"
    seller_feedback_count = Field() # e.g., "(12345)"
    seller_link = Field()
    seller_verified = Field() # Less common directly, might be inferred
    top_rated_seller = Field() # Boolean or text

    # Meta Search Info
    derived_from_keyword = Field()
    category_context_from_search = Field() # Category used in search URL