from flask import Flask, render_template, request, redirect, url_for, session, g, flash
import sqlite3
import requests
import traceback
import re
import os
from urllib.parse import urljoin
from api import search_cards, get_card_by_collector

app = Flask(__name__)
app.secret_key = os.environ.get('MTG_TRACKER_SECRET_KEY', 'mtg-tracker-local-profile-session')
DB_PATH = os.environ.get(
    'MTG_TRACKER_DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'collection.db'),
)
CARDKINGDOM_PRICE_URL = 'https://api.cardkingdom.com/api/v2/pricelist'

@app.errorhandler(500)
def internal_error(error):
    return f"Server Error: {traceback.format_exc()}", 500

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE
        )
    ''')
    conn.execute("INSERT OR IGNORE INTO profiles (name) VALUES ('Patrick')")
    patrick_id = conn.execute("SELECT id FROM profiles WHERE name = 'Patrick' COLLATE NOCASE").fetchone()['id']

    table_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection'").fetchone()
    if not table_exists:
        conn.execute('''
            CREATE TABLE collection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL REFERENCES profiles(id),
                scryfall_id TEXT,
                name TEXT,
                set_name TEXT,
                rarity TEXT,
                quantity INTEGER DEFAULT 1,
                image_url TEXT,
                treatment TEXT DEFAULT 'Non-Foil',
            cardkingdom_retail REAL,
            cardkingdom_buylist REAL,
            cardkingdom_qty_retail INTEGER,
            cardkingdom_qty_buying INTEGER,
            cardkingdom_url TEXT,
            cardkingdom_updated_at TEXT,
                UNIQUE(profile_id, scryfall_id, treatment)
            )
        ''')
    else:
        columns = {row['name'] for row in conn.execute("PRAGMA table_info('collection')").fetchall()}
        unique_indexes = conn.execute("PRAGMA index_list('collection')").fetchall()
        has_profile_unique = False
        for index in unique_indexes:
            if index['unique']:
                index_columns = tuple(row['name'] for row in conn.execute(
                    f"PRAGMA index_info('{index['name']}')"
                ).fetchall())
                if index_columns == ('profile_id', 'scryfall_id', 'treatment'):
                    has_profile_unique = True
                    break

        if 'profile_id' not in columns or not has_profile_unique:
            profile_expr = f'COALESCE(profile_id, {patrick_id})' if 'profile_id' in columns else str(patrick_id)
            field_exprs = {
                'id': 'id' if 'id' in columns else 'NULL',
                'profile_id': profile_expr,
                'scryfall_id': 'scryfall_id' if 'scryfall_id' in columns else 'NULL',
                'name': 'name' if 'name' in columns else "''",
                'set_name': 'set_name' if 'set_name' in columns else "''",
                'rarity': 'rarity' if 'rarity' in columns else "''",
                'quantity': 'quantity' if 'quantity' in columns else '1',
                'image_url': 'image_url' if 'image_url' in columns else 'NULL',
                'treatment': "COALESCE(treatment, 'Non-Foil')" if 'treatment' in columns else "'Non-Foil'",
                'cardkingdom_retail': 'cardkingdom_retail' if 'cardkingdom_retail' in columns else 'NULL',
                'cardkingdom_buylist': 'cardkingdom_buylist' if 'cardkingdom_buylist' in columns else 'NULL',
                'cardkingdom_qty_retail': 'cardkingdom_qty_retail' if 'cardkingdom_qty_retail' in columns else 'NULL',
                'cardkingdom_qty_buying': 'cardkingdom_qty_buying' if 'cardkingdom_qty_buying' in columns else 'NULL',
                'cardkingdom_url': 'cardkingdom_url' if 'cardkingdom_url' in columns else 'NULL',
                'cardkingdom_updated_at': 'cardkingdom_updated_at' if 'cardkingdom_updated_at' in columns else 'NULL',
            }
            conn.execute('''
                CREATE TABLE collection_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL REFERENCES profiles(id),
                    scryfall_id TEXT,
                    name TEXT,
                    set_name TEXT,
                    rarity TEXT,
                    quantity INTEGER DEFAULT 1,
                    image_url TEXT,
                    treatment TEXT DEFAULT 'Non-Foil',
                    cardkingdom_retail REAL,
                    cardkingdom_buylist REAL,
                    cardkingdom_qty_retail INTEGER,
                    cardkingdom_qty_buying INTEGER,
                    cardkingdom_url TEXT,
                    cardkingdom_updated_at TEXT,
                    UNIQUE(profile_id, scryfall_id, treatment)
                )
            ''')
            fields = ', '.join(field_exprs)
            expressions = ', '.join(field_exprs.values())
            conn.execute(f'INSERT INTO collection_new ({fields}) SELECT {expressions} FROM collection')
            conn.execute('DROP TABLE collection')
            conn.execute('ALTER TABLE collection_new RENAME TO collection')
        else:
            conn.execute('UPDATE collection SET profile_id = ? WHERE profile_id IS NULL', (patrick_id,))

    columns = {row['name'] for row in conn.execute("PRAGMA table_info('collection')").fetchall()}
    price_columns = {
        'cardkingdom_retail': 'REAL',
        'cardkingdom_buylist': 'REAL',
        'cardkingdom_qty_retail': 'INTEGER',
        'cardkingdom_qty_buying': 'INTEGER',
        'cardkingdom_url': 'TEXT',
        'cardkingdom_updated_at': 'TEXT',
    }
    for column, column_type in price_columns.items():
        if column not in columns:
            conn.execute(f'ALTER TABLE collection ADD COLUMN {column} {column_type}')

    conn.commit()
    conn.close()

# Initialize the schema for both `python app.py` and WSGI servers such as Gunicorn.
init_db()

def get_profile(profile_id):
    if not profile_id:
        return None
    conn = get_db_connection()
    profile = conn.execute('SELECT id, name FROM profiles WHERE id = ?', (profile_id,)).fetchone()
    conn.close()
    return profile

@app.before_request
def load_active_profile():
    if request.endpoint in {'profile_selection', 'select_profile', 'create_profile', 'static'}:
        g.active_profile = None
        return
    profile = get_profile(session.get('profile_id'))
    g.active_profile = profile
    if profile is None:
        session.pop('profile_id', None)
        return redirect(url_for('profile_selection'))

@app.context_processor
def inject_active_profile():
    return {'active_profile': getattr(g, 'active_profile', None)}

@app.route('/profiles')
def profile_selection():
    session.pop('profile_id', None)
    conn = get_db_connection()
    profiles = conn.execute('SELECT id, name FROM profiles ORDER BY name COLLATE NOCASE').fetchall()
    conn.close()
    return render_template('profiles.html', profiles=profiles)

@app.route('/profiles/select', methods=['POST'])
def select_profile():
    profile = get_profile(request.form.get('profile_id'))
    if profile is None:
        return 'Profile not found', 404
    session['profile_id'] = profile['id']
    return redirect(url_for('index'))

@app.route('/profiles/create', methods=['POST'])
def create_profile():
    name = request.form.get('name', '').strip()
    conn = get_db_connection()
    profiles = conn.execute('SELECT id, name FROM profiles ORDER BY name COLLATE NOCASE').fetchall()
    if not name or len(name) > 40:
        conn.close()
        return render_template('profiles.html', profiles=profiles, error='Enter a name with 1 to 40 characters.'), 400
    try:
        cursor = conn.execute('INSERT INTO profiles (name) VALUES (?)', (name,))
        profile_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template('profiles.html', profiles=profiles, error='That profile name is already in use.'), 400
    conn.close()
    session['profile_id'] = profile_id
    return redirect(url_for('index'))

@app.route('/')
def index():
    filters = {
        'q': request.args.get('q', '').strip(),
        'set': request.args.get('set', '').strip(),
        'rarity': request.args.get('rarity', '').strip(),
        'treatment': request.args.get('treatment', '').strip(),
    }
    sort = request.args.get('sort', 'name_asc')
    sort_options = {
        'name_asc': 'name COLLATE NOCASE ASC',
        'name_desc': 'name COLLATE NOCASE DESC',
        'set_asc': 'set_name COLLATE NOCASE ASC, name COLLATE NOCASE ASC',
        'rarity_asc': "CASE LOWER(rarity) WHEN 'common' THEN 1 WHEN 'uncommon' THEN 2 WHEN 'rare' THEN 3 WHEN 'mythic' THEN 4 ELSE 5 END ASC, name COLLATE NOCASE ASC",
        'quantity_asc': 'quantity ASC, name COLLATE NOCASE ASC',
        'quantity_desc': 'quantity DESC, name COLLATE NOCASE ASC',
        'price_asc': 'cardkingdom_retail IS NULL ASC, cardkingdom_retail ASC, name COLLATE NOCASE ASC',
        'price_desc': 'cardkingdom_retail IS NULL ASC, cardkingdom_retail DESC, name COLLATE NOCASE ASC',
    }
    if sort not in sort_options:
        sort = 'name_asc'
    filters_active = any(filters.values()) or sort != 'name_asc'

    conn = get_db_connection()
    conditions = ['profile_id = ?']
    params = [g.active_profile['id']]
    if filters['q']:
        conditions.append('name LIKE ?')
        params.append(f"%{filters['q']}%")
    if filters['set']:
        conditions.append('set_name = ?')
        params.append(filters['set'])
    if filters['rarity']:
        conditions.append('rarity = ?')
        params.append(filters['rarity'])
    if filters['treatment']:
        conditions.append('treatment = ?')
        params.append(filters['treatment'])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    collection = conn.execute(
        f'SELECT * FROM collection {where_clause} ORDER BY {sort_options[sort]}', params
    ).fetchall()
    total_count = conn.execute('SELECT COUNT(*) FROM collection WHERE profile_id = ?', (g.active_profile['id'],)).fetchone()[0]
    sets = [row[0] for row in conn.execute(
        "SELECT DISTINCT set_name FROM collection WHERE profile_id = ? AND set_name IS NOT NULL AND set_name != '' ORDER BY set_name COLLATE NOCASE",
        (g.active_profile['id'],)
    ).fetchall()]
    rarities = [row[0] for row in conn.execute(
        "SELECT DISTINCT rarity FROM collection WHERE profile_id = ? AND rarity IS NOT NULL AND rarity != '' ORDER BY rarity COLLATE NOCASE",
        (g.active_profile['id'],)
    ).fetchall()]
    treatments = [row[0] for row in conn.execute(
        "SELECT DISTINCT treatment FROM collection WHERE profile_id = ? AND treatment IS NOT NULL AND treatment != '' ORDER BY treatment COLLATE NOCASE",
        (g.active_profile['id'],)
    ).fetchall()]
    conn.close()
    
    updated_collection = []
    for card in collection:
        item = dict(card)
        if not item['image_url']:
            item['image_url'] = "https://cards.scryfall.io/unknown.jpg" 
        updated_collection.append(item)
        
    return render_template(
        'index.html',
        collection=updated_collection,
        filters=filters,
        sort=sort,
        sets=sets,
        rarities=rarities,
        treatments=treatments,
        total_count=total_count,
        filters_active=filters_active,
    )

@app.route('/refresh_prices', methods=['POST'])
def refresh_prices():
    try:
        response = requests.get(CARDKINGDOM_PRICE_URL, headers={
            'User-Agent': 'MTG-Tracker-App/1.0',
            'Accept': 'application/json',
        }, timeout=90)
        response.raise_for_status()
        feed = response.json()
        listings = feed.get('data', [])
        metadata = feed.get('meta', {})
        feed_time = metadata.get('created_at') or 'unknown time'
        by_scryfall = {}
        for listing in listings:
            card_id = listing.get('scryfall_id')
            if card_id:
                by_scryfall.setdefault(card_id, []).append(listing)

        conn = get_db_connection()
        rows = conn.execute('SELECT id, scryfall_id, treatment FROM collection').fetchall()
        updated = 0
        for row in rows:
            candidates = by_scryfall.get(row['scryfall_id'], [])
            treatment = (row['treatment'] or 'Non-Foil').casefold()
            is_foil = treatment in {'foil', 'etched', 'etched foil'}
            matches = [item for item in candidates if str(item.get('is_foil', 'false')).casefold() == str(is_foil).casefold()]
            if treatment == 'etched':
                etched = [item for item in candidates if 'etch' in str(item.get('variation', '')).casefold() or 'etch' in str(item.get('url', '')).casefold()]
                matches = etched or matches
            listing = matches[0] if matches else None
            if listing:
                condition = listing.get('condition_values') or {}
                retail = condition.get('nm_price') or listing.get('price_retail')
                buylist = listing.get('price_buy')
                url = urljoin(metadata.get('base_url', 'https://www.cardkingdom.com/'), listing.get('url', ''))
                conn.execute('''UPDATE collection SET cardkingdom_retail=?, cardkingdom_buylist=?,
                    cardkingdom_qty_retail=?, cardkingdom_qty_buying=?, cardkingdom_url=?, cardkingdom_updated_at=?
                    WHERE id=?''', (retail, buylist, listing.get('qty_retail'), listing.get('qty_buying'), url, feed_time, row['id']))
                updated += 1
            else:
                conn.execute('UPDATE collection SET cardkingdom_retail=NULL, cardkingdom_buylist=NULL, cardkingdom_qty_retail=NULL, cardkingdom_qty_buying=NULL, cardkingdom_url=NULL, cardkingdom_updated_at=? WHERE id=?', (feed_time, row['id']))
        conn.commit()
        conn.close()
        flash(f'Card Kingdom prices refreshed for {updated} of {len(rows)} collection entries (feed updated {feed_time}).', 'success')
    except Exception as error:
        app.logger.exception('Card Kingdom price refresh failed')
        flash(f'Could not refresh Card Kingdom prices: {error}', 'danger')
    return redirect(url_for('index'))

@app.route('/search')
def search():
    try:
        query = request.args.get('q')
        if not query:
            return render_template('search_v2.html', results=[], query="")
        
        results = search_cards(query)
        return render_template('search_v2.html', results=results, query=query)
    except Exception as e:
        return f"Internal Error: {str(e)}", 500

@app.route('/add_confirm/<scryfall_id>')
def add_confirm(scryfall_id):
    url = f"https://api.scryfall.com/cards/{scryfall_id}"
    headers = {"User-Agent": "MTG-Tracker-App/1.0"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return "Card not found", 404
    
    card = resp.json()
    
    # Normalize image URL
    img_url = None
    if 'image_uris' in card:
        img_url = card['image_uris'].get('normal')
    elif 'image_urls' in card:
        img_url = card['image_urls'].get('normal')
    elif 'card_faces' in card and len(card['card_faces']) > 0:
        face = card['card_faces'][0]
        img_url = face.get('image_uris', {}).get('normal') or face.get('image_urls', {}).get('normal')
    card['normalized_image_url'] = img_url
    
    return render_template('add_confirm.html', card=card)

@app.route('/add_card', methods=['POST'])
def add_card_post():
    scryfall_id = request.form.get('scryfall_id')
    treatment = request.form.get('treatment', 'Non-Foil')
    quantity = int(request.form.get('quantity', 1))
    
    url = f"https://api.scryfall.com/cards/{scryfall_id}"
    headers = {"User-Agent": "MTG-Tracker-App/1.0"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return "Card not found", 404
    
    card = resp.json()
    img_url = None
    if 'image_uris' in card:
        img_url = card['image_uris'].get('normal')
    elif 'image_urls' in card:
        img_url = card['image_urls'].get('normal')
    elif 'card_faces' in card and len(card['card_faces']) > 0:
        face = card['card_faces'][0]
        img_url = face.get('image_uris', {}).get('normal') or face.get('image_urls', {}).get('normal')
    
    conn = get_db_connection()
    try:
        # Check if the card with this treatment already exists
        profile_id = g.active_profile['id']
        existing = conn.execute(
            'SELECT quantity FROM collection WHERE profile_id = ? AND scryfall_id = ? AND treatment = ?',
            (profile_id, scryfall_id, treatment)
        ).fetchone()
        
        if existing:
            conn.execute(
                'UPDATE collection SET quantity = quantity + ? WHERE profile_id = ? AND scryfall_id = ? AND treatment = ?',
                (quantity, profile_id, scryfall_id, treatment)
            )
        else:
            conn.execute('''
                INSERT INTO collection (profile_id, scryfall_id, name, set_name, rarity, quantity, image_url, treatment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (profile_id, scryfall_id, card['name'], card['set_name'], card['rarity'], quantity, img_url, treatment))
        
        conn.commit()
    except Exception as e:
        return f"Error adding card: {e}", 500
    finally:
        conn.close()
    
    return redirect(url_for('index'))

