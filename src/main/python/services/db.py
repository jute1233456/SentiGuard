"""数据库连接配置 — pymysql 直连 MySQL"""
from __future__ import annotations

import os

import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "nilihai2580..."),
    "database": os.getenv("MYSQL_DATABASE", "sentiguard"),
    "charset": "utf8mb4",
}


def get_connection() -> pymysql.Connection:
    return pymysql.connect(**DB_CONFIG)
