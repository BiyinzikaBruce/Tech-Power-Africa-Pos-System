import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-123')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    VERCEL_ENV = os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV')

    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    elif VERCEL_ENV:
        SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/pos.db'
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'pos.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False}
    }

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME') or 'noreply@techpower.africa'
    _report_recipients_str = os.environ.get('REPORT_RECIPIENT_EMAILS', '')
    REPORT_RECIPIENT_EMAILS = [email.strip() for email in _report_recipients_str.split(',') if email.strip()] if _report_recipients_str else []
    DAILY_REPORT_TIME = os.environ.get('DAILY_REPORT_TIME', '18:00')
