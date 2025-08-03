from flask import Flask, render_template, request, redirect, flash, session, jsonify, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from flask_mail import Mail, Message
from psycopg2 import pool
from dotenv import load_dotenv
load_dotenv()
import random
import string
import time
from datetime import datetime, date
from calendar import monthrange
import qrcode
import io
import base64
import uuid
import math
from flask import send_file
import pandas as pd
import psycopg2
import psycopg2.extras
import os
from PIL import Image




app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Email config
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='your-email@gmail.com',
    MAIL_PASSWORD='your-app-password'
)
mail = Mail(app)

ALLOWED_DISTANCE_METERS = 100

# DB connection
def get_cursor():
    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cursor

def close_cursor(conn, cursor):
    cursor.close()
    db_pool.putconn(conn)

db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    dbname="neondb",
    user="neondb_owner",
    password="npg_FVRYiqWd18aD",
    host="ep-fancy-fire-a1xrowx1-pooler.ap-southeast-1.aws.neon.tech",
    port="5432",
    sslmode="require"
)

otp_store = {}

@app.route('/')
def home():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = db_pool.getconn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT id, full_name, email, password FROM Teachers WHERE email = %s", (email,))
            user = cursor.fetchone()
        finally:
            cursor.close()
            db_pool.putconn(conn)

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            flash("Logged in successfully!", "success")
            return render_template("dashboard.html")
        else:
            flash("Invalid email or password", "danger")
            return redirect("/login")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm-password")
        security_answer = request.form.get("security-question")
        not_robot = request.form.get("not-robot")

        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect("/signup")
        if not not_robot:
            flash("Please confirm you are not a robot.", "danger")
            return redirect("/signup")

        conn = db_pool.getconn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            # Check if email already exists
            cursor.execute("SELECT * FROM Teachers WHERE email = %s", (email,))
            if cursor.fetchone():
                flash("Email already registered!", "warning")
                return redirect("/signup")

            # Insert new user
            hashed_password = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO Teachers (full_name, email, password, security_answer)
                VALUES (%s, %s, %s, %s)
            """, (full_name, email, hashed_password, security_answer))
            conn.commit()
        finally:
            cursor.close()
            db_pool.putconn(conn)

        flash("Account created successfully. Please log in.", "success")
        return redirect("/login")

    return render_template("signup.html")

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot-password.html")

@app.route("/send_otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify(success=False, message="Email is required"), 400

    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Check if email is registered
        cursor.execute("SELECT * FROM Teachers WHERE email = %s", (email,))
        if not cursor.fetchone():
            return jsonify(success=False, message="Email not registered"), 404
    finally:
        cursor.close()
        db_pool.putconn(conn)

    # Generate and store OTP
    otp = ''.join(random.choices(string.digits, k=6))
    otp_store[email] = (otp, time.time() + 300)

    # Send OTP via email
    try:
        mail.send(Message("Your OTP", sender=app.config['MAIL_USERNAME'], recipients=[email], body=f"OTP: {otp}"))
        return jsonify(success=True, message="OTP sent")
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")
    new_password = data.get("new_password")

    if not all([email, otp, new_password]):
        return jsonify(success=False, message="All fields are required"), 400

    # Check if OTP exists and is valid
    if email not in otp_store:
        return jsonify(success=False, message="No OTP request found"), 404

    stored_otp, expiry = otp_store[email]
    if time.time() > expiry:
        otp_store.pop(email)
        return jsonify(success=False, message="OTP expired"), 403

    if otp != stored_otp:
        return jsonify(success=False, message="Invalid OTP"), 401

    # If OTP is valid, update the password in DB
    conn = db_pool.getconn()
    cursor = conn.cursor()
    try:
        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE Teachers SET password = %s WHERE email = %s", (hashed_password, email))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message="Database error: " + str(e)), 500
    finally:
        cursor.close()
        db_pool.putconn(conn)

    # Clear OTP after use
    otp_store.pop(email)
    return jsonify(success=True, message="Password reset successful")


@app.route("/profile")
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("""
            SELECT full_name, email, phone_number, employee_id, department, designation 
            FROM Teachers WHERE id = %s
        """, (session['user_id'],))
        user = cursor.fetchone()
    finally:
        cursor.close()
        db_pool.putconn(conn)

    return render_template("profile.html", user=user)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        if request.method == "POST":
            form_type = request.form.get("form_type")
            if form_type == "password_change":
                old = request.form.get("current-password")
                new = request.form.get("new-password")
                confirm = request.form.get("confirm-password")

                cursor.execute("SELECT password FROM Teachers WHERE id = %s", (user_id,))
                stored_password = cursor.fetchone()['password']

                if not check_password_hash(stored_password, old):
                    flash("Incorrect current password.", "danger")
                elif new != confirm:
                    flash("New passwords don't match.", "danger")
                else:
                    hashed_new = generate_password_hash(new)
                    cursor.execute("UPDATE Teachers SET password = %s WHERE id = %s", (hashed_new, user_id))
                    conn.commit()
                    flash("Password updated.", "success")

        cursor.execute("""
            SELECT full_name, email, phone_number, employee_id, department, designation 
            FROM Teachers WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()

    finally:
        cursor.close()
        db_pool.putconn(conn)

    return render_template("settings.html", user=user)


