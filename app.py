import os
import datetime
import functools
import psycopg2
import psycopg2.extras
from flask import Flask, request, session, redirect, url_for, render_template_string, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# 从 Zeabur 环境变量读取配置
DB_URL = os.environ.get('DB_URL', 'postgresql://postgres.psqvlhyulnhcmlonpnkz:你的新密码@aws-0-us-west-1.pooler.supabase.com:6543/postgres')
CREEM_API_KEY = os.environ.get('CREEM_API_KEY', '')
CREEM_WEBHOOK_SECRET = os.environ.get('CREEM_WEBHOOK_SECRET', '')

# ⚠️ 明天去 Creem 后台复制真实支付链接，替换下面这行！
CREEM_CHECKOUT_URL = os.environ.get('CREEM_CHECKOUT_URL', 'https://creem.io/pay/你的产品ID')

BASE_TEMPLATE = '''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - Client Tracker</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; background: #f5f7fa; color: #333; }
nav { background: #2c3e50; color: white; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }
nav a { color: white; text-decoration: none; margin-right: 15px; }
main { max-width: 1000px; margin: 20px auto; padding: 0 20px; }
.card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f8f9fa; }
.btn { display: inline-block; padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 4px; text-decoration: none; cursor: pointer; font-size: 14px; }
.btn-danger { background: #e74c3c; }
.btn-success { background: #27ae60; }
.btn-warning { background: #f39c12; }
input, textarea { width: 100%; padding: 8px; margin: 5px 0 15px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
label { font-weight: bold; }
.flashes { list-style: none; padding: 0; }
.flashes li { background: #f39c12; color: white; padding: 10px; border-radius: 4px; margin-bottom: 10px; }
.status-Expired { color: #e74c3c; font-weight: bold; }
.status-7days { color: #e67e22; font-weight: bold; }
.status-30days { color: #3498db; }
.status-Normal { color: #27ae60; }
.status-NoSessions { color: #e74c3c; font-weight: bold; }
</style>
</head>
<body>
<nav>
  <div><a href="/">Client Tracker</a></div>
  <div>
    {% if session.get('user_id') %}
      <a href="/dashboard">Dashboard</a>
      <a href="/logout">Logout</a>
    {% else %}
      <a href="/login">Login</a>
      <a href="/register">Register</a>
    {% endif %}
  </div>
</nav>
<main>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <ul class="flashes">
      {% for message in messages %}
        <li>{{ message }}</li>
      {% endfor %}
      </ul>
    {% endif %}
  {% endwith %}
  {% block content %}{% endblock %}
  
  <footer style="text-align: center; padding: 20px; color: #777; font-size: 12px; border-top: 1px solid #eee; margin-top: 40px;">
      <p>Support: 897548225@qq.com</p>
      <p><a href="/privacy" style="color: #3498db;">Privacy Policy</a> | <a href="/terms" style="color: #3498db;">Terms of Service</a></p>
      <p>&copy; 2026 Client Tracker. All rights reserved.</p>
  </footer>
</main>
</body>
</html>
'''
app.jinja_loader = DictLoader({'base.html': BASE_TEMPLATE})

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = psycopg2.connect(DB_URL)
        db.cursor_factory = psycopg2.extras.DictCursor
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def get_current_user():
    if 'user_id' not in session: return None
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    return cur.fetchone()

def plan_active(user):
    if not user: return False
    if user['is_admin']: return True
    if not user['plan_expires_at']: return False
    return user['plan_expires_at'] >= datetime.date.today().isoformat()

def days_until(expire_date):
    today = datetime.date.today()
    d = datetime.datetime.strptime(expire_date, '%Y-%m-%d').date()
    return (d - today).days

@app.context_processor
def inject_user():
    return dict(user=get_current_user(), plan_active=plan_active, creem_checkout_url=CREEM_CHECKOUT_URL)

