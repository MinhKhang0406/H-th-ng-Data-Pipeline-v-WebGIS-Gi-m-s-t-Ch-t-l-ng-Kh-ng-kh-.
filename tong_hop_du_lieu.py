import pandas as pd
import requests
import ee
import numpy as np
import os

# ==========================================
# CẤU HÌNH API KEYS & PROJECT
# ==========================================
WAQI_API_KEY = "c410ad41ceef478c2ec00ba1afb0caf561eef54f" 
IQAIR_API_KEY = "" 
GEE_PROJECT_ID = "dacn-475523" 

REGION_BOUNDS = "10.1,106.0,11.5,107.5" 

# ==========================================
# 1. HÀM LẤY DỮ LIỆU OPEN-METEO (Lấy Đầy Đủ Chất)
# ==========================================
def get_open_meteo_data():
    print("⏳ Đang lấy dữ liệu chi tiết từ Open-Meteo...")
    lat_range = np.arange(10.2, 11.5, 0.2)
    lon_range = np.arange(106.1, 107.4, 0.2)
    
    danh_sach = []
    for lat in lat_range:
        for lon in lon_range:
            url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide"
            try:
                res = requests.get(url).json()
                current = res.get("current", {})
                if current:
                    danh_sach.append({
                        "Tên_trạm": f"Lưới Open-Meteo ({round(lat,2)}, {round(lon,2)})",
                        "Vĩ_độ": lat,
                        "Kinh_độ": lon,
                        "PM2.5": current.get("pm2_5", 0),
                        "PM10": current.get("pm10", 0),
                        "CO": current.get("carbon_monoxide", 0),
                        "NO2": current.get("nitrogen_dioxide", 0),
                        "SO2": current.get("sulphur_dioxide", 0),
                        "Nguồn": "Open-Meteo"
                    })
            except Exception:
                pass
                
    df = pd.DataFrame(danh_sach)
    print(f"✅ Open-Meteo: Lấy thành công {len(df)} điểm.")
    return df

# ==========================================
# 2. HÀM LẤY DỮ LIỆU WAQI (Vào Từng Trạm Lấy Đủ Chất)
# ==========================================
def get_waqi_data():
    if not WAQI_API_KEY or WAQI_API_KEY == "ĐIỀN_WAQI_API_KEY_CỦA_BẠN_VÀO_ĐÂY":
        print("⚠️ WAQI: Bỏ qua vì chưa có API Key.")
        return pd.DataFrame()

    print("⏳ Đang lấy danh sách trạm WAQI...")
    url_bounds = f"https://api.waqi.info/map/bounds?token={WAQI_API_KEY}&latlng={REGION_BOUNDS}"
    
    try:
        response = requests.get(url_bounds)
        if response.status_code == 200 and response.json().get("status") == "ok":
            cac_tram = response.json()["data"]
            danh_sach = []
            print(f"🔍 Tìm thấy {len(cac_tram)} trạm WAQI. Đang lấy chi tiết...")
            
            for tram in cac_tram:
                uid = tram["uid"]
                url_detail = f"https://api.waqi.info/feed/@{uid}/?token={WAQI_API_KEY}"
                res_detail = requests.get(url_detail).json()
                
                if res_detail.get("status") == "ok":
                    iaqi = res_detail["data"].get("iaqi", {})
                    danh_sach.append({
                        "Tên_trạm": tram["station"]["name"],
                        "Vĩ_độ": tram["lat"],
                        "Kinh_độ": tram["lon"],
                        "PM2.5": iaqi.get("pm25", {}).get("v", 0),
                        "PM10": iaqi.get("pm10", {}).get("v", 0),
                        "CO": iaqi.get("co", {}).get("v", 0),
                        "NO2": iaqi.get("no2", {}).get("v", 0),
                        "SO2": iaqi.get("so2", {}).get("v", 0),
                        "Nguồn": "WAQI"
                    })
            
            df = pd.DataFrame(danh_sach)
            df['PM2.5'] = pd.to_numeric(df['PM2.5'], errors='coerce')
            df = df[df['PM2.5'] > 0] 
            print(f"✅ WAQI: Lấy thành công {len(df)} trạm.")
            return df
    except Exception as e:
        print(f"❌ Lỗi WAQI: {e}")
        
    return pd.DataFrame()

