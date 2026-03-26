import streamlit as st
import pandas as pd
import pydeck as pdk
import re

st.set_page_config(page_title="Hệ thống giám sát chất lượng không khí", layout="wide", page_icon="🌤️")

# ==========================================
# HÀM CHUẨN HÓA TÊN CỘT
# ==========================================
def normalize_columns(df):
    """Ánh xạ các tên cột về tên chuẩn (PM2.5, PM10, CO, NO2, SO2, O3)."""
    mapping = {
        'PM2.5': re.compile(r'^pm2[\._]?5$', re.IGNORECASE),
        'PM10': re.compile(r'^pm10$', re.IGNORECASE),
        'CO': re.compile(r'^co$', re.IGNORECASE),
        'NO2': re.compile(r'^no2$', re.IGNORECASE),
        'SO2': re.compile(r'^so2$', re.IGNORECASE),
        'O3': re.compile(r'^o3$', re.IGNORECASE),
    }
    new_columns = {}
    for col in df.columns:
        col_clean = col.strip()
        found = False
        for std_name, pattern in mapping.items():
            if pattern.match(col_clean):
                new_columns[col] = std_name
                found = True
                break
        if not found:
            new_columns[col] = col_clean
    return df.rename(columns=new_columns)

# ==========================================
# CÁC HÀM XỬ LÝ MÀU SẮC VÀ AQI
# ==========================================
def phan_loai_aqi_vn(pm25):
    if pm25 <= 25: return "Tốt", "#00E400"
    elif pm25 <= 50: return "Trung bình", "#FFFF00"
    elif pm25 <= 80: return "Kém", "#FF7E00"
    elif pm25 <= 150: return "Xấu", "#FF0000"
    elif pm25 <= 250: return "Rất xấu", "#8F3F97"
    else: return "Nguy hại", "#7E0023"

def get_aqi_color(pm25):
    if pm25 <= 25: return [0, 228, 0, 200]
    elif pm25 <= 50: return [255, 255, 0, 200]
    elif pm25 <= 80: return [255, 126, 0, 200]
    elif pm25 <= 150: return [255, 0, 0, 200]
    elif pm25 <= 250: return [143, 63, 151, 200]
    else: return [126, 0, 35, 200]

def get_generic_color(val, max_val):
    if max_val <= 0: return [0, 255, 0, 200]
    ratio = max(0.0, min(val / max_val, 1.0))
    return [int(255 * ratio), int(255 * (1 - ratio)), 0, 200]