@app.route('/take-attendance')
def take_attendance():
    return render_template('take-attendance.html')

@app.route('/<course_type>-courses')
def courses(course_type):
    if course_type == "ug":
        return render_template('ug-courses.html', courses=["BCA", "BBA", "BSC", "B.COM"])
    elif course_type == "pg":
        return render_template('pg-courses.html', courses=["MSC", "MCA", "MBA", "M.COM"])
    return "Invalid course type", 404

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@app.route('/set-limit/<course_name>', methods=['GET', 'POST'])
def set_limit(course_name):
    if request.method == 'POST':
        try:
            scan_limit = int(request.form['scan_limit'])
            lat = float(request.form['lat'])
            lon = float(request.form['lon'])
        except:
            return "Invalid form data", 400

        qr_id = str(uuid.uuid4())
        conn = db_pool.getconn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO qrcodes (id, scan_count, limit_count, origin_lat, origin_lon, target_url)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (qr_id, 0, scan_limit, lat, lon, ""))
            conn.commit()
        finally:
            cursor.close()
            db_pool.putconn(conn)

        qr_url = f"{request.host_url}scan/{qr_id}"
        img = qrcode.make(qr_url)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return render_template(
    'qr.html',
    qr_img_base64=qr_img_base64,
    scan_limit=scan_limit,
    qr_url=qr_url,
    course_name=course_name  # ✅ pass this to the template
)


    return render_template('limit.html')


@app.route('/scan/<qr_id>')
def scan(qr_id):
    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT * FROM qrcodes WHERE id = %s", (qr_id,))
        qr = cursor.fetchone()
    finally:
        cursor.close()
        db_pool.putconn(conn)

    if not qr or qr['scan_count'] >= qr['limit_count']:
        return "Reached the Scan Limit", 403
    return render_template("webpage.html", qr_id=qr_id)



@app.route('/validate_scan/<qr_id>', methods=['POST'])
def validate_scan(qr_id):
    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        data = request.get_json(force=True)
        campusid = data.get('campusid')
        name = data.get('name')
        lat = float(data.get('latitude', 0))
        lon = float(data.get('longitude', 0))

        if not all([campusid, name, lat, lon]):
            return jsonify(success=False, message="Missing fields"), 400

        cursor.execute("SELECT * FROM qrcodes WHERE id = %s", (qr_id,))
        qr = cursor.fetchone()
        if not qr:
            return jsonify(success=False, message="Invalid QR"), 404

        cursor.execute("SELECT * FROM students WHERE campusid = %s AND name = %s", (campusid, name))
        student = cursor.fetchone()
        if not student:
            return jsonify(success=False, message="Student not found"), 404

        distance = haversine(qr['origin_lat'], qr['origin_lon'], lat, lon)
        if distance > ALLOWED_DISTANCE_METERS:
            return jsonify(success=False, message="Too far away"), 403

        today = date.today()
        cursor.execute("""
            INSERT INTO attendance_logs (campusid, name, date, attendance, qr_id)
             VALUES (%s, %s, %s, 'present', %s)
            ON CONFLICT (campusid, qr_id) DO UPDATE SET attendance = 'present'
            """, (campusid, name, today, qr_id))


        cursor.execute("UPDATE qrcodes SET scan_count = scan_count + 1 WHERE id = %s", (qr_id,))
        conn.commit()

        return jsonify(success=True, message="Attendance marked successfully")

    except Exception as e:
        return jsonify(success=False, message="Server error: " + str(e)), 500
    finally:
        cursor.close()
        db_pool.putconn(conn)


