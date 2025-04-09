import os
import tensorflow as tf
import tensorflow_hub as hub
from tensorflow import keras
import numpy as np
from PIL import Image

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'nsfw_model', 'nsfw_mobilenet2.224x224.h5')
IMAGE_DIM = 224

# Load Model
def load_model():
    return tf.keras.models.load_model(MODEL_PATH, custom_objects={'KerasLayer': hub.KerasLayer}, compile=False)

model = load_model()

def classify(model, image_path):
    img = keras.preprocessing.image.load_img(image_path, target_size=(IMAGE_DIM, IMAGE_DIM))
    img = keras.preprocessing.image.img_to_array(img) / 255.0
    img = np.expand_dims(img, axis=0)
    
    categories = ['drawings', 'hentai', 'neutral', 'porn', 'sexy']
    predictions = model.predict(img)[0]
    os.remove(image_path)
    
    return {category: float(predictions[i]) for i, category in enumerate(categories)}

def detect_nsfw(image_path):
    return classify(model, image_path)
