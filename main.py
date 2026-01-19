from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import random
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')

# Database configuration
if os.environ.get('DATABASE_URL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bank.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Available banks for withdrawal
AVAILABLE_BANKS = {
    'US': [
        {'code': 'chase', 'name': 'Chase Bank', 'country': 'USA'},
        {'code': 'wells_fargo', 'name': 'Wells Fargo', 'country': 'USA'},
        {'code': 'bank_of_america', 'name': 'Bank of America', 'country': 'USA'},
        {'code': 'citi', 'name': 'Citibank', 'country': 'USA'},
        {'code': 'capital_one', 'name': 'Capital One', 'country': 'USA'},
    ],
    'CA': [
        {'code': 'rbc', 'name': 'Royal Bank of Canada', 'country': 'Canada'},
        {'code': 'td', 'name': 'TD Canada Trust', 'country': 'Canada'},
        {'code': 'scotiabank', 'name': 'Scotiabank', 'country': 'Canada'},
        {'code': 'bmo', 'name': 'Bank of Montreal', 'country': 'Canada'},
        {'code': 'cibc', 'name': 'CIBC', 'country': 'Canada'},
    ],
    'AU': [
        {'code': 'commonwealth', 'name': 'Commonwealth Bank', 'country': 'Australia'},
        {'code': 'westpac', 'name': 'Westpac', 'country': 'Australia'},
        {'code': 'anz', 'name': 'ANZ Bank', 'country': 'Australia'},
        {'code': 'nab', 'name': 'National Australia Bank', 'country': 'Australia'},
    ],
    'UK': [
        {'code': 'hsbc', 'name': 'HSBC', 'country': 'UK'},
        {'code': 'barclays', 'name': 'Barclays', 'country': 'UK'},
        {'code': 'lloyds', 'name': 'Lloyds Bank', 'country': 'UK'},
        {'code': 'natwest', 'name': 'NatWest', 'country': 'UK'},
    ]
}

# Models
class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    accounts = db.relationship('Account', backref='owner', lazy=True, cascade="all, delete-orphan")
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade="all, delete-orphan")
    withdrawals = db.relationship('Withdrawal', backref='user', lazy=True, cascade="all, delete-orphan")

class Account(db.Model):
    __tablename__ = 'account'
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='account', lazy=True, cascade="all, delete-orphan")

class Transaction(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'deposit', 'withdraw', 'bonus', 'fee'
    description = db.Column(db.String(200))
    status = db.Column(db.String(20), default='completed')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_notes = db.Column(db.String(500), nullable=True)

class Withdrawal(db.Model):
    __tablename__ = 'withdrawal'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    bank_country = db.Column(db.String(50), nullable=False)
    account_number = db.Column(db.String(50), nullable=False)
    account_holder = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default='processing')  # 'processing', 'approved', 'rejected', 'completed'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    processed_by = db.Column(db.Integer, nullable=True)
    admin_notes = db.Column(db.String(500), nullable=True)

