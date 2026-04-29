import os
import time
import threading
import secrets
import hashlib
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from config import Config
from models import db, User, Branch, Product, Stock, Sale, SaleItem, StockTransfer, Tenant, APIKey, UsageLog, Invoice
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@app.context_processor
def inject_current_year():
    return {'current_year': date.today().year}


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def role_required(*roles):
    def wrapper(func):
        from functools import wraps

        @wraps(func)
        def decorated_view(*args, **kwargs):
            if current_user.role not in roles:
                flash('Access denied.', 'warning')
                return redirect(url_for('dashboard'))
            return func(*args, **kwargs)

        return decorated_view

    return wrapper


def tenant_required(func):
    """Decorator to ensure user belongs to a tenant and has active access"""
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.tenant:
            flash('Tenant access required.', 'danger')
            return redirect(url_for('login'))
        if not current_user.tenant.is_active:
            flash('This tenant account is inactive. Contact support.', 'danger')
            return redirect(url_for('logout'))
        return func(*args, **kwargs)
    return decorated_view


def log_usage(tenant_id, metric, value=1):
    """Log usage metric for billing purposes"""
    try:
        usage = UsageLog(tenant_id=tenant_id, metric=metric, value=value)
        db.session.add(usage)
        db.session.commit()
    except Exception as e:
        app.logger.error(f'Failed to log usage: {e}')


def generate_license_key():
    """Generate unique license key for tenant"""
    return f'TPA-{secrets.token_hex(16).upper()}'


def generate_api_key_pair():
    """Generate API key and secret"""
    key = f'key_{secrets.token_urlsafe(32)}'
    secret = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    return key, secret


def get_tenant_plan_limits(plan):
    """Get limits based on plan type"""
    plans = {
        'starter': {'max_users': 5, 'max_branches': 1, 'base_fee': 99.0, 'tx_fee': 0.50},
        'pro': {'max_users': 20, 'max_branches': 5, 'base_fee': 299.0, 'tx_fee': 0.30},
        'enterprise': {'max_users': 999, 'max_branches': 999, 'base_fee': 999.0, 'tx_fee': 0.10}
    }
    return plans.get(plan, plans['starter'])


def get_report_recipients():
    recipients = app.config.get('REPORT_RECIPIENT_EMAILS') or []
    if not recipients:
        recipients = [user.email for user in User.query.filter_by(role='admin').all()]
    return recipients


