import os
import psycopg2

# Lấy mật khẩu bảo mật đã cấu hình trong GitHub Actions Secrets
db_password = os.getenv("DB_PASSWORD")

def test_database_connection():
    try:
        # Cậu thay đổi các thông số host, user, port, dbname cho khớp với PostgreSQL trên máy của cậu nhé
        connection = psycopg2.connect(
            host="localhost", # Hoặc địa chỉ IP/host của máy chủ chứa PostgreSQL
            database="vietnam_stock_database", # Tên cơ sở dữ liệu tài chính của cậu
            user="postgres", # Tên tài khoản quản trị database
            password=db_password,
            port="5432"
        )
        
        cursor = connection.cursor()
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        print(f"Kết nối PostgreSQL thành công! Phiên bản: {db_version[0]}")
        
        cursor.close()
        connection.close()
        
    except Exception as error:
        print(f"Lỗi kết nối cơ sở dữ liệu: {error}")

if __name__ == "__main__":
    print("Đang khởi động tiến trình xử lý dữ liệu tài chính...")
    test_database_connection()
