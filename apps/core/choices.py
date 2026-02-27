"""
Core Choices - Utilities for Country, Currency, and Timezone choices
FIXED: Lazy-load pytz to avoid build-time import errors
"""

# CRITICAL: Do NOT import pytz at module level
# This causes collectstatic to fail during Docker build
# import pytz  # ← WRONG!

# Comprehensive list of countries and their currencies
# Format: (code, display_name, currency_code, currency_name, default_timezone)
COUNTRY_DATA = [
    ('AF', 'Afghanistan', 'AFN', 'Afghan Afghani', 'Asia/Kabul'),
    ('AL', 'Albania', 'ALL', 'Albanian Lek', 'Europe/Tirane'),
    ('DZ', 'Algeria', 'DZD', 'Algerian Dinar', 'Africa/Algiers'),
    ('AD', 'Andorra', 'EUR', 'Euro', 'Europe/Andorra'),
    ('AO', 'Angola', 'AOA', 'Angolan Kwanza', 'Africa/Luanda'),
    ('AR', 'Argentina', 'ARS', 'Argentine Peso', 'America/Argentina/Buenos_Aires'),
    ('AM', 'Armenia', 'AMD', 'Armenian Dram', 'Asia/Yerevan'),
    ('AU', 'Australia', 'AUD', 'Australian Dollar', 'Australia/Sydney'),
    ('AT', 'Austria', 'EUR', 'Euro', 'Europe/Vienna'),
    ('AZ', 'Azerbaijan', 'AZN', 'Azerbaijani Manat', 'Asia/Baku'),
    ('BS', 'Bahamas', 'BSD', 'Bahamian Dollar', 'America/Nassau'),
    ('BH', 'Bahrain', 'BHD', 'Bahraini Dinar', 'Asia/Bahrain'),
    ('BD', 'Bangladesh', 'BDT', 'Bangladeshi Taka', 'Asia/Dhaka'),
    ('BB', 'Barbados', 'BBD', 'Barbadian Dollar', 'America/Barbados'),
    ('BY', 'Belarus', 'BYN', 'Belarusian Ruble', 'Europe/Minsk'),
    ('BE', 'Belgium', 'EUR', 'Euro', 'Europe/Brussels'),
    ('BZ', 'Belize', 'BZD', 'Belize Dollar', 'America/Belize'),
    ('BJ', 'Benin', 'XOF', 'West African CFA Franc', 'Africa/Porto-Novo'),
    ('BT', 'Bhutan', 'BTN', 'Bhutanese Ngultrum', 'Asia/Thimphu'),
    ('BO', 'Bolivia', 'BOB', 'Bolivian Boliviano', 'America/La_Paz'),
    ('BA', 'Bosnia and Herzegovina', 'BAM', 'Bosnia and Herzegovina Convertible Mark', 'Europe/Sarajevo'),
    ('BW', 'Botswana', 'BWP', 'Botswana Pula', 'Africa/Gaborone'),
    ('BR', 'Brazil', 'BRL', 'Brazilian Real', 'America/Sao_Paulo'),
    ('BN', 'Brunei', 'BND', 'Brunei Dollar', 'Asia/Brunei'),
    ('BG', 'Bulgaria', 'BGN', 'Bulgarian Lev', 'Europe/Sofia'),
    ('BF', 'Burkina Faso', 'XOF', 'West African CFA Franc', 'Africa/Ouagadougou'),
    ('BI', 'Burundi', 'BIF', 'Burundian Franc', 'Africa/Bujumbura'),
    ('KH', 'Cambodia', 'KHR', 'Cambodian Riel', 'Asia/Phnom_Penh'),
    ('CM', 'Cameroon', 'XAF', 'Central African CFA Franc', 'Africa/Douala'),
    ('CA', 'Canada', 'CAD', 'Canadian Dollar', 'America/Toronto'),
    ('CV', 'Cape Verde', 'CVE', 'Cape Verdean Escudo', 'Atlantic/Cape_Verde'),
    ('CF', 'Central African Republic', 'XAF', 'Central African CFA Franc', 'Africa/Bangui'),
    ('TD', 'Chad', 'XAF', 'Central African CFA Franc', 'Africa/Ndjamena'),
    ('CL', 'Chile', 'CLP', 'Chilean Peso', 'America/Santiago'),
    ('CN', 'China', 'CNY', 'Chinese Yuan', 'Asia/Shanghai'),
    ('CO', 'Colombia', 'COP', 'Colombian Peso', 'America/Bogota'),
    ('KM', 'Comoros', 'KMF', 'Comorian Franc', 'Indian/Comoro'),
    ('CG', 'Congo', 'XAF', 'Central African CFA Franc', 'Africa/Brazzaville'),
    ('CR', 'Costa Rica', 'CRC', 'Costa Rican Colón', 'America/Costa_Rica'),
    ('HR', 'Croatia', 'EUR', 'Euro', 'Europe/Zagreb'),
    ('CU', 'Cuba', 'CUP', 'Cuban Peso', 'America/Havana'),
    ('CY', 'Cyprus', 'EUR', 'Euro', 'Asia/Nicosia'),
    ('CZ', 'Czech Republic', 'CZK', 'Czech Koruna', 'Europe/Prague'),
    ('DK', 'Denmark', 'DKK', 'Danish Krone', 'Europe/Copenhagen'),
    ('DJ', 'Djibouti', 'DJF', 'Djiboutian Franc', 'Africa/Djibouti'),
    ('DM', 'Dominica', 'XCD', 'East Caribbean Dollar', 'America/Dominica'),
    ('DO', 'Dominican Republic', 'DOP', 'Dominican Peso', 'America/Santo_Domingo'),
    ('EC', 'Ecuador', 'USD', 'United States Dollar', 'America/Guayaquil'),
    ('EG', 'Egypt', 'EGP', 'Egyptian Pound', 'Africa/Cairo'),
    ('SV', 'El Salvador', 'USD', 'United States Dollar', 'America/El_Salvador'),
    ('GQ', 'Equatorial Guinea', 'XAF', 'Central African CFA Franc', 'Africa/Malabo'),
    ('ER', 'Eritrea', 'ERN', 'Eritrean Nakfa', 'Africa/Asmara'),
    ('EE', 'Estonia', 'EUR', 'Euro', 'Europe/Tallinn'),
    ('SZ', 'Eswatini', 'SZL', 'Swazi Lilangeni', 'Africa/Mbabane'),
    ('ET', 'Ethiopia', 'ETB', 'Ethiopian Birr', 'Africa/Addis_Ababa'),
    ('FJ', 'Fiji', 'FJD', 'Fijian Dollar', 'Pacific/Fiji'),
    ('FI', 'Finland', 'EUR', 'Euro', 'Europe/Helsinki'),
    ('FR', 'France', 'EUR', 'Euro', 'Europe/Paris'),
    ('GA', 'Gabon', 'XAF', 'Central African CFA Franc', 'Africa/Libreville'),
    ('GM', 'Gambia', 'GMD', 'Gambian Dalasi', 'Africa/Banjul'),
    ('GE', 'Georgia', 'GEL', 'Georgian Lari', 'Asia/Tbilisi'),
    ('DE', 'Germany', 'EUR', 'Euro', 'Europe/Berlin'),
    ('GH', 'Ghana', 'GHS', 'Ghanaian Cedi', 'Africa/Accra'),
    ('GR', 'Greece', 'EUR', 'Euro', 'Europe/Athens'),
    ('GD', 'Grenada', 'XCD', 'East Caribbean Dollar', 'America/Grenada'),
    ('GT', 'Guatemala', 'GTQ', 'Guatemalan Quetzal', 'America/Guatemala'),
    ('GN', 'Guinea', 'GNF', 'Guinean Franc', 'Africa/Conakry'),
    ('GW', 'Guinea-Bissau', 'XOF', 'West African CFA Franc', 'Africa/Bissau'),
    ('GY', 'Guyana', 'GYD', 'Guyanese Dollar', 'America/Guyana'),
    ('HT', 'Haiti', 'HTG', 'Haitian Gourde', 'America/Port-au-Prince'),
    ('HN', 'Honduras', 'HNL', 'Honduran Lempira', 'America/Tegucigalpa'),
    ('HU', 'Hungary', 'HUF', 'Hungarian Forint', 'Europe/Budapest'),
    ('IS', 'Iceland', 'ISK', 'Icelandic Króna', 'Atlantic/Reykjavik'),
    ('IN', 'India', 'INR', 'Indian Rupee', 'Asia/Kolkata'),
    ('ID', 'Indonesia', 'IDR', 'Indonesian Rupiah', 'Asia/Jakarta'),
    ('IR', 'Iran', 'IRR', 'Iranian Rial', 'Asia/Tehran'),
    ('IQ', 'Iraq', 'IQD', 'Iraqi Dinar', 'Asia/Baghdad'),
    ('IE', 'Ireland', 'EUR', 'Euro', 'Europe/Dublin'),
    ('IL', 'Israel', 'ILS', 'Israeli New Sheqel', 'Asia/Jerusalem'),
    ('IT', 'Italy', 'EUR', 'Euro', 'Europe/Rome'),
    ('JM', 'Jamaica', 'JMD', 'Jamaican Dollar', 'America/Jamaica'),
    ('JP', 'Japan', 'JPY', 'Japanese Yen', 'Asia/Tokyo'),
    ('JO', 'Jordan', 'JOD', 'Jordanian Dinar', 'Asia/Amman'),
    ('KZ', 'Kazakhstan', 'KZT', 'Kazakhstani Tenge', 'Asia/Almaty'),
    ('KE', 'Kenya', 'KES', 'Kenyan Shilling', 'Africa/Nairobi'),
    ('KI', 'Kiribati', 'AUD', 'Australian Dollar', 'Pacific/Tarawa'),
    ('KW', 'Kuwait', 'KWD', 'Kuwaiti Dinar', 'Asia/Kuwait'),
    ('KG', 'Kyrgyzstan', 'KGS', 'Kyrgyzstani Som', 'Asia/Bishkek'),
    ('LA', 'Laos', 'LAK', 'Lao Kip', 'Asia/Vientiane'),
    ('LV', 'Latvia', 'EUR', 'Euro', 'Europe/Riga'),
    ('LB', 'Lebanon', 'LBP', 'Lebanese Pound', 'Asia/Beirut'),
    ('LS', 'Lesotho', 'LSL', 'Lesotho Loti', 'Africa/Maseru'),
    ('LR', 'Liberia', 'LRD', 'Liberian Dollar', 'Africa/Monrovia'),
    ('LY', 'Libya', 'LYD', 'Libyan Dinar', 'Africa/Tripoli'),
    ('LI', 'Liechtenstein', 'CHF', 'Swiss Franc', 'Europe/Vaduz'),
    ('LT', 'Lithuania', 'EUR', 'Euro', 'Europe/Vilnius'),
    ('LU', 'Luxembourg', 'EUR', 'Euro', 'Europe/Luxembourg'),
    ('MG', 'Madagascar', 'MGA', 'Malagasy Ariary', 'Indian/Antananarivo'),
    ('MW', 'Malawi', 'MWK', 'Malawian Kwacha', 'Africa/Lilongwe'),
    ('MY', 'Malaysia', 'MYR', 'Malaysian Ringgit', 'Asia/Kuala_Lumpur'),
    ('MV', 'Maldives', 'MVR', 'Maldivian Rufiyaa', 'Indian/Maldives'),
    ('ML', 'Mali', 'XOF', 'West African CFA Franc', 'Africa/Bamako'),
    ('MT', 'Malta', 'EUR', 'Euro', 'Europe/Malta'),
    ('MH', 'Marshall Islands', 'USD', 'United States Dollar', 'Pacific/Majuro'),
    ('MR', 'Mauritania', 'MRU', 'Mauritanian Ouguiya', 'Africa/Nouakchott'),
    ('MU', 'Mauritius', 'MUR', 'Mauritian Rupee', 'Indian/Mauritius'),
    ('MX', 'Mexico', 'MXN', 'Mexican Peso', 'America/Mexico_City'),
    ('FM', 'Micronesia', 'USD', 'United States Dollar', 'Pacific/Pohnpei'),
    ('MD', 'Moldova', 'MDL', 'Moldovan Leu', 'Europe/Chisinau'),
    ('MC', 'Monaco', 'EUR', 'Euro', 'Europe/Monaco'),
    ('MN', 'Mongolia', 'MNT', 'Mongolian Tögrög', 'Asia/Ulaanbaatar'),
    ('ME', 'Montenegro', 'EUR', 'Euro', 'Europe/Podgorica'),
    ('MA', 'Morocco', 'MAD', 'Moroccan Dirham', 'Africa/Casablanca'),
    ('MZ', 'Mozambique', 'MZN', 'Mozambican Metical', 'Africa/Maputo'),
    ('MM', 'Myanmar', 'MMK', 'Myanmar Kyat', 'Asia/Yangon'),
    ('NA', 'Namibia', 'NAD', 'Namibian Dollar', 'Africa/Windhoek'),
    ('NR', 'Nauru', 'AUD', 'Australian Dollar', 'Pacific/Nauru'),
    ('NP', 'Nepal', 'NPR', 'Nepalese Rupee', 'Asia/Kathmandu'),
    ('NL', 'Netherlands', 'EUR', 'Euro', 'Europe/Amsterdam'),
    ('NZ', 'New Zealand', 'NZD', 'New Zealand Dollar', 'Pacific/Auckland'),
    ('NI', 'Nicaragua', 'NIO', 'Nicaraguan Córdoba', 'America/Managua'),
    ('NE', 'Niger', 'XOF', 'West African CFA Franc', 'Africa/Niamey'),
    ('NG', 'Nigeria', 'NGN', 'Nigerian Naira', 'Africa/Lagos'),
    ('MK', 'North Macedonia', 'MKD', 'Macedonian Denar', 'Europe/Skopje'),
    ('NO', 'Norway', 'NOK', 'Norwegian Krone', 'Europe/Oslo'),
    ('OM', 'Oman', 'OMR', 'Omani Rial', 'Asia/Muscat'),
    ('PK', 'Pakistan', 'PKR', 'Pakistani Rupee', 'Asia/Karachi'),
    ('PW', 'Palau', 'USD', 'United States Dollar', 'Pacific/Palau'),
    ('PS', 'Palestine', 'ILS', 'Israeli New Sheqel', 'Asia/Gaza'),
    ('PA', 'Panama', 'PAB', 'Panamanian Balboa', 'America/Panama'),
    ('PG', 'Papua New Guinea', 'PGK', 'Papua New Guinean Kina', 'Pacific/Port_Moresby'),
    ('PY', 'Paraguay', 'PYG', 'Paraguayan Guaraní', 'America/Asuncion'),
    ('PE', 'Peru', 'PEN', 'Peruvian Sol', 'America/Lima'),
    ('PH', 'Philippines', 'PHP', 'Philippine Peso', 'Asia/Manila'),
    ('PL', 'Poland', 'PLN', 'Polish Zloty', 'Europe/Warsaw'),
    ('PT', 'Portugal', 'EUR', 'Euro', 'Europe/Lisbon'),
    ('QA', 'Qatar', 'QAR', 'Qatari Rial', 'Asia/Qatar'),
    ('RO', 'Romania', 'RON', 'Romanian Leu', 'Europe/Bucharest'),
    ('RU', 'Russia', 'RUB', 'Russian Ruble', 'Europe/Moscow'),
    ('RW', 'Rwanda', 'RWF', 'Rwandan Franc', 'Africa/Kigali'),
    ('KN', 'Saint Kitts and Nevis', 'XCD', 'East Caribbean Dollar', 'America/St_Kitts'),
    ('LC', 'Saint Lucia', 'XCD', 'East Caribbean Dollar', 'America/St_Lucia'),
    ('VC', 'Saint Vincent and the Grenadines', 'XCD', 'East Caribbean Dollar', 'America/St_Vincent'),
    ('WS', 'Samoa', 'WST', 'Samoan Tala', 'Pacific/Apia'),
    ('SM', 'San Marino', 'EUR', 'Euro', 'Europe/San_Marino'),
    ('ST', 'Sao Tome and Principe', 'STN', 'São Tomé and Príncipe Dobra', 'Africa/Sao_Tome'),
    ('SA', 'Saudi Arabia', 'SAR', 'Saudi Riyal', 'Asia/Riyadh'),
    ('SN', 'Senegal', 'XOF', 'West African CFA Franc', 'Africa/Dakar'),
    ('RS', 'Serbia', 'RSD', 'Serbian Dinar', 'Europe/Belgrade'),
    ('SC', 'Seychelles', 'SCR', 'Seychellois Rupee', 'Indian/Mahe'),
    ('SL', 'Sierra Leone', 'SLL', 'Sierra Leonean Leone', 'Africa/Freetown'),
    ('SG', 'Singapore', 'SGD', 'Singapore Dollar', 'Asia/Singapore'),
    ('SK', 'Slovakia', 'EUR', 'Euro', 'Europe/Bratislava'),
    ('SI', 'Slovenia', 'EUR', 'Euro', 'Europe/Ljubljana'),
    ('SB', 'Solomon Islands', 'SBD', 'Solomon Islands Dollar', 'Pacific/Guadalcanal'),
    ('SO', 'Somalia', 'SOS', 'Somali Shilling', 'Africa/Mogadishu'),
    ('ZA', 'South Africa', 'ZAR', 'South African Rand', 'Africa/Johannesburg'),
    ('KR', 'South Korea', 'KRW', 'South Korean Won', 'Asia/Seoul'),
    ('SS', 'South Sudan', 'SSP', 'South Sudanese Pound', 'Africa/Juba'),
    ('ES', 'Spain', 'EUR', 'Euro', 'Europe/Madrid'),
    ('LK', 'Sri Lanka', 'LKR', 'Sri Lankan Rupee', 'Asia/Colombo'),
    ('SD', 'Sudan', 'SDG', 'Sudanese Pound', 'Africa/Khartoum'),
    ('SR', 'Suriname', 'SRD', 'Surinamese Dollar', 'America/Paramaribo'),
    ('SE', 'Sweden', 'SEK', 'Swedish Krone', 'Europe/Stockholm'),
    ('CH', 'Switzerland', 'CHF', 'Swiss Franc', 'Europe/Zurich'),
    ('SY', 'Syria', 'SYP', 'Syrian Pound', 'Asia/Damascus'),
    ('TW', 'Taiwan', 'TWD', 'New Taiwan Dollar', 'Asia/Taipei'),
    ('TJ', 'Tajikistan', 'TJS', 'Tajikistani Somi', 'Asia/Dushanbe'),
    ('TZ', 'Tanzania', 'TZS', 'Tanzanian Shilling', 'Africa/Dar_es_Salaam'),
    ('TH', 'Thailand', 'THB', 'Thai Baht', 'Asia/Bangkok'),
    ('TL', 'Timor-Leste', 'USD', 'United States Dollar', 'Asia/Dili'),
    ('TG', 'Togo', 'XOF', 'West African CFA Franc', 'Africa/Lome'),
    ('TO', 'Tonga', 'TOP', 'Tongan Pa\'anga', 'Pacific/Tongatapu'),
    ('TT', 'Trinidad and Tobago', 'TTD', 'Trinidad and Tobago Dollar', 'America/Port_of_Spain'),
    ('TN', 'Tunisia', 'TND', 'Tunisian Dinar', 'Africa/Tunis'),
    ('TR', 'Turkey', 'TRY', 'Turkish Lira', 'Europe/Istanbul'),
    ('TM', 'Turkmenistan', 'TMT', 'Turkmenistani Manat', 'Asia/Ashgabat'),
    ('TV', 'Tuvalu', 'AUD', 'Australian Dollar', 'Pacific/Funafuti'),
    ('UG', 'Uganda', 'UGX', 'Ugandan Shilling', 'Africa/Kampala'),
    ('UA', 'Ukraine', 'UAH', 'Ukrainian Hryvnia', 'Europe/Kyiv'),
    ('AE', 'United Arab Emirates', 'AED', 'United Arab Emirates Dirham', 'Asia/Dubai'),
    ('GB', 'United Kingdom', 'GBP', 'British Pound Sterling', 'Europe/London'),
    ('US', 'United States', 'USD', 'United States Dollar', 'America/New_York'),
    ('UY', 'Uruguay', 'UYU', 'Uruguayan Peso', 'America/Montevideo'),
    ('UZ', 'Uzbekistan', 'UZS', 'Uzbekistani Som', 'Asia/Tashkent'),
    ('VU', 'Vanuatu', 'VUV', 'Vanuatu Vatu', 'Pacific/Efate'),
    ('VA', 'Vatican City', 'EUR', 'Euro', 'Europe/Vatican'),
    ('VE', 'Venezuela', 'VES', 'Venezuelan Bolívar Soberano', 'America/Caracas'),
    ('VN', 'Vietnam', 'VND', 'Vietnamese Dong', 'Asia/Ho_Chi_Minh'),
    ('YE', 'Yemen', 'YER', 'Yemeni Rial', 'Asia/Aden'),
    ('ZM', 'Zambia', 'ZMW', 'Zambian Kwacha', 'Africa/Lusaka'),
    ('ZW', 'Zimbabwe', 'ZWL', 'Zimbabwean Dollar', 'Africa/Harare'),
]

