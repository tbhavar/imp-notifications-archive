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
    Parses the extracted text to find the Notification Date and Subject using more robust patterns.
    """
    raw_date = None
    subject = "Subject_Not_Found"
    
    # --- 1. Robust Date Extraction ---
    # Try multiple common patterns for official documents:
    # Pattern 1: DD/MM/YYYY or DD-MM-YYYY near 'Dated' or 'No.'
    # It attempts to be flexible with separators (., /, -) and captures the date string.
    date_pattern_1 = re.compile(r'(?:Dated|Date|No\.\s*)\s*[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})', re.IGNORECASE)
    # Pattern 2: DDth day of MONTH, YEAR (e.g., 25th November, 2025)
    date_pattern_2 = re.compile(r'(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December),\s+(\d{4})', re.IGNORECASE)
    
    date_match = date_pattern_1.search(text)
    if date_match:
        raw_date = date_match.group(1).strip()
    else:
        date_match_2 = date_pattern_2.search(text)
        if date_match_2:
            # Reformat the descriptive date into DD/MM/YYYY for consistent parsing later
            day, month_name, year = date_match_2.groups()
            month_number = datetime.strptime(month_name, '%B').month
            raw_date = f"{int(day):02d}/{month_number:02d}/{year}"


    # --- 2. Robust Subject/Purpose Extraction ---
    
    # Get lines of text, skipping empty ones
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # 2a. Search for a line that is long and in ALL CAPS (GST subjects are often bolded/capitalized)
    for line in lines[:10]: # Check first 10 significant lines
        if len(line) > 30 and line == line.upper() and 'GOVERNMENT' not in line:
            subject = line
            break
            
    # 2b. Fallback: Take the text immediately following the main header
    if subject == "Subject_Not_Found":
        # Attempt to split the document after a known header phrase
        relevant_text = text.split("GOVERNMENT OF INDIA", 1)[-1] 
        
        # Take the first 3 relevant, non-header-like lines, and combine them for the subject
        fallback_lines = [
            line.strip() for line in relevant_text.split('\n') 
            if line.strip() and len(line) > 10 and 'Notification No.' not in line
        ][:3]
        
        if fallback_lines:
             subject = " ".join(fallback_lines)


    # --- 3. Clean and Format Filename Components ---
    
    # Clean up the subject for use in a filename (remove non-alphanumeric characters except space/hyphen)
    subject = re.sub(r'[^\w\s-]', '', subject).strip()
    # Replace spaces with underscores and truncate to a reasonable length (e.g., 80 characters)
    subject = re.sub(r'\s+', '_', subject)[:80].rstrip('_') 

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
        
        if raw_date and subject and subject != "Subject_Not_Found":
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
            print(f"Date found: {raw_date}, Subject found: {subject}")
            sys.exit(1)
    else:
        print("Script terminated due to PDF download/read error.")
        sys.exit(1)
