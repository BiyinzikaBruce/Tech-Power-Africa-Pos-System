"""WSGI entry point for Vercel deployment"""
from app import app
from models import db, Tenant, User, Branch


def ensure_demo_data():
    if Tenant.query.first():
        return

    default_tenant = Tenant(
        name='Tech Power Africa Demo',
        slug='demo',
        license_key='DEMO-KEY-0000',
        plan='pro',
        contact_email='demo@techpower.africa',
        max_users=20,
        max_branches=5,
        is_active=True
    )
    db.session.add(default_tenant)
    db.session.flush()

    branch = Branch(name='Head Office', location='Nairobi', tenant_id=default_tenant.id)
    db.session.add(branch)
    db.session.flush()

    demo_users = [
        User(name='Admin', email='admin@techpower.africa', role='admin', branch_id=branch.id, tenant_id=default_tenant.id),
        User(name='Supervisor', email='supervisor@techpower.africa', role='supervisor', branch_id=branch.id, tenant_id=default_tenant.id),
        User(name='Manager', email='manager@techpower.africa', role='manager', branch_id=branch.id, tenant_id=default_tenant.id),
        User(name='Cashier', email='cashier@techpower.africa', role='cashier', branch_id=branch.id, tenant_id=default_tenant.id),
    ]
    for user in demo_users:
        user.set_password('admin123' if user.role == 'admin' else f'{user.role}123')
        db.session.add(user)

    db.session.commit()
    print('✅ Demo tenant and users created for deployment.\n  - admin@techpower.africa / admin123\n  - supervisor@techpower.africa / supervisor123\n  - manager@techpower.africa / manager123\n  - cashier@techpower.africa / cashier123')


with app.app_context():
    db.create_all()
    ensure_demo_data()

if __name__ == "__main__":
    app.run()
