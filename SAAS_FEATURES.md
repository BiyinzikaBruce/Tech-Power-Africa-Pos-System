# Tech Power Africa POS - SaaS Multi-Tenant Architecture

## Overview

This POS system has been architected as a **Software-as-a-Service (SaaS)** platform to support multiple companies (tenants) using the same application while maintaining complete data isolation and independent billing.

---

## Architecture

### Multi-Tenancy Model

Each company (tenant) has:
- **Unique License Key** - For account verification and licensing
- **Independent Database Records** - All data isolated by `tenant_id`
- **Separate Billing** - Monthly invoicing based on usage
- **API Keys** - For third-party integrations
- **Role-Based Users** - Admin, Manager, Supervisor, Cashier per tenant
- **Multiple Branches** - Depending on plan

### Data Isolation

Every table includes `tenant_id` foreign key:
```python
class User:
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

class Sale:
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

class Branch:
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
```

All queries automatically filter by tenant:
```python
# Queries must include tenant_id to prevent data leakage
Sale.query.filter_by(tenant_id=current_user.tenant_id).all()
```

---

## Monetization Plans

### Pricing Tiers

| Plan | Monthly Fee | Per-Transaction | Max Users | Max Branches |
|------|-------------|-----------------|-----------|--------------|
| **Starter** | $99 | $0.50 | 5 | 1 |
| **Pro** | $299 | $0.30 | 20 | 5 |
| **Enterprise** | Custom | $0.10 | Unlimited | Unlimited |

### Revenue Breakdown

**Example: Pro Plan with 50 sales/month**
- Base Fee: $299.00
- Transaction Fee: 50 × $0.30 = $15.00
- Extra Users Fee: (8 users - 20 limit) = $0
- **Total Monthly Invoice: $314.00**

Extra charges:
- Additional user slots: $10/month per extra user
- Upgrade to higher plan: Prorated

---

## Customer Onboarding

### 1. Signup Flow
```
1. User visits /saas/signup
2. Enters company details (name, slug, email, password)
3. Selects plan (Starter/Pro/Enterprise)
4. Creates admin account
5. Receives unique license key
6. Redirected to login
```

### 2. Initial Setup
```
1. Admin logs in
2. Views tenant dashboard
3. Sets contact phone number
4. Creates API keys for integrations
5. Adds first branch and users
```

### 3. Daily Operations
```
- Cashiers record sales → Usage tracked
- Sales counted for billing
- Dashboard shows real-time metrics
- Automatic monthly invoicing
```

---

## Usage Tracking & Billing

### Tracked Metrics

```python
log_usage(tenant_id, metric, value)

# Examples:
log_usage(tenant_id, 'sales_count', 1)      # Per transaction
log_usage(tenant_id, 'users_active', 12)    # Daily user count
log_usage(tenant_id, 'api_calls', 156)      # API endpoint calls
```

### Invoice Generation

Monthly invoices are automatically generated:

```python
def generate_monthly_invoice(tenant_id, month_str):
    # Calculates:
    # 1. Base fee from plan
    # 2. Transaction fees (sales count × per-tx rate)
    # 3. Extra user charges (if over limit)
    # 4. Total due
    # 5. Due date (28th of month)
```

### Dashboard Metrics

Tenants see on `/tenant/dashboard`:
- Total sales this month
- Active user count vs. plan limit
- Branch count vs. plan limit
- Current invoice with breakdown
- Usage activity log
- Billing history (past 12 months)

---

## API Key Management

### Creating API Keys

```python
POST /tenant/api-key/create
{
  "name": "Mobile App Integration"
}

Response:
{
  "key": "key_abc123...",
  "secret": "secret_xyz789..."  # Only shown once
}
```

### Using API Keys

Include in Authorization header:
```
Authorization: Bearer key_abc123
```

### Available Endpoints

- `POST /api/v1/sales` - Record sale
- `GET /api/v1/sales` - List sales
- `GET /api/v1/products` - List products
- `GET /api/v1/branches` - List branches
- `GET /api/v1/usage` - Usage metrics

---

## Database Schema

### Tenant Table
```python
class Tenant(db.Model):
    id                  # Primary key
    name                # Company name
    slug                # URL slug (unique)
    license_key         # Unique license key
    plan                # starter/pro/enterprise
    max_users           # Plan limit
    max_branches        # Plan limit
    contact_email       # Admin email
    contact_phone       # Support phone
    is_active          # Account status
    created_at
    updated_at
```

