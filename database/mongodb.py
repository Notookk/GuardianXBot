# mongodb+srv://guardian:<db_password>@cluster0.thn0z3g.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
# database/mongodb.py
import motor.motor_asyncio

MONGODB_URL = "mongodb+srv://guardian:guardian@cluster0.thn0z3g.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"  # Change as needed

client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client["guardianxbot"]

users_col = db["users"]
violations_col = db["violations"]
# Add more collections as needed.