@app.route('/view-attendance')
def view_attendance():
    return render_template('view-attendance.html')

@app.route('/<course_type>-courses-view')
def view_courses(course_type):
    courses = {"ug": ["BCA", "BBA", "BSC", "B.COM"], "pg": ["MSC", "MCA", "MBA", "M.COM"]}
    if course_type not in courses:
        return "Invalid course type", 404
    return render_template(f'{course_type.upper()}_COURSE.html', courses=courses[course_type], course_type=course_type)


@app.route('/report/<course_name>', methods=['GET'])
def report(course_name):
    return render_template('report.html', course_name=course_name)

@app.route('/get_attendance_matrix')
def get_attendance_matrix():
    course = request.args.get('course')
    month = request.args.get('month')
    year = request.args.get('year')

    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        date_condition = ""
        params = [course]
        if month and year:
            date_condition = "AND EXTRACT(MONTH FROM al.date) = %s AND EXTRACT(YEAR FROM al.date) = %s"
            params.extend([int(month), int(year)])

        cursor.execute(f"""
            SELECT DISTINCT al.date
            FROM attendance_logs al
            JOIN students s ON s.campusid = al.campusid
            WHERE s.course = %s {date_condition}
            ORDER BY al.date ASC
        """, tuple(params))
        date_rows = cursor.fetchall()
        dates = [row['date'].strftime('%Y-%m-%d') for row in date_rows]

        cursor.execute(f"""
            SELECT s.id, s.campusid, s.name, al.date, al.attendance
            FROM students s
            LEFT JOIN attendance_logs al ON s.campusid = al.campusid
            WHERE s.course = %s {date_condition}
        """, tuple(params))
        records = cursor.fetchall()

        matrix = {}
        for row in records:
            sid = row['id']
            if sid not in matrix:
                matrix[sid] = {
                    'id': sid,
                    'campusid': row['campusid'],
                    'name': row['name'],
                    'attendance': {d: '' for d in dates},
                    'present_count': 0
                }
            if row['date']:
                date_str = row['date'].strftime('%Y-%m-%d')
                matrix[sid]['attendance'][date_str] = row['attendance']
                if row['attendance'] == 'present':
                    matrix[sid]['present_count'] += 1

        final_data = []
        for m in matrix.values():
            final_data.append({
                'id': m['id'],
                'campusid': m['campusid'],
                'name': m['name'],
                'attendance': m['attendance'],
                'total_present': m['present_count']
            })

        return jsonify({'dates': dates, 'data': final_data})

    finally:
        cursor.close()
        db_pool.putconn(conn)



@app.route('/download_attendance_excel')
def download_attendance_excel():
    course = request.args.get('course')
    month = request.args.get('month')
    year = request.args.get('year')

    conn = db_pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # RealDictCursor gives dicts

    try:
        query = """
            SELECT al.id, al.name, al.campusid, al.date, al.attendance
            FROM attendance_logs al
            JOIN students s ON al.campusid = s.campusid
            WHERE s.course = %s
        """
        params = [course]

        if month and year:
            query += " AND EXTRACT(MONTH FROM al.date) = %s AND EXTRACT(YEAR FROM al.date) = %s"
            params.extend([int(month), int(year)])

        cursor.execute(query, tuple(params))
        records = cursor.fetchall()

        if not records:
            return "No data available for download", 404

        df = pd.DataFrame(records)
        file_path = f"/tmp/{course}_attendance_{month}_{year}.xlsx"
        df.to_excel(file_path, index=False)

        return send_file(file_path, as_attachment=True)

    finally:
        cursor.close()
        db_pool.putconn(conn)



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)



