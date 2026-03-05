from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
import shutil
import os
import json
import numpy as np
import nltk
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
from tensorflow.keras.preprocessing import image
from sklearn.metrics.pairwise import cosine_similarity
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from typing import Optional
from datetime import datetime, date

# --- NLTK Resources ---
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('wordnet', quiet=True)

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

def clean_text(text):
    tokens = word_tokenize(text.lower())
    cleaned = [lemmatizer.lemmatize(w) for w in tokens if w.isalnum() and w not in stop_words]
    return set(cleaned)

def get_text_similarity(query_text, db_text):
    set1 = clean_text(query_text)
    set2 = clean_text(db_text)
    if not set1 or not set2:
        return 0.0
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return len(intersection) / len(union)

# --- FastAPI Initialization ---
app = FastAPI()
app.mount("/found_items", StaticFiles(directory="found_items"), name="found_items")
model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')

DB_FILE = "found_items_db.json"
STORAGE_DIR = "found_items"
TEMP_DIR = "temp_uploads"
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Minimum similarity score to include in results
MIN_SCORE_THRESHOLD = 0.15

def get_embedding(img_path):
    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)
    return model.predict(img_array, verbose=0).tolist()[0]

def get_all_items():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_to_db(entry):
    items = get_all_items()
    items.append(entry)
    with open(DB_FILE, "w") as f:
        json.dump(items, f, indent=4)

def get_next_id():
    """Generate next ID safely using max existing ID + 1."""
    items = get_all_items()
    if not items:
        return 1
    return max(item.get("id", 0) for item in items) + 1

def get_collection_point(timestamp_str, place_name):
    """
    Determine where the user should collect the item based on when it was found.
    - Same day: go to the discovery location's security desk
    - Previous days: items are moved to Central Office (Block 1)
    """
    try:
        found_date = datetime.fromisoformat(timestamp_str).date()
        today = date.today()
        if found_date == today:
            return {
                "action": "same_day",
                "message": f"Go to the security desk at {place_name}",
                "detail": f"This item was found today at {place_name}. Head there to collect it."
            }
        else:
            days_ago = (today - found_date).days
            return {
                "action": "central_office",
                "message": "Go to Central Office (Block 1)",
                "detail": f"This item was found {days_ago} day(s) ago and has been moved to the Central Office (Block 1) for safekeeping."
            }
    except (ValueError, TypeError):
        return {
            "action": "central_office",
            "message": "Go to Central Office (Block 1)",
            "detail": "Unable to determine the discovery date. Please check the Central Office (Block 1)."
        }

# --- Endpoints ---
@app.post("/register-found-item")
async def register_item(
    description: str = Form(...),
    place_name: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    file: UploadFile = File(...)
):
    # Save uploaded file with a unique name to avoid collisions
    safe_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(STORAGE_DIR, safe_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    vector = get_embedding(file_path)
    timestamp = datetime.now().isoformat()
    new_entry = {
        "id": get_next_id(),
        "description": description,
        "place_name": place_name,
        "location": {"lat": lat, "lon": lon},
        "image_path": file_path,
        "vector": vector,
        "timestamp": timestamp
    }
    save_to_db(new_entry)
    return {
        "message": "Item registered successfully!",
        "item_id": new_entry["id"],
        "timestamp": timestamp,
        "place_name": place_name
    }

@app.post("/search-lost-item")
async def search_item(
    description: str = Form(None),
    file: Optional[UploadFile] = File(None)
):
    db_items = get_all_items()
    if not db_items:
        return {"top_matches": []}

    lost_vector = None
    if file:
        temp_path = os.path.join(TEMP_DIR, f"search_{file.filename}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        lost_vector = np.array(get_embedding(temp_path)).reshape(1, -1)
        # Clean up temp file
        try:
            os.remove(temp_path)
        except OSError:
            pass

    results = []
    seen_images = set()  # Track image paths to de-duplicate

    for item in db_items:
        img_path = item.get("image_path", "")

        # Skip duplicate image entries (keep only the first/best match per image)
        if img_path in seen_images:
            continue

        img_score = 0.0
        if lost_vector is not None and item.get("vector"):
            found_vector = np.array(item["vector"]).reshape(1, -1)
            img_score = float(cosine_similarity(lost_vector, found_vector)[0][0])

        text_score = 0.0
        if description and description.strip():
            text_score = get_text_similarity(description, item.get("description", ""))

        # Hybrid weight logic
        if lost_vector is not None and description and description.strip():
            final_score = (img_score * 0.6) + (text_score * 0.4)
        elif lost_vector is not None:
            final_score = img_score
        else:
            final_score = text_score

        # Apply minimum threshold
        if final_score < MIN_SCORE_THRESHOLD:
            continue

        seen_images.add(img_path)

        timestamp = item.get("timestamp", datetime.now().isoformat())
        place_name = item.get("place_name", "Campus")
        collection = get_collection_point(timestamp, place_name)

        results.append({
            "id": item.get("id", 0),
            "description": item.get("description", "No description"),
            "place_name": place_name,
            "location": item.get("location", {"lat": 12.9344, "lon": 77.6101}),
            "image_path": item.get("image_path"),
            "timestamp": timestamp,
            "similarity_score": round(final_score, 4),
            "collection_point": collection
        })

    # Sort by score descending, return top 2
    results = sorted(results, key=lambda x: x["similarity_score"], reverse=True)
    return {"top_matches": results[:2]}