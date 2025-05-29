import cv2
import os
import numpy as np

# Path to Google credentials JSON (set accordingly)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Path\To\Your\Google\Credentials.json"


def analyze_chart_color_distribution(image_path):
    """
    Analyze the distribution of colors in the chart, merging related categories for consensus.
    Args:
        image_path (str): Path to the chart image.
    Returns:
        dict: Percentage distribution of Buy, Hold, and Sell categories.
    """
    # Define HSV color ranges for merged categories
    color_ranges = {
        "Buy": ((40, 50, 50), (70, 255, 255)),          # Combines Strong Buy and Buy (green shades)
        "Hold": ((20, 100, 100), (30, 255, 255)),       # Yellow
        "Sell": ((0, 100, 100), (20, 255, 255))         # Combines Underperform and Sell (red/orange)
    }

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"OpenCV could not open image: {image_path}")

    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Initialize a dictionary to store the pixel counts for each category
    color_distribution = {category: 0 for category in color_ranges}

    # Calculate the total number of pixels in the relevant area
    total_pixels = hsv_image.shape[0] * hsv_image.shape[1]

    # Count pixels for each color range
    for category, (lower, upper) in color_ranges.items():
        lower_bound = np.array(lower, dtype="uint8")
        upper_bound = np.array(upper, dtype="uint8")

        mask = cv2.inRange(hsv_image, lower_bound, upper_bound)
        color_distribution[category] = cv2.countNonZero(mask)

    # Convert pixel counts to percentages
    color_percentages = {category: (count / total_pixels) * 100 for category, count in color_distribution.items()}

    return color_percentages


def calculate_analyst_recs_score(color_percentages):
    """
    Calculate proportional percentages and return the Buy percentage as the score.
    Args:
        color_percentages (dict): Dictionary containing raw percentages for 'Buy', 'Hold', and 'Sell'.
    Returns:
        dict: A dictionary with proportional percentages and the Buy score.
    """
    total = sum(color_percentages.values())

    if total == 0:
        return {"Proportions": {"Buy": 0, "Hold": 0, "Sell": 0}, "Buy Score": 0}

    proportions = {key: (value / total) * 100 for key, value in color_percentages.items()}
    buy_score = proportions["Buy"]

    return {"Proportions": proportions, "Buy Score": buy_score}


# Example of usage
if __name__ == "__main__":
    image_path = "path_to_your_snapshot.png"

    percentages = analyze_chart_color_distribution(image_path)
    scores = calculate_analyst_recs_score(percentages)

    print("Color Percentages:", percentages)
    print("Analyst Recommendations Buy Score:", scores["Buy Score"])
