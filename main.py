import os
import pandas as pd
from datetime import datetime

# Danh sách 10 mã doanh nghiệp VN30 tiêu biểu
SYMBOLS = ['VCB', 'TCB', 'FPT', 'HPG', 'VIC', 'VHM', 'MBB', 'VPB', 'BID', 'STB']

def main():
    print("🚀 Bắt đầu tiến trình thu thập dữ liệu 10 doanh nghiệp...")
    
    data_list = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol in SYMBOLS:
        print(f"Đang xử lý dữ liệu cho mã: {symbol}...")
        
        # Giả lập dữ liệu cào được cho từng mã cổ phiếu
        data_list.append({
            'symbol': symbol,
            'scrape_time': current_time,
            'status': 'Collected Successfully'
        })
    
    # Chuyển đổi dữ liệu thành DataFrame của Pandas
    df = pd.DataFrame(data_list)
    
    # Tên file lưu trữ dữ liệu
    file_path = 'vietnam_stock_data.csv'
    
    # Kiểm tra xem file cũ đã tồn tại chưa để cộng dồn hoặc ghi mới
    if os.path.exists(file_path):
        # Đọc dữ liệu cũ và gộp dữ liệu mới vào
        df_old = pd.read_csv(file_path)
        df_combined = pd.concat([df_old, df], ignore_index=True)
        df_combined.to_csv(file_path, index=False)
        print(f" Đã cập nhật và lưu dồn dữ liệu vào file '{file_path}'!")
    else:
        # Ghi file mới nếu chưa có
        df.to_csv(file_path, index=False)
        print(f" Đã tạo mới và lưu dữ liệu vào file '{file_path}'!")

if __name__ == "__main__":
    main()
