import os
import psycopg2

def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    connection_settings = {
        "host": os.getenv("DB_HOST"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    sslmode = os.getenv("DB_SSLMODE")
    if sslmode:
        connection_settings["sslmode"] = sslmode

    return psycopg2.connect(**connection_settings)