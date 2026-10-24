import os
import requests
import pandas as pd
from datetime import datetime

# Danh sách 10 mã doanh nghiệp VN30
SYMBOLS = ['VCB', 'TCB', 'FPT', 'HPG', 'VIC', 'VHM', 'MBB', 'VPB', 'BID', 'STB']

def fetch_stock_data(symbol):
    """Hàm gọi API công khai để lấy giá và khối lượng mới nhất của cổ phiếu"""
    try:
        # Sử dụng API công khai của TCBS để lấy thông tin giá khớp lệnh mới nhất
        url = f"https://apilist.tcbs.com.vn/stock-insight/v1/stock/iep-in-day/his-draft?ticker={symbol}&type=stock"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Trích xuất dữ liệu giá và khối lượng nếu API trả về thành công
            if 'data' in data and len(data['data']) > 0:
                latest = data['data'][-1]
                return {
                    'price': latest.get('price', 0),
                    'volume': latest.get('nmVolume', 0),
                    'status': 'Success'
                }
    except Exception as e:
        print(f"Lỗi khi cào mã {symbol}: {e}")
    
    # Giá trị dự phòng nếu lỗi kết nối API tạm thời
    return {
        'price': 0,
        'volume': 0,
        'status': 'API Connection Fallback'
    }

def main():
    print("🚀 Bắt đầu tiến trình thu thập dữ liệu giá và khối lượng VN30 thực tế...")
    
    data_list = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol in SYMBOLS:
        print(f"Đang lấy dữ liệu thực tế cho mã: {symbol}...")
        stock_info = fetch_stock_data(symbol)
        
        data_list.append({
            'symbol': symbol,
            'price': stock_info['price'],
            'volume': stock_info['volume'],
            'scrape_time': current_time,
            'status': stock_info['status']
        })
    
    # Chuyển đổi thành DataFrame của Pandas
    df = pd.DataFrame(data_list)
    file_path = 'vietnam_stock_data.csv'
    
    # Lưu file CSV tích lũy theo thời gian
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