# ==========================================
# HÀM HIỂN THỊ DASHBOARD
# ==========================================
def hien_thi_dashboard(df_filtered, chat_duoc_chon, max_val_hientai, hien_thi_noi_suy, hien_thi_ten_tram, tat_ca_chat_hien_co):
    try:
        # Ép kiểu số cho các cột chất lượng
        for chat in tat_ca_chat_hien_co:
            if chat in df_filtered.columns:
                df_filtered[chat] = pd.to_numeric(df_filtered[chat], errors='coerce').fillna(0)

        data_points = []
        for _, row in df_filtered.iterrows():
            val_chat = float(row[chat_duoc_chon])

            if chat_duoc_chon == "PM2.5":
                label, hex_color = phan_loai_aqi_vn(val_chat)
                mau_sac = get_aqi_color(val_chat)
            else:
                label = "Đang đo lường"
                mau_sac = get_generic_color(val_chat, max_val_hientai)

            chuoi_hien_thi = f"{row['Tên_trạm']} ({val_chat})" if hien_thi_ten_tram else str(round(val_chat, 1))

            data_points.append({
                "Tên_trạm": str(row['Tên_trạm']),
                "Vĩ_độ": float(row['Vĩ_độ']),
                "Kinh_độ": float(row['Kinh_độ']),
                "Chiso_Value": val_chat,
                "Chiso_Text": chuoi_hien_thi,
                "Trang_thai": label,
                "Nguồn": str(row['Nguồn']),
                "Màu_sắc": mau_sac,
                "Kích_thước": 2500 + (val_chat / (max_val_hientai + 0.001) * 3000)
            })

        df_plot = pd.DataFrame(data_points)

        if df_plot.empty:
            st.warning("Không có dữ liệu để hiển thị với các bộ lọc hiện tại. Vui lòng chọn lại Nguồn dữ liệu ở Menu bên trái.")
            return

        # Thẻ thông số
        col1, col2, col3 = st.columns(3)
        col1.metric("Tổng Số Điểm Đo", len(df_plot))
        idx_max = df_plot['Chiso_Value'].idxmax()
        col2.metric(f"{chat_duoc_chon} Cao Nhất", f"{df_plot.loc[idx_max, 'Chiso_Value']} ({df_plot.loc[idx_max, 'Tên_trạm']})")
        col3.metric(f"{chat_duoc_chon} Trung Bình", round(df_plot['Chiso_Value'].mean(), 1))

        st.markdown("---")

        # Tính zoom bản đồ
        lat_mean = df_plot['Vĩ_độ'].mean()
        lon_mean = df_plot['Kinh_độ'].mean()
        if len(df_plot) > 1:
            lat_diff = df_plot['Vĩ_độ'].max() - df_plot['Vĩ_độ'].min()
            lon_diff = df_plot['Kinh_độ'].max() - df_plot['Kinh_độ'].min()
            max_diff = max(lat_diff, lon_diff)
            if max_diff < 0.05: zoom_level = 12
            elif max_diff < 0.2: zoom_level = 10.5
            elif max_diff < 0.8: zoom_level = 9
            elif max_diff < 2.0: zoom_level = 7.5
            else: zoom_level = 6
        else:
            zoom_level = 13

        # Vẽ bản đồ
        st.subheader("📍 BẢN ĐỒ KHÔNG GIAN")
        layer_scatter = pdk.Layer(
            "ScatterplotLayer",
            df_plot,
            get_position=["Kinh_độ", "Vĩ_độ"],
            get_color="Màu_sắc",
            get_radius="Kích_thước",
            pickable=True,
            stroked=True,
            get_line_color=[255, 255, 255, 200],
            line_width_min_pixels=2
        )

        layer_text = pdk.Layer(
            "TextLayer",
            df_plot,
            get_position=["Kinh_độ", "Vĩ_độ"],
            get_text="Chiso_Text",
            get_size=14 if hien_thi_ten_tram else 16,
            get_color=[0, 0, 0, 255],
            get_alignment_baseline="'bottom'",
            get_text_anchor="'middle'"
        )

        layer_heatmap = pdk.Layer(
            "HeatmapLayer",
            df_plot,
            get_position=["Kinh_độ", "Vĩ_độ"],
            get_weight="Chiso_Value",
            radius_pixels=70,
            intensity=1.5,
            threshold=0.05
        )

        layers_to_render = [layer_heatmap, layer_scatter, layer_text] if hien_thi_noi_suy else [layer_scatter, layer_text]

        view_state = pdk.ViewState(
            latitude=lat_mean,
            longitude=lon_mean,
            zoom=zoom_level,
            pitch=0
        )

        st.pydeck_chart(pdk.Deck(
            layers=layers_to_render,
            initial_view_state=view_state,
            tooltip={"text": "Trạm: {Tên_trạm}\nNguồn: {Nguồn}\n" + chat_duoc_chon + ": {Chiso_Value}\nĐánh giá: {Trang_thai}"}
        ))

        st.markdown("---")

        # Bảng dữ liệu
        st.subheader("📊 BẢNG DỮ LIỆU ĐA CHẤT Ô NHIỄM")
        cols_to_show = ["Nguồn", "Tên_trạm"]
        if 'Tỉnh/Thành phố' in df_filtered.columns:
            cols_to_show.append("Tỉnh/Thành phố")
        for chat in tat_ca_chat_hien_co:
            cols_to_show.append(chat)
        st.dataframe(df_filtered[cols_to_show], use_container_width=True)

        st.markdown("---")

        # Biểu đồ cột (ĐÃ ĐƯỢC SỬA LỖI TẠI ĐÂY)
        st.subheader(f"📈 BIỂU ĐỒ CỘT ({chat_duoc_chon})")
        
        # Gom nhóm theo tên trạm và tính trung bình để tránh lỗi trùng lặp dữ liệu
        df_chart = df_plot.groupby("Tên_trạm", as_index=False)["Chiso_Value"].mean()
        
        # Sắp xếp từ cao xuống thấp và lấy Top 30 để biểu đồ không bị quá tải
        df_chart = df_chart.sort_values(by="Chiso_Value", ascending=False).head(30)
        
        # Vẽ biểu đồ với thông số x, y rõ ràng
        if not df_chart.empty:
            st.bar_chart(
                data=df_chart, 
                x="Tên_trạm", 
                y="Chiso_Value", 
                color="#FF4B4B", 
                height=500
            )
        else:
            st.info("Không có dữ liệu biểu đồ phù hợp.")

    except Exception as e:
        st.error(f"❌ Đã xảy ra lỗi khi vẽ hệ thống: {e}. Vui lòng kiểm tra lại.")

