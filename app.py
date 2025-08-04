from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import  request, jsonify
import mysql.connector
from flask_login import current_user
import datetime

from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from session_utils import log_unauthorized_access,write_log_to_file
from utils import send_otp
import random
import string
from utils import send_otp

from dotenv import load_dotenv
import os
print("c")
load_dotenv()
print(os.getenv('secret_key'))
def generate_unique_password(length=10):
	"""
	Generates a random alphanumeric password of given length.
	"""
	characters = string.ascii_letters + string.digits
	return ''.join(random.choices(characters, k=length))

app = Flask(__name__)
app.secret_key = os.getenv('secret_key') 
app.config['SECRET_KEY'] = 'your_secret_key'  # Set your own secret key here

print(app.secret_key)
db_config = {
	'host': os.getenv('DB_HOST'),
	'user': os.getenv('DB_USER'),
	'password': os.getenv('DB_PASSWORD'),
	'database': os.getenv('DB_NAME')
}

db_config_cims = {
	'host': os.getenv('DB_HOST'),
	'user': os.getenv('DB_USER'),
	'password': os.getenv('DB_PASSWORD'),
	'database': "cs432cims"
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

# def is_admin(session_id):
#     cims_conn = get_cims_connection()
#     cims_cursor = cims_conn.cursor()

#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)

#     try:
#         # Get username associated with the session
#         cursor.execute("SELECT username FROM sessions WHERE session_id = %s", (session_id,))
#         result = cursor.fetchone()

#         if result:
#             member_id = result['username']  # Use key since dictionary=True

#             # Check role in Login table of CIMS DB
#             cims_cursor.execute("SELECT Role FROM Login WHERE MemberID = %s", (member_id,))
#             role_result = cims_cursor.fetchone()

#             if role_result and role_result[0].lower() == 'admin':
#                 return True
#     finally:
#         # Make sure cursors and connections are closed
#         cursor.close()
#         conn.close()
#         cims_cursor.close()
#         cims_conn.close()

#     return False

def is_admin(session_id):
	cims_conn = get_cims_connection()
	cims_cursor = cims_conn.cursor(dictionary=True)

	try:
		# Step 1: Find the user with matching session ID in Login table
		cims_cursor.execute(
			"SELECT MemberID, Role, Expiry FROM Login WHERE Session = %s", 
			(session_id,)
		)
		result = cims_cursor.fetchone()
		print(result) # Debugging line

		if result:
			role = result['Role']
			expiry = result['Expiry']

			# Step 2: Check expiry
			if expiry and expiry > int(datetime.datetime.now().timestamp()):
				# Step 3: Check if admin
				if role.lower() == 'admin':
					return True

	finally:
		cims_cursor.close()
		cims_conn.close()

	return False



from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		session_id = session.get('session_id')
		username = session.get('username')
		print(f"Session ID: {session_id}, Username: {username} ibside login re	uied")  # Debugging line
		if not session_id or not username:
			flash("Please log in.")
			return redirect(url_for('login'))

		conn = get_cims_connection()
		cursor = conn.cursor(dictionary=True)
		cursor.execute("SELECT * FROM Login WHERE Session = %s", (session_id,))
		user_session = cursor.fetchone()
		cursor.close()
		conn.close()

		if not user_session:
			flash("Session expired. Please log in again.")
			return redirect(url_for('login'))

		return f(*args, **kwargs)
	return decorated_function

# task 6

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
		# Get member ID from session
		member_id = session.get('member_id')
		print(f"Member ID from session: {member_id}")  # Debugging line
		if not member_id:
			flash("Member information not found", "danger")
			print("Member information not found in session")
			return redirect(url_for('logout'))

		# Get counts for dashboard cards
		cursor.execute("""
			SELECT COUNT(*) as count FROM TRANSACTIONS 
			WHERE MemberID = %s AND Status = 'Issued'
		""", (member_id,))
		current_issues = cursor.fetchone()['count']

		cursor.execute("""
			SELECT COUNT(*) as count FROM TRANSACTIONS 
			WHERE MemberID = %s AND Status = 'Issued' AND Due_Date < CURDATE()
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
		print(f"Error loading dashboard: {str(e)}")
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

@app.route('/user_book_detail/<int:book_id>', methods=['GET', 'POST'])
@login_required
def user_book_detail(book_id):
	conn = get_db_connection()
	cursor = conn.cursor(dictionary=True)
	
	try:
		# Get book details
		cursor.execute("""
			SELECT bd.*, ba.Quantity_Remaining, ba.Availability
			FROM BOOKS_DETAILS bd
			JOIN BOOK_AVAILABILITY ba ON bd.Book_ID = ba.BookID
			WHERE bd.Book_ID = %s
		""", (book_id,))
		book = cursor.fetchone()

		if not book:
			flash('Book not found!', 'danger')
			return redirect(url_for('user_books'))

		# Handle review submission
		if request.method == 'POST':
			review_text = request.form.get('reviewText', '').strip()
			member_id = current_user.id
			
			if not review_text:
				flash('Review cannot be empty!', 'danger')
			elif len(review_text) > 1000:
				flash('Review is too long (max 1000 characters)', 'danger')
			else:
				try:
					# Get next Review_ID
					cursor.execute("SELECT IFNULL(MAX(Review_ID), 0) + 1 FROM REVIEWS_TABLE")
					next_id = cursor.fetchone()['IFNULL(MAX(Review_ID), 0) + 1']
					
					# Insert review with explicit column names
					cursor.execute("""
						INSERT INTO REVIEWS_TABLE 
						(Review_ID, Book_ID, Member_ID, Review_Date, Review) 
						VALUES (%s, %s, %s, CURRENT_DATE(), %s)
					""", (next_id, book_id, member_id, review_text))
					
					# Update review count
					cursor.execute("""
						UPDATE BOOKS_DETAILS 
						SET Total_Reviews = Total_Reviews + 1 
						WHERE Book_ID = %s
					""", (book_id,))
					
					conn.commit()
					flash('Review submitted successfully!', 'success')
				except Exception as e:
					conn.rollback()
					flash(f'Failed to submit review. Error: {str(e)}', 'danger')
					app.logger.error(f"Review submission failed: {str(e)}")
			
			return redirect(url_for('user_book_detail', book_id=book_id))

		# Get existing reviews
		cursor.execute("""
			SELECT r.*, m.Name 
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


def get_member_id_from_session(session_id):
	conn = get_cims_connection()
	cursor = conn.cursor(dictionary=True)
	cursor.execute("SELECT MemberID FROM Login WHERE Session = %s", (session_id,))
	result = cursor.fetchone()
	cursor.close()
	conn.close()
	return result['MemberID'] if result else None


@app.route('/pay_fine/<int:fine_id>', methods=['POST'])
def pay_fine(fine_id):
	session_id = request.headers.get('Session-ID')

	if not session_id or not isValidSession(session_id):
		return jsonify({'error': 'Unauthorized'}), 401

	member_id = get_member_id_from_session(session_id)

	conn = get_db_connection()
	cursor = conn.cursor()
	try:
		cursor.execute("""
			SELECT Member_Id FROM OVERDUE_FINE 
			WHERE Fine_ID = %s 
		""", (fine_id,))
		result = cursor.fetchone()

		if not result or result[0] != member_id:
			return jsonify({'error': 'Invalid fine ID'}), 403

		cursor.execute("""
			UPDATE OVERDUE_FINE 
			SET Payment_Status = 'Paid', 
				Payment_Date = CURDATE() 
			WHERE Fine_ID = %s
		""", (fine_id,))

		cursor.execute("""
			INSERT INTO NOTIFICATIONS 
			(Member_ID, Message, Notification_Date, Type)
			VALUES (%s, %s, NOW(), %s)
		""", (member_id, f"Fine paid (ID: {fine_id})", "Overdue Fine"))

		conn.commit()
		return jsonify({'message': 'Fine paid successfully!'}), 200

	except Exception as e:
		conn.rollback()
		return jsonify({'error': str(e)}), 500
	finally:
		cursor.close()
		conn.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
	error = None

	if request.method == 'POST':
		email = request.form['username']
		password = request.form['password']

		conn = get_cims_connection()
		cursor = conn.cursor(dictionary=True)

		try:
			# Step 1: Get MemberID from email
			cursor.execute("SELECT ID FROM members WHERE emailID = %s", (email,))
			member_row = cursor.fetchone()

			if not member_row:
				error = "No account found with this email."
				return render_template('login.html', error=error)

			member_id = str(member_row['ID'])

			# Step 2: Check Login table using MemberID
			cursor.execute("SELECT * FROM Login WHERE MemberID = %s", (member_id,))
			user = cursor.fetchone()
			print(f"user found with these credentials : {user}")

			if user and check_password_hash(user['Password'], password):
				session_id = str(uuid.uuid4())
				expiry_time = datetime.datetime.now() + datetime.timedelta(hours=2)
				expiry_unix = int(expiry_time.timestamp())
				print(expiry_time)
				print(f"valid credentials, session id : {session_id}")

				# Save session details to Flask session
				

				# ✅ Step 3: Update CIMS Login table with session ID and expiry
				connection = get_cims_connection()
				cursor = connection.cursor()
				cursor.execute(
					"UPDATE Login SET Session = %s, Expiry = %s WHERE MemberID = %s",
					(session_id, expiry_unix, member_id)
				)
				print("Session updated in DB")
				print("login successful")
				connection.commit()
				cursor.close()
				connection.close()


				# ✅ Step 4: Store session in local 'sessions' table (optional)
				# local_conn = get_db_connection()
				# local_cursor = local_conn.cursor()
				# local_cursor.execute(
				# 	"INSERT INTO sessions (username, session_id, role) VALUES (%s, %s, %s)",
				# 	(email, session_id, user['Role'])
				# )
				# local_conn.commit()
				# local_cursor.close()
				# local_conn.close()

				flash('Login successful!')
				print(user['Role'])
				# if user['Role'] == 'admin':
				# 	print("Admin access granted, now going to dashboard")
				# 	session['member_id'] = member_id
				# 	session['username'] = email
				# 	session['role'] = user['Role']
				# 	session['session_id'] = session_id
				# 	return redirect(url_for('dashboard'))
				# else:
				# 	print("User access granted, now going to user dashboard")
				# 	return redirect(url_for('user_dashboard'))

				if user['Role'] == 'admin':
					print("Admin access granted, now going to dashboard")
					session['member_id'] = member_id
					session['username'] = email
					session['role'] = str(user['Role'])
					session['session_id'] = session_id

					print("Session ID:", session['session_id'])
					print("Member ID:", session['member_id'])
					print("Username:", session['username'])
					print("Role:", session['role'])
					return redirect(url_for('dashboard'))
				else:
					print("User access granted, now going to user dashboard")
					session['member_id'] = member_id
					session['username'] = email
					session['role'] = user['Role']
					session['session_id'] = session_id
					print("Session ID:", session['session_id'])
					print("Member ID:", session['member_id'])
					print("Username:", session['username'])
					print("Role:", session['role'])
					print(dict(session))
					return redirect(url_for('user_dashboard'))

		except Exception as e:
			error = f"Login error: {str(e)}"

		finally:
			cursor.close()
			conn.close()

	return render_template('login.html', error=error)


# from werkzeug.security import generate_password_hash
# import uuid
# import time

# @app.route('/add_admin')
# def add_admin():
#     try:
#         username = "mahi"  # Replace with your name
#         email = "msd7@gmail.com"  # Replace with your desired email
#         dob = "1983-07-07"  # Replace if needed
#         raw_password = "12345"  # Replace or generate dynamically
#         hashed_password = generate_password_hash(raw_password)
#         session_token = None
#         expiry = 0  # Default expiry time; can update on login
#         role = "admin"

#         # Connect to CIMS database
#         cims_conn = get_cims_connection()
#         cims_cursor = cims_conn.cursor()

#         # Step 1: Insert into members table
#         cims_cursor.execute("""
#             INSERT INTO members (UserName, emailID, DoB)
#             VALUES (%s, %s, %s)
#         """, (username, email, dob))
#         cims_conn.commit()

#         # Step 2: Fetch newly created MemberID (ID column)
#         cims_cursor.execute("SELECT ID FROM members WHERE emailID = %s", (email,))
#         result = cims_cursor.fetchone()
#         if not result:
#             return "❌ Member insertion failed."
#         member_id = str(result[0])  # Convert to string to match Login table MemberID type

#         # Step 3: Insert into Login table
#         cims_cursor.execute("""
#             INSERT INTO Login (MemberID, Password, Session, Expiry, Role)
#             VALUES (%s, %s, %s, %s, %s)
#         """, (member_id, hashed_password, session_token, expiry, role))
#         cims_conn.commit()

#         cims_cursor.close()
#         cims_conn.close()

#         return f"✅ Admin created! Login with:\nEmail: {email}\nPassword: {raw_password}"

#     except Exception as e:
#         return f"❌ Error: {str(e)}"


from functools import wraps   
from flask import redirect, url_for, flash  

def admin_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		print("Checking admin access...")  # 🔍 Console log
		# Shows current role in terminal

		if 'role' not in session or session['role'] != 'admin':
			print("Access denied. Not an admin.")  # ❌ Console log
			flash("Admin access required.")
			msg = f"Unauthorized access attempt detected. by user: {session.get('username')} with session ID: {session.get('session_id')}"
			write_log_to_file(msg, str(datetime.datetime.now()))
			log_unauthorized_access(session.get('session_id'), session.get('username'))
			return jsonify({'error': 'Unauthorized access','message':'you are not an admin'}),403

		print("Access granted. Admin verified.")  # ✅ Console log
		return f(*args, **kwargs)
	return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
	if request.method == 'POST':
		username = request.form['username']    # Full name
		email = request.form['email']          # Email (used to login)
		dob = request.form['dob']              # Date of birth
		password = request.form['password']

		hashed_password = generate_password_hash(password)
		group_id = 8

		conn = get_cims_connection()
		cursor_cims = conn.cursor(dictionary=True)
		conn2 = get_db_connection();
		cursor_db = conn2.cursor(dictionary=True);
		print("Connected to the database")

		try:
			# Check if email already exists in members table
			cursor_cims.execute("SELECT * FROM members WHERE emailID = %s", (email,))
			existing_member = cursor_cims.fetchone()

			if existing_member:
				flash('User with this email already exists.')
				return redirect(url_for('register'))

			# Insert into members table
			cursor_cims.execute(
				"INSERT INTO members (UserName, emailID, DoB) VALUES (%s, %s, %s)",
				(username, email, dob)
			)

			conn.commit()

			# Get the newly inserted member's ID
			cursor_cims.execute("SELECT ID FROM members WHERE emailID = %s", (email,))
			member = cursor_cims.fetchone()
			member_id = member['ID']

			# Insert into Login table
			cursor_cims.execute(
				"INSERT INTO Login (MemberID, Password, Role) VALUES (%s, %s, %s)",
				(member_id, hashed_password, 'user')
			)
			conn.commit()


			# Insert into MemberGroupMapping table
			cursor_cims.execute(
				"INSERT INTO MemberGroupMapping (MemberID, GroupID) VALUES (%s, %s)",
				(member_id, group_id)
			)
			conn.commit()

			current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			cursor_db.execute(
	"INSERT INTO SYS_LOGS (Action, Timestamp) VALUES (%s, %s)",
	(f"New user registered: {email}", current_time)
)           
			print("Log entry created in SYS_LOGS table")
			write_log_to_file(f"New user registered: {email}", current_time)  # Log to file
			conn2.commit()

			flash('Registration successful. Please log in.')
			return redirect(url_for('login'))

		except Exception as e:
			conn.rollback()
			print(f"Error: {str(e)}")
			flash(f"Registration failed: {str(e)}")

		finally:
			cursor_db.close()
			conn2.close()
			cursor_cims.close()
			conn.close()

	return render_template('register.html')



@app.route('/dashboard') 
def dashboard(): 
	print("Checking admin access...")  # 🔍 Console lo
	print(session.get('role'))  # Shows current role in terminal
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
 




# @app.route('/add_member', methods=['GET', 'POST'])
# @admin_required
# def add_member():
#     if request.method == 'POST':
#         name = request.form['name']
#         dob = request.form['dob']
#         email = request.form['email']
#         contact = request.form['contact']
#         program = request.form['program']
#         branch = request.form['branch']
#         admission_year = request.form['admission_year']
#         graduation_year = request.form['graduation_year']

#         conn = get_db_connection()
#         cursor = conn.cursor()

#         # Insert into member table
#         insert_member = """
#             INSERT INTO MEMBERS 
#             (Name, Date_of_Birth, Email, Contact_Details, Program, Branch, Year_of_Admission, Year_of_Graduation) 
#             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
#         """
#         cursor.execute(insert_member, (name, dob, email, contact, program, branch, admission_year, graduation_year))
#         conn.commit()

#         # Get the newly inserted Member_ID (assuming it's auto-incremented)

#         # Create login credentials
#         username = email  # or f"member{member_id}" or just use the name
#         raw_password = "welcome123"
#         hashed_password = generate_password_hash(raw_password)

#         # Insert into login table
#         insert_login = "INSERT INTO login (username, password) VALUES (%s, %s)"
#         cursor.execute(insert_login, (username, hashed_password))
#         conn.commit()

#         cursor.close()
#         conn.close()

#         message = f"Member added successfully! Login credentials: Username = {username}, Password = {raw_password}"
#         return render_template('add_member.html', message=message)

#     return render_template('add_member.html')


@app.route('/add_member', methods=['GET', 'POST'])
@admin_required
def add_member():
	if request.method == 'POST':
		username = request.form['username']
		email = request.form['email']
		dob = request.form['dob']

		try:
			# Generate a unique password
			raw_password = generate_unique_password()
			with open('output.txt', 'a') as file:
				file.write(f"{raw_password}, {email}")

			# Hash the password
			hashed_password = generate_password_hash(raw_password)

			# Connect to CIMS DB
			cims_conn = get_cims_connection()
			cims_cursor = cims_conn.cursor()

			# Insert member into the members table
			cims_cursor.execute("""
				INSERT INTO members (UserName, emailID, DoB)
				VALUES (%s, %s, %s)
			""", (username, email, dob))
			cims_conn.commit()

			# Get the newly created Member
			cims_cursor.execute("SELECT LAST_INSERT_ID()")
			member_id = cims_cursor.fetchone()[0]
			message = f"""
Dear User,

Welcome to the Centralized Information Management System (CIMS).

We are pleased to inform you that your account has been successfully created. Below are your login credentials for accessing the CIMS portal:

----------------------------------------
Username : {email}
Password : {raw_password}
----------------------------------------

For security purposes, please ensure that you change your password after logging in for the first time.

If you have any questions or face any issues, feel free to contact the system administrator.

Best regards,  
Library Management Team
"""
			send_otp(email, "Your CIMS Portal Login Credentials", message)


			cims_conn.commit()

			# ✅ Write log to file
			write_log_to_file(f"Admin added new member: {username} ({email}) with MemberID: {member_id}")

			# Close the connection
			cims_cursor.close()
			cims_conn.close()

			flash(f'Member added successfully! Credentials -> MemberID: {member_id}, Password: {raw_password}', 'success')
			return redirect(url_for('dashboard'))

		except Exception as e:
			write_log_to_file(f"[ERROR] Failed to add member: {email} — {str(e)}")
			return jsonify({'error': str(e)}), 500

	return render_template('add_member.html')



@app.route('/logout')
def logout():
	session_id = session.get('session_id')

	# Clear the session in the Login table of CIMS DB
	if session_id:
		try:
			cims_conn = get_cims_connection()
			cims_cursor = cims_conn.cursor()
			cims_cursor.execute(
				"UPDATE Login SET Session = NULL, Expiry = NULL WHERE Session = %s",
				(session_id,)
			)
			cims_conn.commit()

			# Optional: Log successful logout
			write_log_to_file(f"User logged out with session ID: {session_id}")

			session.pop('session_id', None)  # Remove session ID from Flask session

		except Exception as e:
			write_log_to_file(f"[ERROR] Logout failed for session ID: {session_id} — {str(e)}")
			print("Logout DB error:", e)

		finally:
			cims_cursor.close()
			cims_conn.close()

	# Clear local Flask session
	session.clear()
	return redirect(url_for('login'))



@app.route('/api/portfolio', methods=['GET'])
def api_portfolio():
	# Debugging: Check what session contains
	print("SESSION:     ",5);session_id = request.headers.get('Session-ID')

	print("SESSION ID:  ",session_id)
	conn = get_cims_connection()
	cursor = conn.cursor(dictionary=True)
	cursor.execute("SELECT * FROM Login WHERE Session = %s", (session_id,))
	result = cursor.fetchone()


	member_id = result['MemberID']
	print("Member ID:   ",member_id)

	try:
		conn = get_cims_connection()
		cursor = conn.cursor(dictionary=True)

		# Step 1: Check if the user is in GroupID 8
		cursor.execute("""
			SELECT * FROM MemberGroupMapping WHERE MemberID = %s AND GroupID = %s
		""", (member_id, 8))
		is_in_group = cursor.fetchone()

		if not is_in_group:
			return jsonify({'error': 'Access Denied'}), 403

		# Step 2: Fetch all members in Group 8
		cursor.execute("""
			SELECT m.ID, m.UserName, m.emailID, m.DoB
			FROM members m
			JOIN MemberGroupMapping gm ON m.ID = gm.MemberID
			WHERE gm.GroupID = %s
		""", (8,))
		group_members = cursor.fetchall()

		return jsonify({'group_members': group_members}), 200

	except Exception as e:
		return jsonify({'error': str(e)}), 500

	finally:
		cursor.close()
		conn.close()


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
		email = request.form['username']  # This is actually the email ID

		try:
			cims_conn = get_cims_connection()
			cims_cursor = cims_conn.cursor()

			# Step 1: Get the MemberID from the members table using emailID
			cims_cursor.execute("SELECT ID FROM members WHERE emailID = %s", (email,))
			result = cims_cursor.fetchone()

			if result is None:
				flash("No member found with that email.")
				write_log_to_file(f"[WARNING] Delete failed — No member found with email: {email}")
				return render_template('delete_member.html')

			member_id = result[0]

			# Step 2: Delete from Login table using MemberID
			cims_cursor.execute("DELETE FROM Login WHERE MemberID = %s", (member_id,))

			# Step 3: Delete from members table using ID
			cims_cursor.execute("DELETE FROM members WHERE ID = %s", (member_id,))

			cims_conn.commit()

			flash('Member deleted successfully!')
			write_log_to_file(f"Deleted member with email: {email} and MemberID: {member_id}")

		except Exception as e:
			cims_conn.rollback()
			write_log_to_file(f"[ERROR] Delete failed for email: {email} — {str(e)}")
			return jsonify({'error': str(e)}), 500

		finally:
			cims_cursor.close()
			cims_conn.close()

	return render_template('delete_member.html')



@app.route('/data')
@admin_required
def data_dashboard():
	table_names = ['MEMBERS', 'login', 'BOOKS_DETAILS', 'BOOK_AVAILABILITY', 'DIGITAL_BOOKS']
	return render_template('data_dashboard.html', tables=table_names)

def isValidSession(session_id):
	cims_conn = get_cims_connection()
	cims_cursor = cims_conn.cursor(dictionary=True)

	try:
		cims_cursor.execute("SELECT * FROM Login WHERE Session = %s", (session_id,))
		result = cims_cursor.fetchone()

		if result:
			expiry = result.get('Expiry')
			current_time = int(datetime.datetime.now().timestamp())
			if expiry and expiry > current_time:
				write_log_to_file(f"Session {session_id} is valid.")
				return True
			else:
				write_log_to_file(f"Session {session_id} found but expired.")
		else:
			write_log_to_file(f"Session {session_id} is invalid or not found.")

	except Exception as e:
		write_log_to_file(f"[ERROR] Session validation failed for session {session_id} — {str(e)}")

	finally:
		cims_cursor.close()
		cims_conn.close()

	return False



@app.route('/api/login', methods=['POST'])
def api_login():
	data = request.get_json()
	username = data['username']
	password = data['password']

	conn = get_db_connection()
	cursor = conn.cursor(dictionary=True)
	cursor.execute("SELECT * FROM Login WHERE username = %s", (username,))
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
def add_book():
	session_id = request.headers.get('Session-ID')
	data = request.get_json()
	print("Adding book with data:", data)
	print("Session ID:", session_id)
	print(is_admin(session_id))

	if not isValidSession(session_id) or not is_admin(session_id):
		log_unauthorized_access("POST /books", "add_book")
		return jsonify({'error': 'Unauthorized'}), 401

	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		print("Permission granted. Proceeding to add book...")

		# Step 1: Insert into BOOKS_DETAILS
		cursor.execute("""
			INSERT INTO BOOKS_DETAILS (Book_Name, Book_Author, Book_Publication_Year, Total_Reviews, Quantity, BOOK_GENRE)
			VALUES (%s, %s, %s, %s, %s, %s)
		""", (
			data['Book_Name'],
			data['Book_Author'],
			data.get('Book_Publication_Year', "XXXX"),
			data.get('Total_Reviews', 0),
			data['Quantity'],
			data['BOOK_GENRE']
		))

		# Step 2: Get the inserted Book_ID
		BookID= cursor.lastrowid
		Quantity_Remaining = data['Quantity']
		Availability = 'Available' if Quantity_Remaining > 0 else 'Not Available'

		# Step 3: Insert into BOOK_AVAILABILITY
		cursor.execute("""
			INSERT INTO BOOK_AVAILABILITY (BookID, Quantity_Remaining, Availability)
			VALUES (%s, %s, %s)
		""", (BookID, Quantity_Remaining, Availability))

		conn.commit()
		return jsonify({'message': 'Book and availability added successfully'}), 201

	except Exception as e:
		return jsonify({'error': str(e)}), 500

	finally: 
		conn.close()


@app.route('/borrow/<int:book_id>', methods=['POST'])
def borrow_book(book_id):
	session_id = request.headers.get('Session-ID')
	print("Session ID from header:", session_id)

	if not session_id:
		log_unauthorized_access("POST /borrow", f"book_id={book_id} — no Session-ID")
		return jsonify({'error': 'Unauthorized - No Session ID'}), 401

	try:
		conn = get_cims_connection()
		cursor = conn.cursor(dictionary=True)

		# ✅ Validate session ID from Login table
		cursor.execute("SELECT MemberID, Expiry FROM Login WHERE Session = %s", (session_id,))
		session_row = cursor.fetchone()

		if not session_row:
			log_unauthorized_access("POST /borrow", f"Invalid session ID: {session_id}")
			return jsonify({'error': 'Unauthorized - Invalid Session'}), 401

		# ✅ Check if session has expired
		import time
		current_unix = int(time.time())
		if session_row['Expiry'] < current_unix:
			log_unauthorized_access("POST /borrow", f"Expired session ID: {session_id}")
			return jsonify({'error': 'Session expired'}), 401

		member_id = session_row['MemberID']
		print("Authorized member ID:", member_id)

		# Now connect to library DB and check book availability
		lib_conn = get_db_connection()
		lib_cursor = lib_conn.cursor(dictionary=True)

		lib_cursor.execute("SELECT Quantity_Remaining FROM BOOK_AVAILABILITY WHERE BookID = %s", (book_id,))
		book = lib_cursor.fetchone()

		if not book:
			return jsonify({'error': 'Book not found'}), 404

		if book['Quantity_Remaining'] <= 0:
			return jsonify({'error': 'Book not available'}), 400

		# Update quantity
		new_quantity = book['Quantity_Remaining'] - 1
		availability = 'Available' if new_quantity > 0 else 'Not Available'

		lib_cursor.execute("""
			UPDATE BOOK_AVAILABILITY
			SET Quantity_Remaining = %s, Availability = %s 
			WHERE BookID = %s
		""", (new_quantity, availability, book_id))

		# Insert into TRANSACTIONS
		from datetime import datetime, timedelta
		issue_date = datetime.now().date()
		due_date = issue_date + timedelta(days=14)

		lib_cursor.execute("""
			INSERT INTO TRANSACTIONS(MemberID, BookID, Issue_Date, Due_Date, Status)
			VALUES (%s, %s, %s, %s, %s)
		""", (member_id, book_id, issue_date, due_date, 'Issued'))

		lib_conn.commit()

		# Cleanup
		lib_cursor.close()
		lib_conn.close()
		cursor.close()
		conn.close()

		return jsonify({
			'message': 'Book issued successfully',
			'book_id': book_id,
			'issued_to': member_id,
			'due_date': str(due_date)
		}), 200

	except Exception as e:
		print(f"Error: {e}")
		return jsonify({'error': 'Internal Server Error'}), 500


# @app.route('/borrow/<int:book_id>', methods=['POST'])
# def borrow_book(book_id):
# 	session_id = request.headers.get('Session-ID')

# 	if not isValidSession(session_id):
# 		log_unauthorized_access("POST /borrow", f"book_id={book_id}")
# 		return jsonify({'error': 'Unauthorized'}), 401

# 	try:
# 		conn = get_db_connection()
# 		cursor = conn.cursor()

# 		# Check current quantity
# 		cursor.execute("SELECT Quantity_Remaining FROM BOOK_AVAILABILITY WHERE BookID = %s", (book_id,))
# 		result = cursor.fetchone()

# 		if not result:
# 			conn.close()
# 			return jsonify({'error': 'Book not found'}), 404

# 		quantity = result[0]

# 		if quantity <= 0:
# 			conn.close()
# 			return jsonify({'error': 'Book not available'}), 400

# 		# Update quantity
# 		new_quantity = quantity - 1
# 		availability = 'Available' if new_quantity > 0 else 'Not Available'

# 		cursor.execute("""
# 			UPDATE BOOK_AVAILABILITY
# 			SET Quantity_Remaining = %s, Availability = %s
# 			WHERE BookID = %s
# 		""", (new_quantity, availability, book_id))
# 		conn.commit()
# 		conn.close()

# 		return jsonify({'message': 'Book borrowed successfully'}), 200

# 	except Exception as e:
# 		return jsonify({'error': str(e)}), 500
	

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



# @app.route('/books/<int:book_id>', methods=['PUT'])
# def update_book(book_id):
# 	session_id = request.headers.get('Session-ID')

# 	if not isValidSession(session_id) or not is_admin(session_id):
# 		log_unauthorized_access("PUT /books", "update_book")
# 		return jsonify({'error': 'Unauthorized'}), 401

# 	data = request.get_json()

# 	try:
# 		conn = get_db_connection()
# 		cursor = conn.cursor()

# 		fields = []
# 		values = []

# 		for key in ['Book_Name', 'Book_Author', 'Book_Publication_Year', 'Total_Reviews', 'Quantity', 'BOOK_GENRE']:
# 			if key in data:
# 				fields.append(f"{key} = %s")
# 				values.append(data[key])

# 		if not fields:
# 			return jsonify({'error': 'No fields to update'}), 400

# 		values.append(book_id)
# 		query = f"UPDATE BOOKS_DETAILS SET {', '.join(fields)} WHERE Book_ID = %s"
# 		cursor.execute(query, tuple(values)) 

# 		conn.commit()
# 		conn.close()

# 		if cursor.rowcount == 0:
# 			return jsonify({'error': 'Book not found'}), 404

# 		return jsonify({'message': 'Book updated successfully'}), 200

# 	except Exception as e:
# 		return jsonify({'error': str(e)}), 500
	

@app.route('/notifications', methods=['POST'])
def send_notification():
	data = request.get_json()
	session_id = request.headers.get('Session-ID')

	if not isValidSession(session_id) or not is_admin(session_id):
		log_unauthorized_access("POST /notifications", "send_notification")
		return jsonify({'error': 'Unauthorized'}), 401

	try:
		conn_cims = get_cims_connection()
		cursor_cims = conn_cims.cursor(dictionary=True)
		cursor_cims.execute("SELECT emailID FROM members WHERE ID = %s", (data['Member_ID'],))
		member_row = cursor_cims.fetchone()
		if not member_row:
			return jsonify({'error': 'Member not found'}), 404
		email = member_row['emailID']
		cursor_cims.close()
		conn_cims.close()
		# send_otp(email, f"Notification from library on : {data['Type']} ",data['Message'])  # Assuming this function sends the email
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

   
@app.route('/checked')
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
   
def check():
	print(dict(session))  # See what's actually in there
	print("Session contents:", dict(session))
	print(session.get('session_id'))

	return f"Role: {session.get('username')}, Session ID: {session.get('session_id')}" 


@app.route('/download_digital_book/<int:digital_id>', methods=['POST'])
def download_digital_book(digital_id):
	conn = get_db_connection()
	cursor = conn.cursor()
	try:
		# Check if the book exists
		cursor.execute("""
			SELECT Digital_Downloads FROM DIGITAL_BOOKS 
			WHERE Digital_ID = %s
		""", (digital_id,))
		result = cursor.fetchone()

		if not result:
			return jsonify({'error': 'Digital book not found'}), 404

		# Increment the download count
		cursor.execute("""
			UPDATE DIGITAL_BOOKS
			SET Digital_Downloads = Digital_Downloads + 1
			WHERE Digital_ID = %s
		""", (digital_id,))

		conn.commit()
		return jsonify({'message': 'Download count updated'}), 200

	except Exception as e:
		conn.rollback()
		return jsonify({'error': str(e)}), 500
	finally:
		cursor.close()
		conn.close()



@app.route('/delete_member/<int:member_id>', methods=['POST'])
def delete_member_cims(member_id):
	session_id = request.headers.get('Session-ID') 
	print("Session ID from header:", session_id)

	if not session_id or not isValidSession(session_id) or not is_admin(session_id):
		return jsonify({'error': 'Unauthorized'}), 401

	conn = get_cims_connection()
	cursor = conn.cursor()

	try:
		# 1. Check if member is in any group
		cursor.execute("""
			SELECT * FROM MemberGroupMapping WHERE MemberID = %s
		""", (member_id,))
		group_links = cursor.fetchall()

		if group_links:
			return jsonify({'error': 'Member is associated with a group and cannot be deleted'}), 400

		# 2. Delete from MEMBERS table
		cursor.execute("DELETE FROM members WHERE ID = %s", (member_id,))
		
		# # 3. Delete from LOGIN table
		# cursor.execute("DELETE FROM Login WHERE Member_ID = %s", (member_id,))
		
		conn.commit()
		return jsonify({'message': f'Member {member_id} deleted successfully'}), 200

	except Exception as e:
		conn.rollback()
		return jsonify({'error': str(e)}), 500

	finally:
		cursor.close()
		conn.close()



if __name__ == '__main__':
	app.run(debug=True, port=5000)
