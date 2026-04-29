from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    branch = db.relationship('Branch', back_populates='users')
    tenant = db.relationship('Tenant', back_populates='users', foreign_keys=[tenant_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    location = db.Column(db.String(256), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    users = db.relationship('User', back_populates='branch', lazy='dynamic')
    stocks = db.relationship('Stock', back_populates='branch', lazy='dynamic')
    sales = db.relationship('Sale', back_populates='branch', lazy='dynamic')
    tenant = db.relationship('Tenant')


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(192), nullable=False)
    sku = db.Column(db.String(64), nullable=False)
    price = db.Column(db.Float, nullable=False, default=0.0)
    cost = db.Column(db.Float, nullable=False, default=0.0)
    category = db.Column(db.String(128), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    stocks = db.relationship('Stock', back_populates='product', lazy='dynamic')
    sale_items = db.relationship('SaleItem', back_populates='product', lazy='dynamic')
    transfers = db.relationship('StockTransfer', back_populates='product', lazy='dynamic')

    @property
    def margin(self):
        if self.price == 0:
            return 0
        return ((self.price - self.cost) / self.price) * 100

    @property
    def profit(self):
        return self.price - self.cost


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    alert_threshold = db.Column(db.Integer, nullable=False, default=5)

    branch = db.relationship('Branch', back_populates='stocks')
    product = db.relationship('Product', back_populates='stocks')

    @property
    def is_low(self):
        return self.quantity <= self.alert_threshold


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    payment_type = db.Column(db.String(32), nullable=False)
    date = db.Column(db.String(10), nullable=False, default=lambda: datetime.utcnow().date().isoformat())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    branch = db.relationship('Branch', back_populates='sales')
    user = db.relationship('User')
    tenant = db.relationship('Tenant')
    items = db.relationship('SaleItem', back_populates='sale', lazy='dynamic')

    @property
    def total_amount(self):
        return sum(item.quantity * item.unit_price for item in self.items)


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)

    sale = db.relationship('Sale', back_populates='items')
    product = db.relationship('Product', back_populates='sale_items')


class StockTransfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    from_branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    to_branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(10), nullable=False, default=lambda: datetime.utcnow().date().isoformat())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', back_populates='transfers')
    from_branch = db.relationship('Branch', foreign_keys=[from_branch_id])
    to_branch = db.relationship('Branch', foreign_keys=[to_branch_id])


class Tenant(db.Model):
    """Multi-tenant company/organization"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    license_key = db.Column(db.String(256), unique=True, nullable=False)
    plan = db.Column(db.String(32), default='starter')  # starter/pro/enterprise
    max_users = db.Column(db.Integer, default=5)
    max_branches = db.Column(db.Integer, default=1)
    contact_email = db.Column(db.String(128))
    contact_phone = db.Column(db.String(32))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    users = db.relationship('User', back_populates='tenant', foreign_keys='User.tenant_id')
    api_keys = db.relationship('APIKey', back_populates='tenant')
    usage_logs = db.relationship('UsageLog', back_populates='tenant')
    invoices = db.relationship('Invoice', back_populates='tenant')


class APIKey(db.Model):
    """API keys for tenant integrations and external access"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    key = db.Column(db.String(256), unique=True, nullable=False)
    secret = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_used = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='api_keys')


class UsageLog(db.Model):
    """Track usage metrics for billing and monitoring"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    metric = db.Column(db.String(64))  # 'sales_count', 'users_active', 'api_calls', etc
    value = db.Column(db.Float, default=0)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='usage_logs')


class Invoice(db.Model):
    """Monthly billing invoices per tenant"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    month = db.Column(db.String(7))  # '2026-04'
    base_fee = db.Column(db.Float, default=0)
    transaction_fee = db.Column(db.Float, default=0)
    extra_user_fee = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(32), default='pending')  # pending/paid/overdue
    due_date = db.Column(db.Date)
    paid_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='invoices')
