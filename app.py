from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'budget_buddy_secure_key_2026'
app.config['SERVER_NAME'] = 'budgetbuddy:5000'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

CATEGORIES = ["Food", "Transport", "Bills", "Entertainment", "Other"]

def init_db():
    conn = sqlite3.connect('expenses.db')
    # Added budget column with a default of 5000.0
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     username TEXT UNIQUE, password TEXT, budget REAL DEFAULT 5000.0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS expenses 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     user_id INTEGER, category TEXT, amount REAL, date TEXT)''')
    conn.commit()
    conn.close()

class User(UserMixin):
    def __init__(self, id, username, budget):
        self.id = id
        self.username = username
        self.budget = budget

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('expenses.db')
    user = conn.execute('SELECT id, username, budget FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user[0], user[1], user[2])
    return None

# --- NEW ROUTE TO UPDATE BUDGET ---
@app.route('/set_budget', methods=['POST'])
@login_required
def set_budget():
    new_budget = float(request.form.get('budget', 5000))
    conn = sqlite3.connect('expenses.db')
    conn.execute('UPDATE users SET budget = ? WHERE id = ?', (new_budget, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        try:
            conn = sqlite3.connect('expenses.db')
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            return "Username already exists!"
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('expenses.db')
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1], user[3]))
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    conn = sqlite3.connect('expenses.db')
    
    # Fetch latest user budget
    user_row = conn.execute('SELECT budget FROM users WHERE id = ?', (current_user.id,)).fetchone()
    user_budget = user_row[0] if user_row else 5000.0

    if start_date and end_date:
        query = "SELECT * FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?"
        df = pd.read_sql_query(query, conn, params=(current_user.id, start_date, end_date))
    else:
        df = pd.read_sql_query("SELECT * FROM expenses WHERE user_id = ?", conn, params=(current_user.id,))
    
    total_spent = df['amount'].sum() if not df.empty else 0
    
    # CIRA Insights
    insight_msg = "Budget Buddy AI is ready."
    if not df.empty:
        df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
        this_week = df[df['date_dt'] > (datetime.now() - timedelta(days=7))]['amount'].sum()
        last_week = df[(df['date_dt'] > (datetime.now() - timedelta(days=14))) & 
                       (df['date_dt'] <= (datetime.now() - timedelta(days=7)))]['amount'].sum()
        if last_week > 0:
            diff = ((this_week - last_week) / last_week) * 100
            insight_msg = f"CIRA Note: Spending is {abs(diff):.1f}% {'up' if diff > 0 else 'down'} from last week."

    # Dynamic Gauge using user_budget
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = total_spent,
        title = {'text': f"Limit: ₹{user_budget}", 'font': {'color': "#8b5e3c", 'size': 14}},
        gauge = {'axis': {'range': [None, user_budget], 'tickcolor': "#8b5e3c"},
                 'bar': {'color': "#8b5e3c"},
                 'steps': [{'range': [0, user_budget*0.7], 'color': 'rgba(139, 94, 60, 0.1)'},
                           {'range': [user_budget*0.7, user_budget], 'color': 'rgba(239, 68, 68, 0.1)'}]}))
    fig_gauge.update_layout(margin=dict(l=30, r=30, t=50, b=20), height=220, paper_bgcolor='rgba(0,0,0,0)', font={'color': "#8b5e3c"})
    graph_gauge = pio.to_html(fig_gauge, full_html=False, config={'displayModeBar': False})

    graph_pie = ""
    graph_trend = ""
    if not df.empty:
        fig_pie = px.pie(df, values='amount', names='category', hole=0.4, template="plotly_white",
                         color_discrete_sequence=['#8b5e3c', '#bc8a5f', '#deab90', '#f5ebe0'])
        fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300, paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        graph_pie = pio.to_html(fig_pie, full_html=False)

        trend_df = df.groupby('date')['amount'].sum().reset_index()
        trend_df['date'] = pd.to_datetime(trend_df['date']).dt.date
        trend_df = trend_df.sort_values('date')
        fig_trend = px.area(trend_df, x='date', y='amount', template="plotly_white")
        fig_trend.update_traces(line_color='#8b5e3c', fillcolor='rgba(139, 94, 60, 0.1)')
        fig_trend.update_layout(margin=dict(l=40, r=20, t=20, b=40), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        graph_trend = pio.to_html(fig_trend, full_html=False)

    conn.close()
    return render_template('index.html', expenses=df.to_dict('records'), total=total_spent, 
                           graph_pie=graph_pie, graph_trend=graph_trend, graph_gauge=graph_gauge, 
                           insight_msg=insight_msg, categories=CATEGORIES, user_budget=user_budget)

@app.route('/export')
@login_required
def export_data():
    conn = sqlite3.connect('expenses.db')
    df = pd.read_sql_query("SELECT category, amount, date FROM expenses WHERE user_id = ?", conn, params=(current_user.id,))
    conn.close()
    file_path = "Budget_Buddy_Report.csv"
    df.to_csv(file_path, index=False)
    return send_file(file_path, as_attachment=True)

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    category, amount, date = request.form['category'], float(request.form['amount']), request.form['date']
    conn = sqlite3.connect('expenses.db')
    conn.execute('INSERT INTO expenses (user_id, category, amount, date) VALUES (?, ?, ?, ?)', (current_user.id, category, amount, date))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)