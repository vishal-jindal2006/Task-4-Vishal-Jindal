from flask import (
    Flask,
    render_template,
    request,
    send_file
)

import os
import cv2
import sqlite3
import pytesseract

from flask import redirect

from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet
)

app = Flask(__name__)

# ==========================
# CONFIG
# ==========================

UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    "static/exports",
    exist_ok=True
)

os.makedirs(
    "database",
    exist_ok=True
)

if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

# ==========================
# DATABASE
# ==========================

def init_db():

    conn = sqlite3.connect(
        "database/scans.db"
    )

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scans (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        filename TEXT,

        word_count INTEGER,

        char_count INTEGER,

        confidence REAL,

        scan_date TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()

# ==========================
# GLOBAL STORAGE
# ==========================

latest_text = ""
latest_word_count = 0
latest_char_count = 0
latest_confidence = 0

# ==========================
# ROUTES
# ==========================

@app.route("/")
def home():

    conn = sqlite3.connect(
        "database/scans.db"
    )

    cursor = conn.cursor()

    # Total Scans

    cursor.execute(
        "SELECT COUNT(*) FROM scans"
    )

    total_scans = cursor.fetchone()[0]

    # Average Confidence

    cursor.execute(
        "SELECT AVG(confidence) FROM scans"
    )

    avg_confidence = cursor.fetchone()[0]

    if avg_confidence is None:
        avg_confidence = 0

    avg_confidence = round(
        avg_confidence,
        2
    )

    conn.close()

    return render_template(
        "index.html",
        total_scans=total_scans,
        avg_confidence=avg_confidence,
        reports_generated=total_scans
    )

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/history")
def history():

    conn = sqlite3.connect(
        "database/scans.db"
    )

    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM scans
    ORDER BY id DESC
    """)

    scans = cursor.fetchall()

    conn.close()

    return render_template(
        "history.html",
        scans=scans
    )


@app.route("/ocr", methods=["POST"])
def ocr():

    global latest_text
    global latest_word_count
    global latest_char_count
    global latest_confidence

    if "image" not in request.files:
        return "No image uploaded"

    image = request.files["image"]

    if image.filename == "":
        return "No image selected"

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        image.filename
    )

    image.save(filepath)

    img = cv2.imread(filepath)

    if img is None:
        return "Unable to read image"

    # Image upscale for better OCR

    img = cv2.resize(
        img,
        None,
        fx=2,
        fy=2,
        interpolation=cv2.INTER_CUBIC
    )

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )

    processed = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    processed_filename = (
        "processed_" + image.filename
    )

    processed_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        processed_filename
    )

    cv2.imwrite(
        processed_path,
        processed
    )

    custom_config = r'--oem 3 --psm 4'

    text = pytesseract.image_to_string(
        processed,
        config=custom_config
    )

    ocr_data = pytesseract.image_to_data(
        processed,
        output_type=pytesseract.Output.DICT,
        config=custom_config
    )

    confidences = []

    for conf in ocr_data["conf"]:

        try:
            conf = float(conf)

            if conf > 0:
                confidences.append(conf)

        except:
            pass

    text = text.strip()

    if confidences:
        confidence_score = round(
            sum(confidences) / len(confidences),
            2
        )
    else:
        confidence_score = 0

    text = text.strip()

    if confidences:

        confidence_score = round(
            sum(confidences) /
            len(confidences),
            2
        )

    else:

        confidence_score = 0

    word_count = len(
        text.split()
    )

    char_count = len(
        text
    )

    latest_text = text
    latest_word_count = word_count
    latest_char_count = char_count
    latest_confidence = confidence_score

    # Save Scan History

    conn = sqlite3.connect(
        "database/scans.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO scans
        (
            filename,
            word_count,
            char_count,
            confidence,
            scan_date
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            image.filename,
            word_count,
            char_count,
            confidence_score,
            datetime.now().strftime(
                "%d-%m-%Y %H:%M:%S"
            )
        )
    )

    conn.commit()
    conn.close()

    image_path = (
        "/" +
        filepath.replace("\\", "/")
    )

    processed_image_path = (
        "/" +
        processed_path.replace("\\", "/")
    )

    return render_template(
        "result.html",
        text=text,
        word_count=word_count,
        char_count=char_count,
        confidence_score=confidence_score,
        image_path=image_path,
        processed_image_path=processed_image_path
    )


@app.route("/download-txt")
def download_txt():

    txt_path = (
        "static/exports/ocr_result.txt"
    )

    with open(
        txt_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            latest_text
        )

    return send_file(
        txt_path,
        as_attachment=True
    )


@app.route("/download-pdf")
def download_pdf():

    pdf_path = (
        "static/exports/ocr_report.pdf"
    )

    doc = SimpleDocTemplate(
        pdf_path
    )

    styles = getSampleStyleSheet()

    content = []

    content.append(
        Paragraph(
            "AI Vision OCR Report",
            styles["Title"]
        )
    )

    content.append(
        Spacer(1, 20)
    )

    content.append(
        Paragraph(
            f"Words: {latest_word_count}",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"Characters: {latest_char_count}",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"Confidence: {latest_confidence}%",
            styles["Normal"]
        )
    )

    content.append(
        Spacer(1, 20)
    )

    content.append(
        Paragraph(
            "Extracted Text",
            styles["Heading2"]
        )
    )

    content.append(
        Paragraph(
            latest_text.replace(
                "\n",
                "<br/>"
            ),
            styles["Normal"]
        )
    )

    doc.build(content)

    return send_file(
        pdf_path,
        as_attachment=True
    )


@app.route("/delete-history/<int:scan_id>")
def delete_history(scan_id):

    conn = sqlite3.connect(
        "database/scans.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM scans WHERE id=?",
        (scan_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/history")

@app.route("/clear-history")
def clear_history():

    conn = sqlite3.connect(
        "database/scans.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM scans"
    )

    conn.commit()
    conn.close()

    return redirect("/history")


if __name__ == "__main__":
    app.run(debug=True)