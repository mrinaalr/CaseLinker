"""
Ingestion Layer

Purpose: Handle diverse, messy data sources and normalize them into a consistent format for processing.

Design Ideas from Architecture:
- Keep it very simple: parse file (start with text-based), simple pre-processing
- Nothing too fancy - just take the info from the source to the data processing layer
- Data validation & sanitization
- Basic cleaning, pandas-based
- Modular so can upload website/pdf
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


def extract_pdf_text(pdf_path: str) -> str:
    """
    Extract all text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text as a string
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber is required for PDF extraction. Install with: pip install pdfplumber")
    
    text_content = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        
        return "\n".join(text_content)
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")


def ingest_file(file_path: str, file_type: Optional[str] = None) -> pd.DataFrame:
    """
    Ingest a file and return a DataFrame.
    Supports PDF files (extracts text) and other formats as needed.
    
    Args:
        file_path: Path to the file to ingest
        file_type: Optional file type hint (e.g., 'pdf', 'csv', 'txt')
                   If None, will be inferred from file extension
        
    Returns:
        DataFrame with ingested data
    """
    path = Path(file_path)
    
    if file_type is None:
        file_type = path.suffix.lower().lstrip('.')
    
    if file_type == 'pdf':
        text = extract_pdf_text(str(path))
        
        df = pd.DataFrame({
            'source_file': [path.name],
            'extracted_text': [text],
            'source': ['AZICAC'],
        })
        
        return df
    
    elif file_type == 'csv':
        return pd.read_csv(file_path)
    
    elif file_type == 'txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        df = pd.DataFrame({
            'source_file': [path.name],
            'extracted_text': [text],
            'source': ['unknown'],
        })
        
        return df
    
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def validate_data(df: pd.DataFrame) -> bool:
    """
    Basic data validation.
    
    Args:
        df: DataFrame to validate
        
    Returns:
        True if valid, False otherwise
    """
    if df.empty:
        return False
    
    return True