@app.route('/delete/<scryfall_id>')
def delete_card(scryfall_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM collection WHERE profile_id = ? AND scryfall_id = ?', (g.active_profile['id'], scryfall_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/card/<scryfall_id>')
def card_detail(scryfall_id):
    url = f"https://api.scryfall.com/cards/{scryfall_id}"
    headers = {"User-Agent": "MTG-Tracker-App/1.0"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return "Card not found", 404
    
    card = resp.json()
    
    # Normalize main image
    img_url = None
    if 'image_uris' in card:
        img_url = card['image_uris'].get('normal')
    elif 'image_urls' in card:
        img_url = card['image_urls'].get('normal')
    card['normalized_image_url'] = img_url
    
    # Normalize face images
    if 'card_faces' in card:
        for face in card['card_faces']:
            face_img = None
            if 'image_uris' in face:
                face_img = face['image_uris'].get('normal')
            elif 'image_urls' in face:
                face_img = face['image_urls'].get('normal')
            face['normalized_image_url'] = face_img
            
    return render_template('card_detail.html', card=card)

@app.route('/import')
def import_page():
    return render_template('import.html')

@app.route('/import', methods=['POST'])
def import_cards():
    if 'file' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['file']
    if file.filename == '':
        return "No file selected", 400
    
    try:
        content = file.read().decode('utf-8')
        lines = content.splitlines()
        print(f"File content sample: {lines[:5]}")
        
        # ManaBox exports use "quantity name (SET) number [*F*]". Some older
        # exports include an additional numeric prefix followed by a pipe.
        pattern = re.compile(r'^(?:\d+\|)?(\d+)\s+(.*?)\s+\(([A-Z0-9]+)\)\s+([A-Za-z0-9-]+)(?:\s+\*F\*)?$')

        parsed_cards = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if not match:
                continue
            qty, name, set_code, col_num = match.groups()
            treatment = 'Foil' if '*F*' in line else 'Non-Foil'
            key = (set_code.lower(), col_num, treatment)
            if key in parsed_cards:
                parsed_cards[key]['quantity'] += int(qty)
            else:
                parsed_cards[key] = {
                    'quantity': int(qty),
                    'name': name,
                    'set_code': set_code,
                    'collector_number': col_num,
                    'treatment': treatment,
                }

        # Scryfall accepts up to 75 card identifiers per collection request.
        unique_identifiers = sorted({(item['set_code'].lower(), item['collector_number']) for item in parsed_cards.values()})
        cards_by_identifier = {}
        headers = {"User-Agent": "MTG-Tracker-App/1.0", "Content-Type": "application/json"}
        for start in range(0, len(unique_identifiers), 75):
            batch = unique_identifiers[start:start + 75]
            response = requests.post(
                "https://api.scryfall.com/cards/collection",
                json={"identifiers": [{"set": set_code, "collector_number": col_num} for set_code, col_num in batch]},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            for card in response.json().get('data', []):
                cards_by_identifier[(card['set'].lower(), str(card['collector_number']))] = card

        imported_count = 0
        conn = get_db_connection()

        for item in parsed_cards.values():
            qty = item['quantity']
            treatment = item['treatment']
            card = cards_by_identifier.get((item['set_code'].lower(), item['collector_number']))
            if not card:
                continue
                
            scryfall_id = card['id']
            
            # Normalize image URL
            img_url = None
            if 'image_uris' in card:
                img_url = card['image_uris'].get('normal')
            elif 'image_urls' in card:
                img_url = card['image_urls'].get('normal')
            elif 'card_faces' in card and len(card['card_faces']) > 0:
                face = card['card_faces'][0]
                img_url = face.get('image_uris', {}).get('normal') or face.get('image_urls', {}).get('normal')

            # Database update (similar to add_card_post)
            profile_id = g.active_profile['id']
            existing = conn.execute(
                'SELECT quantity FROM collection WHERE profile_id = ? AND scryfall_id = ? AND treatment = ?',
                (profile_id, scryfall_id, treatment)
            ).fetchone()
            if existing:
                conn.execute(
                    'UPDATE collection SET quantity = quantity + ? WHERE profile_id = ? AND scryfall_id = ? AND treatment = ?',
                    (qty, profile_id, scryfall_id, treatment)
                )
            else:
                conn.execute('''
                    INSERT INTO collection (profile_id, scryfall_id, name, set_name, rarity, quantity, image_url, treatment)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (profile_id, scryfall_id, card['name'], card['set_name'], card['rarity'], qty, img_url, treatment))
            
            imported_count += 1
            
        conn.commit()
        conn.close()
        
        return f"Successfully imported {imported_count} cards! <a href='/'>Return to Gallery</a>"
        
    except Exception as e:
        return f"Import Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=9006)
