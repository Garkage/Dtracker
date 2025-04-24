# Dental Laboratory Tracking System

A web-based application for dental laboratories to track patient cases sent and received from dentists. This system helps manage case information, track status, and generate reports.

## Features

- User authentication and role-based access control
- Dashboard with key metrics and overviews
- Case management (add, edit, view, delete)
- Detailed teeth selection interface
- Status tracking (Try-in/Finish, In-Lab/Sent)
- Printable PDF reports based on selected criteria
- User management for administrators

## Requirements

- Python 3.8 or higher
- Flask and related packages (see requirements.txt)
- WeasyPrint for PDF generation

## Installation

1. Clone or download this repository
2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Start the application:
   ```
   python app.py
   ```
2. Open a web browser and navigate to http://127.0.0.1:5000
3. Log in with the default admin credentials:
   - Username: admin
   - Password: admin123

## Application Structure

- `app.py` - Main application file with routes and database models
- `templates/` - HTML templates for the web interface
- `static/` - CSS and other static files

## Database

The application uses SQLite for data storage. The database file (`dental_lab.db`) will be created automatically when the application is first run.

## Security

For production use, make sure to:
1. Change the default admin password
2. Update the secret key in app.py
3. Consider using a more robust database like PostgreSQL

## License

This project is licensed under the MIT License.