import streamlit as st
import requests
import pandas as pd
import time
from io import BytesIO

st.set_page_config(
    page_title="Générateur de Prospects",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

    .stApp { background: #0a0a0a; font-family: 'Inter', sans-serif; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 2rem !important; max-width: 820px; }

    h1 { color: #fff !important; font-size: 1.9rem !important; font-weight: 700 !important; }
    h3 { color: #bbb !important; font-size: 1rem !important; }
    p, label, li { color: #aaa !important; }
    strong { color: #fff !important; }

    .stButton > button {
        background: #4ade80 !important;
        color: #000 !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        border: none !important;
        font-size: 1rem !important;
        padding: 0.75rem !important;
    }
    .stButton > button:hover { opacity: 0.85 !important; }

    .stDownloadButton > button {
        background: #141414 !important;
        color: #4ade80 !important;
        border: 1px solid #4ade80 !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }

    .stTextInput input, .stSelectbox select {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 8px !important;
        color: #fff !important;
    }

    .stat-grid { display: flex; gap: 1rem; margin: 1.5rem 0; flex-wrap: wrap; }
    .stat-card {
        flex: 1;
        min-width: 120px;
        background: #111;
        border: 1px solid #1e1e1e;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .stat-number { font-size: 2rem; font-weight: 700; color: #4ade80; line-height: 1; }
    .stat-label { font-size: 0.75rem; color: #555; margin-top: 0.4rem; }

    [data-testid="stDataFrame"] {
        border: 1px solid #1e1e1e !important;
        border-radius: 10px !important;
    }

    hr { border-color: #1a1a1a !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HEADERS = {
    "User-Agent": "ProspectsTool/2.0 (projet-etudiant; contact via github)",
}

TYPE_MAP = {
    "🍽️ Restaurants": ('["amenity"="restaurant"]', "restaurant"),
    "🍕 Fast-food": ('["amenity"="fast_food"]', "fast_food"),
    "☕ Cafés": ('["amenity"="cafe"]', "cafe"),
    "🍺 Bars": ('["amenity"="bar"]', "bar"),
    "✂️ Coiffeurs": ('["shop"="hairdresser"]', "coiffeur"),
    "💅 Instituts de beauté": ('["shop"="beauty"]', "beaute"),
    "💊 Pharmacies": ('["amenity"="pharmacy"]', "pharmacie"),
    "🏋️ Salles de sport": ('["leisure"="fitness_centre"]', "fitness"),
}

# Rayons d'extension progressive (en mètres)
RADIUS_STEPS = [7000, 15000, 30000]
RADIUS_LABELS = {7000: "la ville", 15000: "la ville + proche banlieue", 30000: "toute l'agglomération (30 km)"}


# ─────────────────────────────────────────────────────────────────────────────
# FONCTIONS
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def geocode_city(city_name: str):
    """Trouve les coordonnées GPS d'une ville française via Nominatim."""
    params = {
        "q": f"{city_name}, France",
        "format": "json",
        "limit": 1,
        "countrycodes": "fr",
    }
    r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    results = r.json()
    if not results:
        return None
    return {
        "lat": float(results[0]["lat"]),
        "lon": float(results[0]["lon"]),
        "display": results[0]["display_name"].split(",")[0],
    }


def query_overpass(lat: float, lon: float, radius: int, osm_filter: str):
    """Interroge Overpass avec recherche par rayon (rapide et fiable)."""
    query = f"""
[out:json][timeout:40];
(
  node{osm_filter}(around:{radius},{lat},{lon});
  way{osm_filter}(around:{radius},{lat},{lon});
);
out body center;
"""
    last_error = None
    errors_detail = []
    for server in OVERPASS_SERVERS:
        try:
            r = requests.post(server, data={"data": query}, headers=HEADERS, timeout=50)
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as e:
            errors_detail.append(f"{server.split('/')[2]} → {type(e).__name__}: {str(e)[:120]}")
            last_error = e
            continue
    raise RuntimeError(" | ".join(errors_detail))


def parse_elements(elements, ville_defaut: str):
    """Transforme les résultats bruts OSM en lignes propres."""
    rows, seen = [], set()
    for elem in elements:
        tags = elem.get("tags", {})
        name = tags.get("name", "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        if elem["type"] == "node":
            lat, lon = elem.get("lat", ""), elem.get("lon", "")
        else:
            c = elem.get("center", {})
            lat, lon = c.get("lat", ""), c.get("lon", "")

        phone = tags.get("phone", "") or tags.get("contact:phone", "") or tags.get("telephone", "")
        website = tags.get("website", "") or tags.get("contact:website", "")
        insta = tags.get("contact:instagram", "")
        fb = tags.get("contact:facebook", "")
        email = tags.get("email", "") or tags.get("contact:email", "")

        rows.append({
            "Nom": name,
            "Adresse": f"{tags.get('addr:housenumber', '')} {tags.get('addr:street', '')}".strip(),
            "Ville": tags.get("addr:city", ville_defaut),
            "Téléphone": phone,
            "Site web": website,
            "Email": email,
            "Instagram": insta,
            "Facebook": fb,
            "Google Maps": f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else "",
            "Statut": "À contacter",
            "Notes": "",
        })
    return rows


def build_excel(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prospects")
        ws = writer.sheets["Prospects"]
        widths = [30, 35, 18, 16, 35, 28, 22, 30, 45, 15, 25]
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
st.title("🎯 Générateur de Prospects")
st.markdown("Trouve les commerces d'une ville française + ses alentours, et télécharge-les en **Excel**.")
st.divider()

col1, col2 = st.columns(2)
with col1:
    ville = st.text_input("📍 Ville cible", placeholder="Perpignan, Angers, Metz...")
with col2:
    type_label = st.selectbox("🏪 Type de commerce", list(TYPE_MAP.keys()))

col3, col4 = st.columns(2)
with col3:
    objectif = st.number_input("🎯 Nombre de prospects visé", min_value=10, max_value=500, value=100, step=10)
with col4:
    zone = st.selectbox(
        "🗺️ Zone de recherche",
        ["Auto (étend aux alentours si besoin)", "Ville uniquement (7 km)", "Agglomération (15 km)", "Large (30 km)"]
    )

filtre_chaud = st.checkbox(
    "🔥 Prospects chauds uniquement — commerces SANS site web (moins démarchés, plus de besoin)",
    value=True
)

if st.button("🚀 Générer la liste de prospects", use_container_width=True):

    if not ville.strip():
        st.error("❌ Entre une ville svp")
        st.stop()

    progress = st.progress(0, text="📍 Localisation de la ville...")

    # ── 1. Géocodage ─────────────────────────────────────────────────────────
    try:
        geo = geocode_city(ville.strip())
    except Exception:
        st.error("❌ Impossible de localiser la ville. Réessaie dans 30 secondes.")
        st.stop()

    if geo is None:
        st.error(f"❌ Ville « {ville} » introuvable en France. Vérifie l'orthographe.")
        st.stop()

    osm_filter, type_slug = TYPE_MAP[type_label]

    # ── 2. Détermination des rayons à essayer ────────────────────────────────
    if zone.startswith("Auto"):
        radii = RADIUS_STEPS
    elif "7 km" in zone:
        radii = [7000]
    elif "15 km" in zone:
        radii = [15000]
    else:
        radii = [30000]

    # ── 3. Recherche avec extension progressive ──────────────────────────────
    df = pd.DataFrame()
    zone_utilisee = ""

    for i, radius in enumerate(radii):
        progress.progress(
            20 + i * 25,
            text=f"🔎 Recherche dans {RADIUS_LABELS.get(radius, f'{radius//1000} km')}..."
        )
        try:
            elements = query_overpass(geo["lat"], geo["lon"], radius, osm_filter)
        except Exception as e:
            st.error("❌ Aucun serveur n'a répondu. Détail technique :")
            st.code(str(e), language=None)
            st.stop()

        rows = parse_elements(elements, geo["display"])
        df = pd.DataFrame(rows)

        if filtre_chaud and not df.empty:
            df_filtre = df[df["Site web"] == ""].reset_index(drop=True)
        else:
            df_filtre = df

        zone_utilisee = RADIUS_LABELS.get(radius, f"{radius//1000} km")

        # Assez de résultats ? On s'arrête là
        if len(df_filtre) >= objectif:
            df = df_filtre
            break

        # Sinon on garde et on tente le rayon supérieur (mode auto)
        df = df_filtre
        if i < len(radii) - 1:
            time.sleep(1)  # politesse envers les serveurs

    progress.progress(85, text="📊 Préparation des résultats...")

    if df.empty:
        st.warning("⚠️ Aucun résultat. Essaie sans le filtre 🔥 ou avec une zone plus large.")
        st.stop()

    # ── 4. Tri par facilité de contact ───────────────────────────────────────
    df["_score"] = (
        df["Instagram"].astype(bool).astype(int) * 3
        + df["Téléphone"].astype(bool).astype(int) * 2
        + df["Facebook"].astype(bool).astype(int) * 2
        + df["Email"].astype(bool).astype(int)
    )
    df = df.sort_values("_score", ascending=False).drop(columns="_score").reset_index(drop=True)

    # Limite à l'objectif demandé
    df = df.head(int(objectif))

    # ── 5. Affichage ─────────────────────────────────────────────────────────
    total = len(df)
    with_phone = int(df["Téléphone"].astype(bool).sum())
    with_insta = int(df["Instagram"].astype(bool).sum())
    with_fb = int(df["Facebook"].astype(bool).sum())

    progress.progress(100, text="✅ Terminé !")

    st.success(f"✅ **{total} prospects** trouvés dans **{zone_utilisee}**")

    st.markdown(f"""
<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-number">{total}</div>
        <div class="stat-label">Prospects</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{with_phone}</div>
        <div class="stat-label">Avec téléphone</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{with_insta}</div>
        <div class="stat-label">Avec Instagram</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{with_fb}</div>
        <div class="stat-label">Avec Facebook</div>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 👀 Aperçu")
    st.dataframe(
        df[["Nom", "Adresse", "Ville", "Téléphone", "Instagram"]],
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        label=f"📥 Télécharger les {total} prospects — Excel",
        data=build_excel(df),
        file_name=f"prospects_{ville.lower().replace(' ', '_')}_{type_slug}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.divider()
st.markdown(
    "<p style='text-align:center;color:#2a2a2a;font-size:0.75rem'>"
    "Données OpenStreetMap — libres et mises à jour en temps réel"
    "</p>",
    unsafe_allow_html=True
)
