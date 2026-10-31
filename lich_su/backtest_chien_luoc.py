# ============================================================================
# lich_su/backtest_chien_luoc.py
# [v44-PERF] Đã sửa: Bọc try/except cho vectorbt & pandas-ta
#            → App chạy được dù KHÔNG cài 2 thư viện này
#            → Giữ nguyên 100% data khủng hoảng + logic
# ============================================================================
import pandas as pd
import numpy as np

# --- Optional: vectorbt (chỉ dùng cho backtest nâng cao) ---
try:
    import vectorbt as vbt
    HAS_VECTORBT = True
    print("[backtest_chien_luoc] ✅ vectorbt đã sẵn sàng.")
except ImportError:
    vbt = None
    HAS_VECTORBT = False
    print("[backtest_chien_luoc] ⚠️ vectorbt không khả dụng — dùng fallback an toàn.")

# --- Optional: pandas-ta (chỉ báo kỹ thuật) ---
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
    print("[backtest_chien_luoc] ✅ pandas-ta đã sẵn sàng.")
except ImportError:
    ta = None
    HAS_PANDAS_TA = False
    print("[backtest_chien_luoc] ⚠️ pandas-ta không khả dụng — dùng công thức thuần.")


# ============================================================================
# DỮ LIỆU KHỦNG HOẢNG LỊCH SỬ – CẬP NHẬT TỪ TƯ LIỆU MỚI
# ============================================================================
HISTORICAL_CRISES = {
    "1987_black_monday": {
        "title": "Cuộc khủng hoảng Ngày Thứ Hai Đen Tối (Black Monday) – 19/10/1987",
        "source": "Hồi ký Alan Greenspan, trang 124-128 (bản dịch)",
        "impact": (
            "Thị trường sụt giảm kỷ lục 508 điểm Dow Jones (-22,5%) trong một ngày, "
            "bốc hơi gần 500 tỷ USD vốn hóa toàn cầu. Đây là mức giảm lớn nhất trong lịch sử, "
            "tồi tệ hơn cả ngày Thứ Sáu Đen tối năm 1929."
        ),
        "context": {
            "trigger": (
                "Fed nâng lãi suất nhằm kiềm chế lạm phát → các ngân hàng thương mại nâng lãi suất cho vay → "
                "tăng trưởng chậm lại + đồng USD yếu đi → tâm lý hoảng loạn lan rộng."
            ),
            "timeline": [
                {"period": "Tuần đầu tháng 10/1987", "market_impact": "Thị trường giảm 5%"},
                {"period": "Tuần thứ hai tháng 10/1987", "market_impact": "Giảm thêm 12%"},
                {"period": "Thứ Sáu 16/10/1987", "market_impact": "Dow Jones mất 108 điểm"},
                {"period": "Thứ Hai 19/10/1987 (Black Monday)", "market_impact": "Dow Jones mất 508 điểm (-22.5%) – kỷ lục lịch sử"}
            ]
        },
        "metrics": {
            "single_day_dow_drop_points": -508,
            "single_day_dow_drop_pct": -22.5,
            "total_market_loss_usd": 500e9,
            "great_depression_comparison_pct": -80.0
        },
        "fed_actions_and_philosophy": {
            "core_mission": (
                "Chặn đứng tình trạng tê liệt của ngành tài chính – ngăn chặn sự đình trệ "
                "khi các ngân hàng và doanh nghiệp ngừng thanh toán giao dịch."
            ),
            "key_decision": (
                "Bơm thanh khoản khẩn cấp, tăng lượng tiền mặt dùng cho thanh toán để hỗ trợ "
                "các thể chế tài chính quan trọng bị khan hiếm tiền mặt."
            ),
            "famous_quote": (
                "Các vị biết người ta nói gì về cảm giác khi bị bắn không? Đầu tiên người ta cảm thấy "
                "như mình vừa bị ai đó đấm một cú, nhưng ngay lúc đó bạn vẫn chưa cảm thấy đau đớn ngay. "
                "Khoảng 24 đến 48 giờ sau thì cảm giác đau đớn mới rõ rệt."
            ),
            "market_lesson": (
                "Không đóng cửa thị trường chứng khoán khi hoảng loạn. Giữ thị trường mở để nhà đầu tư "
                "biết họ vẫn có thể rút ra, tránh gây gián đoạn toàn bộ hệ thống tài chính. "
                "Đóng cửa chỉ làm tăng thêm tổn thất và hoang mang."
            ),
            "policy_rule": (
                "Ưu tiên duy trì thanh khoản hệ thống, sẵn sàng cung cấp tiền mặt không giới hạn "
                "để ổn định thị trường tiền tệ và tín dụng."
            )
        },
        "stress_test_parameters": {
            "valuation_haircut_pct": -22.5,
            "liquidity_stress_factor": 0.75,
            "capital_erosion_factor": 0.85
        }
    },

    "1998_1999_ltcm_dotcom": {
        "title": "Khủng hoảng tài chính châu Á, vỡ nợ Nga, sụp đổ LTCM và bong bóng Dot-com (1998–1999)",
        "source": "Hồi ký Alan Greenspan, trang 252-253 (bản dịch)",
        "impact": (
            "Khủng hoảng nợ Nga bùng nổ, quỹ LTCM mất gần 5 tỷ USD chỉ trong một đêm. "
            "NASDAQ tăng gần gấp đôi trong 12 tháng (+100%), Dow Jones tăng 20% – hình thành bong bóng công nghệ "
            "mà Fed phải đối mặt với bài toán phân biệt tăng trưởng lành mạnh và đầu cơ."
        ),
        "context": {
            "trigger": (
                "Khủng hoảng tài chính châu Á (1997-1998) lan sang các nước đang phát triển; "
                "Nga vỡ nợ công; LTCM (Long-Term Capital Management) sụp đổ do đòn bẩy quá lớn, "
                "gây ra hiệu ứng lan truyền hệ thống."
            ),
            "timeline": [
                {"period": "Năm 1998", "market_impact": "Khủng hoảng lan rộng châu Á, Nga, Brazil. Dow Jones mất 1.000 điểm/ngày."},
                {"period": "Năm 1998", "market_impact": "LTCM bốc hơi gần 5 tỷ USD vốn chỉ trong thời gian ngắn."},
                {"period": "Tháng 12/1999", "market_impact": "NASDAQ tăng gấp đôi trong 12 tháng (+100%), Dow Jones tăng 20% – hình thành bong bóng Internet và cáp quang."}
            ]
        },
        "metrics": {
            "dow_single_day_drop_pts": -1000,
            "ltcm_capital_loss_usd": 5e9,
            "nasdaq_12m_growth_pct": 100.0,
            "dow_12m_growth_pct": 20.0,
            "fed_tightening_rate_1994_pct": 3.0
        },
        "fed_actions_and_philosophy": {
            "core_dilemma": (
                "Phân biệt rạch ròi giữa phát triển kinh tế lành mạnh với bong bóng chứng khoán đầu cơ "
                "được thúc đẩy bởi bản chất con người. Cả hai yếu tố này thường cùng tồn tại, gây khó khăn "
                "cho việc ra quyết định chính sách."
            ),
            "key_decision": (
                "Không dùng chính sách thắt chặt tiền tệ đột ngột để cố 'xì hơi' bong bóng, "
                "vì điều đó sẽ phá hoại nền kinh tế và xóa sổ tăng trưởng. "
                "Thay vào đó, Fed tập trung duy trì bình ổn giá cả và sẵn sàng cung cấp thanh khoản khi cần."
            ),
            "famous_quote": (
                "Mặc dù tình huống bong bóng vỡ hiếm khi được coi là tin tốt, thì hệ quả của nó "
                "cũng không đến nỗi bi thảm đối với nền kinh tế nếu Fed đặt mình vào vị trí bảo vệ nền kinh tế trong trường hợp đổ vỡ."
            ),
            "policy_rule": (
                "Duy trì mục tiêu chính là bình ổn giá cả hàng hóa và dịch vụ. Khi thị trường suy giảm nghiêm trọng, "
                "chính sách cần hướng tới hạ lãi suất dứt khoát và cung cấp thanh khoản để giảm thiểu thiệt hại kinh tế. "
                "Không can thiệp trực tiếp để ngăn chặn bong bóng vì điều đó nằm ngoài tầm với."
            )
        },
        "stress_test_parameters": {
            "valuation_haircut_pct": -35.0,
            "liquidity_stress_factor": 0.60,
            "capital_erosion_factor": 0.60
        }
    }
}


