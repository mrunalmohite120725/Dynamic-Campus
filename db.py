"""
db.py — MySQL connection factory using environment-based config.
"""
import mysql.connector
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Config


def get_connection():
    return mysql.connector.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
    )