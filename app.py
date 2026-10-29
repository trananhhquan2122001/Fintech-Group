import streamlit as st
import pandas as pd
import plotly.express as px
import os

# Cấu hình giao diện Streamlit
st.set_page_config(
    page_title="FINEX VN Terminal — Phân Tích & Định Giá", 
    page_icon="📈", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ FINEX VN Terminal — Enterprise Financial Intelligence")
st.markdown("Hệ thống khai thác, trực quan hóa và định giá tự động cơ sở dữ liệu tài chính doanh nghiệp Việt Nam.")
st.markdown("---")

# ============================================================================
# 1. HÀM TẢI DỮ LIỆU TỐC ĐỘ CAO (CÓ CACHE)
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_database():
    possible_paths = [
        "data/vietnam_stock_database_tong_hop.csv",
        "vietnam_stock_database_tong_hop.csv",
        "../data/vietnam_stock_database_tong_hop.csv",
        "du_lieu/vietnam_stock_database_tong_hop.csv"
    ]
    
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                df_load = pd.read_csv(path, low_memory=False)
                # Giữ nguyên chữ hoa/thường hoặc chuẩn hóa khoảng trắng thừa
                df_load.columns = [str(c).strip() for c in df_load.columns]
                return df_load
            except Exception:
                continue
    return pd.DataFrame()

df = load_database()

# ============================================================================
# 2. XỬ LÝ GIAO DIỆN & LOGIC HIỂN THỊ
# ============================================================================
if df.empty:
    st.warning("⚠️ Hiện chưa tìm thấy file cơ sở dữ liệu tổng hợp (`vietnam_stock_database_tong_hop.csv`). Hãy kiểm tra lại thư mục `data/` trên kho GitHub!")
else:
    # Khớp chính xác với tên các cột tiếng Việt thực tế trong file CSV của bạn
    ticker_col = 'mã chứng khoán' if 'mã chứng khoán' in df.columns else next((c for c in df.columns if 'mã' in c), None)
    period_col = 'năm' if 'năm' in df.columns else next((c for c in df.columns if 'kỳ' in c or 'năm' in c), None)
    metric_col = 'chỉ tiêu tiếng việt' if 'chỉ tiêu tiếng việt' in df.columns else next((c for c in df.columns if 'chỉ tiêu' in c), None)
    value_col = 'giá trị' if 'giá trị' in df.columns else next((c for c in df.columns if 'giá trị' in c), None)

    if not ticker_col:
        st.error(f"❌ Không tìm thấy cột mã chứng khoán. Các cột hiện có: {list(df.columns)}")
    else:
        # Làm sạch mã chứng khoán
        df[ticker_col] = df[ticker_col].astype(str).str.strip().str.upper()
        all_tickers = sorted([t for t in df[ticker_col].unique() if t and t != 'NAN'])

        # --- SIDEBAR: BỘ LỌC & TÌM KIẾM MÃ THÔNG MINH ---
        st.sidebar.header("🔍 Tra Cứu Doanh Nghiệp")
        default_idx = all_tickers.index("FPT") if "FPT" in all_tickers else 0
        selected_ticker = st.sidebar.selectbox("🎯 Chọn hoặc gõ mã chứng khoán:", all_tickers, index=default_idx)
        
        st.sidebar.markdown("---")
        st.sidebar.info(f"💡 **Trạng thái:** Đã tải `{len(all_tickers)}` mã doanh nghiệp.")

        # Lọc dữ liệu theo mã được chọn
        df_sub = df[df[ticker_col] == selected_ticker]

        # --- MAIN DISPLAY ---
        st.subheader(f"📊 Hồ sơ tài chính doanh nghiệp: **{selected_ticker}**")
        
        # Thẻ thông tin nhanh (KPI Metrics)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="Tổng số bản ghi dữ liệu", value=f"{len(df_sub):,}")
        with col2:
            unique_periods = df_sub[period_col].nunique() if period_col else 0
            st.metric(label="Số năm/kỳ báo cáo theo dõi", value=unique_periods)
        with col3:
            unique_metrics = df_sub[metric_col].nunique() if metric_col else 0
            st.metric(label="Chỉ tiêu tài chính khai thác", value=unique_metrics)

        st.markdown("")

        # --- BIỂU ĐỒ TRỰC QUAN ---
        if not df_sub.empty and period_col and metric_col and value_col:
            st.markdown("### 📈 Trực Quan Hóa Chỉ Số Tài Chính")
            
            # Chuyển đổi dữ liệu giá trị sang kiểu số an toàn
            df_sub[value_col] = pd.to_numeric(df_sub[value_col].astype(str).str.replace(',', ''), errors='coerce')
            
            available_metrics = sorted(df_sub[metric_col].dropna().unique())
            default_selection = available_metrics[:5] if len(available_metrics) >= 5 else available_metrics
            
            selected_metrics = st.multiselect(
                "🧩 Chọn các chỉ tiêu tài chính muốn hiển thị trên biểu đồ:",
                options=available_metrics,
                default=default_selection
            )
            
            if selected_metrics:
                df_chart = df_sub[df_sub[metric_col].isin(selected_metrics)]
                
                chart_type = st.radio(
                    "🎨 Kiểu hiển thị biểu đồ:", 
                    ["Cột nhóm (Bar Chart)", "Đường xu hướng (Line Chart)"], 
                    horizontal=True
                )
                
                if "Bar" in chart_type:
                    fig = px.bar(
                        df_chart.dropna(subset=[value_col]),
                        x=period_col,
                        y=value_col,
                        color=metric_col,
                        barmode='group',
                        title=f"Biểu đồ cột so sánh chỉ tiêu tài chính - {selected_ticker}",
                        template="plotly_dark"
                    )
                else:
                    fig = px.line(
                        df_chart.dropna(subset=[value_col]),
                        x=period_col,
                        y=value_col,
                        color=metric_col,
                        markers=True,
                        title=f"Biểu đồ đường xu hướng tài chính - {selected_ticker}",
                        template="plotly_dark"
                    )
                
                fig.update_layout(
                    xaxis_title="Năm / Kỳ báo cáo",
                    yaxis_title="Giá trị (VND / Tỷ lệ)",
                    legend_title="Chỉ tiêu",
                    hovermode="x unified",
                    height=550
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("👈 Vui lòng chọn ít nhất một chỉ tiêu tài chính ở trên để vẽ biểu đồ.")

        # --- BẢNG DỮ LIỆU CHI TIẾT ---
        st.markdown("---")
        st.markdown(f"### 📋 Bảng Dữ Liệu Chi Tiết Của {selected_ticker}")
        
        search_query = st.text_input("🔍 Lọc nhanh từ khóa trong bảng dữ liệu:", placeholder="Nhập tên chỉ tiêu cần tìm...")
        
        if search_query:
            mask = df_sub.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
            df_display = df_sub[mask]
        else:
            df_display = df_sub

        st.dataframe(df_display, use_container_width=True, height=400)

        # Nút tải xuống
        csv_data = df_sub.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"📥 Tải xuống dữ liệu CSV của {selected_ticker}",
            data=csv_data,
            file_name=f"FINEX_Data_{selected_ticker}.csv",
            mime="text/csv",
        )
