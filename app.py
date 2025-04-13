from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import  request, jsonify
import mysql.connector
from flask_login import current_user
import datetime

from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from session_utils import log_unauthorized_access

import random
import string

def generate_unique_password(length=10):
    """
    Generates a random alphanumeric password of given length.
    """
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))

app = Flask(__name__)
app.secret_key = 'lms2025' 

db_config = {
    'host': '10.0.116.125', 
    'user': 'cs432g8', 
    'password': 'X7mLpNZq', 
    'database': 'cs432g8' 
}

db_config_cims = {
    'host' : '10.0.116.125',
    'user' :    'cs432cims',
    'password' : 'X7mLpNZq',
    'database' : 'cs432cims'
}

def get_cims_connection():
    return mysql.connector.connect(**db_config_cims)
  
def get_db_connection():
    return mysql.connector.connect(**db_config) 


from werkzeug.security import generate_password_hash
from flask import jsonify

 
@app.route('/')  
def home():  
    return redirect(url_for('login')) 

def is_admin(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # First get the username linked to this session
    cursor.execute("SELECT username FROM sessions WHERE session_id = %s", (session_id,))
    result = cursor.fetchone()

    if result:
        username = result[0]
        # Now check if this user is admin
        cursor.execute("SELECT role FROM login WHERE username = %s", (username,))
        role_result = cursor.fetchone()
        conn.close()
        if role_result and role_result[0] == 'admin':
            return True

    conn.close()
    return False

from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = session.get('session_id')
        username = session.get('username')

        if not session_id or not username:
            flash("Please log in.")
            return redirect(url_for('login'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM sessions WHERE username = %s AND session_id = %s", (username, session_id))
        user_session = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user_session:
            flash("Session expired. Please log in again.")
            return redirect(url_for('login'))

        return f(*args, **kwargs)
    return decorated_function

# task 7

def log_change(operation_type, table_name, changes):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open("change_log.txt", "a") as log_file:
        log_file.write(f"[{timestamp}] {operation_type} on {table_name}\n")
        for key, value in changes.items():
            log_file.write(f"    {key}: {value}\n")
        log_file.write("\n")

def execute_and_log_query(query, params=None, table_name=None, operation_type=None):
    connection = get_db_connection()
    cursor = connection.cursor()

    # Fetch pre-change data
    pre_state = {}
    if operation_type in ['UPDATE', 'DELETE'] and 'WHERE' in query:
        where_clause = query.split('WHERE')[1]
        cursor.execute(f"SELECT * FROM {table_name} WHERE {where_clause}", params)
        result = cursor.fetchone()
        if result:
            columns = [desc[0] for desc in cursor.description]
            pre_state = dict(zip(columns, result))

    # Execute query
    cursor.execute(query, params or ())

    # Fetch post-change data
    post_state = {}
    if operation_type == 'INSERT':
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            columns = [desc[0] for desc in cursor.description]
            post_state = dict(zip(columns, result))
    elif operation_type == 'UPDATE' and 'WHERE' in query:
        where_clause = query.split('WHERE')[1]
        cursor.execute(f"SELECT * FROM {table_name} WHERE {where_clause}", params)
        result = cursor.fetchone()
        if result:
            columns = [desc[0] for desc in cursor.description]
            post_state = dict(zip(columns, result))

    # Detect and log changes
    changes = {}
    if operation_type == 'INSERT':
        changes = post_state
    elif operation_type == 'UPDATE':
        for key in post_state:
            if post_state[key] != pre_state.get(key):
                changes[key] = {'old': pre_state.get(key), 'new': post_state[key]}
    elif operation_type == 'DELETE':
        changes = pre_state

    log_change(operation_type, table_name, changes)

    connection.commit()
    cursor.close()
    connection.close()

@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if session.get('role') == 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get member ID if not already in session
        if 'member_id' not in session:
            cursor.execute("SELECT Member_ID FROM MEMBERS WHERE Email = %s", (session['username'],))
            member = cursor.fetchone()
            if member:
                session['member_id'] = member['Member_ID']

        member_id = session.get('member_id')
        if not member_id:
            flash("Member information not found", "danger")
            return redirect(url_for('logout'))

        # Get counts for dashboard cards
        cursor.execute("""
            SELECT COUNT(*) as count FROM TRANSACTIONS 
            WHERE Member_ID = %s AND Status = 'Issued'
        """, (member_id,))
        current_issues = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count FROM TRANSACTIONS 
            WHERE Member_ID = %s AND Status = 'Issued' AND Due_Date < CURDATE()
        """, (member_id,))
        overdue_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count FROM RESERVATIONS 
            WHERE Member_ID = %s AND Status = 'Active'
        """, (member_id,))
        active_reservations = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COALESCE(SUM(Fine_Amount), 0) as total FROM OVERDUE_FINE 
            WHERE Member_Id = %s AND Payment_Status != 'Paid'
        """, (member_id,))
        total_fines = cursor.fetchone()['total']

        # Get recent notifications
        cursor.execute("""
            SELECT * FROM NOTIFICATIONS 
            WHERE Member_ID = %s 
            ORDER BY Notification_Date DESC 
            LIMIT 5
        """, (member_id,))
        notifications = cursor.fetchall()

        return render_template(
            'user_dashboard.html',
            current_issues=current_issues,
            overdue_count=overdue_count,
            active_reservations=active_reservations,
            total_fines=total_fines,
            notifications=notifications,
            active_page='dashboard'
        )
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return redirect(url_for('logout'))
    finally:
        cursor.close()
        conn.close()

@app.route('/user_books')
@login_required
def user_books():
    search_query = request.args.get('query', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT bd.Book_ID, bd.Book_Name, bd.Book_Author, ba.Availability 
            FROM BOOKS_DETAILS bd
            JOIN BOOK_AVAILABILITY ba ON bd.Book_ID = ba.BookID
            WHERE bd.Book_Name LIKE %s OR bd.Book_Author LIKE %s
            ORDER BY bd.Book_Name
        """
        search_param = f"%{search_query}%"
        cursor.execute(query, (search_param, search_param))
        books = cursor.fetchall()

        return render_template(
            'user_books.html',
            books=books,
            active_page='books'
        )
    except Exception as e:
        flash(f"Error loading books: {str(e)}", "danger")
        return redirect(url_for('user_dashboard'))
    finally:
        cursor.close()
        conn.close()

@app.route('/user_issued')
@login_required
def user_issued():
    if 'member_id' not in session:
        flash("Please log in to view issued books", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT 
                bd.Book_Name as title,
                bd.Book_Author as author,
                t.Issue_Date as issue_date,
                t.Due_Date as due_date,
                t.Status as status,
                t.Due_Date < CURDATE() as is_overdue
            FROM TRANSACTIONS t
            JOIN BOOKS_DETAILS bd ON t.Book_ID = bd.Book_ID
            WHERE t.Member_ID = %s
            ORDER BY t.Issue_Date DESC
        """
        cursor.execute(query, (session['member_id'],))
        issued_books = cursor.fetchall()

        return render_template(
            'user_issued.html',
            issued_books=issued_books,
            active_page='issued'
        )
    except Exception as e:
        flash(f"Error loading issued books: {str(e)}", "danger")
        return redirect(url_for('user_dashboard'))
    finally:
        cursor.close()
        conn.close()
        
@app.route('/user_digital')
@login_required
def user_digital():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM DIGITAL_BOOKS 
            ORDER BY Digital_Downloads DESC
        """)
        ebooks = cursor.fetchall()

        return render_template(
            'user_digital.html',
            ebooks=ebooks,
            active_page='digital'
        )
    except Exception as e:
        flash(f"Error loading digital books: {str(e)}", "danger")
        return redirect(url_for('user_dashboard'))
    finally:
        cursor.close()
        conn.close()        

@app.route('/user_history')
@login_required
def user_history():
    if 'member_id' not in session:
        flash("Please log in to view reading history", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                b.Book_Name, 
                b.Book_Author, 
                t.Issue_Date, 
                t.Return_Date
            FROM TRANSACTIONS t
            JOIN BOOKS_DETAILS b ON t.Book_ID = b.Book_ID
            WHERE t.Member_ID = %s
            ORDER BY t.Issue_Date DESC
        """, (session['member_id'],))
        history = cursor.fetchall()

        return render_template(
            'user_history.html',
            history=history,
            active_page='history'
        )
    except Exception as e:
        flash(f"Error loading reading history: {str(e)}", "danger")
        return redirect(url_for('user_dashboard'))
    finally:
        cursor.close()
        conn.close()
        
       
@app.route('/user_fines')
@login_required
def user_fines():
    if 'member_id' not in session:
        flash("Please log in to view fines", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                f.Fine_ID,
                b.Book_Name,
                f.Due_Date,
                f.Return_Date,
                f.Fine_Amount,
                f.Payment_Status
            FROM OVERDUE_FINE f
            JOIN BOOKS_DETAILS b ON f.BookID = b.Book_ID
            WHERE f.Member_Id = %s
            ORDER BY f.Due_Date DESC
        """, (session['member_id'],))
        fines = cursor.fetchall()

        return render_template(
            'user_fines.html',
            fines=fines,
            active_page='fines'
        )
    except Exception as e:
        flash(f"Error loading fines: {str(e)}", "danger")
        return redirect(url_for('user_dashboard'))
    finally:
        cursor.close()
        conn.close()       
   
   
@app.route('/user_notifications')
@login_required
def user_notifications():
    if 'member_id' not in session:
        flash("Please log in to view notifications", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM NOTIFICATIONS 
            WHERE Member_ID = %s 
            ORDER BY Notification_Date DESC
        """, (session['member_id'],))
        all_notifications = cursor.fetchall()

        return render_template(
            'user_notifications.html',
            all_notifications=all_notifications,
            active_page='notifications'
        )
    except Exception as e:
        flash(f"Error loading notifications: {str(e)}", "danger")
        return redirect(url_for('user_dashboard'))
    finally:
        cursor.close()
        conn.close()      

@app.route('/user_book_detail/<int:book_id>')
@login_required
def user_book_detail(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get book details
        cursor.execute("""
            SELECT 
                bd.*, 
                ba.Quantity_Remaining, 
                ba.Availability 
            FROM BOOKS_DETAILS bd
            JOIN BOOK_AVAILABILITY ba ON bd.Book_ID = ba.BookID
            WHERE bd.Book_ID = %s
        """, (book_id,))
        book = cursor.fetchone()

        if not book:
            flash('Book not found!', 'danger')
            return redirect(url_for('user_books'))

        # Get reviews
        cursor.execute("""
            SELECT 
                r.Review, 
                r.Rating, 
                r.Review_Date,
                m.Name 
            FROM REVIEWS_TABLE r
            JOIN MEMBERS m ON r.Member_ID = m.Member_ID
            WHERE r.Book_ID = %s
            ORDER BY r.Review_Date DESC
        """, (book_id,))
        reviews = cursor.fetchall()

        return render_template(
            'user_book_detail.html',
            book=book,
            reviews=reviews,
            active_page='books'
        )
    except Exception as e:
        flash(f"Error loading book details: {str(e)}", "danger")
        return redirect(url_for('user_books'))
    finally:
        cursor.close()
        conn.close()

@app.route('/submit_review/<int:book_id>', methods=['POST'])
@login_required
def submit_review(book_id):
    if 'member_id' not in session:
        flash("Please log in to submit a review", "danger")
        return redirect(url_for('login'))

    review_text = request.form.get('review')
    rating = request.form.get('rating')

    if not review_text or not rating:
        flash("Please provide both a rating and review text", "warning")
        return redirect(url_for('user_book_detail', book_id=book_id))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Insert review
        cursor.execute("""
            INSERT INTO REVIEWS_TABLE 
            (Book_ID, Member_ID, Review_Date, Review, Rating)
            VALUES (%s, %s, CURDATE(), %s, %s)
        """, (book_id, session['member_id'], review_text, rating))

        # Update total reviews count
        cursor.execute("""
            UPDATE BOOKS_DETAILS 
            SET Total_Reviews = Total_Reviews + 1 
            WHERE Book_ID = %s
        """, (book_id,))

        conn.commit()
        flash('Review submitted successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Error submitting review: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('user_book_detail', book_id=book_id))


@app.route('/reserve_book/<int:book_id>', methods=['POST'])
@login_required
def reserve_book(book_id):
    if 'member_id' not in session:
        flash("Please log in to reserve books", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if book is available
        cursor.execute("""
            SELECT Quantity_Remaining FROM BOOK_AVAILABILITY 
            WHERE BookID = %s FOR UPDATE
        """, (book_id,))
        result = cursor.fetchone()

        if not result:
            flash('Book not found!', 'danger')
            return redirect(url_for('user_books'))

        if result['Quantity_Remaining'] > 0:
            flash('Book is available for immediate issue!', 'info')
            return redirect(url_for('user_books'))

        # Check existing reservations
        cursor.execute("""
            SELECT * FROM RESERVATIONS 
            WHERE Book_ID = %s AND Member_ID = %s AND Status = 'Active'
        """, (book_id, session['member_id']))
        if cursor.fetchone():
            flash('You already have an active reservation for this book!', 'warning')
            return redirect(url_for('user_books'))

        # Create reservation
        cursor.execute("""
            INSERT INTO RESERVATIONS 
            (Member_ID, Book_ID, Reservation_Date, Expiry_Date, Status)
            VALUES (%s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 7 DAY), 'Active')
        """, (session['member_id'], book_id))
        
        # Add notification
        cursor.execute("""
            INSERT INTO NOTIFICATIONS 
            (Member_ID, Message, Notification_Date, Type)
            VALUES (%s, %s, NOW(), %s)
        """, (session['member_id'], f"Book reservation created (ID: {book_id})", "Book Available"))
        
        conn.commit()
        flash('Book reserved successfully! You will be notified when available.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Error reserving book: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('user_books'))

@app.route('/pay_fine/<int:fine_id>', methods=['POST'])
@login_required
def pay_fine(fine_id):
    if 'member_id' not in session:
        flash("Please log in to pay fines", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verify the fine belongs to the current user
        cursor.execute("""
            SELECT Member_Id FROM OVERDUE_FINE 
            WHERE Fine_ID = %s
        """, (fine_id,))
        result = cursor.fetchone()

        if not result or result[0] != session['member_id']:
            flash("Invalid fine ID", "danger")
            return redirect(url_for('user_fines'))

        # Update fine payment status
        cursor.execute("""
            UPDATE OVERDUE_FINE 
            SET Payment_Status = 'Paid', 
                Payment_Date = CURDATE() 
            WHERE Fine_ID = %s
        """, (fine_id,))

        # Add notification
        cursor.execute("""
            INSERT INTO NOTIFICATIONS 
            (Member_ID, Message, Notification_Date, Type)
            VALUES (%s, %s, NOW(), %s)
        """, (session['member_id'], f"Fine paid (ID: {fine_id})", "Payment Confirmation"))

        conn.commit()
        flash('Fine paid successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Error paying fine: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('user_fines'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM login WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                session_id = str(uuid.uuid4())

                # Store member_id for regular users
                if user['role'] != 'admin':
                    cursor.execute("SELECT Member_ID FROM MEMBERS WHERE Email = %s", (username,))
                    member = cursor.fetchone()
                    if member:
                        session['member_id'] = member['Member_ID']

                cursor.execute(
                    "INSERT INTO sessions (username, session_id, role) VALUES (%s, %s, %s)",
                    (username, session_id, user['role'])
                )
                conn.commit()

                session['username'] = user['username']
                session['role'] = user['role']
                session['session_id'] = session_id

                flash('Login successful!')
                
                # Redirect based on role
                if user['role'] == 'admin':
                    return redirect(url_for('dashboard'))
                else:
                    return redirect(url_for('user_dashboard'))  # Correct - goes to dashboard route
            
            error = "Invalid username or password"
        except Exception as e:
            error = f"Login error: {str(e)}"
        finally:
            cursor.close()
            conn.close()
    
    return render_template('login.html', error=error)

from functools import wraps   
from flask import redirect, url_for, flash  

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print("Checking admin access...")  # 🔍 Console log
        print(f"Session role: {session.get('role')}")  # Shows current role in terminal

        if 'role' not in session or session['role'] != 'admin':
            print("Access denied. Not an admin.")  # ❌ Console log
            flash("Admin access required.")
            return redirect(url_for('dashboard'))

        print("Access granted. Admin verified.")  # ✅ Console log
        return f(*args, **kwargs)
    return decorated_function

@app.route('/dashboard') 
def dashboard(): 
    if 'username' in session:
        return render_template('dashboard.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/view_table/', methods=['GET', 'POST'])
@admin_required
def view_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    print("Connected to the database")

    # Get all table names
    cursor.execute("SHOW TABLES")
    table_names = [row[0] for row in cursor.fetchall()]

    selected_table = None
    columns = []
    rows = []

    if request.method == 'POST':
        selected_table = request.form.get('table_name')
        try:
            cursor.execute(f"SELECT * FROM {selected_table}")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        except Exception as e:
            flash(f"Error loading table {selected_table}: {e}", 'danger')

    cursor.close()
    conn.close()
    return render_template('view_table.html', table_names=table_names, selected_table=selected_table, columns=columns, rows=rows)
 

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if user already exists 
        cursor.execute('SELECT * FROM login WHERE username = %s', (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Username already exists. Please choose a different one.')
            cursor.close()
            conn.close()
            return redirect(url_for('register'))

        cursor.execute('INSERT INTO login (username, password, role) VALUES (%s, %s, %s)',(username, hashed_password, 'user'))
        conn.commit()

        cursor.close()
        conn.close()

        # Use execute_and_log_query to log the INSERT
        query = 'INSERT INTO login (username, password) VALUES (%s, %s)'
        params = (username, hashed_password)
        execute_and_log_query(query, params, table_name="login", operation_type="INSERT")

        flash('Registration successful. Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/add_member', methods=['GET', 'POST'])
@admin_required
def add_member():
    if request.method == 'POST':
        name = request.form['name']
        dob = request.form['dob']
        email = request.form['email']
        contact = request.form['contact']
        program = request.form['program']
        branch = request.form['branch']
        admission_year = request.form['admission_year']
        graduation_year = request.form['graduation_year']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into member table
        insert_member = """
            INSERT INTO MEMBERS 
            (Name, Date_of_Birth, Email, Contact_Details, Program, Branch, Year_of_Admission, Year_of_Graduation) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_member, (name, dob, email, contact, program, branch, admission_year, graduation_year))
        conn.commit()

        # Get the newly inserted Member_ID (assuming it's auto-incremented)

        # Create login credentials
        username = email  # or f"member{member_id}" or just use the name
        raw_password = "welcome123"
        hashed_password = generate_password_hash(raw_password)

        # Insert into login table
        insert_login = "INSERT INTO login (username, password) VALUES (%s, %s)"
        cursor.execute(insert_login, (username, hashed_password))
        conn.commit()

        cursor.close()
        conn.close()

        message = f"Member added successfully! Login credentials: Username = {username}, Password = {raw_password}"
        return render_template('add_member.html', message=message)

    return render_template('add_member.html')


@app.route('/add_member_cims', methods=['GET', 'POST'])
@admin_required
def add_member_cims():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        dob = request.form['dob']

        try:
            # Generate a unique password
            raw_password = generate_unique_password()
            hashed_password = generate_password_hash(raw_password)

            # Insert into CIMS database
            cims_conn = get_cims_connection()
            cims_cursor = cims_conn.cursor()

            cims_cursor.execute("""
                INSERT INTO members (username, email, dob)
                VALUES (%s, %s, %s)
            """, (username, email, dob))
            cims_conn.commit()

            # Insert into local login table
            local_conn = get_db_connection()
            local_cursor = local_conn.cursor()

            local_cursor.execute("""
                INSERT INTO login (username, password, role)
                VALUES (%s, %s, %s)
            """, (email, hashed_password, 'user'))

            local_conn.commit()

            cims_cursor.close()
            cims_conn.close()
            local_cursor.close()
            local_conn.close()

            flash(f'Member added successfully! Credentials -> Username: {email}, Password: {raw_password}', 'success')
            return redirect(url_for('dashboard'))

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return render_template('add_member_cims.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/authUser', methods=['POST'])
def auth_user():
    data = request.json

    if not data or 'username' not in data or 'password' not in data:
        return {'status': 'fail', 'message': 'Missing credentials'}, 400

    username = data['username']
    password = data['password'] 

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM login WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user['password'], password):
        token = str(uuid.uuid4())  
        session['username'] = username
        session['token'] = token
        return {'status': 'success', 'token': token}, 200
    else:
        return {'status': 'fail', 'message': 'Invalid credentials'}, 401
    

