import requests

def get_card_details(card_name):
    url = f"https://api.scryfall.com/cards/named?fuzzy={card_name}"
    headers = {"User-Agent": "MTG-Tracker-App/1.0"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def get_card_by_collector(set_code, collector_number):
    url = "https://api.scryfall.com/cards/search"
    params = {"q": f"set:{set_code} number:{collector_number}"}
    headers = {"User-Agent": "MTG-Tracker-App/1.0"}
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json().get('data', [])
        return data[0] if data else None
    return None

def search_cards(query):
    url = "https://api.scryfall.com/cards/search"
    params = {"q": query}
    headers = {"User-Agent": "MTG-Tracker-App/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get('data', [])
            # Normalize image URLs for the template
            for card in data:
                img = None
                if 'image_uris' in card:
                    img = card['image_uris'].get('normal')
                elif 'card_faces' in card and len(card['card_faces']) > 0:
                    img = card['card_faces'][0].get('image_uris', {}).get('normal')
                card['image_url'] = img
            return data
    except Exception as e:
        print(f"API Error: {e}")
    return []
