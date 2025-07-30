import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2 import service_account
import os
import json

# ===== SETTINGS =====
SHEET_NAME = "PDK_Appointment_Bookings"
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']

OFFICE_HOURS = {
    'Monday':    ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Tuesday':   ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Wednesday': ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Thursday':  ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Friday':    ['09:00', '09:30', '10:00', '10:30','14:00', '14:30', '15:00', '15:30', '16:00'],
}

OFFICER_CALENDARS = {
    "DO": "do@keningau.gov.my",
    "ADO": "rabiatulsyafiqahhh@gmail.com"
}

# ===== AUTH =====
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    *CALENDAR_SCOPES
]

# Load credentials from environment
creds_dict = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Initialize services with error handling
try:
    sheet = client.open(SHEET_NAME).sheet1
except Exception as e:
    print(f"Failed to access Google Sheet: {e}")
    sheet = None

try:
    calendar_service = build('calendar', 'v3', credentials=creds)
except Exception as e:
    print(f"Calendar service initialization failed: {e}")
    calendar_service = None

# ===== HELPERS =====
def is_valid_date(date_str):
    """Check if date is in future and valid format (DD/MM/YYYY)"""
    try:
        day, month, year = map(int, date_str.split('/'))
        input_date = datetime(year, month, day).date()
        today = datetime.now().date()
        return input_date >= today
    except (ValueError, IndexError):
        return False

def is_weekend(date_str):
    """
    Check if the given date (DD/MM/YYYY) falls on a weekend (Saturday/Sunday).
    Returns True if it's a weekend, False otherwise.
    """
    try:
        day, month, year = map(int, date_str.split('/'))
        date_obj = datetime(year, month, day)
        return date_obj.weekday() >= 5  # 5=Saturday, 6=Sunday
    except (ValueError, IndexError, AttributeError):
        # If date parsing fails for any reason, assume it's not a weekend
        return False

def get_available_slots(date_str):
    """Return available time slots for a given date"""
    try:
        day, month, year = map(int, date_str.split('/'))
        date_obj = datetime(year, month, day)
        weekday = date_obj.strftime('%A')
        return OFFICE_HOURS.get(weekday, [])
    except:
        return []
def is_valid_date(date_str):
    """Check if date is in future and valid format (DD/MM/YYYY)"""
    try:
        day, month, year = map(int, date_str.split('/'))
        input_date = datetime(year, month, day).date()
        today = datetime.now().date()
        return input_date >= today
    except (ValueError, IndexError):
        return False

def is_slot_available(date, time, officer):
    """Check if slot is available and date is valid"""
    if not is_valid_date(date):
        return False
        
    if is_weekend(date):
        return False
        
    data = sheet.get_all_records()
    for row in data:
        if row['Date'] == date and row['Time'] == time and row['Officer'] == officer:
            return False
    return True

def get_alternative_times(date, officer):
    """
    Suggest available times from a fixed list for that date+officer.
    Only suggests times for weekdays (automatically excludes weekends).
    """
    if is_weekend(date):
        return []  # No alternatives for weekends
        
    options = ['09:00', '10:30', '14:00', '15:30']
    data = sheet.get_all_records()
    booked = [row['Time'] for row in data if row['Date'] == date and row['Officer'] == officer]
    return [t for t in options if t not in booked]

def save_booking(user_id, name, phone, email, officer, purpose, date, time):
    """
    Append a new confirmed row to the sheet.
    Note: This function assumes the booking has already been validated (not a weekend, slot available)
    """
    sheet.append_row([user_id, name, phone, email, officer, purpose, date, time, "CONFIRMED"])

# ===== CALENDAR FUNCTIONS =====
def create_calendar_event(officer, date_str, time_str, user_name, purpose, phone):
    """Create calendar event in officer's calendar"""
    try:
        # Convert date format from DD/MM/YYYY to YYYY-MM-DD
        day, month, year = map(int, date_str.split('/'))
        date_obj = datetime(year, month, day)
        
        # Convert time to datetime objects
        start_time = datetime.strptime(time_str, '%H:%M')
        end_time = start_time + timedelta(minutes=30)  # 30-min appointments
        
        # Format for Google Calendar API
        start_datetime = datetime.combine(date_obj, start_time.time()).isoformat() + '+08:00'
        end_datetime = datetime.combine(date_obj, end_time.time()).isoformat() + '+08:00'
        
        event = {
            'summary': f'Temu Janji: {user_name}',
            'description': f'Purpose: {purpose}\nContact: {phone}',
            'start': {'dateTime': start_datetime},
            'end': {'dateTime': end_datetime},
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }
        
        return calendar_service.events().insert(
            calendarId=OFFICER_CALENDARS[officer],
            body=event
        ).execute()
        
    except Exception as e:
        print(f"Calendar error: {e}")
        return None

# ===== UPDATED SAVE FUNCTION =====
def save_booking(user_id, name, phone, email, officer, purpose, date, time):
    """
    Save to sheet AND create calendar event
    """
    # 1. Save to Google Sheets
    sheet.append_row([user_id, name, phone, email, officer, purpose, date, time, "CONFIRMED"])
    
    # 2. Create calendar event 
    event = create_calendar_event(officer, date, time, name, purpose, phone)
    
    if event:
        print(f"Created calendar event: {event.get('htmlLink')}")
    else:
        print("Failed to create calendar event")