@app.route('/delete_member', methods=['GET', 'POST'])
@admin_required
def delete_member():
    if request.method == 'POST':
        username = request.form['username']

        conn = get_db_connection()
        cursor = conn.cursor()

        # First delete from login table
        cursor.execute("DELETE FROM login WHERE username = %s", (username,))

        # Then delete from members table
        cursor.execute("DELETE FROM MEMBERS WHERE Email = %s", (username,))

        conn.commit()
        cursor.close()
        conn.close()

        flash('Member deleted successfully!')

    return render_template('delete_member.html')

  
@app.route('/data')
@admin_required
def data_dashboard():
    table_names = ['MEMBERS', 'login', 'BOOKS_DETAILS', 'BOOK_AVAILABILITY', 'DIGITAL_BOOKS']
    return render_template('data_dashboard.html', tables=table_names)

def isValidSession(session_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sessions WHERE session_id = %s", (session_id,))
    result = cursor.fetchone()
    conn.close()
    # print("Session ID:", session_id)
    # print(result)
    return result is not None

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data['username']
    password = data['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM login WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user['password'], password):
        session_id = str(uuid.uuid4())
        session['username'] = username
        session['token'] = session_id
        return jsonify({'status': 'success', 'token': session_id}), 200
    else:
        return jsonify({'status': 'fail', 'message': 'Invalid credentials'}), 401
    

@app.route('/books', methods=['POST'])
def ADD_book():
    data = request.get_json()
    session_id = request.headers.get('Session-ID')

    print("Headers:", request.headers)
    print("JSON Body:", request.get_json())


    # Session check
    print("Session ID:", session_id)
    # print(isValidSession(session_id))
    # print(is_admin(session_id))
    if not isValidSession(session_id) or not is_admin(session_id):
        log_unauthorized_access("POST /books", "add_book")
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    # Get book fields
    name = data.get('Book_Name')
    author = data.get('Book_Author')
    year = data.get('Book_Publication_Year')
    reviews = data.get('Total_Reviews', 0)  # Default to 0 if not provided
    quantity = data.get('Quantity')
    genre = data.get('BOOK_GENRE')

    # Insert into DB
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO BOOKS_DETAILS
            (Book_Name, Book_Author, Book_Publication_Year, Total_Reviews, Quantity, BOOK_GENRE) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, author, year, reviews, quantity, genre))

        conn.commit()
        conn.close()
        return jsonify({'message': 'Book added successfully'}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/borrow/<int:book_id>', methods=['POST'])
def borrow_book(book_id):
    session_id = request.headers.get('Session-ID')

    if not isValidSession(session_id):
        log_unauthorized_access("POST /borrow", f"book_id={book_id}")
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check current quantity
        cursor.execute("SELECT Quantity_Remaining FROM BOOK_AVAILABILITY WHERE BookID = %s", (book_id,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return jsonify({'error': 'Book not found'}), 404

        quantity = result[0]

        if quantity <= 0:
            conn.close()
            return jsonify({'error': 'Book not available'}), 400

        # Update quantity
        new_quantity = quantity - 1
        availability = 'Available' if new_quantity > 0 else 'Not Available'

        cursor.execute("""
            UPDATE BOOK_AVAILABILITY
            SET Quantity_Remaining = %s, Availability = %s
            WHERE BookID = %s
        """, (new_quantity, availability, book_id))
        conn.commit()
        conn.close()

        return jsonify({'message': 'Book borrowed successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/books', methods=['GET'])
def get_books():
    session_id = request.headers.get('Session-ID')
    if not isValidSession(session_id):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM BOOKS_DETAILS")
    books = cursor.fetchall()
    conn.close()
    return jsonify(books), 200



@app.route('/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    session_id = request.headers.get('Session-ID')

    if not isValidSession(session_id) or not is_admin(session_id):
        log_unauthorized_access("PUT /books", "update_book")
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        fields = []
        values = []

        for key in ['Book_Name', 'Book_Author', 'Book_Publication_Year', 'Total_Reviews', 'Quantity', 'BOOK_GENRE']:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])

        if not fields:
            return jsonify({'error': 'No fields to update'}), 400

        values.append(book_id)
        query = f"UPDATE BOOKS_DETAILS SET {', '.join(fields)} WHERE Book_ID = %s"
        cursor.execute(query, tuple(values)) 

        conn.commit()
        conn.close()

        if cursor.rowcount == 0:
            return jsonify({'error': 'Book not found'}), 404

        return jsonify({'message': 'Book updated successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/notifications', methods=['POST'])
def send_notification():
    data = request.get_json()
    session_id = request.headers.get('Session-ID')

    if not isValidSession(session_id) or not is_admin(session_id):
        log_unauthorized_access("POST /notifications", "send_notification")
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO NOTIFICATIONS (Member_ID, Message, Notification_Date, Type)
            VALUES (%s, %s, NOW(), %s)
        """, (data['Member_ID'], data['Message'], data['Type']))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Notification sent successfully'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/available_books_page')
@login_required
def available_books_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT 
        bd.Book_Name AS title,
        bd.Book_Author AS author,
        ba.Availability AS available
    FROM 
        BOOKS_DETAILS bd
    JOIN 
        BOOK_AVAILABILITY ba ON bd.book_ID = ba.bookID;
    """

    cursor.execute(query)
    books = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('available_books.html', books=books)


@app.route('/view_issued_books')
@login_required
def view_issued_books():
    member_id = session.get('member_id')  # Ensure this is stored during login

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT 
        bd.Book_Name AS title,
        t.Issue_Date AS issue_date,
        t.Due_Date AS due_date
    FROM 
        TRANSACTIONS t
    JOIN 
        BOOKS_DETAILS bd ON t.Book_ID = bd.Book_ID
    WHERE 
        t.Member_ID = %s AND t.Status = 'Issued';
    """

    cursor.execute(query, (member_id,))
    issued_books = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('view_issued_books.html', issued_books=issued_books)


from datetime import date, timedelta
from flask import flash

@app.route('/issue_book', methods=['POST'])
@login_required
def issue_book():
    member_id = current_user.id  # Assuming you're using Flask-Login
    book_id = request.form.get('book_id')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check availability
    cursor.execute("SELECT Quantity_Remaining FROM BOOK_AVAILABILITY WHERE BookID = %s", (book_id,))
    book = cursor.fetchone()

    if book and book['Quantity_Remaining'] > 0:
        # Set due date (e.g., 14 days from now)
        from datetime import datetime, timedelta
        issue_date = datetime.now().date()
        due_date = issue_date + timedelta(days=14)

        # Insert into TRANSACTIONS
        cursor.execute("""
            INSERT INTO TRANSACTIONS (Member_ID, Book_ID, Issue_Date, Due_Date)
            VALUES (%s, %s, %s, %s)
        """, (member_id, book_id, issue_date, due_date))

        # Update availability
        cursor.execute("""
            UPDATE BOOK_AVAILABILITY
            SET Quantity_Remaining = Quantity_Remaining - 1,
                Availability = CASE WHEN Quantity_Remaining - 1 > 0 THEN 'Available' ELSE 'Not Available' END
            WHERE BookID = %s
        """, (book_id,))

        conn.commit()
        flash('Book issued successfully!', 'success')
    else:
        flash('Book is currently not available.', 'danger')

    cursor.close()
    conn.close()
    return redirect(url_for('available_books_page'))
   

if __name__ == '__main__':
    app.run(debug=True)            