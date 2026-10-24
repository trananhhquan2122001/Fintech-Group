import os
import psycopg2
from datetime import datetime

# Danh sách 10 mã doanh nghiệp VN30 tiêu biểu
SYMBOLS = ['VCB', 'TCB', 'FPT', 'HPG', 'VIC', 'VHM', 'MBB', 'VPB', 'BID', 'STB']

def get_db_connection():
    # Lấy mật khẩu bảo mật từ GitHub Secrets (biến môi trường DB_PASSWORD)
    db_password = os.getenv("DB_PASSWORD")
    
    connection = psycopg2.connect(
        host="localhost",
        database="vietnam_stock_database",  # Tên cơ sở dữ liệu của cậu
        user="postgres",
        password=db_password,
        port="5432"
    )
    return connection

def setup_database(cursor):
    # Tạo bảng lưu dữ liệu với đúng tên yêu cầu: du_lieu_10_doanh_nghiep
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS du_lieu_10_doanh_nghiep (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            scrape_time TIMESTAMP NOT NULL,
            status VARCHAR(50) NOT NULL
        );
    """)

def main():
    print("🚀 Bắt đầu tiến trình thu thập dữ liệu 10 doanh nghiệp...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Khởi tạo cấu trúc bảng
        setup_database(cursor)
        conn.commit()

        for symbol in SYMBOLS:
            print(f" Đang xử lý dữ liệu cho mã: {symbol}...")
            
            current_time = datetime.now()
            status = "Collected Successfully"
            
            # Lưu dữ liệu vào bảng du_lieu_10_doanh_nghiep
            cursor.execute("""
                INSERT INTO du_lieu_10_doanh_nghiep (symbol, scrape_time, status)
                VALUES (%s, %s, %s);
            """, (symbol, current_time, status))
            conn.commit()
            
        print(" Đã lưu thành công dữ liệu của cả 10 doanh nghiệp vào bảng 'du_lieu_10_doanh_nghiep'!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Có lỗi xảy ra trong quá trình thực thi: {e}")

if __name__ == "__main__":
    main()
