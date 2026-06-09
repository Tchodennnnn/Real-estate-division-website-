import mysql.connector

def get_connection():
    conn = mysql.connector.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="17626259",
        database="RED_Dash"
    )
    return conn