# Create all tables
with app.app_context():
    # Drop all tables if they exist (for clean restart)
    db.drop_all()
    # Create all tables
    db.create_all()
    
    # Create admin user if not exists
    admin_exists = db.session.query(User).filter_by(username='admin').first()
    if not admin_exists:
        admin = User(
            username='admin',
            email='admin@simplebank.com',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        
        # Create admin account
        admin_account = Account(
            account_number=f"ADMIN{random.randint(10000, 99999)}",
            user_id=1,  # Admin will have ID 1
            balance=0.00
        )
        db.session.add(admin_account)
        db.session.commit()
        print("✅ Admin user created: admin / admin123")

# Helper functions
def generate_unique_account_number():
    while True:
        account_number = f"SB{random.randint(10000000, 99999999)}"
        existing_account = db.session.query(Account).filter_by(account_number=account_number).first()
        if not existing_account:
            return account_number

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = db.session.get(User, session['user_id'])
        if not user or not user.is_admin:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please fill all fields', 'danger')
            return render_template('login.html')
        
        user = db.session.query(User).filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('Login successful!', 'success')
            
            if user.is_admin:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not all([username, email, password, confirm_password]):
            flash('Please fill all fields', 'danger')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return render_template('signup.html')
        
        # Check if user exists
        existing_user = db.session.query(User).filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'danger')
            return render_template('signup.html')
        
        existing_email = db.session.query(User).filter_by(email=email).first()
        if existing_email:
            flash('Email already exists', 'danger')
            return render_template('signup.html')
        
        try:
            # Create user
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, email=email, password_hash=hashed_password)
            db.session.add(new_user)
            db.session.flush()  # Get user ID without committing
            
            # Create account for user with unique number
            account_number = generate_unique_account_number()
            new_account = Account(
                account_number=account_number, 
                user_id=new_user.id, 
                balance=0.00  # Start with $0 - only admin can add money
            )
            db.session.add(new_account)
            db.session.flush()  # Get account ID without committing
            
            # Commit everything
            db.session.commit()
            
            flash(f'Account created successfully! Account number: {account_number}. Please contact admin to add funds.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account. Please try again.', 'danger')
            return render_template('signup.html')
    
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = db.session.get(User, session['user_id'])
    account = db.session.query(Account).filter_by(user_id=user.id).first()
    
    if not account:
        flash('Account not found', 'danger')
        return redirect(url_for('logout'))
    
    # Get recent transactions
    transactions = db.session.query(Transaction).filter_by(
        user_id=user.id
    ).order_by(Transaction.created_at.desc()).limit(5).all()
    
    # Get recent withdrawals
    withdrawals = db.session.query(Withdrawal).filter_by(
        user_id=user.id
    ).order_by(Withdrawal.created_at.desc()).limit(5).all()
    
    # Statistics
    total_deposits = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=user.id, 
        type='deposit',
        status='completed'
    ).scalar() or 0
    
    total_withdrawals = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=user.id, 
        type='withdraw',
        status='completed'
    ).scalar() or 0
    
    return render_template('dashboard.html', 
                         user=user, 
                         account=account,
                         transactions=transactions,
                         withdrawals=withdrawals,
                         total_deposits=total_deposits,
                         total_withdrawals=total_withdrawals,
                         banks=AVAILABLE_BANKS)

