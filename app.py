import streamlit as st
from PIL import Image
from pathlib import Path
import io
from google.cloud import vision
from googletrans import Translator
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfMerger
import json

import os
from dotenv import load_dotenv

load_dotenv()

# Initialize
translator = Translator()
vision_client = vision.ImageAnnotatorClient()

# Directories
PHOTOS_DIR = Path("photos")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

def ocr_image(image_path):
    """Extract text from image using Google Cloud Vision"""
    with io.open(image_path, 'rb') as image_file:
        content = image_file.read()
    
    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    
    if texts:
        return texts[0].description
    return ""

def process_all_images(image_files, progress_bar):
    """OCR all images and return extracted text"""
    all_text = []
    
    for idx, img_file in enumerate(image_files):
        progress_bar.progress((idx + 1) / len(image_files))
        text = ocr_image(img_file)
        all_text.append({
            'page': idx + 1,
            'filename': img_file.name,
            'text': text
        })
    
    return all_text

def combine_text_with_continuity(pages_data):
    """Combine text from all pages, handling sentence breaks"""
    combined = ""
    
    for page in pages_data:
        text = page['text'].strip()
        
        # If previous text doesn't end with punctuation, add space
        if combined and not combined[-1] in '.!?。':
            combined += " "
        
        combined += text
    
    return combined

def translate_text(text, progress_callback=None):
    """Translate Korean text to English in chunks"""
    # Split into chunks (Google Translate has limits)
    chunk_size = 5000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    translated_chunks = []
    for idx, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback((idx + 1) / len(chunks))
        
        result = translator.translate(chunk, src='ko', dest='en')
        translated_chunks.append(result.text)
    
    return " ".join(translated_chunks)

def create_original_pdf(image_files, output_path):
    """Create PDF from original images"""
    merger = PdfMerger()
    temp_pdfs = []
    
    for img_file in image_files:
        img = Image.open(img_file)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Create temporary PDF for this image
        temp_pdf = OUTPUT_DIR / f"temp_{img_file.stem}.pdf"
        img.save(temp_pdf, 'PDF', resolution=100.0)
        temp_pdfs.append(temp_pdf)
        merger.append(str(temp_pdf))
    
    merger.write(str(output_path))
    merger.close()
    
    # Clean up temp files
    for temp_pdf in temp_pdfs:
        temp_pdf.unlink()

def create_translated_pdf(translated_text, output_path):
    """Create PDF with translated text"""
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Split into paragraphs
    paragraphs = translated_text.split('\n\n')
    
    for para in paragraphs:
        if para.strip():
            p = Paragraph(para.strip(), styles['Normal'])
            story.append(p)
            story.append(Spacer(1, 0.2*inch))
    
    doc.build(story)

def main():
    st.title("할아버지 Book Translation")
    st.write("Translate grandfather's Korean book to English")
    
    # Step 1: Load images
    st.header("Step 1: Load Images")
    
    image_files = sorted(list(PHOTOS_DIR.glob("*.jpg")) + 
                        list(PHOTOS_DIR.glob("*.jpeg")) + 
                        list(PHOTOS_DIR.glob("*.png")) +
                        list(PHOTOS_DIR.glob("*.JPG")) +
                        list(PHOTOS_DIR.glob("*.JPEG")) +
                        list(PHOTOS_DIR.glob("*.PNG")))
    
    if not image_files:
        st.warning(f"No images found in {PHOTOS_DIR}. Please add your photos there.")
        return
    
    st.success(f"Found {len(image_files)} images")
    
    # Show first few images as preview
    st.subheader("Preview (first 3 pages)")
    cols = st.columns(3)
    for idx, img_file in enumerate(image_files[:3]):
        with cols[idx]:
            img = Image.open(img_file)
            st.image(img, caption=f"Page {idx+1}", use_container_width=True)
    
    # Step 2: Create original PDF
    st.header("Step 2: Create Original PDF")
    if st.button("Generate Original PDF"):
        with st.spinner("Creating PDF from images..."):
            original_pdf_path = OUTPUT_DIR / "original_book.pdf"
            create_original_pdf(image_files, original_pdf_path)
            st.success(f"Original PDF created: {original_pdf_path}")
    
    # Step 3: OCR
    st.header("Step 3: Extract Text (OCR)")
    if st.button("Run OCR on All Pages"):
        progress_bar = st.progress(0)
        
        with st.spinner("Running OCR..."):
            ocr_results = process_all_images(image_files, progress_bar)
            
            # Save OCR results
            ocr_output = OUTPUT_DIR / "ocr_results.json"
            with open(ocr_output, 'w', encoding='utf-8') as f:
                json.dump(ocr_results, f, ensure_ascii=False, indent=2)
            
            st.success(f"OCR complete! Results saved to {ocr_output}")
            
            # Show sample
            st.subheader("Sample (Page 1)")
            st.text_area("Extracted Korean text:", ocr_results[0]['text'], height=200)
    
    # Step 4: Translate
    st.header("Step 4: Translate to English")
    
    ocr_file = OUTPUT_DIR / "ocr_results.json"
    if ocr_file.exists():
        if st.button("Translate All Text"):
            # Load OCR results
            with open(ocr_file, 'r', encoding='utf-8') as f:
                ocr_results = json.load(f)
            
            # Combine text
            combined_text = combine_text_with_continuity(ocr_results)
            
            # Translate
            progress_bar = st.progress(0)
            with st.spinner("Translating..."):
                translated = translate_text(combined_text, 
                                          lambda p: progress_bar.progress(p))
            
            # Save translation
            translation_output = OUTPUT_DIR / "translation.txt"
            with open(translation_output, 'w', encoding='utf-8') as f:
                f.write(translated)
            
            st.success(f"Translation complete! Saved to {translation_output}")
            
            # Show sample
            st.subheader("Sample translation (first 500 chars)")
            st.text_area("English translation:", translated[:500], height=200)
    else:
        st.info("Run OCR first before translating")
    
    # Step 5: Create final PDF
    st.header("Step 5: Create Translated PDF")
    
    translation_file = OUTPUT_DIR / "translation.txt"
    if translation_file.exists():
        if st.button("Generate Translated PDF"):
            with open(translation_file, 'r', encoding='utf-8') as f:
                translated_text = f.read()
            
            with st.spinner("Creating translated PDF..."):
                final_pdf = OUTPUT_DIR / "translated_book.pdf"
                create_translated_pdf(translated_text, final_pdf)
                st.success(f"✅ Final PDF created: {final_pdf}")
                st.balloons()
    else:
        st.info("Run translation first before creating PDF")

if __name__ == "__main__":
    main()


