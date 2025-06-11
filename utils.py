import os
import cx_Oracle
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        dsn = cx_Oracle.makedsn(
            os.getenv("ORACLE_HOST", "localhost"),
            os.getenv("ORACLE_PORT", "1521"),
            service_name=os.getenv("ORACLE_SERVICE", "xe")
        )
        connection = cx_Oracle.connect(
            user=os.getenv("ORACLE_USER"),
            password=os.getenv("ORACLE_PASSWORD"),
            dsn=dsn
        )
        return connection
    except cx_Oracle.Error as error:
        print("Error connecting to Oracle DB:", error)
        return None




