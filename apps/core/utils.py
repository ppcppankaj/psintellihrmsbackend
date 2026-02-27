"""
Core Utilities
"""

import re
import uuid
import hashlib
import secrets
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


def generate_uuid() -> str:
    """Generate a UUID string"""
    return str(uuid.uuid4())


def generate_short_id(length: int = 8) -> str:
    """Generate a short unique ID"""
    return secrets.token_urlsafe(length)[:length].upper()


def generate_employee_id(prefix: str = 'EMP') -> str:
    """Generate an employee ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_part = secrets.token_hex(2).upper()
    return f"{prefix}{timestamp}{random_part}"


def hash_string(value: str) -> str:
    """Create SHA-256 hash of a string"""
    return hashlib.sha256(value.encode()).hexdigest()


def mask_email(email: str) -> str:
    """Mask email address for privacy"""
    if '@' not in email:
        return email
    local, domain = email.split('@')
    if len(local) <= 2:
        masked_local = local[0] + '*' * (len(local) - 1)
    else:
        masked_local = local[:2] + '*' * (len(local) - 4) + local[-2:]
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """Mask phone number for privacy"""
    if len(phone) < 4:
        return '*' * len(phone)
    return phone[:2] + '*' * (len(phone) - 4) + phone[-2:]


def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    pattern = r'^\+?[1-9]\d{6,14}$'
    return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))


def validate_email_address(email: str) -> bool:
    """Validate email address format"""
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


def calculate_age(birth_date: date) -> int:
    """Calculate age from birth date"""
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def get_financial_year(date_obj: Optional[date] = None) -> str:
    """Get financial year string (e.g., '2024-25')"""
    if date_obj is None:
        date_obj = date.today()
    
    if date_obj.month >= 4:
        start_year = date_obj.year
    else:
        start_year = date_obj.year - 1
    
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def get_financial_year_dates(date_obj: Optional[date] = None) -> tuple:
    """Get start and end dates of financial year"""
    if date_obj is None:
        date_obj = date.today()
    
    if date_obj.month >= 4:
        start_year = date_obj.year
    else:
        start_year = date_obj.year - 1
    
    start_date = date(start_year, 4, 1)
    end_date = date(start_year + 1, 3, 31)
    
    return start_date, end_date


def format_currency(amount: float, currency: str = 'INR') -> str:
    """Format amount as currency"""
    currency_symbols = {
        'INR': '₹',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
    }
    symbol = currency_symbols.get(currency, currency)
    
    if currency == 'INR':
        # Indian numbering system
        if amount >= 10000000:
            return f"{symbol}{amount/10000000:.2f} Cr"
        elif amount >= 100000:
            return f"{symbol}{amount/100000:.2f} L"
        else:
            return f"{symbol}{amount:,.2f}"
    else:
        return f"{symbol}{amount:,.2f}"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    # Remove path components
    filename = filename.replace('\\', '/').split('/')[-1]
    # Remove dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limit length
    if len(filename) > 200:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = f"{name[:190]}.{ext}" if ext else name[:200]
    return filename


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """Split a list into chunks"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def flatten_dict(d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """Flatten a nested dictionary"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class Singleton:
    """Singleton decorator"""
    _instances = {}
    
    def __new__(cls, class_):
        if class_ not in cls._instances:
            cls._instances[class_] = super().__new__(cls)
        return cls._instances[class_]
