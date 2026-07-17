from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.config import get_settings


@lru_cache
def get_mongo_client() -> MongoClient:
    settings = get_settings()
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)


def get_mongo_db() -> Database:
    settings = get_settings()
    return get_mongo_client()[settings.mongodb_db]


def generations_collection() -> Collection:
    return get_mongo_db()["generations"]
