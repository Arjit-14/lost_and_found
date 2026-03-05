"""
Standalone demo script for image similarity using MobileNetV2.
This file is NOT used by the main app (app.py + interface.py).
It serves as a quick test to compare a lost item photo against found items.
"""
import os
import numpy as np
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
from tensorflow.keras.preprocessing import image
from sklearn.metrics.pairwise import cosine_similarity

# Load the Pre-trained Model (Feature Extractor)
# We use 'include_top=False' to get the feature vector, not a classification label.
model = MobileNetV2(weights="imagenet", include_top=False, pooling='avg')

def get_embedding(img_path):
    """Extract a 1280-dimensional feature vector from an image."""
    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)
    return model.predict(img_array, verbose=0)

if __name__ == "__main__":
    found_folder = "found_items"
    lost_photo = "lost_items/lost_bottle.jpg"

    if not os.path.exists(lost_photo):
        print(f"Error: '{lost_photo}' not found. Place a test image there first.")
    else:
        lost_vector = get_embedding(lost_photo)

        print("Scanning for matches...")
        results = []
        for file_name in os.listdir(found_folder):
            found_path = os.path.join(found_folder, file_name)
            if not os.path.isfile(found_path):
                continue
            found_vector = get_embedding(found_path)
            score = cosine_similarity(lost_vector, found_vector)[0][0]
            results.append((file_name, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        print(f"\n{'File':<30} {'Similarity':>10}")
        print("-" * 42)
        for name, score in results:
            print(f"{name:<30} {score:>10.4f}")