### Invoice Table
```python
class Invoice(db.Model):
    id
    tenant_id           # Which tenant
    month               # YYYY-MM
    base_fee            # Plan base fee
    transaction_fee     # Sales × rate
    extra_user_fee      # Overage charges
    total               # Total amount due
    status              # pending/paid/overdue
    due_date
    paid_date
    created_at
```

### UsageLog Table
```python
class UsageLog(db.Model):
    id
    tenant_id           # Which tenant
    metric              # sales_count, api_calls, etc
    value               # Numeric value
    date                # When recorded
```

### APIKey Table
```python
class APIKey(db.Model):
    id
    tenant_id
    name                # Key description
    key                 # Public key
    secret              # Private secret
    is_active
    last_used
    created_at
```

---

## Implementation Checklist

### Phase 1: Core Multi-Tenancy ✓
- [x] Tenant model with license keys
- [x] User/Branch/Product tenant relationships
- [x] Tenant signup flow
- [x] Tenant dashboard
- [x] Usage tracking on sales

### Phase 2: Billing ✓
- [x] Invoice model
- [x] Monthly invoice generation
- [x] Invoice dashboard
- [x] Plan limits enforcement

### Phase 3: API Keys ✓
- [x] APIKey model and generation
- [x] API key management interface
- [x] Key activation/deactivation

### Phase 4: Next Steps (Recommended)
- [ ] Stripe payment integration
- [ ] Automated invoice email delivery
- [ ] Usage alerts (e.g., near user limit)
- [ ] Admin panel for support team
- [ ] Trial period (free 14-day starter plan)
- [ ] Auto-upgrade warnings
- [ ] Usage API endpoint
- [ ] Advanced analytics dashboard
- [ ] Webhook notifications
- [ ] Single Sign-On (SSO)

---

## Security Considerations

### Tenant Isolation
- ✓ Every query filters by `current_user.tenant_id`
- ✓ Never expose data without tenant validation
- ✓ API keys have limited scopes
- ✓ License key verification on login

### Data Protection
- [ ] Encrypt sensitive fields (phone, API secret)
- [ ] Implement audit logging
- [ ] Data retention policies
- [ ] GDPR compliance (right to be forgotten)
- [ ] SOC 2 compliance

### Rate Limiting
- [ ] API rate limits per tenant plan
- [ ] Query result limits
- [ ] File upload limits

---

## Deployment Notes

### Database Initialization

```bash
flask --app app initdb
```

This creates:
1. Demo tenant "Tech Power Africa Demo"
2. Demo users for all roles
3. Default branch

### Environment Variables

```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=noreply@techpower.africa
REPORT_RECIPIENT_EMAILS=admin@techpower.africa,owner@techpower.africa
DAILY_REPORT_TIME=18:00
```

### Next Deployment Steps

1. **Payment Processing**
   - Integrate Stripe (recommended)
   - Sync invoices to Stripe
   - Handle webhooks for payment status

2. **Monitoring & Analytics**
   - Track MRR (Monthly Recurring Revenue)
   - Monitor churn rate
   - Alert on overdue invoices

3. **Customer Support**
   - Support ticketing system
   - Feature requests board
   - Knowledge base

4. **Marketing**
   - Landing page with pricing
   - Free trial signup
   - Documentation site

---

## Example: Adding a New Tenant

```python
# Via API (programmatically)
tenant = Tenant(
    name='Best Store Ltd',
    slug='best-store',
    license_key=generate_license_key(),
    plan='pro',
    contact_email='owner@beststore.com'
)
db.session.add(tenant)
db.session.flush()

# Create admin user
admin = User(
    name='Store Owner',
    email='owner@beststore.com',
    role='admin',
    tenant_id=tenant.id
)
admin.set_password('secure_password')
db.session.add(admin)

# Create first branch
branch = Branch(
    name='Main Store',
    location='Nairobi CBD',
    tenant_id=tenant.id
)
db.session.add(branch)
db.session.commit()

print(f"Tenant created with license key: {tenant.license_key}")
```

---

## Revenue Projection Example

**500 Starter Plan Customers**
```
Base Fee: 500 × $99 = $49,500/month
Avg Sales/month: 100 per customer
Transaction Fees: 500 × 100 × $0.50 = $25,000/month
Extra User Charges: ~$5,000/month

Total MRR = $79,500
Annual ARR = $954,000
```

---

## Support & Resources

For production deployment:
- Add email notifications on invoice due
- Implement payment retry logic
- Create admin panel for support team
- Set up usage alerts
- Monitor system performance
- Implement backup strategy

---

*Last Updated: 2026-04-29*
*Version: 1.0 Multi-Tenant SaaS*
