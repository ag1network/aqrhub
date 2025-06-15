from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import qrcode
from PIL import Image, ImageDraw
import os
import sqlite3
import uuid
import svgwrite  # Import svgwrite for SVG generation
from datetime import datetime  # Import datetime for timestamping
import requests
import user_agents
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import time
from flask import flash
from qrcode.image.styles.moduledrawers import CircleModuleDrawer, GappedSquareModuleDrawer, VerticalBarsDrawer, HorizontalBarsDrawer
from dotenv import load_dotenv  # Import dotenv
load_dotenv()  # Load environment variables from the .env file

app = Flask(__name__)

# Fetch secret key and database path from environment variables
app.secret_key = os.getenv('FLASK_SECRET_KEY')  # Use secret key from .env
DATABASE_PATH = os.getenv('DATABASE_PATH')  # Use database path from .env

LOGO_PATH = os.getenv('LOGO_PATH')  # Use logo path from .env
QR_CODES_DIR = os.path.join(app.root_path, 'static', 'qr_codes')

# Database initialization
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qr_codes (
            id INTEGER PRIMARY KEY,
            original_url TEXT NOT NULL,
            short_url TEXT NOT NULL UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

# Call init_db to ensure the database is initialized
init_db()

# Ensure the directories exist
if not os.path.exists(QR_CODES_DIR):
    os.makedirs(QR_CODES_DIR)

def clean_old_files(directory, days=1):
    """Deletes files older than a certain number of days in the specified directory."""
    now = time.time()
    cutoff = now - (days * 86400)  # 86400 seconds in a day

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.stat(file_path).st_mtime < cutoff:  # Compare modification time
            try:
                os.remove(file_path)
                print(f"Deleted old file: {file_path}")
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")

# Initialize the scheduler
scheduler = BackgroundScheduler()

# Set the cleanup task to run once a day
scheduler.add_job(
    func=lambda: clean_old_files(QR_CODES_DIR, days=1), 
    trigger=IntervalTrigger(days=1),  # Set it to run every 1 day
    id='cleanup_job',  # Job ID (optional)
    name='Cleanup old QR code files',  # Optional name for the job
    replace_existing=True  # Replaces any existing job with the same ID
)

# Start the scheduler
scheduler.start()

@app.route('/')
def index():
    return render_template('index.html')

# Function to save QR code as SVG
def save_qr_svg(qr_data, filename, fill_color='black', background_color='#f8f8f8', pattern='default'):
    qr = qrcode.QRCode(version=5, box_size=10, border=1)  # Adjust size for a better fit
    qr.add_data(qr_data)
    qr.make(fit=True)

    # Get the size of the matrix and calculate the overall size
    matrix = qr.get_matrix()
    size = len(matrix)  # Size of the QR matrix
    qr_size = size * 10  # 10px per square for QR code cells

    # Create an SVG drawing with calculated width and height
    dwg = svgwrite.Drawing(filename, profile='tiny', size=(f"{qr_size}px", f"{qr_size}px"))
    
    # Set background color
    dwg.add(dwg.rect(insert=(0, 0), size=('100%', '100%'), fill=background_color))
    
    # Apply the selected pattern to the SVG
    if pattern == 'circle':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    dwg.add(dwg.circle(center=(x * 10 + 5, y * 10 + 5), r=4, fill=fill_color))
    elif pattern == 'gapped_square':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    dwg.add(dwg.rect(insert=(x * 10 + 2, y * 10 + 2), size=(6, 6), fill=fill_color))
    elif pattern == 'vertical_bars':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    dwg.add(dwg.rect(insert=(x * 10, y * 10), size=(5, 10), fill=fill_color))
    elif pattern == 'horizontal_bars':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    dwg.add(dwg.rect(insert=(x * 10, y * 10), size=(10, 5), fill=fill_color))
    else:
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    dwg.add(dwg.rect(insert=(x * 10, y * 10), size=(10, 10), fill=fill_color))
    
    dwg.save()

# Generate QR code image with a pattern
def generate_image_with_pattern(qr, pattern, color, background):
    matrix = qr.get_matrix()  # This gives us the matrix (2D array of 0s and 1s)
    size = len(matrix)  # Get the size of the matrix
    img = Image.new('RGB', (size * 10, size * 10), background)  # 10px per square for QR code cells
    draw = ImageDraw.Draw(img)

    # Apply pattern for PNG
    if pattern == 'circle':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    draw.ellipse((x * 10 + 2, y * 10 + 2, x * 10 + 8, y * 10 + 8), fill=color)
    elif pattern == 'gapped_square':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    draw.rectangle((x * 10 + 2, y * 10 + 2, x * 10 + 8, y * 10 + 8), fill=color)
    elif pattern == 'vertical_bars':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    draw.rectangle((x * 10, y * 10, x * 10 + 5, y * 10 + 10), fill=color)
    elif pattern == 'horizontal_bars':
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    draw.rectangle((x * 10, y * 10, x * 10 + 10, y * 10 + 5), fill=color)
    else:
        for y in range(size):
            for x in range(size):
                if matrix[y][x]:
                    draw.rectangle((x * 10, y * 10, x * 10 + 10, y * 10 + 10), fill=color)

    return img


# Replace 'your_api_key' with your ipstack API key
IPSTACK_API_KEY = os.getenv('IPSTACK_API_KEY')  # Get the IP stack API key from .env file
IPSTACK_URL = 'http://api.ipstack.com/'

# Function to get location data from IP address (using ipstack API)
def get_location_from_ip(ip_address):
    url = f"{IPSTACK_URL}{ip_address}?access_key={IPSTACK_API_KEY}"
    response = requests.get(url)
    location_data = response.json()

    if 'error' in location_data:
        print(f"Error retrieving location data for IP: {ip_address}")
        return {
            'city': 'Unknown',
            'region_name': 'Unknown',
            'country_name': 'Unknown'
        }

    return location_data


# Route for generating QR code
@app.route('/q/<short_url>')
def redirect_qr(short_url):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Fetch the original URL and current scan count from the qr_codes table
    cursor.execute('SELECT original_url, scan_count FROM qr_codes WHERE short_url = ?', (short_url,))
    qr_code = cursor.fetchone()

    if qr_code:
        # Increment the scan count
        new_scan_count = qr_code[1] + 1
        cursor.execute('UPDATE qr_codes SET scan_count = ? WHERE short_url = ?', (new_scan_count, short_url))
        conn.commit()

        # Capture the IP address
        ip_address = request.remote_addr
        
        # Use ipstack API to get location data
        location_data = get_location_from_ip(ip_address)
        
        # Extract city, state, and country from the API response
        city = location_data.get('city', 'Unknown')
        state = location_data.get('region_name', 'Unknown')
        country = location_data.get('country_name', 'Unknown')

        # Capture the User-Agent (for device type)
        user_agent_string = request.headers.get('User-Agent')

        # Detect device type (Android, iPhone, or others)
        if "Android" in user_agent_string:
            device_type = "Android"
        elif "python-requests" in user_agent_string:
            device_type = "Server"
        else:
            device = user_agents.parse(user_agent_string)
            device_type = device.device.family  # e.g., iPhone, Samsung

        # Fallback mechanism for device type if it returns "Other" or "Unknown"
        if device_type == "Other" or device_type == "K" or not device_type:
            device_type = "Unknown Device"

        # Log the scan in the qr_code_scans table
        cursor.execute(''' 
            INSERT INTO qr_code_scans (short_url, ip_address, device_type, city, state, country)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (short_url, ip_address, device_type, city, state, country))
        conn.commit()

        conn.close()

        # Redirect to the original URL
        return redirect(qr_code[0])
    else:
        conn.close()
        return "QR Code not found", 404




# Route for generating the QR code, Dynamic and SMS
@app.route('/generate', methods=['POST'])
def generate():
    # Get the selected color, background color, and pattern from the form
    color = request.form.get('color', '#000000')  # Default to black if no color selected
    background = request.form.get('background', '#f8f8f8')  # Default to off-white if no background color selected
    pattern = request.form.get('pattern', 'default')  # Default to 'default' pattern if no pattern is selected

    # Generate a timestamp for the filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Standard Link QR Code
    if 'url' in request.form and request.form['url']:
        url = request.form['url'].strip()
        if not url.startswith(('http://', 'https://')):  # Add https if missing
            url = 'https://' + url
        qr = qrcode.QRCode(version=5, box_size=30, border=2)
        qr.add_data(url)
        qr.make(fit=True)

        # Apply the selected pattern to the image
        img = generate_image_with_pattern(qr, pattern, color, background)

        # Save PNG file
        png_filename = f"{timestamp}_link_qr_code.png"
        png_path = os.path.join(QR_CODES_DIR, png_filename)
        img.save(png_path)

        # Save SVG file with the same pattern
        svg_filename = f"{timestamp}_link_qr_code.svg"
        svg_path = os.path.join(QR_CODES_DIR, svg_filename)
        save_qr_svg(url, svg_path, fill_color=color, background_color=background, pattern=pattern)

        # Load the SVG content
        with open(svg_path, 'r') as svg_file:
            svg_content = svg_file.read()

        # Return the preview page
        return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)

    # Dynamic URL QR Code
    elif 'dynamic_url' in request.form and request.form['dynamic_url']:
        dynamic_url = request.form['dynamic_url'].strip()
        if not dynamic_url.startswith(('http://', 'https://')):  # Add https if missing
            dynamic_url = 'https://' + dynamic_url
        short_url = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute('INSERT INTO qr_codes (original_url, short_url) VALUES (?, ?)', (dynamic_url, short_url))
        conn.commit()
        conn.close()

        qr = qrcode.QRCode(version=5, box_size=30, border=2)
        qr.add_data(f"https://aqrhub.com/q/{short_url}")
        qr.make(fit=True)

        # Apply the selected pattern
        img = generate_image_with_pattern(qr, pattern, color, background)

        # Save PNG file
        png_filename = f"{timestamp}_dynamic_qr_code.png"
        png_path = os.path.join(QR_CODES_DIR, png_filename)
        img.save(png_path)

        # Save SVG file with the correct pattern
        svg_filename = f"{timestamp}_dynamic_qr_code.svg"
        svg_path = os.path.join(QR_CODES_DIR, svg_filename)
        save_qr_svg(f"https://aqrhub.com/q/{short_url}", svg_path, fill_color=color, background_color=background, pattern=pattern)

        with open(svg_path, 'r') as svg_file:
            svg_content = svg_file.read()

        # Return the preview page with both SVG and PNG filenames
        return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)

    # SMS QR Code
    elif 'sms_number' in request.form and request.form['sms_number']:
        sms_number = request.form['sms_number'].strip()
        sms_message = request.form.get('sms_message', '').strip()

        sms_data = f"sms:{sms_number}"
        if sms_message:
            sms_data += f"?body={sms_message}"

        qr = qrcode.QRCode(version=5, box_size=30, border=2)
        qr.add_data(sms_data)
        qr.make(fit=True)

        # Apply the selected pattern
        img = generate_image_with_pattern(qr, pattern, color, background)

        # Save PNG file
        png_filename = f"{timestamp}_sms_qr_code.png"
        png_path = os.path.join(QR_CODES_DIR, png_filename)
        img.save(png_path)

        # Save SVG file with the correct pattern
        svg_filename = f"{timestamp}_sms_qr_code.svg"
        svg_path = os.path.join(QR_CODES_DIR, svg_filename)
        save_qr_svg(sms_data, svg_path, fill_color=color, background_color=background, pattern=pattern)

        with open(svg_path, 'r') as svg_file:
            svg_content = svg_file.read()

        return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)

    return "No QR code data provided", 400  # If no valid data was entered




# Routes for generating QR codes for various types of data

@app.route('/generate_email', methods=['POST'])
def generate_email():
    # Get the email details from the form
    email_address = request.form.get('email_address', '').strip()
    email_subject = request.form.get('email_subject', '').strip()
    email_body = request.form.get('email_body', '').strip()

    # Construct the mailto URL with the subject and body if provided
    email_data = f"mailto:{email_address}"
    if email_subject:
        email_data += f"?subject={email_subject}"
    if email_body:
        email_data += f"&body={email_body}"

    # Get the selected color, background color, and pattern from the form
    color = request.form.get('color', '#000000')  # Default color: black
    background = request.form.get('background', '#f8f8f8')  # Default background: off-white
    pattern = request.form.get('pattern', 'default')  # Default pattern: square

    # Generate a timestamp for the filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Initialize the QR code object
    qr = qrcode.QRCode(version=5, box_size=30, border=2)
    qr.add_data(email_data)
    qr.make(fit=True)

    # Apply the selected pattern to the PNG image
    img = generate_image_with_pattern(qr, pattern, color, background)

    # Save PNG file with timestamp in filename
    png_filename = f"{timestamp}_email_qr_code.png"
    png_path = os.path.join(QR_CODES_DIR, png_filename)
    img.save(png_path)

    # Save SVG file with selected colors and pattern
    svg_filename = f"{timestamp}_email_qr_code.svg"
    svg_path = os.path.join(QR_CODES_DIR, svg_filename)
    
    # Ensure the pattern is applied to the SVG as well
    save_qr_svg(email_data, svg_path, fill_color=color, background_color=background, pattern=pattern)

    # Read SVG content
    with open(svg_path, 'r') as svg_file:
        svg_content = svg_file.read()

    # Return the preview page with both SVG and PNG content
    return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)



@app.route('/generate_vcard', methods=['POST'])
def generate_vcard():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Get the selected color, background color, and pattern from the form
    color = request.form.get('color', '#000000')  # Default color: black
    background = request.form.get('background', '#f8f8f8')  # Default background: off-white
    pattern = request.form.get('pattern', 'default')  # Default pattern: square

    # Get vCard details from the form
    name = request.form.get('name', '').strip()
    company = request.form.get('company', '').strip()
    title = request.form.get('title', '').strip()
    phone = request.form.get('phone', '').strip()
    mobile = request.form.get('mobile', '').strip()
    email = request.form.get('email', '').strip()
    work_address = request.form.get('work_address', '').strip()
    home_address = request.form.get('home_address', '').strip()
    website = request.form.get('website', '').strip()
    home_phone = request.form.get('home_phone', '').strip()

    # Create vCard data with optional fields
    vcard_data = "BEGIN:VCARD\nVERSION:3.0\n"
    if name:
        vcard_data += f"N:{name};;;\nFN:{name}\n"
    if company:
        vcard_data += f"ORG:{company}\n"
    if title:
        vcard_data += f"TITLE:{title}\n"
    if phone:
        vcard_data += f"TEL;TYPE=WORK:{phone}\n"
    if mobile:
        vcard_data += f"TEL;TYPE=CELL:{mobile}\n"
    if email:
        vcard_data += f"EMAIL;TYPE=WORK:{email}\n"
    if work_address:
        vcard_data += f"ADR;TYPE=WORK:{work_address}\n"
    if home_address:
        vcard_data += f"ADR;TYPE=HOME:{home_address}\n"
    if website:
        vcard_data += f"URL:{website}\n"
    if home_phone:
        vcard_data += f"TEL;TYPE=HOME:{home_phone}\n"
    vcard_data += "END:VCARD"

    # Initialize the QR code object
    qr = qrcode.QRCode(version=5, box_size=30, border=2)
    qr.add_data(vcard_data)
    qr.make(fit=True)

    # Apply the selected pattern to the QR code
    img = generate_image_with_pattern(qr, pattern, color, background)

    # Save PNG file
    png_filename = f"{timestamp}_vcard_qr_code.png"
    png_path = os.path.join(QR_CODES_DIR, png_filename)
    img.save(png_path)

    # Save SVG with selected colors and pattern
    svg_filename = f"{timestamp}_vcard_qr_code.svg"
    svg_path = os.path.join(QR_CODES_DIR, svg_filename)
    save_qr_svg(vcard_data, svg_path, fill_color=color, background_color=background, pattern=pattern)

    # Read SVG content
    with open(svg_path, 'r') as svg_file:
        svg_content = svg_file.read()

    return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)



@app.route('/generate_wifi', methods=['POST'])
def generate_wifi():
    ssid = request.form['ssid'].strip()
    password = request.form['password'].strip()
    encryption = request.form['encryption']

    color = request.form.get('color', '#000000')  # Default color: black
    background = request.form.get('background', '#f8f8f8')  # Default background: off-white
    pattern = request.form.get('pattern', 'default')  # Default pattern: square

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Construct the Wi-Fi data string for the QR code
    if encryption == 'nopass':
        wifi_data = f"WIFI:S:{ssid};T:nopass;P:;;"
    else:
        wifi_data = f"WIFI:S:{ssid};T:{encryption};P:{password};;"

    # Initialize the QR code object
    qr = qrcode.QRCode(version=5, box_size=30, border=2)
    qr.add_data(wifi_data)
    qr.make(fit=True)

    # Apply the selected pattern to the QR code
    img = generate_image_with_pattern(qr, pattern, color, background)

    # Save PNG file
    png_filename = f"{timestamp}_wifi_qr_code.png"
    png_path = os.path.join(QR_CODES_DIR, png_filename)
    img.save(png_path)

    # Save SVG with selected colors and pattern
    svg_filename = f"{timestamp}_wifi_qr_code.svg"
    svg_path = os.path.join(QR_CODES_DIR, svg_filename)
    save_qr_svg(wifi_data, svg_path, fill_color=color, background_color=background, pattern=pattern)

    # Read SVG content
    with open(svg_path, 'r') as svg_file:
        svg_content = svg_file.read()

    return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)


@app.route('/generate_note', methods=['POST'])
def generate_note():
    note_content = request.form.get('note_content', '').strip()

    color = request.form.get('color', '#000000')  # Default color: black
    background = request.form.get('background', '#f8f8f8')  # Default background: off-white
    pattern = request.form.get('pattern', 'default')  # Default pattern: square

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Initialize the QR code object
    qr = qrcode.QRCode(version=5, box_size=30, border=2)
    qr.add_data(note_content)
    qr.make(fit=True)

    # Apply the selected pattern to the QR code
    img = generate_image_with_pattern(qr, pattern, color, background)

    # Save PNG file
    png_filename = f"{timestamp}_note_qr_code.png"
    png_path = os.path.join(QR_CODES_DIR, png_filename)
    img.save(png_path)

    # Save SVG with selected colors and pattern
    svg_filename = f"{timestamp}_note_qr_code.svg"
    svg_path = os.path.join(QR_CODES_DIR, svg_filename)
    save_qr_svg(note_content, svg_path, fill_color=color, background_color=background, pattern=pattern)

    # Read SVG content
    with open(svg_path, 'r') as svg_file:
        svg_content = svg_file.read()

    return render_template('preview.html', svg_content=svg_content, svg_filename=svg_filename, png_filename=png_filename)


# Additional route for updating dynamic URLs
@app.route('/update', methods=['POST'])
def update_url():
    short_url = request.form['short_url'].strip()
    new_url = request.form['new_url'].strip()

    if new_url and not new_url.startswith(('http://', 'https://')):
        new_url = 'https://' + new_url

    if short_url and new_url:
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('UPDATE qr_codes SET original_url = ? WHERE short_url = ?', (new_url, short_url))
            conn.commit()
            conn.close()
            flash("The Dynamic QR code link successfully updated! Try scanning the QR code again, it should point you to the new link.", "success")
        except Exception as e:
            flash(f"Error updating the URL: {e}", "error")
    else:
        flash("Both fields must be provided.", "error")

    return redirect(url_for('index'))

@app.route('/donate')
def donate():
    return render_template('donate.html')


if __name__ == '__main__':
    init_db()  # Initialize the database
    app.run(host='0.0.0.0', port=5000, debug=True)  # Run the app
