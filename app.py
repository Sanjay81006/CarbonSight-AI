import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
import time
import streamlit as st
from fpdf import FPDF

# ==========================================
# 🔐 YOUR KEYS (PASTE HERE)
# ==========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
CLIMATIQ_API_KEY = st.secrets["CLIMATIQ_API_KEY"]

# ==========================================
# ⚙️ PAGE CONFIG & STYLE
# ==========================================
st.set_page_config(page_title="CarbonSight AI", page_icon="🌿", layout="wide")

st.markdown("""
<style>
    /* 1. BACKGROUND */
    .stApp {
        background-image: linear-gradient(rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.95)), 
                          url("https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=2070&auto=format&fit=crop");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
        color: #e2e8f0;
    }

    /* 2. NAVBAR */
    .navbar {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px 40px;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 40px;
    }
    .logo { font-size: 28px; font-weight: 700; color: #4ade80; font-family: sans-serif; }
    
    /* 3. CENTERED METRIC CARD */
    .metric-card {
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 50px;
        border-radius: 20px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    
    /* 4. BUTTONS & INPUTS */
    .stTextArea textarea {
        background-color: rgba(15, 23, 42, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: white !important;
        font-size: 16px;
        border-radius: 12px;
    }
    .stButton button {
        background: linear-gradient(135deg, #22c55e 0%, #15803d 100%);
        color: white;
        border: none;
        padding: 15px;
        font-size: 18px;
        font-weight: bold;
        border-radius: 12px;
        width: 100%;
        margin-top: 10px;
    }
    .stButton button:hover { opacity: 0.9; transform: scale(1.01); }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 📄 PDF GENERATOR (FIXED!)
# ==========================================
def clean_text(text):
    """Removes emojis and special characters that crash PDFs"""
    return text.encode('latin-1', 'replace').decode('latin-1')

def create_pdf(data, emissions, advice):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Title
    pdf.set_font("Arial", 'B', 24)
    pdf.cell(200, 20, txt="CarbonSight Report", ln=True, align='C')
    pdf.ln(10)
    
    # Result
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=clean_text(f"Total Carbon Footprint: {emissions['co2e']:.2f} kg CO2e"), ln=True, align='C')
    pdf.ln(20)
    
    # Details
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Shipment Details:", ln=True)
    pdf.cell(200, 10, txt=clean_text(f"- Weight: {data['weight']} kg"), ln=True)
    pdf.cell(200, 10, txt=clean_text(f"- Distance: {data['distance']} km"), ln=True)
    pdf.cell(200, 10, txt=clean_text(f"- Mode: {data['mode'].upper()}"), ln=True)
    pdf.ln(10)
    
    # Advice
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 10, txt=clean_text(f"Analysis: {advice}"))
    
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 🕵️ API FIX (DIAGNOSTIC)
# ==========================================
def get_working_model(api_key):
    if "PASTE_" in api_key: return None
    try:
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in models:
            if 'flash' in m: return m
        if models: return models[0]
        return None
    except: return None

# ==========================================
# 🧠 AI LOGIC
# ==========================================
def ai_agent(model_name, text):
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)
        prompt = f"""Extract data from: "{text}". Return JSON: weight (kg), distance (km), mode (truck, train, ship, plane), query_string."""
        response = model.generate_content(prompt)
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)
    except Exception as e: return {"error": str(e)}

def calculate_emissions(data):
    if "PASTE_" in CLIMATIQ_API_KEY: return {"error": "Key Missing"}
    url = "https://api.climatiq.io/data/v1/search"
    headers = {"Authorization": f"Bearer {CLIMATIQ_API_KEY}"}
    
    params = {"query": f"freight {data['query_string']}", "results_per_page": 1, "data_version": "^1"}
    search = requests.get(url, params=params, headers=headers)
    
    if not search.json().get("results"):
        params['query'] = f"freight {data['mode']}"
        search = requests.get(url, params=params, headers=headers)
    
    if not search.json().get("results"): return {"error": "Database not found"}

    factor = search.json()["results"][0]
    est_url = "https://api.climatiq.io/data/v1/estimate"
    payload = {
        "emission_factor": {"activity_id": factor['activity_id'], "data_version": "^1"},
        "parameters": {"weight": data['weight'], "weight_unit": "kg", "distance": data['distance'], "distance_unit": "km"}
    }
    
    res = requests.post(est_url, json=payload, headers=headers)
    if res.status_code == 200:
        final = res.json()
        final['factor_name'] = factor['name']
        return final
    return {"error": "API Error"}

# ==========================================
# 🖥️ DASHBOARD UI
# ==========================================
st.markdown("""
<div class="navbar">
    <div class="logo">🌿 CarbonSight AI</div>
    <div style="color: #aaa; font-weight: bold;">Enterprise Edition</div>
</div>
""", unsafe_allow_html=True)

# 1. CHECK API
active_model = get_working_model(GEMINI_API_KEY)
if not active_model and "PASTE_" not in GEMINI_API_KEY:
    st.error("⚠️ API Key Error. Please check your Google Cloud Console.")
    st.stop()

# 2. INPUT SECTION (CENTERED & STACKED)
# We use columns to center the input box on the screen
spacer_left, main_col, spacer_right = st.columns([1, 2, 1])

with main_col:
    st.markdown("<h3 style='text-align: center; margin-bottom: 10px;'>Analyze Shipment</h3>", unsafe_allow_html=True)
    
    # Text Input
    if 'input_text' not in st.session_state: st.session_state.input_text = ""
    user_input = st.text_area("Enter Details", value=st.session_state.input_text, height=120, placeholder="Example: 500kg electronics to Mumbai via Truck...", label_visibility="collapsed")
    
    # File Uploader (Small)
    uploaded_file = st.file_uploader("Or upload file", type=["csv", "xlsx"], label_visibility="collapsed")
    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"): df = pd.read_csv(uploaded_file)
            else: df = pd.read_excel(uploaded_file)
            st.session_state.input_text = df.to_string()
            st.rerun()
        except: pass

    # Big Button (Below Text)
    if st.button("🚀 ANALYZE IMPACT"):
        if "PASTE_" in GEMINI_API_KEY:
            st.error("Please paste API Keys in code!")
        elif not user_input:
            st.warning("Enter details first")
        else:
            # 3. RESULTS SECTION (Below Button)
            st.markdown("---")
            with st.spinner("Processing..."):
                ai_data = ai_agent(active_model, user_input)
                
                if "error" in ai_data:
                    st.error(ai_data['error'])
                else:
                    emissions = calculate_emissions(ai_data)
                    if "error" in emissions:
                        st.error(emissions['error'])
                    else:
                        # Logic
                        mode = ai_data['mode'].lower()
                        if "air" in mode or "plane" in mode:
                            badge_color, badge_text = "#ef4444", "HIGH INTENSITY"
                            advice = "⚠️ Air freight is ~50x more intensive than sea."
                        elif "truck" in mode:
                            badge_color, badge_text = "#f59e0b", "MEDIUM INTENSITY"
                            advice = "🚛 Standard road freight."
                        else:
                            badge_color, badge_text = "#22c55e", "LOW INTENSITY"
                            advice = "✅ Excellent choice (Sea/Rail)."

                        # --- DISPLAY CARD ---
                        st.markdown(f"""
                        <div class="metric-card">
                            <h3 style="color: #94a3b8; margin:0; text-transform: uppercase; letter-spacing: 2px;">Total Carbon Footprint</h3>
                            <h1 style="color: white; font-size: 80px; margin: 20px 0; font-weight: 800;">{emissions['co2e']:.2f} <span style="font-size: 30px; color: #64748b;">kg CO2e</span></h1>
                            <div style="display: inline-block; background: {badge_color}20; color: {badge_color}; padding: 10px 25px; border-radius: 30px; font-weight: bold; border: 1px solid {badge_color}40; font-size: 16px;">
                                {badge_text}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        # Metrics
                        c1, c2, c3 = st.columns(3)
                        c1.metric("📦 Weight", f"{ai_data['weight']} kg")
                        c2.metric("🛣️ Distance", f"{ai_data['distance']} km")
                        c3.metric("🚛 Mode", ai_data['mode'].upper())
                        
                        st.info(advice)
                        
                        # PDF Download (Sanitized!)
                        pdf_bytes = create_pdf(ai_data, emissions, advice)
                        st.download_button(
                            label="📄 Download Official Report (PDF)",
                            data=pdf_bytes,
                            file_name="CarbonSight_Report.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )