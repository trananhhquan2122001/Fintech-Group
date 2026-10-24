import os
import pandas as pd
from datetime import datetime
import yfinance as yf

# Danh sách 10 mã doanh nghiệp VN30
SYMBOLS = ['VCB', 'TCB', 'FPT', 'HPG', 'VIC', 'VHM', 'MBB', 'VPB', 'BID', 'STB']

def main():
    print("🚀 Bắt đầu lấy dữ liệu giá và khối lượng thực tế...")
    
    data_list = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol in SYMBOLS:
        print(f"Đang xử lý mã: {symbol}...")
        try:
            # Thêm hậu tố .VN để lấy dữ liệu chuẩn từ thị trường chứng khoán Việt Nam
            ticker = yf.Ticker(f"{symbol}.VN")
            hist = ticker.history(period="1d")
            
            if not hist.empty:
                latest_row = hist.iloc[-1]
                price = float(latest_row['Close'])
                volume = int(latest_row['Volume'])
                status = 'Success'
            else:
                price = 0
                volume = 0
                status = 'No Data Found'
        except Exception as e:
            print(f"Lỗi lấy dữ liệu mã {symbol}: {e}")
            price = 0
            volume = 0
            status = 'Error'
            
        data_list.append({
            'symbol': symbol,
            'price': price,
            'volume': volume,
            'scrape_time': current_time,
            'status': status
        })
    
    # Chuyển đổi thành DataFrame của Pandas
    df = pd.DataFrame(data_list)
    file_path = 'vietnam_stock_data.csv'
    
    # Lưu file CSV tích lũy
    if os.path.exists(file_path):
        df_old = pd.read_csv(file_path)
        df_combined = pd.concat([df_old, df], ignore_index=True)
        df_combined.to_csv(file_path, index=False)
        print(f" Đã cập nhật thêm dữ liệu mới vào '{file_path}'!")
    else:
        df.to_csv(file_path, index=False)
        print(f" Đã tạo mới file dữ liệu '{file_path}'!")

if __name__ == "__main__":
    main()