@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return render_template_string('''{% extends "base.html" %}{% block content %}
    <div class="card">
        <h1>Client Tracker</h1>
        <p>Simple tool to track client renewals and session credits. Start your 14-day free trial now.</p>
        <p><strong>Subscription: $19.90/month</strong> (Billed monthly. Cancel anytime.)</p>
        <p><a class="btn" href="/register">Start 14-Day Free Trial</a> <a class="btn" href="/login">Login</a></p>
    </div>
    <div class="card">
        <h2>What is Client Tracker?</h2>
        <p>Client Tracker is a web-based SaaS tool designed for small business owners, such as pet groomers, salons, and gyms. It helps you manage your clients, track session credits (e.g., 10 grooming sessions), and never miss a renewal date.</p>
        <h3>Why choose us?</h3>
        <ul>
            <li>Easy to use, no complex setup.</li>
            <li>Track client sessions and remaining credits.</li>
            <li>Generate reminder texts to reduce client churn.</li>
            <li>Affordable flat monthly price of $19.90.</li>
        </ul>
    </div>
    {% endblock %}''')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if username and password:
            db = get_db()
            cur = db.cursor()
            try:
                trial_end = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()
                cur.execute('INSERT INTO users (username, password_hash, plan_expires_at) VALUES (%s, %s, %s)', (username, generate_password_hash(password), trial_end))
                db.commit()
                flash('Registered successfully. 14-day trial started.')
                return redirect(url_for('login'))
            except psycopg2.IntegrityError:
                db.rollback()
                flash('Username already exists')
    return render_template_string('''{% extends "base.html" %}{% block content %}<div class="card"><h2>Register</h2><form method="post"><label>Username</label><input name="username" required><label>Password</label><input name="password" type="password" required><button class="btn" type="submit">Register</button></form></div>{% endblock %}''')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template_string('''{% extends "base.html" %}{% block content %}<div class="card"><h2>Login</h2><form method="post"><label>Username</label><input name="username" required><label>Password</label><input name="password" type="password" required><button class="btn" type="submit">Login</button></form></div>{% endblock %}''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM customers WHERE user_id = %s ORDER BY expire_date ASC', (user['id'],))
    customers = cur.fetchall()
    items = []
    for c in customers:
        days = days_until(c['expire_date'])
        remaining = c['total_count'] - c['used_count']
        if remaining <= 0:
            color = 'NoSessions'
            status = 'No sessions left'
        elif days < 0:
            color = 'Expired'
            status = 'Expired'
        elif days <= 7:
            color = '7days'
            status = f'{days} days left'
        elif days <= 30:
            color = '30days'
            status = f'{days} days left'
        else:
            color = 'Normal'
            status = f'{days} days left'
        items.append({'c': c, 'status': status, 'color': color, 'remaining': remaining})
    return render_template_string('''
    {% extends "base.html" %}
    {% block content %}
    <div class="card">
        <h2>Dashboard</h2>
        <p>Status: {% if plan_active(user) %}Active{% else %}Expired{% endif %}</p>
        {% if plan_active(user) %}<a class="btn" href="/customer/add">Add Client</a>{% endif %}
        {% if not user['is_admin'] %}
        <a class="btn btn-warning" href="{{ creem_checkout_url }}" target="_blank">Upgrade to Pro ($19.90/mo)</a>
        {% endif %}
    </div>
    <div class="card">
        <h3>Client List</h3>
        {% if items %}
        <table>
            <tr><th>Name</th><th>Sessions Left</th><th>Expiry Date</th><th>Status</th><th>Actions</th></tr>
            {% for item in items %}
            <tr>
                <td>{{ item.c['name'] }}</td>
                <td>{{ item.remaining }} left</td>
                <td>{{ item.c['expire_date'] }}</td>
                <td class="status-{{ item.color }}">{{ item.status }}</td>
                <td>
                    <a class="btn btn-success" href="/customer/{{ item.c['id'] }}/use">Use</a>
                    <a class="btn" href="/customer/{{ item.c['id'] }}/remind">Remind</a>
                    <form method="post" action="/customer/{{ item.c['id'] }}/delete" style="display:inline">
                        <button class="btn btn-danger" type="submit" onclick="return confirm('Delete?')">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p>No clients yet. Click "Add Client" to start.</p>
        {% endif %}
    </div>
    {% endblock %}
    ''', items=items)

@app.route('/customer/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    user = get_current_user()
    if not plan_active(user):
        flash('Subscription expired. Please renew.')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone = request.form.get('phone', '').strip()
        expire_date = request.form['expire_date']
        total_count = int(request.form.get('total_count', 10))
        if name and expire_date:
            db = get_db()
            cur = db.cursor()
            cur.execute('INSERT INTO customers (user_id, name, phone, expire_date, total_count, used_count) VALUES (%s, %s, %s, %s, %s, 0)', (user['id'], name, phone, expire_date, total_count))
            db.commit()
            flash('Client added')
            return redirect(url_for('dashboard'))
    return render_template_string('''{% extends "base.html" %}{% block content %}<div class="card"><h2>Add Client</h2><form method="post"><label>Name *</label><input name="name" required><label>Phone</label><input name="phone"><label>Expiry Date *</label><input name="expire_date" type="date" required><label>Total Sessions *</label><input name="total_count" type="number" value="10" required><button class="btn" type="submit">Save</button><a class="btn" href="/dashboard">Back</a></form></div>{% endblock %}''')

@app.route('/customer/<int:id>/use', methods=['GET'])
@login_required
def use_customer(id):
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute('UPDATE customers SET used_count = used_count + 1 WHERE id = %s AND user_id = %s', (id, user['id']))
    db.commit()
    flash('Session deducted')
    return redirect(url_for('dashboard'))

@app.route('/customer/<int:id>/delete', methods=['POST'])
@login_required
def delete_customer(id):
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM customers WHERE id = %s AND user_id = %s', (id, user['id']))
    db.commit()
    flash('Client deleted')
    return redirect(url_for('dashboard'))

@app.route('/customer/<int:id>/remind')
@login_required
def remind(id):
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM customers WHERE id = %s AND user_id = %s', (id, user['id']))
    c = cur.fetchone()
    if not c: return redirect(url_for('dashboard'))
    remaining = c['total_count'] - c['used_count']
    text = f"Hi {c['name']}, your membership/service will expire on {c['expire_date']}. You have {remaining} sessions left. Please renew to avoid interruption."
    return render_template_string('''{% extends "base.html" %}{% block content %}<div class="card"><h2>Reminder Message</h2><textarea rows="6" onclick="this.select()">{{ text }}</textarea><p><a class="btn" href="/dashboard">Back</a></p></div>{% endblock %}''', text=text)

@app.route('/privacy')
def privacy():
    return render_template_string('''{% extends "base.html" %}{% block content %}<div class="card"><h2>Privacy Policy</h2><p>We collect your email address and client data solely to provide the service. We do not sell or share your data with third parties. All data is stored securely. If you have questions, contact us at 897548225@qq.com.</p></div>{% endblock %}''')

@app.route('/terms')
def terms():
    return render_template_string('''{% extends "base.html" %}{% block content %}<div class="card"><h2>Terms of Service</h2><p>This service is provided "as-is" for $19.90/month. You can cancel anytime. We are not liable for any data loss or business interruption. By using this service, you agree to these terms.</p></div>{% endblock %}''')

# 新增：接收 Creem 付款成功通知的 Webhook 路由
@app.route('/creem-webhook', methods=['POST'])
def creem_webhook():
    payload = request.get_data(as_text=True)
    # 为了安全，可以在这里使用 CREEM_WEBHOOK_SECRET 验证签名
    try:
        data = request.get_json()
        event_type = data.get('event_type')
        
        # 监听付款成功和订阅激活事件
        if event_type in ['checkout.completed', 'subscription.paid', 'subscription.active']:
            customer_email = data.get('data', {}).get('customer', {}).get('email', '')
            
            if customer_email:
                db = get_db()
                cur = db.cursor()
                # 查找对应的用户，并增加30天有效期
                cur.execute('SELECT id, plan_expires_at FROM users WHERE username = %s', (customer_email,))
                user = cur.fetchone()
                
                if user:
                    current_expire = user['plan_expires_at'] or datetime.date.today().isoformat()
                    try:
                        new_expire = (datetime.datetime.strptime(current_expire, '%Y-%m-%d').date() + datetime.timedelta(days=30)).isoformat()
                    except:
                        new_expire = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
                        
                    cur.execute('UPDATE users SET plan_expires_at = %s WHERE id = %s', (new_expire, user['id']))
                    db.commit()
    except Exception as e:
        print(f"Webhook Error: {e}")
        return 'Error', 400
        
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))