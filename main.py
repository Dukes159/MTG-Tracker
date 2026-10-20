import sqlite3
from api import get_card_details, search_cards

DB_PATH = "collection.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scryfall_id TEXT UNIQUE,
            name TEXT,
            set_name TEXT,
            rarity TEXT,
            quantity INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def add_card_by_details(details):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO collection (scryfall_id, name, set_name, rarity, quantity)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(scryfall_id) DO UPDATE SET quantity = quantity + 1
        ''', (details['id'], details['name'], details['set_name'], details['rarity']))
        conn.commit()
        print(f"Added {details['name']} from {details['set_name']} to collection.")
    except Exception as e:
        print(f"Error adding card: {e}")
    finally:
        conn.close()

def handle_add_card():
    query = input("Enter card name (fuzzy search): ")
    results = search_cards(query)
    
    if not results:
        print(f"No cards found matching: {query}")
        return
    
    if len(results) == 1:
        add_card_by_details(results[0])
        return

    print("\nMultiple cards found. Please choose one:")
    for i, card in enumerate(results[:10], 1):
        print(f"{i}. {card['name']} ({card['set_name']}) - {card['rarity']}")
    
    if len(results) > 10:
        print(f"... and {len(results) - 10} more.")

    try:
        choice = int(input("\nChoice (number) or 0 to cancel: "))
        if 1 <= choice <= len(results) and choice <= 10:
            add_card_by_details(results[choice - 1])
        elif choice == 0:
            print("Canceled.")
        else:
            print("Invalid choice.")
    except ValueError:
        print("Please enter a valid number.")

def list_collection():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, set_name, rarity, quantity FROM collection")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("Collection is empty.")
        return

    print(f"{'Name':<40} | {'Set':<30} | {'Rarity':<12} | {'Qty':<5}")
    print("-" * 90)
    for row in rows:
        print(f"{row[0]:<40} | {row[1]:<30} | {row[2]:<12} | {row[3]:<5}")

def main():
    init_db()
    while True:
        print("\n--- MTG Collection Tracker ---")
        print("1. Add Card")
        print("2. List Collection")
        print("3. Exit")
        choice = input("Choice: ")
        
        if choice == '1':
            handle_add_card()
        elif choice == '2':
            list_collection()
        elif choice == '3':
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
