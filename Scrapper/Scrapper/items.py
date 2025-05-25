from scrapy.item import Item, Field

class ScrapperItem(Item):
    # Product information:
    title = Field()
    price = Field()
    link = Field()
    description = Field()
    images = Field()
    category = Field()
    condition = Field()
    brand = Field()
    location = Field()
    
    # Seller information
    seller_name = Field()
    seller_rating = Field()