import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, and_
import tempfile
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dental_lab_tracking_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dental_lab.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Register custom Jinja2 filters
@app.template_filter('nl2br')
def nl2br_filter(text):
    if text:
        return text.replace('\n', '<br>')
    return ''

# Initialize database
db = SQLAlchemy(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_name = db.Column(db.String(100), nullable=False)
    patient_first_name = db.Column(db.String(100), nullable=False)
    patient_last_name = db.Column(db.String(100), nullable=False)
    shade = db.Column(db.String(50))
    size = db.Column(db.String(50))
    teeth_numbers = db.Column(db.String(200))  # Comma-separated list or 'Full Clearance'
    case_status = db.Column(db.String(20))  # 'Try-in' or 'Finish'
    date_received = db.Column(db.Date, nullable=False)
    date_due = db.Column(db.Date, nullable=False)
    location_status = db.Column(db.String(20))  # 'Sent' or 'In-Lab'
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get counts for dashboard
    total_cases = Case.query.count()
    in_lab_cases = Case.query.filter_by(location_status='In-Lab').count()
    sent_cases = Case.query.filter_by(location_status='Sent').count()
    try_in_cases = Case.query.filter_by(case_status='Try-in').count()
    finish_cases = Case.query.filter_by(case_status='Finish').count()
    
    # Get cases due today
    today = datetime.date.today()
    due_today = Case.query.filter_by(date_due=today).all()
    
    # Get overdue cases
    overdue = Case.query.filter(Case.date_due < today, Case.location_status == 'In-Lab').all()
    
    return render_template('dashboard.html', 
                           total_cases=total_cases,
                           in_lab_cases=in_lab_cases,
                           sent_cases=sent_cases,
                           try_in_cases=try_in_cases,
                           finish_cases=finish_cases,
                           due_today=due_today,
                           overdue=overdue)

@app.route('/cases')
@login_required
def cases():
    # Get filter parameters
    doctor = request.args.get('doctor', '')
    status = request.args.get('status', '')
    location = request.args.get('location', '')
    search = request.args.get('search', '')
    
    # Build query
    query = Case.query
    
    if doctor:
        query = query.filter(Case.doctor_name == doctor)
    if status:
        query = query.filter(Case.case_status == status)
    if location:
        query = query.filter(Case.location_status == location)
    if search:
        search_term = f'%{search}%'
        query = query.filter(or_(
            Case.patient_first_name.like(search_term),
            Case.patient_last_name.like(search_term),
            Case.doctor_name.like(search_term)
        ))
    
    # Get all cases with filters applied
    cases = query.order_by(Case.date_due).all()
    
    # Get unique doctor names for filter dropdown
    doctors = db.session.query(Case.doctor_name).distinct().all()
    
    return render_template('cases.html', cases=cases, doctors=doctors)

@app.route('/case/new', methods=['GET', 'POST'])
@login_required
def new_case():
    if request.method == 'POST':
        # Get form data
        doctor_name = request.form.get('doctor_name')
        patient_first_name = request.form.get('patient_first_name')
        patient_last_name = request.form.get('patient_last_name')
        shade = request.form.get('shade')
        size = request.form.get('size')
        
        # Handle teeth numbers (either full clearance or specific teeth)
        if 'full_clearance' in request.form:
            teeth_numbers = 'Full Clearance'
        else:
            # Get selected teeth numbers
            selected_teeth = []
            for i in range(1, 33):  # Assuming 32 teeth
                if f'tooth_{i}' in request.form:
                    selected_teeth.append(str(i))
            teeth_numbers = ','.join(selected_teeth) if selected_teeth else ''
        
        case_status = request.form.get('case_status')
        date_received = datetime.datetime.strptime(request.form.get('date_received'), '%Y-%m-%d').date()
        date_due = datetime.datetime.strptime(request.form.get('date_due'), '%Y-%m-%d').date()
        location_status = request.form.get('location_status')
        notes = request.form.get('notes', '')
        
        # Create new case
        new_case = Case(
            doctor_name=doctor_name,
            patient_first_name=patient_first_name,
            patient_last_name=patient_last_name,
            shade=shade,
            size=size,
            teeth_numbers=teeth_numbers,
            case_status=case_status,
            date_received=date_received,
            date_due=date_due,
            location_status=location_status,
            notes=notes
        )
        
        db.session.add(new_case)
        db.session.commit()
        
        flash('Case added successfully!')
        return redirect(url_for('cases'))
    
    # Get unique doctor names for dropdown
    doctors = db.session.query(Case.doctor_name).distinct().all()
    
    return render_template('case_form.html', doctors=doctors, case=None)

@app.route('/case/<int:case_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_case(case_id):
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'POST':
        # Update case with form data
        case.doctor_name = request.form.get('doctor_name')
        case.patient_first_name = request.form.get('patient_first_name')
        case.patient_last_name = request.form.get('patient_last_name')
        case.shade = request.form.get('shade')
        case.size = request.form.get('size')
        
        # Handle teeth numbers
        if 'full_clearance' in request.form:
            case.teeth_numbers = 'Full Clearance'
        else:
            selected_teeth = []
            for i in range(1, 33):
                if f'tooth_{i}' in request.form:
                    selected_teeth.append(str(i))
            case.teeth_numbers = ','.join(selected_teeth) if selected_teeth else ''
        
        case.case_status = request.form.get('case_status')
        case.date_received = datetime.datetime.strptime(request.form.get('date_received'), '%Y-%m-%d').date()
        case.date_due = datetime.datetime.strptime(request.form.get('date_due'), '%Y-%m-%d').date()
        case.location_status = request.form.get('location_status')
        case.notes = request.form.get('notes', '')
        case.updated_at = datetime.datetime.utcnow()
        
        db.session.commit()
        
        flash('Case updated successfully!')
        return redirect(url_for('cases'))
    
    # Get unique doctor names for dropdown
    doctors = db.session.query(Case.doctor_name).distinct().all()
    
    return render_template('case_form.html', case=case, doctors=doctors)

@app.route('/case/<int:case_id>/delete', methods=['POST'])
@login_required
def delete_case(case_id):
    case = Case.query.get_or_404(case_id)
    db.session.delete(case)
    db.session.commit()
    
    flash('Case deleted successfully!')
    return redirect(url_for('cases'))

@app.route('/case/<int:case_id>/view')
@login_required
def view_case(case_id):
    case = Case.query.get_or_404(case_id)
    return render_template('case_view.html', case=case)

@app.route('/reports')
@login_required
def reports():
    # Get unique doctor names for filter dropdown
    doctors = db.session.query(Case.doctor_name).distinct().all()
    return render_template('reports.html', doctors=doctors)

@app.route('/generate_report', methods=['POST'])
@login_required
def generate_report():
    # Get filter criteria
    doctor = request.form.get('doctor')
    case_status = request.form.get('case_status')
    location_status = request.form.get('location_status')
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')
    report_type = request.form.get('report_type')
    
    # Build query
    query = Case.query
    
    if doctor and doctor != 'All':
        query = query.filter(Case.doctor_name == doctor)
    if case_status and case_status != 'All':
        query = query.filter(Case.case_status == case_status)
    if location_status and location_status != 'All':
        query = query.filter(Case.location_status == location_status)
    
    # Handle date range
    if date_from:
        from_date = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
        if report_type == 'received':
            query = query.filter(Case.date_received >= from_date)
        else:  # due date
            query = query.filter(Case.date_due >= from_date)
    
    if date_to:
        to_date = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
        if report_type == 'received':
            query = query.filter(Case.date_received <= to_date)
        else:  # due date
            query = query.filter(Case.date_due <= to_date)
    
    # Get filtered cases
    cases = query.order_by(Case.date_due).all()
    
    # Create a temporary file for the PDF
    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    
    # Generate PDF using ReportLab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Title
    elements.append(Paragraph("Dental Laboratory Case Report", title_style))
    elements.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Report Info
    elements.append(Paragraph(f"Doctor: {doctor if doctor and doctor != 'All' else 'All Doctors'}", normal_style))
    elements.append(Paragraph(f"Case Status: {case_status if case_status and case_status != 'All' else 'All Statuses'}", normal_style))
    elements.append(Paragraph(f"Location Status: {location_status if location_status and location_status != 'All' else 'All Locations'}", normal_style))
    
    # Date Range
    date_range_text = f"Date Range ({report_type.capitalize()}): "
    if date_from and date_to:
        date_range_text += f"{date_from} to {date_to}"
    elif date_from:
        date_range_text += f"From {date_from}"
    elif date_to:
        date_range_text += f"To {date_to}"
    else:
        date_range_text += "All dates"
    elements.append(Paragraph(date_range_text, normal_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Table data
    if cases:
        data = [
            ['ID', 'Doctor', 'Patient', 'Status', 'Location', 'Received', 'Due']
        ]
        
        for case in cases:
            data.append([
                str(case.id),
                case.doctor_name,
                f"{case.patient_first_name} {case.patient_last_name}",
                case.case_status,
                case.location_status,
                case.date_received.strftime('%Y-%m-%d'),
                case.date_due.strftime('%Y-%m-%d')
            ])
        
        # Create table
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
    else:
        elements.append(Paragraph("No cases found matching the criteria.", normal_style))
    
    # Build PDF
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    with open(temp_file.name, 'wb') as f:
        f.write(pdf_data)
    
    # Send the PDF file
    return send_file(temp_file.name, 
                     download_name=f'dental_lab_report_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
                     as_attachment=True)

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('You do not have permission to access the admin area')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    return render_template('admin.html', users=users)

@app.route('/admin/user/new', methods=['GET', 'POST'])
@login_required
def new_user():
    if not current_user.is_admin:
        flash('You do not have permission to create users')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_admin = 'is_admin' in request.form
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('user_form.html')
        
        # Create new user
        user = User(username=username, is_admin=is_admin)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('User created successfully')
        return redirect(url_for('admin'))
    
    return render_template('user_form.html')

@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('You do not have permission to edit users')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_admin = 'is_admin' in request.form
        
        # Check if username already exists and is not the current user
        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.id != user_id:
            flash('Username already exists')
            return render_template('user_form.html', user=user)
        
        # Update user
        user.username = username
        if password:
            user.set_password(password)
        user.is_admin = is_admin
        
        db.session.commit()
        
        flash('User updated successfully')
        return redirect(url_for('admin'))
    
    return render_template('user_form.html', user=user)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('You do not have permission to delete users')
        return redirect(url_for('dashboard'))
    
    # Prevent deleting yourself
    if user_id == current_user.id:
        flash('You cannot delete your own account')
        return redirect(url_for('admin'))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully')
    return redirect(url_for('admin'))

# Initialize the database and create admin user
# Using with_appcontext instead of before_first_request which is deprecated in Flask 2.3+
def create_tables_and_admin():
    db.create_all()
    
    # Check if admin user exists, if not create one
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

# Context processor to make 'now' available in all templates
@app.context_processor
def inject_now():
    return {'now': datetime.datetime.now(), 'timedelta': datetime.timedelta}

# Call initialization function when app starts
with app.app_context():
    create_tables_and_admin()

if __name__ == '__main__':
    app.run(debug=True)