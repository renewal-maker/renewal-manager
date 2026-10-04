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

# 连接 Supabase 云端数据库
DB_URL = "postgresql://postgres.psqvlhyulnhcmlonpnkz:xf48TnqNi4gAWz0i@aws-0-us-west-1.pooler.supabase.com:6543/postgres"

BASE_TEMPLATE = '''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>{{ title }} - 续费提醒管家</title></head>
<body>
<nav><a href="/">续费提醒管家</a> | <a href="/dashboard">仪表盘</a> | <a href="/logout">退出</a></nav>
<main>{% with messages = get_flashed_messages() %}{% if messages %}<ul>{% for message in messages %}<li>{{ message }}</li>{% endfor %}</ul>{% endif %}{% endwith %}{% block content %}{% endblock %}</main>
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
    if 'user_id' not in session:
        return None
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
    return dict(user=get_current_user(), plan_active=plan_active)

@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return render_template_string('''{% extends "base.html" %}{% block content %}<div><h1>续费提醒管家</h1><p><a href="/register">注册</a> <a href="/login">登录</a></p></div>{% endblock %}''')

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
                flash('注册成功，已赠送 14 天试用')
                return redirect(url_for('login'))
            except psycopg2.IntegrityError:
                db.rollback()
                flash('用户名已存在')
    return render_template_string('''{% extends "base.html" %}{% block content %}<form method="post"><input name="username" placeholder="用户名" required><input name="password" type="password" placeholder="密码" required><button type="submit">注册</button></form>{% endblock %}''')

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
        flash('用户名或密码错误')
    return render_template_string('''{% extends "base.html" %}{% block content %}<form method="post"><input name="username" placeholder="用户名" required><input name="password" type="password" placeholder="密码" required><button type="submit">登录</button></form>{% endblock %}''')

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
        color = '已过期' if days < 0 else ('7天内' if days <= 7 else ('30天内' if days <= 30 else '正常'))
        items.append({'c': c, 'status': f'{days}天后到期' if days >= 0 else '已过期', 'color': color})
    return render_template_string('''{% extends "base.html" %}{% block content %}<p>状态：{% if plan_active(user) %}有效{% else %}已过期{% endif %}</p>{% if plan_active(user) %}<a href="/customer/add">添加客户</a>{% endif %}<table>{% for item in items %}<tr><td>{{ item.c['name'] }}</td><td>{{ item.c['expire_date'] }}</td><td>{{ item.status }}</td></tr>{% endfor %}</table>{% endblock %}''', items=items)

@app.route('/customer/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    user = get_current_user()
    if not plan_active(user):
        flash('订阅已过期')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form['name'].strip()
        expire_date = request.form['expire_date']
        if name and expire_date:
            db = get_db()
            cur = db.cursor()
            cur.execute('INSERT INTO customers (user_id, name, expire_date) VALUES (%s, %s, %s)', (user['id'], name, expire_date))
            db.commit()
            flash('客户已添加')
            return redirect(url_for('dashboard'))
    return render_template_string('''{% extends "base.html" %}{% block content %}<form method="post"><input name="name" placeholder="姓名" required><input name="expire_date" type="date" required><button type="submit">保存</button></form>{% endblock %}''')

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    user = get_current_user()
    if not user['is_admin']: return redirect(url_for('dashboard'))
    db = get_db()
    cur = db.cursor()
    if request.method == 'POST':
        cur.execute('UPDATE users SET plan_expires_at = %s WHERE id = %s', (request.form['plan_expires_at'], request.form['user_id']))
        db.commit()
        return redirect(url_for('admin'))
    cur.execute('SELECT * FROM users ORDER BY id')
    users = cur.fetchall()
    return render_template_string('''{% extends "base.html" %}{% block content %}<h2>管理后台</h2><table>{% for u in users %}<tr><td>{{ u['id'] }}</td><td>{{ u['username'] }}</td><td>{{ u['plan_expires_at'] or '未开通' }}</td><td><form method="post"><input type="hidden" name="user_id" value="{{ u['id'] }}"><input name="plan_expires_at" type="date"><button type="submit">设置</button></form></td></tr>{% endfor %}</table>{% endblock %}''', users=users)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))