# ============================================================================
# CÁC HÀM KỸ THUẬT VÀ BACKTEST — ĐÃ BỌC FALLBACK AN TOÀN
# ============================================================================
def _pandas_rsi(series, length=14):
    """[v44] Fallback RSI bằng pandas thuần."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(length).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(length).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _pandas_macd(series, fast=12, slow=26, signal=9):
    """[v44] Fallback MACD bằng pandas thuần."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _pandas_bbands(series, length=20, std=2):
    """[v44] Fallback Bollinger Bands bằng pandas thuần."""
    ma = series.rolling(length).mean()
    sd = series.rolling(length).std()
    return ma - std * sd, ma, ma + std * sd


def _pandas_atr(df, price_col='price', length=14):
    """[v44] Fallback ATR — dùng high/low nếu có, không thì dùng price."""
    if {'high', 'low', 'close'}.issubset(df.columns):
        high, low, close = df['high'], df['low'], df['close']
    else:
        # Không có high/low → dùng price làm xấp xỉ
        close = pd.to_numeric(df[price_col], errors='coerce')
        high = close.shift(1).fillna(close)
        low = close.shift(1).fillna(close)
        close = close
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(length).mean()


def calculate_technical_indicators(df, price_col='price'):
    """
    [v44] Tính chỉ báo kỹ thuật — dùng pandas-ta nếu có,
    ngược lại fallback sang công thức pandas thuần.
    """
    if df is None or df.empty:
        return df

    # Nếu df không có cột price_col → không tính gì
    if price_col not in df.columns:
        return df

    df_ta = df.copy()
    df_ta[price_col] = pd.to_numeric(df_ta[price_col], errors='coerce')

    # --- Nếu có pandas-ta → dùng như cũ ---
    if HAS_PANDAS_TA and ta is not None:
        try:
            df_ta['rsi_14'] = ta.rsi(df_ta[price_col], length=14)

            macd = ta.macd(df_ta[price_col], fast=12, slow=26, signal=9)
            if macd is not None:
                df_ta['macd'] = macd['MACD_12_26_9']
                df_ta['macd_signal'] = macd['MACDs_12_26_9']
                df_ta['macd_hist'] = macd['MACDh_12_26_9']

            df_ta['sma_20'] = ta.sma(df_ta[price_col], length=20)
            df_ta['sma_50'] = ta.sma(df_ta[price_col], length=50)
            df_ta['sma_200'] = ta.sma(df_ta[price_col], length=200)

            bbands = ta.bbands(df_ta[price_col], length=20, std=2)
            if bbands is not None:
                df_ta['bb_lower'] = bbands['BBL_20_2.0']
                df_ta['bb_middle'] = bbands['BBM_20_2.0']
                df_ta['bb_upper'] = bbands['BBU_20_2.0']

            df_ta['atr_14'] = ta.atr(df_ta[price_col], length=14)
            return df_ta
        except Exception as e:
            print(f"[v44] pandas-ta lỗi → fallback pandas: {e}")
            # Rơi xuống fallback bên dưới

    # --- Fallback: tính bằng pandas thuần ---
    price_series = df_ta[price_col]

    # RSI 14
    df_ta['rsi_14'] = _pandas_rsi(price_series, 14)

    # MACD
    macd_line, macd_signal, macd_hist = _pandas_macd(price_series, 12, 26, 9)
    df_ta['macd'] = macd_line
    df_ta['macd_signal'] = macd_signal
    df_ta['macd_hist'] = macd_hist

    # SMA
    df_ta['sma_20'] = price_series.rolling(20).mean()
    df_ta['sma_50'] = price_series.rolling(50).mean()
    df_ta['sma_200'] = price_series.rolling(200).mean()

    # Bollinger Bands
    bb_lower, bb_mid, bb_upper = _pandas_bbands(price_series, 20, 2)
    df_ta['bb_lower'] = bb_lower
    df_ta['bb_middle'] = bb_mid
    df_ta['bb_upper'] = bb_upper

    # ATR
    df_ta['atr_14'] = _pandas_atr(df_ta, price_col, 14)

    return df_ta


