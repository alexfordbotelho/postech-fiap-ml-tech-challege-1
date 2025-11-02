from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
load_dotenv

class Connection:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URL")
        self.db_name = os.getenv("DATABASE_NAME")
        self.client = AsyncIOMotorClient(self.uri)
        self.db = self.client[self.db_name]

    def get_collection(self, collection_name):
        return self.db[collection_name]

    def disconnect(self):
        self.client.close()
