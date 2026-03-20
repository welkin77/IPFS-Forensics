# src/analyzer/ip_mapper.py
"""
重构自 IF-DSS ipmap.py
修复：geocoder超时崩溃、坐标解析错误、国内图源不可用
"""

import json
import os

try:
    import geocoder
except ImportError:
    geocoder = None

try:
    import folium
except ImportError:
    folium = None


def create_ip_list(file_path: str) -> list:
    """从track.json提取去重IP列表（复用IF-DSS逻辑）"""
    with open(file_path, 'r') as fd:
        json_data = json.load(fd)

    ip_list = []
    for key in json_data.keys():
        for ip in json_data[key].get('IP', []):
            ip_list.append(ip)

    return list(dict.fromkeys(ip_list))


def geolocate_ips(ip_list: list) -> dict:
    """
    IP地理定位
    IF-DSS原始：直接用geocoder.ip()，超时则崩溃
    v3改进：增加超时处理和错误跳过
    """
    if geocoder is None:
        print("[WARN] geocoder not installed, skipping geolocation")
        return {}

    data = {}
    for ip in ip_list:
        try:
            result = geocoder.ip(ip)
            latlng = result.latlng
            if latlng and len(latlng) == 2:
                key = str(latlng)
                if key in data:
                    data[key] = data[key] + ' ' + ip
                else:
                    data[key] = ip
            else:
                print(f"[WARN] No location for {ip}")
        except Exception as e:
            print(f"[WARN] Geocoding failed for {ip}: {e}")
            continue

    return data


def create_map(file_path: str, output: str):
    """
    生成IP地理分布地图
    IF-DSS原始：geocoder超时崩溃，坐标含字母时float转换崩溃
    v3修复：容错处理，可用图源
    """
    if folium is None:
        print("[ERROR] folium not installed. Run: pip install folium")
        return

    ip_list = create_ip_list(file_path)
    if not ip_list:
        print("[WARN] No IPs to map")
        return

    data = geolocate_ips(ip_list)

    map_html = folium.Map(
        location=[20, 0],
        zoom_start=2,
        tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        attr='&copy; OpenStreetMap contributors &copy; CARTO'
    )

    for location_str, ips in data.items():
        if location_str in ('[]', 'None', ''):
            continue

        raw_coord = location_str.strip('[]')

        # 跳过包含字母的无效坐标（IF-DSS的bug）
        if any(c.isalpha() for c in raw_coord):
            print(f"[WARN] Skipping invalid coord: {location_str}")
            continue

        try:
            parts = raw_coord.split(', ')
            if len(parts) != 2:
                continue
            coords = [float(parts[0]), float(parts[1])]

            popup_text = '<br>'.join(ips.split(' '))
            popup = folium.Popup(popup_text)
            marker = folium.Marker(
                location=coords,
                popup=popup,
                icon=folium.Icon(color='blue')
            )
            marker.add_to(map_html)
        except (ValueError, IndexError) as e:
            print(f"[WARN] Cannot parse coord '{raw_coord}': {e}")
            continue

    output_file = os.path.join(output, "IPMAP_result.html")
    map_html.save(output_file)
    print(f"[OK] Map saved to {output_file}")