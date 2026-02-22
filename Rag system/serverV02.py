import os
import json
import base64
from datetime import datetime
from functools import partial
from flask import Flask, jsonify, send_from_directory
from gevent.pywsgi import WSGIServer
import qrcode
from pyngrok import ngrok, conf

# --- REPORTLAB IMPORTS ---
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_LEFT

# --- CONFIGURATION ---
NGROK_AUTH_TOKEN = 'YOUR NGROK TOKEN HERE' 
NGROK_REGION = 'us'
PORT = 5050  # Changed from 5000 to 5050

# --- PATH CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Files
BRANDING_FILE = os.path.join(BASE_DIR, 'conclusion', 'branding.json')
TEXT_FILE = os.path.join(BASE_DIR, 'conclusion', 'conclusion.txt') # New Text File

# Folders
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'PDF results')
ASSETS_FOLDER = os.path.join(BASE_DIR, 'assets')

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
public_url = ""

# --- HELPER: Resolve Image Path ---
def resolve_path(relative_path):
    if not relative_path: return None
    clean_path = relative_path.replace('assets/', '').replace('assets\\', '')
    full_path = os.path.join(ASSETS_FOLDER, clean_path)
    if os.path.exists(full_path):
        return full_path
    print(f"[WARNING] Image not found at: {full_path}")
    return None

# --- HELPER: Load Branding (JSON) ---
def load_branding():
    if os.path.exists(BRANDING_FILE):
        try:
            with open(BRANDING_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading Branding JSON: {e}")
    return {}

# --- HELPER: Load Conclusion (TEXT) ---
def load_conclusion_text():
    if os.path.exists(TEXT_FILE):
        try:
            with open(TEXT_FILE, 'r', encoding='utf-8') as f:
                # Read file and replace newlines with <br/> for PDF formatting
                text = f.read()
                return text.replace('\n', '<br/>')
        except Exception as e:
            print(f"Error reading Text file: {e}")
            return "Error reading conclusion.txt"
    return "No conclusion.txt found in the conclusion folder."

def image_to_base64(relative_path):
    full_path = resolve_path(relative_path)
    if full_path:
        try:
            with open(full_path, "rb") as img_file:
                b64_string = base64.b64encode(img_file.read()).decode('utf-8')
                return f"data:image/png;base64,{b64_string}"
        except Exception:
            pass
    return ""

# --- HELPER: Draw Header & Footer ---
def draw_page_template(canvas, doc, branding_data):
    canvas.saveState()
    width, height = letter
    
    logos = branding_data.get('logos', {})
    
    # --- HEADER ---
    header_top_y = height - 40
    title_text = branding_data.get('project_title', 'Report')
    
    raw_proj_path = logos.get('project', '')
    project_logo_path = resolve_path(raw_proj_path)
    
    # Settings
    logo_width = 1.0 * inch
    logo_height = 1.0 * inch
    spacing = 15
    
    # Title Style
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Heading1'],
        fontSize=14,
        leading=16,
        alignment=TA_LEFT,
        textColor=colors.black
    )
    
    title_para = Paragraph(title_text, header_style)
    
    # Layout Calculations
    max_text_width = width - 100 - logo_width - spacing
    w, h = title_para.wrap(max_text_width, height)
    content_width = logo_width + spacing + w
    start_x = (width - content_width) / 2.0
    current_y = header_top_y - max(logo_height, h)
    
    # Draw Logo
    if project_logo_path:
        try:
            img_obj = ImageReader(project_logo_path)
            logo_y = current_y + (h - logo_height)/2 if h > logo_height else current_y
            canvas.drawImage(img_obj, start_x, logo_y, width=logo_width, height=logo_height, mask='auto')
        except Exception:
            pass
            
    # Draw Title
    text_x = start_x + logo_width + spacing
    text_y = current_y + (logo_height - h)/2 if logo_height > h else current_y
    title_para.drawOn(canvas, text_x, text_y)

    # Line
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(1)
    canvas.line(30, current_y - 15, width - 30, current_y - 15)

    # --- FOOTER ---
    try:
        footer_y = 50
        uni_logo_size = 0.6 * inch
        
        uni_logos_raw = logos.get('uni', [])
        valid_uni_logos = [resolve_path(p) for p in uni_logos_raw if resolve_path(p)]
        
        if valid_uni_logos:
            padding = 20
            total_logos_width = (len(valid_uni_logos) * uni_logo_size) + ((len(valid_uni_logos) - 1) * padding)
            current_x = (width - total_logos_width) / 2.0
            
            for logo_path in valid_uni_logos:
                try:
                    img_obj = ImageReader(logo_path)
                    canvas.drawImage(img_obj, current_x, footer_y, width=uni_logo_size, height=uni_logo_size, mask='auto')
                    current_x += (uni_logo_size + padding)
                except Exception:
                    pass

        footer_text = branding_data.get('footer_text', '')
        canvas.setFont('Helvetica-Oblique', 9)
        canvas.setFillColor(colors.gray)
        canvas.drawCentredString(width / 2.0, 30, footer_text)

    except Exception:
        pass

    canvas.restoreState()

