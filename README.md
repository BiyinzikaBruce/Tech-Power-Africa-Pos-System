# Tech Power Africa POS System

A web-based point-of-sale system for branch inventory, sales, receipts, stock transfers, and email reporting.

## Features
- Admin, supervisor, manager, and cashier roles
- Branch-aware stock management with low-stock alerts
- Product categories and cost/profit tracking
- Sales recording with cash / mobile money payment types
- Receipt generation for each sale
- Daily sales report with email delivery (scheduled and manual)
- Analytics dashboard with 7-day sales charts
- Profit reports by branch and date range
- Product categories page
- SQLite database for fast prototyping

## Setup
1. Create a Python virtual environment and activate it.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set environment variables for email and scheduling:
   - `MAIL_SERVER`
   - `MAIL_PORT`
   - `MAIL_USERNAME`
   - `MAIL_PASSWORD`
   - `MAIL_DEFAULT_SENDER`
   - `REPORT_RECIPIENT_EMAILS` (comma-separated admin emails to receive scheduled reports)
   - `DAILY_REPORT_TIME` (e.g. `18:00`)
   - `SECRET_KEY` (optional)

4. Initialize the database and default users:
   ```bash
   flask --app app initdb
   ```

5. Run the application:
   ```bash
   flask --app app run
   ```

## Default accounts
- `admin@techpower.africa` / `admin123`
- `supervisor@techpower.africa` / `supervisor123`
- `manager@techpower.africa` / `manager123`
- `cashier@techpower.africa` / `cashier123`

## Notes
- Use admin to add branches, products, and users.
- Supervisors and managers can update branch stock and view branch reports.
- Cashiers can record sales and print receipts.
- Email reporting is available from the admin dashboard.
- Scheduled daily reports send automatically at the configured time.
