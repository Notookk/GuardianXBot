import os

# Bot credentials
API_ID = '25193832'
API_HASH = 'e154b1ccb0195edec0bc91ae7efebc2f'

# MongoDB connection string (primary database)
MONGODB_URI = 'mongodb+srv://guardian:guardian@cluster0.thn0z3g.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'

# Telegram bot settings
TOKEN = "7141521775:AAEIpE2pDzaPNGMttlSZk"
OWNER_ID = 7875192045  # Change to your actual owner ID
OWNER_IDS = [7875192045, 6656608288, 6545754981]  # Add as many as you want!
AUTH_USERS = [7875192045]

# Log and alert channels
LOG_CHANNEL = '-1002240372506'
ALERT_CHANNEL_ID = "-1002329693689"

# Other settings
MEDIA_DIR = "../media"
IMAGES_DIR = "https://files.catbox.moe/f23vlq.jpg"
BROADCAST_AS_COPY = True

# For backward compatibility, if any code still looks for DB_URI:
DB_URI = MONGODB_URI