# --- HELPER: Generate PDF ---
def generate_pdf(branding, text_content, filename):
    try:
        save_path = os.path.join(OUTPUT_FOLDER, filename)
        doc = SimpleDocTemplate(save_path, pagesize=letter, topMargin=150, bottomMargin=100)
        styles = getSampleStyleSheet()
        story = []
        
        # 1. Conclusion (From Text File)
        story.append(Paragraph("Conclusion", styles['Heading3']))
        story.append(Paragraph(text_content, styles['BodyText']))
        story.append(Spacer(1, 20))

        # 2. Project Details (From Branding JSON)
        if 'details' in branding:
            story.append(Paragraph("Project Details", styles['Heading3']))
            story.append(Paragraph(branding['details'].replace('\n', '<br/>'), styles['BodyText']))

        page_callback = partial(draw_page_template, branding_data=branding)
        doc.build(story, onFirstPage=page_callback, onLaterPages=page_callback)
        print(f"[SUCCESS] PDF Saved: {save_path}")
        return True
    except Exception as e:
        print(f"[CRITICAL ERROR] PDF Gen Failed: {e}")
        return False

# --- API ENDPOINT ---
@app.route('/api/generate', methods=['POST', 'GET'])
def generate_endpoint():
    global public_url
    
    # 1. Load Data
    branding = load_branding()
    conclusion_text = load_conclusion_text()
    
    if not branding: 
        return jsonify({"error": "Branding JSON missing."}), 500

    # 2. Generate PDF
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    pdf_filename = f"Report_{timestamp}.pdf"
    
    if not generate_pdf(branding, conclusion_text, pdf_filename):
        return jsonify({"error": "Failed to generate PDF"}), 500

    # 3. Generate QR
    download_link = f"{public_url}/download/{pdf_filename}"
    qr_filename = os.path.join(OUTPUT_FOLDER, "latest_qr.png")
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(download_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    img.save(qr_filename)

    # 4. Create HTML Preview
    logos = branding.get('logos', {})
    b64_project = image_to_base64(logos.get('project', ''))
    
    with open(qr_filename, "rb") as qr_f:
         b64_qr_raw = base64.b64encode(qr_f.read()).decode('utf-8')
    
    uni_imgs_html = ""
    for p in logos.get('uni', []):
        b64 = image_to_base64(p)
        if b64: uni_imgs_html += f'<img src="{b64}">'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: sans-serif; padding: 15px; margin: 0; display: flex; flex-direction: column; min-height: 95vh; }}
            .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; display: flex; flex-direction: column; }}
            .header {{ display: flex; align-items: center; justify-content: center; border-bottom: 2px solid #ddd; padding-bottom: 20px; margin-bottom: 20px; }}
            .header img {{ height: 60px; margin-right: 15px; }}
            .header h2 {{ margin: 0; color: #333; font-size: 18px; }}
            .content {{ flex: 1; }}
            h3 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 15px; }}
            .footer {{ margin-top: 40px; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }}
            .footer-logos {{ margin-bottom: 10px; display: flex; justify-content: center; gap: 15px; }}
            .footer-logos img {{ height: 40px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                {f'<img src="{b64_project}">' if b64_project else ''}
                <h2>{branding.get('project_title', 'Report')}</h2>
            </div>
            <div class="content">
                <h3>Conclusion</h3>
                <p>{conclusion_text}</p>
                <h3>Project Details</h3>
                <p>{branding.get('details', '')}</p>
            </div>
            <div class="footer">
                <div class="footer-logos">{uni_imgs_html}</div>
                <div>{branding.get('footer_text', '')}</div>
            </div>
        </div>
    </body>
    </html>
    """
    return jsonify({"pdf_url": download_link, "qr_image": b64_qr_raw, "html_content": html_content})

@app.route('/download/<path:filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

if __name__ == '__main__':
    conf.get_default().auth_token = NGROK_AUTH_TOKEN
    conf.get_default().region = NGROK_REGION
    
    try:
        # Try to kill any existing ngrok processes first
        import subprocess
        import sys
        
        print("Checking for existing ngrok processes...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/f", "/im", "ngrok.exe"], 
                          shell=True, capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "ngrok"], 
                          shell=True, capture_output=True)
        
        import time
        time.sleep(2)
        
        # Start new tunnel on port 5050
        tunnel = ngrok.connect(PORT, 'http')
        public_url = tunnel.public_url
        print(f"Ngrok URL: {public_url}")
        print(f"Local URL: http://localhost:{PORT}")
        http_server = WSGIServer(('0.0.0.0', PORT), app)
        http_server.serve_forever()
        
    except Exception as e:
        print(f"Error starting ngrok: {e}")
        print(f"Running locally at: http://localhost:{PORT}")
        # Fallback to regular Flask server
        app.run(host='0.0.0.0', port=PORT, debug=True)
