#!/usr/bin/env python3
import argparse
import json
import fitz  
import os
import sys

def chunk_pdf_to_jsonl(input_pdf, output_jsonl):

    if not os.path.exists(input_pdf):
        print(f"Error: Input file '{input_pdf}' does not exist")
        sys.exit(1)
    
    try:
        # Opening PDF doc
        doc = fitz.open(input_pdf)
        total_pages = len(doc)
        
        #To check the right doc
        print(f"Found {total_pages} pages in document")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_jsonl)), exist_ok=True)
        
        # Process each page and write to JSONL
        with open(output_jsonl, 'w', encoding='utf-8') as outfile:
            chunk_count = 0
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                text = page.get_text().strip()
                
                """
                   # To split text based on paragraphs 
                    raw_text = page.get_text().strip()
                    paragraphs = [p.strip() for p in raw_text.split("\n\n") if len(p.strip()) > 40]
                    lines = raw_text.split("\n")
                    possible_headers = [
                        line.strip()
                        for line in lines
                        if line.isupper() and 5 < len(line) < 120
                    ]
                    current_header = possible_headers[0] if possible_headers else None
                    #if this is implied we must change Metadata "section_title": current_header,
                    for para_idx, paragraph in enumerate(paragraphs):
                    chunk_data = {
                        "chunk_id": f"page_{page_num+1}_para_{para_idx+1}",
                        "page_number": page_num + 1,
                        "paragraph_number": para_idx + 1,
                        "total_pages": total_pages,
                        "text": paragraph,
                        "source_file": os.path.basename(input_pdf),
                    }


                """


                # Only create chunk if page has text and avoid empty space saving 
                if text:
                    chunk_data = {
                        "chunk_id": f"page_{page_num + 1}",
                        "page_number": page_num + 1,
                        "total_pages": total_pages,
                        "text": text,
                        "source_file": os.path.basename(input_pdf)
                    }
                    
                    # Write as JSON line and support non english
                    json_line = json.dumps(chunk_data, ensure_ascii=False)
                    outfile.write(json_line + '\n')
                    chunk_count += 1
        
        doc.close()
        print(f"Successfully created {chunk_count} chunks in {output_jsonl}")
        
    except Exception as e:
        print(f"Error processing PDF: {e}")
        sys.exit(1)

#command line helo
def main():
    parser = argparse.ArgumentParser(description='Chunk PDF documents by page for RAG')
    parser.add_argument('--input', '-i', required=True, help='Input PDF file path')
    parser.add_argument('--output', '-o', required=True, help='Output JSONL file path')
    
    args = parser.parse_args()
    
    chunk_pdf_to_jsonl(args.input, args.output)

if __name__ == "__main__":
    main()
