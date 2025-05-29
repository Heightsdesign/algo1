from bs4 import BeautifulSoup


def extract_price_targets(driver):
    """
    Extract analyst price targets from the loaded Yahoo Finance analysis page.

    Args:
        driver (selenium.webdriver): An active Selenium WebDriver instance with the page loaded.

    Returns:
        dict: A dictionary containing extracted price targets (Low, Average, Current, High).
    """
    # Use BeautifulSoup to parse the loaded page
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    price_section = soup.find('section', {'data-testid': 'analyst-price-target-card'})
    prices = {}

    if price_section:
        spans = price_section.find_all('span', {'class': 'price'})
        labels = ["Low", "Average", "Current", "High"]

        for label, span in zip(labels, spans):
            try:
                prices[label] = float(span.text.strip().replace(",", ""))
            except ValueError:
                prices[label] = None

    return prices
