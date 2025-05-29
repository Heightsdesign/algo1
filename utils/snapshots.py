# snapshots.py

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from PIL import Image
from datetime import datetime
import time
import os
import io

def take_snapshot(ticker, driver, output_path="snapshots"):
    """
    Automate the snapshot of the 'Analyst Recommendations' section.
    Args:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        driver (webdriver): Selenium WebDriver instance.
        output_path (str): Directory where the snapshot will be saved.
    """
    # Ensure the output directory exists
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    url = f"https://finance.yahoo.com/quote/{ticker}/analysis"
    driver.get(url)
    time.sleep(3)  # Allow the page to load

    # Accept cookies if prompted
    try:
        cookie_button = driver.find_element(By.NAME, "agree")
        cookie_button.click()
        time.sleep(2)
    except Exception as e:
        print("No cookie consent required.")

    # Locate the 'Analyst Recommendations' section
    recommendations_section = driver.find_element(By.XPATH, "//section[@data-testid='analyst-recommendations-card']")

    # Get location and size of the recommendations section
    location = recommendations_section.location
    size = recommendations_section.size

    # Take a full-page screenshot in memory
    screenshot_data = driver.get_screenshot_as_png()

    # Open the screenshot with PIL
    with Image.open(io.BytesIO(screenshot_data)) as img:
        # Crop the recommendations section
        left = location["x"]
        top = location["y"]
        right = left + size["width"]
        bottom = top + size["height"]
        cropped_img = img.crop((left, top, right, bottom))

        # Add year and month to the file name
        current_date = datetime.now().strftime("%Y_%m")
        snapshot_filename = os.path.join(output_path, f"{ticker}_recommendations_{current_date}.png")
        cropped_img.save(snapshot_filename)

    print(f"Snapshot saved for {ticker} in {snapshot_filename}.")