# ==========================================
# SIDEBAR VÀ QUẢN LÝ DỮ LIỆU CHÍNH
# ==========================================
st.sidebar.title("MENU HỆ THỐNG")

menu_trang = st.sidebar.radio(
    "CHỌN TRANG PHÂN TÍCH:",
    ["🌍 Tổng quan Toàn vùng", "📍 Chi tiết Tỉnh/Thành phố"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("QUẢN LÝ DỮ LIỆU")
uploaded_file = st.sidebar.file_uploader("Tải tệp dữ liệu CSV lên", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    # Chuẩn hóa tên cột ngay sau khi đọc
    df = normalize_columns(df)

    st.sidebar.subheader("1. Lọc Nguồn Dữ Liệu")
    ds_nguon = df['Nguồn'].unique()
    nguon_selected = st.sidebar.multiselect("Chọn Nguồn:", ds_nguon, default=ds_nguon)
    df = df[df['Nguồn'].isin(nguon_selected)]

    st.sidebar.subheader("2. Cài đặt Thang đo")
    danh_sach_chat = ["PM2.5", "PM10", "CO", "NO2", "SO2", "O3"]
    chat_hien_co = [chat for chat in danh_sach_chat if chat in df.columns]

    if len(chat_hien_co) > 0:
        chat_duoc_chon = st.sidebar.selectbox("Lựa chọn chất ô nhiễm để hiển thị:", chat_hien_co)
        # Loại bỏ các dòng thiếu tọa độ hoặc giá trị chất được chọn
        df = df.dropna(subset=['Vĩ_độ', 'Kinh_độ', chat_duoc_chon])
        # Ép kiểu số cho cột được chọn
        df[chat_duoc_chon] = pd.to_numeric(df[chat_duoc_chon], errors='coerce').fillna(0)
        max_val_hientai = df[chat_duoc_chon].max() if not df.empty else 1
    else:
        st.error("Không tìm thấy cột chất ô nhiễm nào (PM2.5, PM10, CO, NO2, SO2, O3) trong file dữ liệu. Hãy kiểm tra lại tên cột.")
        st.stop()

    st.sidebar.subheader("3. Công cụ Bản đồ")
    hien_thi_noi_suy = st.sidebar.checkbox("🔥 Bật Nội suy Heatmap", value=False)
    hien_thi_ten_tram = st.sidebar.checkbox("🏷️ Hiện Tên Trạm trên Bản đồ", value=False)

    if menu_trang == "🌍 Tổng quan Toàn vùng":
        st.title("🌤️ TỔNG QUAN CHẤT LƯỢNG KHÔNG KHÍ TOÀN VÙNG")
        st.markdown("---")
        hien_thi_dashboard(df, chat_duoc_chon, max_val_hientai, hien_thi_noi_suy, hien_thi_ten_tram, chat_hien_co)

    elif menu_trang == "📍 Chi tiết Tỉnh/Thành phố":
        st.title("📍 CẮT LÁT KHÔNG GIAN - TỈNH/THÀNH PHỐ")
        st.markdown("---")

        if 'Tỉnh/Thành phố' in df.columns:
            ds_tinh = df['Tỉnh/Thành phố'].dropna().unique()
            if len(ds_tinh) == 1:
                st.warning(f"⚠️ **Nhắc nhở dữ liệu:** Tệp CSV của bạn hiện chỉ có một giá trị là `{ds_tinh[0]}` trong cột 'Tỉnh/Thành phố'. Để có thể cắt lát từng tỉnh, bạn hãy mở tệp CSV bằng Excel, điền tên các tỉnh thành (Hồ Chí Minh, Vũng Tàu,...) tương ứng vào cột này rồi tải lên lại nhé!")

            tinh_selected = st.selectbox("🎯 Chọn Khu Vực / Tỉnh Thành cần cắt lát:", ds_tinh)
            df_filtered = df[df['Tỉnh/Thành phố'] == tinh_selected]
            st.success(f"Đang phân tích chuyên sâu khu vực: **{tinh_selected}**")

            hien_thi_dashboard(df_filtered, chat_duoc_chon, max_val_hientai, hien_thi_noi_suy, hien_thi_ten_tram, chat_hien_co)
        else:
            st.error("Rất tiếc! Tệp dữ liệu CSV của bạn không có cột 'Tỉnh/Thành phố'.")

else:
    st.info("👋 Xin chào! Hãy tải tệp CSV của bạn lên ở Menu bên trái để bắt đầu.")