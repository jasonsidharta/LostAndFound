import sqlite3
from flask import Flask, render_template, request, session, redirect, url_for, make_response

app = Flask(__name__)
app.secret_key = 'lost-and-found-secret-key'
DATABASE = 'lostandfound.db'


def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    conn.commit()
    conn.close()


# ── Auth routes ──

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('browse'))
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('signup.html', error='Username and password are required.')

    if len(password) < 4:
        return render_template('signup.html', error='Password must be at least 4 characters.')

    conn = sqlite3.connect(DATABASE)
    existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        conn.close()
        return render_template('signup.html', error='Username already taken.')

    conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
    conn.commit()
    conn.close()

    return redirect(url_for('login', msg='Account created. Please log in.'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        last_user = request.cookies.get('last_user', '')
        return render_template('login.html', msg=request.args.get('msg'), last_user=last_user)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('login.html', error='Username and password are required.')

    conn = sqlite3.connect(DATABASE)
    user = conn.execute('SELECT id, username, password, role FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if not user or user[2] != password:
        return render_template('login.html', error='Invalid username or password.')

    session['user_id'] = user[0]
    session['username'] = user[1]
    session['role'] = user[3]

    return redirect(url_for('browse'))


@app.route('/logout')
def logout():
    username = session.get('username', '')
    session.clear()
    response = make_response(redirect(url_for('login')))
    response.set_cookie('last_user', username, max_age=30*24*60*60)
    return response


# ── Browse / Search ──

@app.route('/browse')
def browse():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Read filters from query string (request.args)
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    item_type = request.args.get('item_type', '')
    status = request.args.get('status', '')

    conn = sqlite3.connect(DATABASE)

    # Build query dynamically
    query = '''
        SELECT i.id, i.title, i.item_type, i.category, i.location, i.status, i.created_at, u.username
        FROM items i
        JOIN users u ON i.user_id = u.id
        WHERE 1=1
    '''
    params = []

    if q:
        query += ' AND (i.title LIKE ? OR i.description LIKE ? OR i.location LIKE ?)'
        params.extend(['%' + q + '%', '%' + q + '%', '%' + q + '%'])
    if category:
        query += ' AND i.category = ?'
        params.append(category)
    if item_type:
        query += ' AND i.item_type = ?'
        params.append(item_type)
    if status:
        query += ' AND i.status = ?'
        params.append(status)

    query += ' ORDER BY i.created_at DESC'

    rows = conn.execute(query, params).fetchall()

    items = []
    for r in rows:
        items.append({
            'id': r[0], 'title': r[1], 'item_type': r[2], 'category': r[3],
            'location': r[4], 'status': r[5], 'created_at': r[6], 'username': r[7]
        })

    # Get counts for summary
    total_lost = conn.execute("SELECT COUNT(*) FROM items WHERE item_type = 'lost'").fetchone()[0]
    total_found = conn.execute("SELECT COUNT(*) FROM items WHERE item_type = 'found'").fetchone()[0]
    total_resolved = conn.execute("SELECT COUNT(*) FROM items WHERE status = 'resolved'").fetchone()[0]

    conn.close()

    return render_template('browse.html', items=items, q=q, category=category,
                           item_type=item_type, status=status,
                           total_lost=total_lost, total_found=total_found,
                           total_resolved=total_resolved)


# ── Submit Item ──

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_template('submit.html')

    title = request.form.get('title', '').strip()
    item_type = request.form.get('item_type', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    location = request.form.get('location', '').strip()

    if not title or not item_type or not category or not description or not location:
        return render_template('submit.html', error='All fields are required.')

    conn = sqlite3.connect(DATABASE)
    conn.execute(
        'INSERT INTO items (user_id, item_type, title, category, description, location) VALUES (?, ?, ?, ?, ?, ?)',
        (session['user_id'], item_type, title, category, description, location)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('browse'))


# ── Item Detail ──

@app.route('/item/<int:item_id>')
def item_detail(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)

    # Get item with author info
    item_row = conn.execute('''
        SELECT i.id, i.title, i.item_type, i.category, i.description, i.location,
               i.status, i.created_at, i.user_id, u.username
        FROM items i JOIN users u ON i.user_id = u.id
        WHERE i.id = ?
    ''', (item_id,)).fetchone()

    if not item_row:
        conn.close()
        return redirect(url_for('browse'))

    item = {
        'id': item_row[0], 'title': item_row[1], 'item_type': item_row[2],
        'category': item_row[3], 'description': item_row[4], 'location': item_row[5],
        'status': item_row[6], 'created_at': item_row[7], 'user_id': item_row[8],
        'username': item_row[9]
    }

    # Get claims for this item
    claim_rows = conn.execute('''
        SELECT c.id, c.message, c.status, c.created_at, u.username, c.user_id
        FROM claims c JOIN users u ON c.user_id = u.id
        WHERE c.item_id = ?
        ORDER BY c.created_at DESC
    ''', (item_id,)).fetchall()

    claims = []
    for c in claim_rows:
        claims.append({
            'id': c[0], 'message': c[1], 'status': c[2],
            'created_at': c[3], 'username': c[4], 'user_id': c[5]
        })

    # Get comments for this item
    comment_rows = conn.execute('''
        SELECT co.content, co.created_at, u.username
        FROM comments co JOIN users u ON co.user_id = u.id
        WHERE co.item_id = ?
        ORDER BY co.created_at
    ''', (item_id,)).fetchall()

    comments = []
    for co in comment_rows:
        comments.append({
            'content': co[0], 'created_at': co[1], 'username': co[2]
        })

    conn.close()

    is_owner = (item['user_id'] == session.get('user_id'))
    is_admin = (session.get('role') == 'admin')

    return render_template('item.html', item=item, claims=claims, comments=comments,
                           is_owner=is_owner, is_admin=is_admin)


# ── Claim an Item ──

@app.route('/item/<int:item_id>/claim', methods=['POST'])
def claim_item(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    message = request.form.get('message', '').strip()
    if not message:
        return redirect(url_for('item_detail', item_id=item_id))

    conn = sqlite3.connect(DATABASE)

    # Check user hasn't already claimed this item
    existing = conn.execute(
        'SELECT id FROM claims WHERE item_id = ? AND user_id = ?',
        (item_id, session['user_id'])
    ).fetchone()

    if not existing:
        conn.execute(
            'INSERT INTO claims (item_id, user_id, message) VALUES (?, ?, ?)',
            (item_id, session['user_id'], message)
        )
        # Update item status to claimed
        conn.execute("UPDATE items SET status = 'claimed' WHERE id = ? AND status = 'open'", (item_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('item_detail', item_id=item_id))


# ── Comment on Item ──

@app.route('/item/<int:item_id>/comment', methods=['POST'])
def add_comment(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    content = request.form.get('content', '').strip()
    if not content:
        return redirect(url_for('item_detail', item_id=item_id))

    conn = sqlite3.connect(DATABASE)
    conn.execute(
        'INSERT INTO comments (item_id, user_id, content) VALUES (?, ?, ?)',
        (item_id, session['user_id'], content)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('item_detail', item_id=item_id))


# ── Approve / Reject Claim ──

@app.route('/claim/<int:claim_id>/<action>', methods=['POST'])
def handle_claim(claim_id, action):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if action not in ('approve', 'reject'):
        return redirect(url_for('browse'))

    conn = sqlite3.connect(DATABASE)

    # Get the claim and its item
    claim = conn.execute('''
        SELECT c.id, c.item_id, i.user_id FROM claims c
        JOIN items i ON c.item_id = i.id
        WHERE c.id = ?
    ''', (claim_id,)).fetchone()

    if not claim:
        conn.close()
        return redirect(url_for('browse'))

    item_owner_id = claim[2]
    item_id = claim[1]

    # Only the item owner or admin can approve/reject
    if session['user_id'] != item_owner_id and session.get('role') != 'admin':
        conn.close()
        return redirect(url_for('item_detail', item_id=item_id))

    if action == 'approve':
        conn.execute("UPDATE claims SET status = 'approved' WHERE id = ?", (claim_id,))
        conn.execute("UPDATE items SET status = 'resolved' WHERE id = ?", (item_id,))
    else:
        conn.execute("UPDATE claims SET status = 'rejected' WHERE id = ?", (claim_id,))
        # If no more pending claims, set item back to open
        pending = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE item_id = ? AND status = 'pending'",
            (item_id,)
        ).fetchone()[0]
        if pending <= 1:
            conn.execute("UPDATE items SET status = 'open' WHERE id = ?", (item_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('item_detail', item_id=item_id))


# ── Resolve Item ──

@app.route('/item/<int:item_id>/resolve', methods=['POST'])
def resolve_item(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)
    item = conn.execute('SELECT user_id FROM items WHERE id = ?', (item_id,)).fetchone()

    if item and (item[0] == session['user_id'] or session.get('role') == 'admin'):
        conn.execute("UPDATE items SET status = 'resolved' WHERE id = ?", (item_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('item_detail', item_id=item_id))


# ── Profile ──

@app.route('/profile/<username>')
def profile(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)

    profile_user = conn.execute(
        'SELECT id, username, role, created_at FROM users WHERE username = ?', (username,)
    ).fetchone()
    if not profile_user:
        conn.close()
        return redirect(url_for('browse'))

    user_id = profile_user[0]

    # Stats
    items_posted = conn.execute('SELECT COUNT(*) FROM items WHERE user_id = ?', (user_id,)).fetchone()[0]
    claims_made = conn.execute('SELECT COUNT(*) FROM claims WHERE user_id = ?', (user_id,)).fetchone()[0]
    comments_made = conn.execute('SELECT COUNT(*) FROM comments WHERE user_id = ?', (user_id,)).fetchone()[0]
    items_resolved = conn.execute(
        "SELECT COUNT(*) FROM items WHERE user_id = ? AND status = 'resolved'", (user_id,)
    ).fetchone()[0]

    stats = {
        'items_posted': items_posted,
        'claims_made': claims_made,
        'comments_made': comments_made,
        'items_resolved': items_resolved
    }

    # Badges
    badges = []
    if items_posted >= 1:
        badges.append('Reporter')
    if items_posted >= 5:
        badges.append('Active Reporter')
    if claims_made >= 1:
        badges.append('Claimant')
    if items_resolved >= 1:
        badges.append('Resolver')
    if items_resolved >= 5:
        badges.append('Hero')
    if comments_made >= 5:
        badges.append('Helpful')
    if profile_user[2] == 'admin':
        badges.append('Administrator')

    conn.close()

    profile_data = {
        'username': profile_user[1],
        'role': profile_user[2],
        'created_at': profile_user[3]
    }

    return render_template('profile.html', profile_user=profile_data, stats=stats,
                           badges=badges)


# ── Admin ──

@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'admin':
        return redirect(url_for('browse'))

    conn = sqlite3.connect(DATABASE)

    users = conn.execute('''
        SELECT u.username, u.role, u.created_at,
            COUNT(DISTINCT i.id) AS item_count,
            COUNT(DISTINCT c.id) AS claim_count,
            COUNT(DISTINCT co.id) AS comment_count
        FROM users u
        LEFT JOIN items i ON u.id = i.user_id
        LEFT JOIN claims c ON u.id = c.user_id
        LEFT JOIN comments co ON u.id = co.user_id
        GROUP BY u.id
        ORDER BY u.created_at
    ''').fetchall()

    user_list = []
    for u in users:
        user_list.append({
            'username': u[0], 'role': u[1], 'created_at': u[2],
            'item_count': u[3], 'claim_count': u[4], 'comment_count': u[5]
        })

    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_items = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    total_claims = conn.execute('SELECT COUNT(*) FROM claims').fetchone()[0]
    total_resolved = conn.execute("SELECT COUNT(*) FROM items WHERE status = 'resolved'").fetchone()[0]

    # Category breakdown
    categories = conn.execute('''
        SELECT category, COUNT(*) AS count FROM items GROUP BY category ORDER BY count DESC
    ''').fetchall()
    cat_list = []
    for c in categories:
        cat_list.append({'category': c[0], 'count': c[1]})

    conn.close()

    totals = {
        'total_users': total_users, 'total_items': total_items,
        'total_claims': total_claims, 'total_resolved': total_resolved
    }

    return render_template('admin.html', users=user_list, totals=totals, categories=cat_list)


# ── About ──

@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