COUNTRY_CHOICES = [(c[1], c[1]) for c in COUNTRY_DATA]
CURRENCY_CHOICES = sorted(list(set([(c[2], f"{c[2]} - {c[3]}") for c in COUNTRY_DATA])))

# CRITICAL FIX: Lazy-load timezone choices
# This prevents pytz import during Django setup (which breaks collectstatic)
_TIMEZONE_CHOICES_CACHE = None

def get_timezone_choices():
    """
    Lazy-load timezone choices from pytz.
    Called at runtime, not at import time.
    """
    global _TIMEZONE_CHOICES_CACHE
# For backward compatibility, provide TIMEZONE_CHOICES as callable
def get_timezone_choices():
    """Get timezone choices (lazy-loaded from pytz)"""
    global _TIMEZONE_CHOICES_CACHE
    if _TIMEZONE_CHOICES_CACHE is None:
        import pytz  # ← Import INSIDE function, not at module level
        _TIMEZONE_CHOICES_CACHE = [(tz, tz) for tz in pytz.all_timezones]
    return _TIMEZONE_CHOICES_CACHE

# Provide TIMEZONE_CHOICES as a callable reference
TIMEZONE_CHOICES = get_timezone_choices

DATE_FORMAT_CHOICES = [
    ('DD/MM/YYYY', 'DD/MM/YYYY (e.g. 31/12/2024)'),
    ('MM/DD/YYYY', 'MM/DD/YYYY (e.g. 12/31/2024)'),
    ('YYYY-MM-DD', 'YYYY-MM-DD (e.g. 2024-12-31)'),
    ('DD-MM-YYYY', 'DD-MM-YYYY (e.g. 31-12-2024)'),
]


def get_country_info(country_name):
    """Get currency and timezone info for a country"""
    for c in COUNTRY_DATA:
        if c[1] == country_name:
            return {
                'code': c[0],
                'currency': c[2],
                'currency_name': c[3],
                'timezone': c[4]
            }
    return None
