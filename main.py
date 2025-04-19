import scrapy
from scrapy.crawler import CrawlerProcess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import time
from urllib.parse import urljoin, urlparse

class WestsideProductSpider(scrapy.Spider):
    name = 'westside_product_crawler'
    
    def __init__(self, start_urls=None, domain=None, *args, **kwargs):
        super(WestsideProductSpider, self).__init__(*args, **kwargs)
        self.start_urls = start_urls if start_urls else ['https://www.westside.com/']
        self.allowed_domains = [domain] if domain else ['westside.com']
        
        # Configure Selenium
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(service=webdriver.ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        # Set to store visited URLs to avoid duplicates
        self.visited_urls = set()
        
    def parse(self, response):
        # Skip if we've already visited this URL
        if response.url in self.visited_urls:
            return
        self.visited_urls.add(response.url)
        
        # First, find all collection links in the navigation
        collection_links = response.css('a[href*="/collections/"]::attr(href)').getall()
        
        # Process collection links
        for link in collection_links:
            absolute_url = urljoin(response.url, link)
            yield scrapy.Request(absolute_url, callback=self.parse_collection)
        
        # Also follow other links to crawl the site (but limit depth)
        if len(self.visited_urls) < 50:  # Safety limit
            all_links = response.css('a::attr(href)').getall()
            for link in all_links:
                absolute_url = urljoin(response.url, link)
                if self.should_follow(absolute_url):
                    yield scrapy.Request(absolute_url, callback=self.parse)
    
    def parse_collection(self, response):
        """Parse collection pages to find product links"""
        # Use Selenium to handle dynamic content on collection pages
        self.driver.get(response.url)
        
        # Scroll to bottom to trigger lazy loading
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scroll_attempts = 5
        
        while scroll_attempts < max_scroll_attempts:
            # Scroll down to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # Wait to load page
            time.sleep(2)
            
            # Calculate new scroll height and compare with last scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        
        # Now extract product links with the specific class
        try:
            product_elements = self.driver.find_elements(By.CSS_SELECTOR, 'a.wizzy-result-product-item')
            for element in product_elements:
                product_url = element.get_attribute('href')
                if product_url and '/products/' in product_url:
                    yield {
                        'url': product_url,
                        'collection_url': response.url,
                        'title': element.get_attribute('title') or element.text.strip()
                    }
        except Exception as e:
            self.logger.error(f"Error extracting product links: {e}")
    
    def should_follow(self, url):
        """Determine if we should follow this link"""
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        if not any(domain in parsed.netloc for domain in self.allowed_domains):
            return False
        if url in self.visited_urls:
            return False
        # Skip common non-content URLs
        skip_keywords = ['account', 'login', 'signin', 'cart', 'checkout', 'wishlist']
        if any(kw in parsed.path.lower() for kw in skip_keywords):
            return False
        return True
    
    def closed(self, reason):
        self.driver.quit()

# Example usage
if __name__ == "__main__":
    process = CrawlerProcess(settings={
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'FEEDS': {
            'westside_products.json': {
                'format': 'json',
                'encoding': 'utf8',
                'overwrite': True
            }
        },
        'LOG_LEVEL': 'INFO',
        'ROBOTSTXT_OBEY': False,
        'CONCURRENT_REQUESTS': 4,
        'DOWNLOAD_DELAY': 2,
        'DEPTH_LIMIT': 3  # Limit crawling depth
    })
    
    # Start the crawler with your target website
    process.crawl(WestsideProductSpider)
    process.start()