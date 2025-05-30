# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from scrapy.pipelines.images import ImagesPipeline
import os
import re
from urllib.parse import urlparse

class ScrapperPipeline:
    def process_item(self, item, spider):
        # Example: clean up some fields or validate
        adapter = ItemAdapter(item)
        if adapter.get('title'):
            adapter['title'] = adapter['title'].strip()
        # Add more processing if needed
        return item

class CustomEbayImagesPipeline(ImagesPipeline):
    def file_path(self, request, response=None, info=None, *, item=None):
        """
        Generates the file path for downloaded images.
        Images will be stored in: IMAGES_STORE/product_id/product_id_image_INDEX.ext
        """
        adapter = ItemAdapter(item)
        product_id = adapter.get('product_id')
        if not product_id:
            product_id = 'unknown_product'
        
        # Sanitize product_id for directory name
        product_id_sanitized = re.sub(r'[^\w\-_\.]', '_', str(product_id))

        image_url = request.url
        try:
            # Find the original index of the image URL in the item's image list
            image_index = adapter.get(self.IMAGES_URLS_FIELD, []).index(image_url)
        except ValueError:
            # Fallback if URL isn't found (e.g. due to redirects, though ImagesPipeline often uses original URL)
            # Or if item['images'] was modified.
            # A simple hash for the image name if index is not found.
            import hashlib
            image_index = hashlib.sha1(request.url.encode()).hexdigest()[:6]

        # Extract image extension
        parsed_url = urlparse(image_url)
        original_filename = os.path.basename(parsed_url.path)
        _, ext = os.path.splitext(original_filename)
        
        if not ext or len(ext) > 5: # Basic check for valid extension from URL
            image_ext_from_content_type = ''
            if response:
                content_type = response.headers.get('Content-Type', b'').decode('utf-8').lower()
                if 'jpeg' in content_type or 'jpg' in content_type: image_ext_from_content_type = '.jpg'
                elif 'png' in content_type: image_ext_from_content_type = '.png'
                elif 'webp' in content_type: image_ext_from_content_type = '.webp'
                elif 'gif' in content_type: image_ext_from_content_type = '.gif'
            ext = image_ext_from_content_type if image_ext_from_content_type else '.jpg' # Default extension

        return f'{product_id_sanitized}/{product_id_sanitized}_image_{image_index}{ext}'

    def item_completed(self, results, item, info):
        """
        Called when all image requests for an item have completed.
        results is a list of 2-tuples (ok, result_dict), where ok is a boolean indicating success or failure,
        """
        image_paths = [x['path'] for ok, x in results if ok]
        if not image_paths and ItemAdapter(item).get(self.IMAGES_URLS_FIELD) and info.spider.settings.getbool('DOWNLOAD_IMAGES'):
            info.spider.logger.warning(f"No images downloaded for item {ItemAdapter(item).get('product_id')} (PID: {ItemAdapter(item).get('product_id')}) although image URLs were present: {ItemAdapter(item).get(self.IMAGES_URLS_FIELD)}")
        
        adapter = ItemAdapter(item)
        adapter[self.IMAGES_RESULT_FIELD] = image_paths # e.g., item['image_paths']
        return item