# ==========================================
# 3. HÀM LẤY DỮ LIỆU GOOGLE EARTH ENGINE (Đã sửa lỗi 0 điểm)
# ==========================================
def get_gee_data():
    print("⏳ Đang lấy dữ liệu từ Google Earth Engine...")
    try:
        if GEE_PROJECT_ID and GEE_PROJECT_ID != "ĐIỀN_PROJECT_ID_CỦA_BẠN_VÀO_ĐÂY":
            ee.Initialize(project=GEE_PROJECT_ID)
        else:
            ee.Initialize() 
    except Exception:
        print("❌ LỖI GEE: Vui lòng kiểm tra lại Project ID hoặc xác thực.")
        return pd.DataFrame()

    try:
        vung_quan_tam = ee.Geometry.Rectangle([106.0, 10.1, 107.5, 11.5])
        
        # SỬA LỖI: Quét lùi lại 7 ngày để tổng hợp dữ liệu, tránh bị mây che hoặc khuyết ảnh
        ngay_ket_thuc = ee.Date(pd.Timestamp.now().strftime('%Y-%m-%d'))
        ngay_bat_dau = ngay_ket_thuc.advance(-7, 'day')
        
        dataset = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_AER_AI') \
                    .filterBounds(vung_quan_tam) \
                    .filterDate(ngay_bat_dau, ngay_ket_thuc) \
                    .select('absorbing_aerosol_index') \
                    .median() # Lấy trung vị của 7 ngày để lọc nhiễu
        
        diem_mau = ee.FeatureCollection.randomPoints(vung_quan_tam, 15)
        gia_tri = dataset.reduceRegions(collection=diem_mau, reducer=ee.Reducer.mean(), scale=1000).getInfo()
        
        danh_sach = []
        for i, feature in enumerate(gia_tri['features']):
            coords = feature['geometry']['coordinates']
            val = feature['properties'].get('mean', None)
            if val is not None:
                pm25_uoc_tinh = max(0, val * 20 + 15) 
                danh_sach.append({
                    "Tên_trạm": f"Vệ tinh GEE Điểm {i+1}",
                    "Vĩ_độ": coords[1], "Kinh_độ": coords[0], 
                    "PM2.5": round(pm25_uoc_tinh, 1),
                    "PM10": 0, "CO": 0, "NO2": 0, "SO2": 0, 
                    "Nguồn": "Google Earth Engine"
                })
        df = pd.DataFrame(danh_sach)
        print(f"✅ GEE: Lấy thành công {len(df)} điểm.")
        return df
    except Exception as e:
        print(f"❌ LỖI GEE trong quá trình xử lý: {e}")
        return pd.DataFrame()

# ==========================================
# 4. HÀM LẤY DỮ LIỆU IQAIR
# ==========================================
def get_iqair_data():
    if not IQAIR_API_KEY: return pd.DataFrame()
    print("⏳ Đang lấy dữ liệu từ IQAir...")
    coords = [{"lat": 10.8231, "lon": 106.6297, "name": "HCM"}, {"lat": 11.1833, "lon": 106.6500, "name": "Bình Dương"}]
    danh_sach = []
    for loc in coords:
        try:
            url = f"http://api.airvisual.com/v2/nearest_city?lat={loc['lat']}&lon={loc['lon']}&key={IQAIR_API_KEY}"
            data = requests.get(url).json().get("data")
            if data:
                danh_sach.append({
                    "Tên_trạm": f"IQAir - {loc['name']}",
                    "Vĩ_độ": data["location"]["coordinates"][1], "Kinh_độ": data["location"]["coordinates"][0],
                    "PM2.5": data["current"]["pollution"]["aqius"],
                    "PM10": 0, "CO": 0, "NO2": 0, "SO2": 0,
                    "Nguồn": "IQAir"
                })
        except: pass
    df = pd.DataFrame(danh_sach)
    if not df.empty: print(f"✅ IQAir: Lấy thành công {len(df)} trạm.")
    return df

# ==========================================
# CHƯƠNG TRÌNH CHÍNH
# ==========================================
def main():
    print("🚀 BẮT ĐẦU TỔNG HỢP DỮ LIỆU TỪ 4 NGUỒN...")
    df_om = get_open_meteo_data()
    df_waqi = get_waqi_data()
    df_gee = get_gee_data()
    df_iqair = get_iqair_data()
    
    cac_bang = [df for df in [df_om, df_waqi, df_gee, df_iqair] if not df.empty]
    
    if cac_bang:
        df_tong = pd.concat(cac_bang, ignore_index=True)
        df_tong = df_tong.fillna(0) # Đảm bảo không bị trống dữ liệu
        df_tong['Tỉnh/Thành phố'] = "Vùng Đông Nam Bộ"
        
        ten_file = "tram_quantrac_toan_vung.csv"
        df_tong.to_csv(ten_file, index=False, encoding='utf-8-sig')
        print(f"🎉 HOÀN TẤT! Đã lưu {len(df_tong)} điểm vào file '{ten_file}'.")
    else:
        print("❌ Không thu thập được dữ liệu nào.")

if __name__ == "__main__":
    main()