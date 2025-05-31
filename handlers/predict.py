import os
import tensorflow as tf
import tensorflow_hub as hub
from tensorflow import keras
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'nsfw_model', 'nsfw_mobilenet2.224x224.h5')
IMAGE_DIM = 224

def load_model():
    """Loads the NSFW classifier model."""
    try:
        return tf.keras.models.load_model(
            MODEL_PATH, custom_objects={'KerasLayer': hub.KerasLayer}, compile=False
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load model from {MODEL_PATH}: {e}")

# Lazy-load singleton
_model = None
def get_model():
    global _model
    if _model is None:
        _model = load_model()
    return _model

def classify(model, image_path: str) -> dict:
    """Classifies an image and returns category probabilities."""
    from tensorflow.keras.preprocessing import image as keras_image
    try:
        img = keras_image.load_img(image_path, target_size=(IMAGE_DIM, IMAGE_DIM))
        img = img.convert('RGB')
        img = keras_image.img_to_array(img) / 255.0
        img = np.expand_dims(img, axis=0)

        categories = ['drawings', 'hentai', 'neutral', 'porn', 'sexy']
        predictions = model.predict(img)[0]
        return {category: float(predictions[i]) for i, category in enumerate(categories)}
    finally:
        try:
            os.remove(image_path)
        except Exception:
            pass  # Optionally log

def detect_nsfw(image_path: str) -> dict:
    """Detects NSFW content in an image file."""
    model = get_model()
    return classify(model, image_path)
