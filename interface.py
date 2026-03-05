import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import base64
import os
from datetime import datetime
from streamlit_js_eval import get_geolocation

st.set_page_config(page_title="Smart Campus Lost & Found", layout="wide")

# --- CSS Styling ---
st.markdown("""
    <style>
    [data-testid="stImage"] img {
        height: 200px;
        object-fit: cover;
        border-radius: 10px;
    }
    .collection-box {
        padding: 18px 20px;
        border-radius: 12px;
        margin: 10px 0;
        font-size: 15px;
        line-height: 1.6;
    }
    .collection-same-day {
        background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
        border-left: 6px solid #43a047;
        color: #1b5e20;
    }
    .collection-central {
        background: linear-gradient(135deg, #fff3e0, #ffe0b2);
        border-left: 6px solid #ef6c00;
        color: #e65100;
    }
    .timestamp-badge {
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        margin: 4px 0;
    }
    .score-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 15px;
        font-size: 13px;
        font-weight: 700;
    }
    .score-high { background: #c8e6c9; color: #2e7d32; }
    .score-med  { background: #fff9c4; color: #f57f17; }
    .score-low  { background: #ffcdd2; color: #c62828; }
    .reg-success {
        background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
        padding: 20px;
        border-radius: 14px;
        border-left: 6px solid #43a047;
        margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

API_BASE = "http://127.0.0.1:8000"

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return None

def score_badge(score):
    """Return styled HTML badge based on similarity score."""
    pct = f"{score:.0%}"
    if score >= 0.6:
        return f'<span class="score-badge score-high">🟢 {pct}</span>'
    elif score >= 0.3:
        return f'<span class="score-badge score-med">🟡 {pct}</span>'
    else:
        return f'<span class="score-badge score-low">🔴 {pct}</span>'

# --- Session State ---
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'selected_item' not in st.session_state:
    st.session_state.selected_item = None
if 'gps_active' not in st.session_state:
    st.session_state.gps_active = False

st.title("🔍 Smart Campus Lost & Found")
tab1, tab2 = st.tabs(["🔎 Find My Item", "➕ Report a Found Item"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1: SEARCH FOR LOST ITEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("🖼️ Step 1: Upload a Photo (Optional)")
        up_file = st.file_uploader(
            "Upload a picture of what you lost",
            type=['png', 'jpg', 'jpeg'],
            key="search_up",
            help="The AI will compare your photo against found items."
        )
        if up_file:
            st.image(up_file, use_container_width=True)

    with col_r:
        st.subheader("📝 Step 2: Describe It")
        u_desc = st.text_input("What did you lose?", placeholder="e.g. Black Dell laptop charger, silver chain necklace")
        st.caption("💡 Tip: Use details like color, brand, and type for better results.")

        if st.button("🔍 Start Smart Search", type="primary", use_container_width=True):
            if not up_file and not u_desc:
                st.warning("⚠️ Please provide a photo or a text description.")
            else:
                # Build multipart request properly
                files = {}
                if up_file:
                    files["file"] = (up_file.name, up_file.getvalue(), up_file.type)
                data = {"description": u_desc if u_desc else ""}

                with st.spinner("🔍 Scanning the database..."):
                    try:
                        res = requests.post(f"{API_BASE}/search-lost-item", files=files if files else None, data=data)
                        if res.status_code == 200:
                            st.session_state.search_results = res.json().get("top_matches", [])
                            st.session_state.selected_item = None
                        else:
                            st.error(f"Server error: {res.status_code}")
                    except requests.ConnectionError:
                        st.error("❌ Cannot connect to the server. Make sure the FastAPI backend is running on port 8000.")

    # --- Display Results ---
    if st.session_state.search_results is not None:
        results = st.session_state.search_results
        st.write("---")

        if not results:
            st.info("🔎 No matching items found. Try a different photo or description.")
        else:
            st.subheader(f"🎯 Top {len(results)} Match{'es' if len(results) > 1 else ''}")

            # Use max 5 columns, min 1
            num_cols = min(len(results), 5)
            cols = st.columns(num_cols)
            for i, match in enumerate(results):
                with cols[i % num_cols]:
                    with st.container(border=True):
                        if match.get('image_path') and os.path.exists(match['image_path']):
                            st.image(match['image_path'])
                        else:
                            st.write("🖼️ *Image not available*")

                        st.write(f"**{match['description'].title()}**")
                        st.markdown(score_badge(match['similarity_score']), unsafe_allow_html=True)

                        # Show timestamp badge
                        ts = match.get('timestamp')
                        if ts:
                            try:
                                ts_dt = datetime.fromisoformat(ts)
                                ts_label = ts_dt.strftime("%b %d, %I:%M %p")
                            except ValueError:
                                ts_label = "Unknown"
                        else:
                            ts_label = "Unknown"
                        st.markdown(f'<span class="timestamp-badge">📅 {ts_label}</span>', unsafe_allow_html=True)

                        if st.button(f"📍 Locate", key=f"btn_{i}", use_container_width=True):
                            st.session_state.selected_item = match

    # --- Selected Item: Collection Guide + Map ---
    if st.session_state.selected_item:
        sel = st.session_state.selected_item
        st.write("---")

        # Determine collection instructions from API response
        collection = sel.get('collection_point', {})
        action = collection.get('action', 'central_office')
        col_message = collection.get('message', 'Go to Central Office (Block 1)')
        col_detail = collection.get('detail', '')

        # Parse timestamp for display
        raw_ts = sel.get('timestamp')
        if raw_ts:
            try:
                r_time = datetime.fromisoformat(raw_ts).strftime("%b %d, %Y at %I:%M %p")
            except ValueError:
                r_time = "Unknown"
        else:
            r_time = "Unknown"

        # Choose style based on same-day vs central office
        if action == "same_day":
            box_class = "collection-same-day"
            icon = "✅"
        else:
            box_class = "collection-central"
            icon = "🏢"

        st.markdown(f"""
        <div class="collection-box {box_class}">
            <h3>{icon} Collection Guide — Match #{sel.get('id', 'N/A')}</h3>
            <p><b>Found at:</b> {sel.get('place_name', 'Campus')} &nbsp;|&nbsp; <b>When:</b> {r_time}</p>
            <p style="font-size:17px; font-weight:600; margin-top:8px;">👉 {col_message}</p>
            <p style="font-size:14px; opacity:0.85;">{col_detail}</p>
        </div>
        """, unsafe_allow_html=True)

        # Render Map
        lat = sel['location']['lat']
        lon = sel['location']['lon']
        m = folium.Map(location=[lat, lon], zoom_start=18)
        encoded = get_base64_image(sel.get('image_path', ''))
        if encoded:
            popup_html = f"""
            <div style="text-align:center;">
                <b style="color:#2E86C1;">{sel.get('place_name', 'Location')}</b><br>
                <img src="data:image/png;base64,{encoded}" width="140" style="margin-top:5px; border-radius:5px;">
            </div>
            """
        else:
            popup_html = f'<b style="color:#2E86C1;">{sel.get("place_name", "Location")}</b>'

        folium.Marker(
            [lat, lon],
            popup=folium.Popup(folium.IFrame(popup_html, width=170, height=200))
        ).add_to(m)
        st_folium(m, width='stretch', height=450, key="map_final")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2: REGISTER FOUND ITEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.subheader("➕ Register a Found Item")
    st.caption("📌 Help someone find their lost item! Fill in the details below and upload a photo.")

    # Show current timestamp preview
    current_ts = datetime.now().strftime("%b %d, %Y at %I:%M %p")
    st.markdown(f'<span class="timestamp-badge">📅 Will be registered at: {current_ts}</span>', unsafe_allow_html=True)

    campus_presets = {
        "Front Gate [12.9344, 77.6124]": {"lat": 12.93444, "lon": 77.61245},
        "Central Block [12.9338, 77.6105]": {"lat": 12.93385, "lon": 77.61054},
        "Central Block Canteen [12.9337, 77.6104]": {"lat": 12.93372, "lon": 77.61042},
        "Nandini / CCD Area [12.9341, 77.6110]": {"lat": 12.93415, "lon": 77.61105},
        "Audi Block [12.9348, 77.6108]": {"lat": 12.93481, "lon": 77.61085},
        "Christ PUC [12.9355, 77.6119]": {"lat": 12.93551, "lon": 77.61192},
        "Block 1 [12.9333, 77.6101]": {"lat": 12.93335, "lon": 77.61012},
        "Block 2 [12.9343, 77.6100]": {"lat": 12.93438, "lon": 77.61005},
        "Block 3 [12.9348, 77.6095]": {"lat": 12.93485, "lon": 77.60952},
        "Block 4 [12.9356, 77.6091]": {"lat": 12.93562, "lon": 77.60915},
        "Birds Park [12.9336, 77.6111]": {"lat": 12.93361, "lon": 77.61118},
        "Fresheteria [12.9351, 77.6102]": {"lat": 12.93512, "lon": 77.61021},
        "Basement Parking [12.9330, 77.6098]": {"lat": 12.93301, "lon": 77.60985},
        "Back Gate [12.9358, 77.6088]": {"lat": 12.93582, "lon": 77.60885}
    }

    if st.button("🛰️ Detect My Location"):
        loc = get_geolocation()
        if loc:
            st.session_state.detected_lat = loc['coords']['latitude']
            st.session_state.detected_lon = loc['coords']['longitude']
            st.session_state.gps_active = True

    preset = st.selectbox("📍 Select Campus Location", ["Manual"] + list(campus_presets.keys()))

    with st.form("reg_form", clear_on_submit=True):
        f_desc = st.text_input("📋 Item Description", placeholder="e.g. Black Dell laptop charger, silver chain necklace")
        f_name = st.text_input("🏫 Building / Area Name", value=preset if preset != "Manual" else "")
        col1, col2 = st.columns(2)

        # Location Logic
        def_lat = campus_presets[preset]['lat'] if preset != "Manual" else 12.9344
        def_lon = campus_presets[preset]['lon'] if preset != "Manual" else 77.6101

        f_lat = col1.number_input("Latitude", value=float(st.session_state.get('detected_lat', def_lat)), format="%.6f")
        f_lon = col2.number_input("Longitude", value=float(st.session_state.get('detected_lon', def_lon)), format="%.6f")
        f_file = st.file_uploader("📷 Upload Image of Found Item", type=['png', 'jpg', 'jpeg'])

        if st.form_submit_button("✅ Submit to Registry", type="primary"):
            if not f_file:
                st.warning("⚠️ Please upload a photo of the item.")
            elif not f_desc:
                st.warning("⚠️ Please provide a description.")
            elif not f_name:
                st.warning("⚠️ Please provide a building/area name.")
            else:
                # Build proper multipart file
                files = {"file": (f_file.name, f_file.getvalue(), f_file.type)}
                data = {"description": f_desc, "place_name": f_name, "lat": f_lat, "lon": f_lon}

                try:
                    with st.spinner("📤 Registering item..."):
                        res = requests.post(f"{API_BASE}/register-found-item", files=files, data=data)

                    if res.status_code == 200:
                        result = res.json()
                        reg_ts = result.get('timestamp', datetime.now().isoformat())
                        try:
                            reg_ts_display = datetime.fromisoformat(reg_ts).strftime("%b %d, %Y at %I:%M %p")
                        except ValueError:
                            reg_ts_display = reg_ts

                        st.markdown(f"""
                        <div class="reg-success">
                            <h3>✅ Item Registered Successfully!</h3>
                            <p><b>Item ID:</b> #{result.get('item_id', 'N/A')}</p>
                            <p><b>Description:</b> {f_desc}</p>
                            <p><b>Location:</b> {result.get('place_name', f_name)}</p>
                            <p><b>Registered at:</b> {reg_ts_display}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        st.balloons()
                    else:
                        st.error(f"❌ Server error: {res.status_code}")
                except requests.ConnectionError:
                    st.error("❌ Cannot connect to the server. Make sure the FastAPI backend is running on port 8000.")