def generate_monthly_invoice(tenant_id, month_str):
    """Generate invoice for a tenant for the given month (YYYY-MM)"""
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return None
    
    # Check if invoice already exists
    existing = Invoice.query.filter_by(tenant_id=tenant_id, month=month_str).first()
    if existing:
        return existing
    
    # Get plan limits
    limits = get_tenant_plan_limits(tenant.plan)
    
    # Count transactions in the month
    month_start = f'{month_str}-01'
    if month_str.endswith('-12'):
        month_end = f'{int(month_str[:4])+1}-01-01'
    else:
        next_month = str(int(month_str.split('-')[1])+1).zfill(2)
        month_end = f'{month_str[:4]}-{next_month}-01'
    
    sales = Sale.query.filter(Sale.tenant_id==tenant_id, Sale.date>=month_start, Sale.date<month_end).count()
    
    # Calculate fees
    base_fee = limits['base_fee']
    transaction_fee = sales * limits['tx_fee']
    
    # Count users (extra users beyond plan)
    user_count = User.query.filter_by(tenant_id=tenant_id).count()
    extra_user_fee = max(0, user_count - limits['max_users']) * 10  # $10 per extra user
    
    total = base_fee + transaction_fee + extra_user_fee
    due_date = datetime.strptime(f'{month_str}-28', '%Y-%m-%d').date()
    
    invoice = Invoice(
        tenant_id=tenant_id,
        month=month_str,
        base_fee=base_fee,
        transaction_fee=transaction_fee,
        extra_user_fee=extra_user_fee,
        total=total,
        due_date=due_date
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def build_report_for_date(target_date):
    sales = Sale.query.filter(Sale.date == target_date).all()
    summary = {}
    total_sales = 0
    for sale in sales:
        branch_name = sale.branch.name
        summary.setdefault(branch_name, {'count': 0, 'total': 0})
        summary[branch_name]['count'] += 1
        summary[branch_name]['total'] += sale.total_amount
        total_sales += sale.total_amount
    lines = [f'Daily Sales Report for {target_date}', '']
    for branch_name, data in summary.items():
        lines.append(f'{branch_name}: {data["count"]} sales, total UGX {data["total"]:.2f}')
    lines.append('')
    lines.append(f'Total sales: UGX {total_sales:.2f}')
    return '\n'.join(lines), sales, summary, total_sales


def send_daily_report(target_date=None):
    target_date = target_date or date.today().isoformat()
    recipients = get_report_recipients()
    if not recipients:
        return 0
    body, sales, summary, total_sales = build_report_for_date(target_date)
    subject = f'Tech Power Africa Daily Sales {target_date}'
    for recipient in recipients:
        send_email(recipient, subject, body)
    return len(recipients)


def schedule_daily_reports():
    while True:
        now = datetime.now()
        try:
            report_time = datetime.strptime(app.config['DAILY_REPORT_TIME'], '%H:%M').time()
        except Exception:
            report_time = datetime.strptime('18:00', '%H:%M').time()
        next_run = datetime.combine(now.date(), report_time)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        time.sleep(wait_seconds)
        with app.app_context():
            try:
                count = send_daily_report()
                app.logger.info(f'Daily report sent to {count} recipients for {date.today().isoformat()}')
            except Exception as exc:
                app.logger.error('Scheduled daily report failed: %s', exc)


@app.before_request
def start_daily_report_scheduler():
    if not hasattr(app, '_scheduler_started'):
        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            thread = threading.Thread(target=schedule_daily_reports, daemon=True)
            thread.start()
            app._scheduler_started = True


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            # Check tenant is active
            if not user.tenant or not user.tenant.is_active:
                flash('Your account is inactive. Contact support.', 'danger')
                return redirect(url_for('login'))
            login_user(user)
            flash(f'Welcome, {user.name}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        branches = Branch.query.order_by(Branch.name).all()
        users = User.query.order_by(User.role, User.name).all()
        products = Product.query.order_by(Product.name).all()
        low_stock_alerts = Stock.query.filter(Stock.quantity <= Stock.alert_threshold).all()
        today_sales = Sale.query.filter(Sale.date == date.today().isoformat()).all()
        today_total = sum(sale.total_amount for sale in today_sales)
        return render_template(
            'admin_dashboard.html',
            branches=branches,
            users=users,
            products=products,
            low_stock_alerts=low_stock_alerts,
            today_total=today_total,
        )
    if current_user.role in ('manager', 'supervisor'):
        branch = current_user.branch
        stocks = Stock.query.filter_by(branch_id=branch.id).join(Product).all()
        sales = Sale.query.filter_by(branch_id=branch.id).order_by(Sale.date.desc()).limit(10).all()
        low_stock_alerts = [stock for stock in stocks if stock.is_low]
        return render_template('manager_dashboard.html', branch=branch, stocks=stocks, sales=sales, low_stock_alerts=low_stock_alerts)
    if current_user.role == 'cashier':
        branch = current_user.branch
        products = Product.query.order_by(Product.name).all()
        return render_template('cashier_dashboard.html', branch=branch, products=products)
    flash('Role not supported.', 'warning')
    return redirect(url_for('logout'))


@app.route('/admin/branches', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_branches():
    if request.method == 'POST':
        name = request.form['name'].strip()
        location = request.form['location'].strip()
        if name:
            branch = Branch(name=name, location=location)
            db.session.add(branch)
            db.session.commit()
            flash('Branch added.', 'success')
        return redirect(url_for('manage_branches'))
    branches = Branch.query.order_by(Branch.name).all()
    return render_template('branch_form.html', branches=branches)


@app.route('/admin/branch/<int:branch_id>')
@login_required
@role_required('admin')
def branch_view(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    stocks = Stock.query.filter_by(branch_id=branch_id).join(Product).order_by(Product.name).all()
    sales = Sale.query.filter_by(branch_id=branch_id).order_by(Sale.date.desc()).limit(20).all()
    workers = User.query.filter_by(branch_id=branch_id).order_by(User.role, User.name).all()
    return render_template('branch_view.html', branch=branch, stocks=stocks, sales=sales, workers=workers)


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_users():
    branches = Branch.query.order_by(Branch.name).all()
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        role = request.form['role']
        branch_id = request.form.get('branch_id') or None
        password = request.form['password']
        if not name or not email or not password:
            flash('Name, email, and password are required.', 'danger')
            return redirect(url_for('manage_users'))
        if User.query.filter_by(email=email).first():
            flash('User already exists.', 'warning')
            return redirect(url_for('manage_users'))
        user = User(name=name, email=email, role=role, branch_id=branch_id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('User created.', 'success')
        return redirect(url_for('manage_users'))
    users = User.query.order_by(User.role, User.name).all()
    return render_template('user_form.html', users=users, branches=branches)


@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_products():
    if request.method == 'POST':
        name = request.form['name'].strip()
        sku = request.form['sku'].strip()
        category = request.form.get('category', '').strip() or None
        cost = float(request.form['cost'] or 0)
        price = float(request.form['price'] or 0)
        if name and sku:
            product = Product(name=name, sku=sku, category=category, cost=cost, price=price)
            db.session.add(product)
            db.session.commit()
            flash('Product added.', 'success')
        return redirect(url_for('manage_products'))
    products = Product.query.order_by(Product.name).all()
    return render_template('product_form.html', products=products)


@app.route('/admin/stock', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'supervisor')
def manage_stock():
    branches = Branch.query.order_by(Branch.name).all()
    products = Product.query.order_by(Product.name).all()
    if request.method == 'POST':
        branch_id = int(request.form['branch_id'])
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])
        threshold = int(request.form.get('alert_threshold') or 5)
        stock = Stock.query.filter_by(branch_id=branch_id, product_id=product_id).first()
        if not stock:
            stock = Stock(branch_id=branch_id, product_id=product_id, quantity=0, alert_threshold=threshold)
            db.session.add(stock)
        stock.quantity += quantity
        stock.alert_threshold = threshold
        db.session.commit()
        flash('Stock updated.', 'success')
        return redirect(url_for('manage_stock'))
    stocks = Stock.query.join(Branch).join(Product).order_by(Branch.name, Product.name).all()
    if current_user.role in ('manager', 'supervisor'):
        stocks = [item for item in stocks if item.branch_id == current_user.branch_id]
    return render_template('stock_form.html', branches=branches, products=products, stocks=stocks)


@app.route('/admin/transfers', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'manager', 'supervisor')
def transfer_stock():
    branches = Branch.query.order_by(Branch.name).all()
    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        from_branch_id = int(request.form['from_branch_id'])
        to_branch_id = int(request.form['to_branch_id'])
        quantity = int(request.form['quantity'])
        if from_branch_id == to_branch_id:
            flash('Choose different source and destination branches.', 'warning')
            return redirect(url_for('transfer_stock'))
        from_stock = Stock.query.filter_by(branch_id=from_branch_id, product_id=product_id).first()
        if not from_stock or from_stock.quantity < quantity:
            flash('Insufficient stock to transfer.', 'danger')
            return redirect(url_for('transfer_stock'))
        to_stock = Stock.query.filter_by(branch_id=to_branch_id, product_id=product_id).first()
        if not to_stock:
            to_stock = Stock(branch_id=to_branch_id, product_id=product_id, quantity=0)
            db.session.add(to_stock)
        from_stock.quantity -= quantity
        to_stock.quantity += quantity
        transfer = StockTransfer(
            product_id=product_id,
            from_branch_id=from_branch_id,
            to_branch_id=to_branch_id,
            quantity=quantity,
        )
        db.session.add(transfer)
        db.session.commit()
        flash('Stock transfer completed.', 'success')
        return redirect(url_for('transfer_stock'))
    transfers = StockTransfer.query.order_by(StockTransfer.date.desc()).limit(20).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('transfer_form.html', branches=branches, products=products, transfers=transfers)


@app.route('/cashier/sale', methods=['GET', 'POST'])
@login_required
@role_required('cashier')
def record_sale():
    branch = current_user.branch
    products = Product.query.order_by(Product.name).all()
    if request.method == 'POST':
        payment_type = request.form['payment_type']
        items = []
        total_amount = 0
        for product in products:
            quantity = int(request.form.get(f'quantity_{product.id}', 0) or 0)
            if quantity <= 0:
                continue
            stock = Stock.query.filter_by(branch_id=branch.id, product_id=product.id).first()
            if not stock or stock.quantity < quantity:
                flash(f'Insufficient stock for {product.name}.', 'danger')
                return redirect(url_for('record_sale'))
            items.append((product, quantity))
            total_amount += product.price * quantity
        if not items:
            flash('Select at least one product.', 'warning')
            return redirect(url_for('record_sale'))
        sale = Sale(branch_id=branch.id, user_id=current_user.id, payment_type=payment_type, tenant_id=current_user.tenant_id)
        db.session.add(sale)
        db.session.flush()
        for product, quantity in items:
            stock = Stock.query.filter_by(branch_id=branch.id, product_id=product.id).first()
            stock.quantity -= quantity
            sale_item = SaleItem(sale_id=sale.id, product_id=product.id, quantity=quantity, unit_price=product.price)
            db.session.add(sale_item)
        db.session.commit()
        # Log usage for billing
        log_usage(current_user.tenant_id, 'sales_count', 1)
        flash('Sale recorded.', 'success')
        return redirect(url_for('receipt', sale_id=sale.id))
    return render_template('sale_form.html', branch=branch, products=products)


@app.route('/cashier/receipt/<int:sale_id>')
@login_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if current_user.role == 'cashier' and sale.branch_id != current_user.branch_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('receipt.html', sale=sale)


@app.route('/products/categories')
@login_required
def product_categories():
    categories = db.session.query(Product.category).distinct().filter(Product.category.isnot(None)).all()
    category_data = {}
    for cat in categories:
        cat_name = cat[0]
        products = Product.query.filter_by(category=cat_name).all()
        category_data[cat_name] = products
    uncategorized = Product.query.filter(Product.category.is_(None)).all()
    if uncategorized:
        category_data['Uncategorized'] = uncategorized
    return render_template('product_categories.html', category_data=category_data)


@app.route('/reports/analytics')
@login_required
@role_required('admin', 'manager', 'supervisor')
def analytics():
    start_date = date.today() - timedelta(days=6)
    labels = []
    dates = []
    for i in range(7):
        current = start_date + timedelta(days=i)
        labels.append(current.strftime('%b %d'))
        dates.append(current.isoformat())
    if current_user.role in ('manager', 'supervisor'):
        branches = [current_user.branch]
    else:
        branches = Branch.query.order_by(Branch.name).all()
    branch_ids = [branch.id for branch in branches]
    raw_sales = Sale.query.filter(Sale.date >= dates[0], Sale.date <= dates[-1], Sale.branch_id.in_(branch_ids)).all()
    branch_map = {branch.id: branch.name for branch in branches}
    sales_by_branch = {branch.name: [0] * 7 for branch in branches}
    day_index = {date_str: idx for idx, date_str in enumerate(dates)}
    for sale in raw_sales:
        if sale.date in day_index and sale.branch_id in branch_map:
            branch_name = branch_map[sale.branch_id]
            sales_by_branch[branch_name][day_index[sale.date]] += sale.total_amount
    return render_template('analytics.html', labels=labels, sales_by_branch=sales_by_branch)


@app.route('/reports/profit')
@login_required
@role_required('admin', 'manager', 'supervisor')
def profit_reports():
    start_date = request.args.get('start_date') or (date.today() - timedelta(days=30)).isoformat()
    end_date = request.args.get('end_date') or date.today().isoformat()
    query = Sale.query.filter(Sale.date >= start_date, Sale.date <= end_date)
    if current_user.role in ('manager', 'supervisor'):
        query = query.filter_by(branch_id=current_user.branch_id)
    sales = query.all()
    branch_profits = {}
    total_profit = 0
    for sale in sales:
        branch_name = sale.branch.name
        profit = sum((item.unit_price - item.product.cost) * item.quantity for item in sale.items)
        branch_profits.setdefault(branch_name, {'sales': 0, 'profit': 0})
        branch_profits[branch_name]['sales'] += sale.total_amount
        branch_profits[branch_name]['profit'] += profit
        total_profit += profit
    return render_template('profit_reports.html', start_date=start_date, end_date=end_date, branch_profits=branch_profits, total_profit=total_profit)


@app.route('/reports/daily')
@login_required
@role_required('admin', 'manager', 'supervisor')
def daily_reports():
    query_date = request.args.get('date') or date.today().isoformat()
    query = Sale.query.filter(Sale.date == query_date)
    if current_user.role in ('manager', 'supervisor'):
        query = query.filter_by(branch_id=current_user.branch_id)
    sales = query.order_by(Sale.date.desc()).all()
    summary = {}
    for sale in sales:
        key = sale.branch.name
        summary.setdefault(key, {'count': 0, 'total': 0})
        summary[key]['count'] += 1
        summary[key]['total'] += sale.total_amount
    schedule_time = app.config.get('DAILY_REPORT_TIME')
    recipients = app.config.get('REPORT_RECIPIENT_EMAILS')
    return render_template('reports.html', query_date=query_date, sales=sales, summary=summary, schedule_time=schedule_time, recipients=recipients)


@app.route('/reports/send_email', methods=['POST'])
@login_required
@role_required('admin')
def send_email_report():
    target_date = request.form.get('date') or date.today().isoformat()
    admin_email = request.form.get('admin_email') or app.config['MAIL_DEFAULT_SENDER']
    if not admin_email:
        flash('Admin email is required.', 'danger')
        return redirect(url_for('daily_reports'))
    body, sales, summary, total_sales = build_report_for_date(target_date)
    try:
        send_email(admin_email, f'Tech Power Africa Daily Sales {target_date}', body)
        flash(f'Report sent to {admin_email}.', 'success')
    except Exception as exc:
        flash(f'Email failed: {exc}', 'danger')
    return redirect(url_for('daily_reports'))


def send_email(recipient, subject, body):
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = app.config['MAIL_DEFAULT_SENDER']
    message['To'] = recipient
    message.set_content(body)
    with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as smtp:
        if app.config['MAIL_USE_TLS']:
            smtp.starttls()
        smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        smtp.send_message(message)


# ===== SAAS ROUTES =====

@app.route('/saas/signup', methods=['GET', 'POST'])
def saas_signup():
    """Tenant signup/onboarding"""
    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
        contact_email = request.form.get('contact_email', '').strip().lower()
        plan = request.form.get('plan', 'starter')
        admin_name = request.form.get('admin_name', '').strip()
        admin_password = request.form.get('admin_password', '')
        
        if not all([company_name, slug, contact_email, admin_name, admin_password]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('saas_signup'))
        
        if Tenant.query.filter_by(slug=slug).first():
            flash('Slug already taken.', 'warning')
            return redirect(url_for('saas_signup'))
        
        # Create tenant
        license_key = generate_license_key()
        tenant = Tenant(
            name=company_name,
            slug=slug,
            license_key=license_key,
            plan=plan,
            contact_email=contact_email,
            **get_tenant_plan_limits(plan)
        )
        db.session.add(tenant)
        db.session.flush()
        
        # Create admin user
        admin = User(
            name=admin_name,
            email=contact_email,
            role='admin',
            tenant_id=tenant.id
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        
        flash(f'Tenant created! License key: {license_key}. Log in with your email.', 'success')
        return redirect(url_for('login'))
    
    return render_template('saas_signup.html')


@app.route('/tenant/dashboard')
@login_required
@tenant_required
def tenant_dashboard():
    """Tenant admin dashboard showing usage and billing"""
    tenant = current_user.tenant
    
    # Current month
    current_month = date.today().strftime('%Y-%m')
    
    # Get or create invoice
    invoice = Invoice.query.filter_by(tenant_id=tenant.id, month=current_month).first()
    if not invoice:
        invoice = generate_monthly_invoice(tenant.id, current_month)
    
    # Usage stats
    sales_count = Sale.query.filter_by(tenant_id=tenant.id).count()
    user_count = User.query.filter_by(tenant_id=tenant.id).count()
    branch_count = Branch.query.filter_by(tenant_id=tenant.id).count()
    
    # Plan limits
    limits = get_tenant_plan_limits(tenant.plan)
    
    # Recent usage
    usage_logs = UsageLog.query.filter_by(tenant_id=tenant.id).order_by(UsageLog.date.desc()).limit(20).all()
    
    # Recent invoices
    invoices = Invoice.query.filter_by(tenant_id=tenant.id).order_by(Invoice.month.desc()).limit(12).all()
    
    return render_template('tenant_dashboard.html', 
                         tenant=tenant, 
                         invoice=invoice,
                         sales_count=sales_count,
                         user_count=user_count,
                         branch_count=branch_count,
                         limits=limits,
                         usage_logs=usage_logs,
                         invoices=invoices)


@app.route('/tenant/api-keys')
@login_required
@tenant_required
@role_required('admin')
def manage_api_keys():
    """Manage API keys for tenant"""
    tenant = current_user.tenant
    api_keys = APIKey.query.filter_by(tenant_id=tenant.id).all()
    return render_template('api_keys.html', api_keys=api_keys, tenant=tenant)


@app.route('/tenant/api-key/create', methods=['POST'])
@login_required
@tenant_required
@role_required('admin')
def create_api_key():
    """Create new API key"""
    tenant = current_user.tenant
    name = request.form.get('name', 'API Key').strip()
    
    key, secret = generate_api_key_pair()
    api_key = APIKey(tenant_id=tenant.id, name=name, key=key, secret=secret)
    db.session.add(api_key)
    db.session.commit()
    
    flash(f'API Key created. Secret: {secret} (save this, you won\'t see it again)', 'success')
    return redirect(url_for('manage_api_keys'))


@app.route('/tenant/api-key/<int:key_id>/delete', methods=['POST'])
@login_required
@tenant_required
@role_required('admin')
def delete_api_key(key_id):
    """Delete an API key"""
    api_key = APIKey.query.get_or_404(key_id)
    if api_key.tenant_id != current_user.tenant_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('manage_api_keys'))
    
    db.session.delete(api_key)
    db.session.commit()
    flash('API Key deleted.', 'success')
    return redirect(url_for('manage_api_keys'))


@app.route('/tenant/settings')
@login_required
@tenant_required
@role_required('admin')
def tenant_settings():
    """Tenant account settings"""
    tenant = current_user.tenant
    if request.method == 'POST':
        tenant.contact_phone = request.form.get('contact_phone', '').strip()
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('tenant_settings'))
    
    return render_template('tenant_settings.html', tenant=tenant)


@app.cli.command('initdb')
def init_db():
    db.create_all()
    
    # Create default tenant if not exists
    if not Tenant.query.first():
        default_tenant = Tenant(
            name='Tech Power Africa Demo',
            slug='demo',
            license_key=generate_license_key(),
            plan='pro',
            contact_email='demo@techpower.africa'
        )
        db.session.add(default_tenant)
        db.session.flush()
        
        # Create default branch for tenant
        branch = Branch(name='Head Office', location='Nairobi', tenant_id=default_tenant.id)
        db.session.add(branch)
        db.session.flush()
        
        # Create admin user
        admin = User(name='Admin', email='admin@techpower.africa', role='admin', tenant_id=default_tenant.id)
        admin.set_password('admin123')
        db.session.add(admin)
        
        # Create supervisor user
        supervisor = User(name='Supervisor', email='supervisor@techpower.africa', role='supervisor', branch_id=branch.id, tenant_id=default_tenant.id)
        supervisor.set_password('supervisor123')
        db.session.add(supervisor)
        
        # Create manager user
        manager = User(name='Manager', email='manager@techpower.africa', role='manager', branch_id=branch.id, tenant_id=default_tenant.id)
        manager.set_password('manager123')
        db.session.add(manager)
        
        # Create cashier user
        cashier = User(name='Cashier', email='cashier@techpower.africa', role='cashier', branch_id=branch.id, tenant_id=default_tenant.id)
        cashier.set_password('cashier123')
        db.session.add(cashier)
        
        db.session.commit()
        
        print('✓ Created default tenant: Tech Power Africa Demo')
        print(f'✓ License Key: {default_tenant.license_key}')
        print('✓ Created users:')
        print('  - admin@techpower.africa / admin123')
        print('  - supervisor@techpower.africa / supervisor123')
        print('  - manager@techpower.africa / manager123')
        print('  - cashier@techpower.africa / cashier123')


if __name__ == '__main__':
    app.run(debug=True)