def _pandas_backtest(price: np.ndarray, signal: np.ndarray):
    """
    [v44] Fallback backtest bằng pandas thuần khi không có vectorbt.
    Tính các chỉ số đơn giản: số lệnh, win rate, tổng lợi nhuận.
    """
    try:
        price = np.asarray(price, dtype=float)
        signal = np.asarray(signal, dtype=bool)

        entries = np.where(signal)[0]
        n_trades = len(entries)
        if n_trades < 2:
            return None, None

        # Giả lập: mua tại tín hiệu, bán tại tín hiệu tiếp theo
        pnl_list = []
        for i in range(len(entries) - 1):
            buy_price = price[entries[i]]
            sell_price = price[entries[i + 1]]
            if buy_price > 0:
                pnl_pct = (sell_price - buy_price) / buy_price * 100
                pnl_list.append(pnl_pct)

        if not pnl_list:
            return None, None

        pnl_arr = np.array(pnl_list)
        wins = (pnl_arr > 0).sum()
        total = len(pnl_arr)
        win_rate = wins / total * 100 if total > 0 else 0
        avg_return = float(pnl_arr.mean())
        total_return = float(pnl_arr.sum())
        best_trade = float(pnl_arr.max())
        worst_trade = float(pnl_arr.min())

        # DataFrame giả làm stats
        stats = pd.Series({
            "Total Trades": total,
            "Win Rate [%]": round(win_rate, 2),
            "Avg Return [%]": round(avg_return, 2),
            "Total Return [%]": round(total_return, 2),
            "Best Trade [%]": round(best_trade, 2),
            "Worst Trade [%]": round(worst_trade, 2),
            "Note": "Fallback backtest (không có vectorbt)",
        })

        # Trả về 1 dict-like thay vì portfolio
        pf = {"trades": total, "win_rate": win_rate, "total_return": total_return}
        return pf, stats
    except Exception as e:
        print(f"[v44] Fallback backtest lỗi: {e}")
        return None, None


def run_backtest_vectorbt(df, price_col='price', signal_col='signal_buy'):
    """
    [v44] Chạy backtest với vectorbt nếu có.
    Nếu không có → dùng pandas fallback.
    Trả về (Portfolio|dict, stats) hoặc (None, None).
    """
    if df is None or df.empty:
        return None, None
    if price_col not in df.columns or signal_col not in df.columns:
        return None, None

    price = df[price_col].values
    signal = df[signal_col].fillna(False).values.astype(bool)

    if not np.any(signal):
        return None, None

    # --- Nếu có vectorbt → dùng như cũ ---
    if HAS_VECTORBT and vbt is not None:
        try:
            pf = vbt.Portfolio.from_signals(price, entries=signal, short_exits=signal)
            stats = pf.stats()
            return pf, stats
        except Exception as e:
            print(f"[v44] vectorbt lỗi → fallback pandas: {e}")
            # Rơi xuống fallback

    # --- Fallback: pandas backtest ---
    return _pandas_backtest(price, signal) 
