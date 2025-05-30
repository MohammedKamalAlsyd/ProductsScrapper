**Scrapper Project**

A modular, configurable web‑scraping framework built with **Scrapy**, **Selenium**, and **BeautifulSoup** to extract product and seller information from eBay (US). This project automates keyword‑based searches, parses autocomplete suggestions, navigates search result pages, and retrieves detailed item data along with associated images.

---

## 🔍 Features

* **Config‑Driven**: External `scraper_config.json` to define search keywords, site settings, proxy options, and more.
* **Selenium Integration**: Uses Firefox (via GeckoDriver) to interact with dynamic autocomplete suggestions.
* **Proxy Support**: Optional Tor SOCKS proxy configuration for enhanced anonymity.
* **Robust Parsing**: Combines Scrapy selectors and BeautifulSoup for reliable extraction of titles, prices, descriptions, images, and seller details.
* **Pagination Handling**: Automatically follows "Next page" links to traverse multiple result pages.
* **ImagesPipeline**: Leverages Scrapy's images pipeline to download and store product images locally.
* **Extensible**: Easily add new sites or parser types in `scraper_config.json` and spider methods.

---

## ⚙️ Project Structure

```
Scrapper/                   # Root package
├── scrapy.cfg               # Scrapy configuration
├── Scrapper/                # Spider and configuration directory
│   ├── spiders/             # Spider implementations
│   │   └── main.py          # MainSpider: core scraping logic
│   ├── items.py             # Definition of ScrapperItem
│   ├── middlewares.py       # (Optional) custom spider/downloader middlewares
│   ├── pipelines.py         # Item processing pipelines
│   ├── settings.py          # Scrapy project settings
│   └── scraper_config.json  # External scraper configuration
└── downloaded_images/       # Directory for downloaded product images
```

---

## 🛠 Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/Scrapper.git
   cd Scrapper
   ```

2. **Create a virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate   # Windows
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Ensure Firefox and Tor (optional) are installed**

   * [Firefox Download](https://www.mozilla.org/firefox)
   * [Tor Browser Bundle](https://www.torproject.org)

---

## 📝 Configuration

All behavior is controlled via `Scrapper/Scrapper/scraper_config.json`:

* **base\_keywords**: List of search terms to query on the site.
* **headless**: Run Firefox in headless mode (`true`/`false`).
* **use\_tor**: Enable Tor proxy (`true`/`false`).
* **tor\_socks\_port**: Port on which Tor SOCKS proxy listens.
* **selenium\_wait\_timeout**: Seconds to wait for page elements.
* **sites**: Dictionary of site configurations:

  * `base_url`
  * CSS selectors for search bar and autocomplete container
  * Parser type (e.g., `ebay_list`)
  * URL templates for search with/without category
  * Category filters and flags

---

## 🚀 Usage

* **Run the Spider**

  ```bash
  scrapy crawl main -o output.json --logfile=scrapy_log.txt
  ```

  * Outputs scraped items to `output.json` in JSON format.
  * Downloads images to the `downloaded_images` directory.

* **Customizing**

  * Add or modify keywords in `scraper_config.json`.
  * Extend `MainSpider` or add new spiders under `spiders/` for additional sites.
  * Adjust pipelines in `pipelines.py` for data cleaning or database storage.

---

## 📦 Extending the Project

1. **Add a New Site**:

   * Update `scraper_config.json` with new site entry.
   * Implement parsing logic in `MainSpider` or create a new spider class.
2. **New Parser Types**:

   * Add methods to `_parse_autocomplete_suggestions` and corresponding helper parsers.
3. **Data Storage**:

   * Integrate pipelines for databases (e.g., MongoDB, PostgreSQL) in `pipelines.py`.
4. **Middleware Enhancements**:

   * Implement request throttling, custom headers, or proxy rotation in `middlewares.py`.

---

## 📝 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

Pull requests, issues, and feature requests are welcome! Please follow the [contribution guidelines](CONTRIBUTING.md).

---

*Happy scraping!*
