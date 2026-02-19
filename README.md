# book_Price_Scraper
A Python web scraping project that collects book titles, prices, and availability from a public website and stores the data in a structured CSV file. Built using requests, BeautifulSoup, and pandas to practice data extraction and automation.

Book Price Scraper (Python)

## Overview:

This project is a simple web scraping script built with Python. It collects book titles, prices, and availability information from a public practice website and stores the data in a structured CSV file.

# The goal of this project was to practice:

Web scraping using requests and BeautifulSoup
Handling pagination
Extracting structured data from HTML
Saving data using pandas
Writing clean and organized automation scripts

## Technologies Used
Python 3
requests
BeautifulSoup4
pandas

## Features

Scrapes multiple pages automatically
Extracts:
Book Title
Price
Availability Status
Timestamp of scraping
Saves results to a CSV file
Includes basic error handling
Adds delay between requests to avoid overloading the server

## How to Run

Clone the repository:
-git clone https://github.com/yourusername/book-price-scraper.git
-cd book-price-scraper
-Install required packages:
-pip install -r requirements.txt
-Run the script: python main.py
-After running, a file named:
 book_data.csv will be generated containing the scraped data.


## Sample Output Columns
-Book Title
-Price
-Availability Status
-Scraped At


## What I Learned:

Through this project, I improved my understanding of:
-Inspecting website HTML structure
-Selecting elements using class names
-Looping through paginated content
-Structuring scraped data cleanly
-Building small automation tools

This project is part of my learning journey in Python and data automation.

## Ethical Note:
This project uses a publicly available practice website designed for web scraping exercises.
The script includes request delays to avoid sending excessive traffic.
