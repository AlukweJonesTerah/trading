from pymongo import MongoClient
from decouple import config

# Load MongoDB URI and Database name from environment variables
MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")
MONGO_DB_NAME = config("MONGO_DB_NAME", default="trading_db")

# Create a connection to the MongoDB server
client = MongoClient(MONGO_URI)

# Select the database and collection
db = client[MONGO_DB_NAME]
collection = db["trading_pairs"]

# Run a query
result = collection.find({})

# Print the results
for document in result:
    print(document)
