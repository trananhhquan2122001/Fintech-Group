import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="FINEX VN Terminal", page_icon="📈", layout="wide")

st.title("🏛️ FINEX VN Terminal - Hệ Thống Dữ Liệu & Định Giá 500 Mã Cổ Phiếu")
st.markdown("---")

# Kiểm tra và load dữ liệu cơ sở dữ liệu tổng hợp
data_path = "data/vietnam_stock_database_tong_hop.csv" # Hoặc file excel tùy cấu trúc cào của bạn

if os.path.exists(data_path):
    df = pd.read_csv(data_path)
    st.success(f"Đã tải thành công cơ sở dữ liệu! Tổng số bản ghi: {len(df)}")
    
    # Hiển thị bảng dữ liệu mẫu
    st.subheader("📊 Dữ liệu tài chính doanh nghiệp mới nhất")
    st.dataframe(df.head(50), use_container_width=True)
else:
    st.warning("⚠️ Hiện chưa tìm thấy file dữ liệu tổng hợp. Hãy chạy GitHub Actions `main.py` để cào dữ liệu mới nhất về kho!")