@app.route('/withdraw/bank', methods=['POST'])
def withdraw_bank():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        amount = float(request.form.get('amount', 0))
        bank_country = request.form.get('bank_country')
        bank_code = request.form.get('bank_code')
        account_number = request.form.get('account_number', '').strip()
        account_holder = request.form.get('account_holder', '').strip()
        email = request.form.get('email', '').strip()
        
        # Validation
        if amount <= 0:
            flash('Amount must be positive', 'danger')
            return redirect(url_for('dashboard'))
        
        if not all([bank_country, bank_code, account_number, account_holder, email]):
            flash('Please fill all withdrawal details', 'danger')
            return redirect(url_for('dashboard'))
        
        user = db.session.get(User, session['user_id'])
        account = db.session.query(Account).filter_by(user_id=user.id).first()
        
        if not account:
            flash('Account not found', 'danger')
            return redirect(url_for('dashboard'))
        
        if account.balance < amount:
            flash('Insufficient funds', 'danger')
            return redirect(url_for('dashboard'))
        
        # Find bank name
        bank_name = "Unknown Bank"
        for bank in AVAILABLE_BANKS.get(bank_country, []):
            if bank['code'] == bank_code:
                bank_name = bank['name']
                break
        
        # Create withdrawal request
        withdrawal = Withdrawal(
            amount=amount,
            bank_name=bank_name,
            bank_country=bank_country,
            account_number=account_number,
            account_holder=account_holder,
            email=email,
            status='processing',
            user_id=user.id,
            account_id=account.id
        )
        
        # Create pending transaction
        transaction = Transaction(
            amount=amount,
            type='withdraw',
            description=f'Withdrawal to {bank_name} ({account_number})',
            status='pending',
            user_id=user.id,
            account_id=account.id
        )
        
        db.session.add(withdrawal)
        db.session.add(transaction)
        db.session.commit()
        
        flash(f'Withdrawal request of ${amount:.2f} submitted successfully! Status: Processing', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing withdrawal: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/get_banks/<country>')
def get_banks(country):
    banks = AVAILABLE_BANKS.get(country, [])
    return jsonify(banks)

@app.route('/admin')
@admin_required
def admin_panel():
    user = db.session.get(User, session['user_id'])
    
    # Get statistics
    total_users = db.session.query(User).count()
    total_accounts = db.session.query(Account).count()
    total_balance = db.session.query(db.func.sum(Account.balance)).scalar() or 0
    
    # Get pending withdrawals
    pending_withdrawals = db.session.query(Withdrawal).filter_by(
        status='processing'
    ).order_by(Withdrawal.created_at.desc()).all()
    
    # Get recent transactions
    recent_transactions = db.session.query(Transaction).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()
    
    # Get all users for deposit form
    all_users = db.session.query(User).all()
    
    return render_template('admin.html',
                         user=user,
                         total_users=total_users,
                         total_accounts=total_accounts,
                         total_balance=total_balance,
                         pending_withdrawals=pending_withdrawals,
                         recent_transactions=recent_transactions,
                         all_users=all_users)

@app.route('/admin/add_deposit', methods=['POST'])
@admin_required
def add_deposit():
    try:
        user_id = int(request.form.get('user_id'))
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description', '').strip()
        admin_notes = request.form.get('admin_notes', '').strip()
        
        if amount <= 0:
            flash('Amount must be positive', 'danger')
            return redirect(url_for('admin_panel'))
        
        user = db.session.get(User, user_id)
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin_panel'))
        
        account = db.session.query(Account).filter_by(user_id=user.id).first()
        if not account:
            flash('Account not found', 'danger')
            return redirect(url_for('admin_panel'))
        
        # Update balance
        account.balance += amount
        
        # Record transaction
        transaction = Transaction(
            amount=amount,
            type='deposit',
            description=description or f'Admin deposit: ${amount:.2f}',
            status='completed',
            user_id=user.id,
            account_id=account.id,
            admin_notes=admin_notes
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        flash(f'Added ${amount:.2f} to {user.username}\'s account', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding deposit: {str(e)}', 'danger')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/edit_transaction/<int:transaction_id>', methods=['POST'])
@admin_required
def edit_transaction(transaction_id):
    try:
        transaction = db.session.get(Transaction, transaction_id)
        if not transaction:
            flash('Transaction not found', 'danger')
            return redirect(url_for('admin_panel'))
            
        old_amount = transaction.amount
        new_amount = float(request.form.get('amount', 0))
        description = request.form.get('description', '').strip()
        admin_notes = request.form.get('admin_notes', '').strip()
        
        if new_amount <= 0:
            flash('Amount must be positive', 'danger')
            return redirect(url_for('admin_panel'))
        
        # Get account
        account = db.session.get(Account, transaction.account_id)
        if not account:
            flash('Account not found', 'danger')
            return redirect(url_for('admin_panel'))
        
        # Update balance difference
        amount_diff = new_amount - old_amount
        account.balance += amount_diff
        
        # Update transaction
        transaction.amount = new_amount
        if description:
            transaction.description = description
        if admin_notes:
            transaction.admin_notes = admin_notes
        
        db.session.commit()
        
        flash(f'Transaction #{transaction_id} updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating transaction: {str(e)}', 'danger')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_withdrawal/<int:withdrawal_id>', methods=['POST'])
@admin_required
def update_withdrawal(withdrawal_id):
    try:
        status = request.form.get('status')
        admin_notes = request.form.get('admin_notes', '').strip()
        
        withdrawal = db.session.get(Withdrawal, withdrawal_id)
        if not withdrawal:
            flash('Withdrawal not found', 'danger')
            return redirect(url_for('admin_panel'))
        
        if status in ['approved', 'rejected', 'completed']:
            old_status = withdrawal.status
            withdrawal.status = status
            withdrawal.processed_at = datetime.utcnow()
            withdrawal.processed_by = session['user_id']
            if admin_notes:
                withdrawal.admin_notes = admin_notes
            
            # Find related transaction
            transaction = db.session.query(Transaction).filter_by(
                user_id=withdrawal.user_id,
                account_id=withdrawal.account_id,
                type='withdraw',
                status='pending'
            ).order_by(Transaction.created_at.desc()).first()
            
            if status == 'approved':
                account = db.session.get(Account, withdrawal.account_id)
                if account.balance >= withdrawal.amount:
                    account.balance -= withdrawal.amount
                    if transaction:
                        transaction.status = 'completed'
                        if admin_notes:
                            transaction.admin_notes = f'Withdrawal approved. {admin_notes}'
                else:
                    flash('Insufficient funds in account', 'danger')
                    return redirect(url_for('admin_panel'))
            
            elif status == 'rejected':
                if transaction:
                    transaction.status = 'cancelled'
                    if admin_notes:
                        transaction.admin_notes = f'Withdrawal rejected. {admin_notes}'
            
            elif status == 'completed':
                if transaction:
                    transaction.status = 'completed'
                    if admin_notes:
                        transaction.admin_notes = f'Withdrawal completed. {admin_notes}'
            
            db.session.commit()
            flash(f'Withdrawal #{withdrawal_id} updated from {old_status} to {status}', 'success')
        else:
            flash('Invalid status', 'danger')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating withdrawal: {str(e)}', 'danger')
    
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Server starting on http://localhost:{port}")
    print("👉 Login as admin: admin / admin123")
    app.run(host='0.0.0.0', port=port, debug=True)