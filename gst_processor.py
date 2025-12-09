import sys
import os
import re
import requests
from io import BytesIO
from pypdf import PdfReader
from datetime import datetime

# --- Configuration ---
PDF_OUTPUT_DIR = "notifications"

def download_and_read_pdf(url):
    """Downloads PDF content from a URL and extracts text from the first page."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
        
        # Read content into a BytesIO object (in-memory file)
        pdf_file = BytesIO(response.content)
        
        # Initialize PdfReader and extract text from the first page
        reader = PdfReader(pdf_file)
        if not reader.pages:
            print("Error: PDF has no pages.")
            return None
            
        first_page_text = reader.pages[0].extract_text()
        return first_page_text

    except requests.exceptions.RequestException as e:
        print(f"Error downloading the PDF: {e}")
        return None
    except Exception as e:
        print(f"Error reading the PDF content: {e}")
        return None

def parse_gst_details(text):
    """
    Parses the extracted text to find the Notification Date and Subject.
    NOTE: Regex is highly dependent on the exact format.
    GST Notifications usually have a date and a brief subject/purpose.
    """
    # 1. Date Extraction: Looks for DD/MM/YYYY or DD-MM-YYYY near keywords like 'Dated' or 'Notification No.'
    # It attempts to be flexible with separators (., /, -) and captures the date string.
    date_match = re.search(r'(?:Dated|Date|No\.\s*)\s*[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})', text)
    raw_date = date_match.group(1).strip() if date_match else None

    # 2. Subject Extraction: Looks for a line or a large paragraph typically near the top.
    # We will simply take a section of the text for the subject, as official PDFs vary.
    # This example takes the first non-empty line of text *after* a generic header.
    
    # We'll split the text and look for the first non-header-like line to use as the subject
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Simple logic: skip lines that are too short (like page numbers) or generic headers
    subject = next((line for line in lines if len(line) > 20 and 'Notification No.' not in line), "Generic_Subject")
    
    # Clean up the subject for use in a filename (remove special characters)
    subject = re.sub(r'[^\w\s-]', '', subject).strip()
    subject = re.sub(r'\s+', '_', subject)[:50] # Replace spaces with underscores and truncate

    return raw_date, subject

def create_and_save_pdf(url, new_filename):
    """Downloads the PDF and saves it with the new filename."""
    try:
        # Re-download the full content using the URL provided by GitHub Actions
        response = requests.get(url)
        response.raise_for_status() 
        
        # Ensure the output directory exists
        os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)
        
        file_path = os.path.join(PDF_OUTPUT_DIR, new_filename)
        
        # Write the content to the new file path
        with open(file_path, 'wb') as f:
            f.write(response.content)
            
        print(f"::notice file={file_path}::Successfully saved as {new_filename}")
        print(f"File saved successfully as {file_path}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error saving PDF (second download): {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during file saving: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python gst_processor.py <PDF_URL>")
        sys.exit(1)

    pdf_url = sys.argv[1]
    
    print(f"Processing URL: {pdf_url}")
    
    pdf_text = download_and_read_pdf(pdf_url)

    if pdf_text:
        raw_date, subject = parse_gst_details(pdf_text)
        
        if raw_date and subject:
            # Attempt to parse the date into YYYY-MM-DD format for proper sorting
            try:
                # Assuming the most common Indian date format (DD/MM/YYYY)
                date_obj = datetime.strptime(raw_date.replace('-', '/').replace('.', '/'), '%d/%m/%Y')
                date_prefix = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                print(f"Warning: Could not parse date '{raw_date}'. Using current date.")
                date_prefix = datetime.now().strftime('%Y-%m-%d')
                
            new_filename = f"{date_prefix}_{subject}.pdf"
            print(f"Constructed filename: {new_filename}")
            
            # Use the original URL to re-download and save the file
            create_and_save_pdf(pdf_url, new_filename)
        else:
            print("Error: Could not extract both date and subject from PDF.")
            sys.exit(1)
    else:
        print("Script terminated due to PDF download/read error.")
        sys.exit(1)
