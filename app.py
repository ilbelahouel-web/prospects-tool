import streamlit as st
import requests
import pandas as pd
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

    /* Bouton principal */
    .stButton > button {
        background: #4ade80 !important;
        color: #000 !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        border: none !important;
        font-size: 1rem !important;
        padding: 0.75rem !important;
        transition: opacity 0.2s !important;
    }
    .stButton > button:hover { opacity: 0.85 !important; }

    /* Bouton download */
    .stDownloadButton > button {
        background: #141414 !important;
        color: #4ade80 !important;
        border: 1px solid #4ade80 !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }

    /* Inputs */
    .stTextInput input, .stSelectbox select {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 8px !important;
        color: #fff !important;
    }

    /* Stat cards */
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

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border: 1px solid #1e1e1e !important;
        border-radius: 10px !important;
    }

    hr { border-color: #1a1a1a !important; }
</style>
""", unsafe_allow_html=True)

# ─── HEADER ──────────────────────────────────────────────────────────────────
st.title("🎯 Générateur de Prospects")
st.markdown("Trouve automatiquement les commerces d'une ville française et télécharge-les en **Excel**.")
st.divider()

# ─── FORMULAIRE ──────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    ville = st.text_input(
        "📍 Ville cible",
        placeholder="Lyon, Bordeaux, Marseille, Nice..."
    )

with col2:
    type_map = {
        "🍽️ Restaurants": "restaurant",
        "☕ Cafés & Bars": "bar",
        "✂️ Coiffeurs": "hairdresser",
        "💅 Salons de beauté": "beauty",
        "🍕 Fast-food": "fast_food",
        "🏥 Médecins": "doctors",
        "💊 Pharmacies": "pharmacy",
    }
    type_label = st.selectbox("🏪 Type de commerce", list(type_map.keys()))
    type_commerce = type_map[type_label]

max_results = st.slider("Nombre maximum de résultats", 20, 500, 150)

filtre_chaud = st.checkbox(
    "🔥 Prospects chauds uniquement — commerces SANS site web (moins démarchés, plus de besoin)",
    value=True
)

# ─── BOUTON ──────────────────────────────────────────────────────────────────
if st.button("🚀 Générer la liste de prospects", use_container_width=True):

    if not ville.strip():
        st.error("❌ Entre une ville svp")

    else:
        progress = st.progress(0, text="Connexion à la base OpenStreetMap...")

        OVERPASS_URL = "https://overpass-api.de/api/interpreter"

        query = f"""
[out:json][timeout:45];
area["name"="{ville.strip()}"]["admin_level"~"6|7|8"]->.a;
(
  node["amenity"="{type_commerce}"](area.a);
  way["amenity"="{type_commerce}"](area.a);
);
out body center;
"""

        try:
            progress.progress(15, text=f"Recherche des {type_label.split()[1].lower()}s à {ville}...")
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=45)
            resp.raise_for_status()

            progress.progress(55, text="Traitement des données...")
            elements = resp.json().get("elements", [])

            rows = []
            for elem in elements[:max_results]:
                tags = elem.get("tags", {})
                name = tags.get("name", "").strip()
                if not name:
                    continue

                # Coordonnées
                if elem["type"] == "node":
                    lat, lon = elem.get("lat", ""), elem.get("lon", "")
                else:
                    c = elem.get("center", {})
                    lat, lon = c.get("lat", ""), c.get("lon", "")

                maps_url = f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else ""

                phone = (
                    tags.get("phone", "")
                    or tags.get("contact:phone", "")
                    or tags.get("telephone", "")
                )

                rows.append({
                    "Nom": name,
                    "Adresse": f"{tags.get('addr:housenumber', '')} {tags.get('addr:street', '')}".strip(),
                    "Ville": tags.get("addr:city", ville),
                    "Téléphone": phone,
                    "Site web": tags.get("website", "") or tags.get("contact:website", ""),
                    "Email": tags.get("email", "") or tags.get("contact:email", ""),
                    "Instagram": tags.get("contact:instagram", ""),
                    "Facebook": tags.get("contact:facebook", ""),
                    "Google Maps": maps_url,
                    "Statut": "À contacter",
                    "Notes": "",
                })

            progress.progress(85, text="Génération du fichier Excel...")

            if not rows:
                st.warning(
                    "⚠️ Aucun résultat trouvé. Essaie avec une autre orthographe de la ville "
                    "(ex: 'Lyon' fonctionne mieux que 'Grand Lyon')."
                )
                progress.empty()

            else:
                df = pd.DataFrame(rows)

                # ─── FILTRE PROSPECTS CHAUDS ─────────────────────────────────
                if filtre_chaud:
                    # Sans site web = pas encore digitalisé = cible idéale
                    df = df[df["Site web"] == ""].reset_index(drop=True)
                    # Priorise ceux qu'on peut contacter (tel ou réseaux sociaux)
                    df["_score"] = (
                        df["Téléphone"].astype(bool).astype(int) * 2
                        + df["Instagram"].astype(bool).astype(int) * 3
                        + df["Facebook"].astype(bool).astype(int) * 2
                        + df["Email"].astype(bool).astype(int)
                    )
                    df = df.sort_values("_score", ascending=False).drop(columns="_score").reset_index(drop=True)

                if df.empty:
                    st.warning("⚠️ Aucun prospect chaud trouvé avec ce filtre. Décoche le filtre ou essaie une autre ville.")
                    st.stop()

                # ─── STATS ───────────────────────────────────────────────────
                total = len(df)
                with_phone = int(df["Téléphone"].astype(bool).sum())
                with_web = int(df["Site web"].astype(bool).sum())
                with_insta = int(df["Instagram"].astype(bool).sum())

                st.markdown(f"""
<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-number">{total}</div>
        <div class="stat-label">Commerces trouvés</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{with_phone}</div>
        <div class="stat-label">Avec téléphone</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{with_web}</div>
        <div class="stat-label">Avec site web</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{with_insta}</div>
        <div class="stat-label">Avec Instagram</div>
    </div>
</div>
""", unsafe_allow_html=True)

                # ─── APERÇU ──────────────────────────────────────────────────
                st.markdown("### 👀 Aperçu")
                st.dataframe(
                    df[["Nom", "Adresse", "Téléphone", "Site web", "Statut"]],
                    use_container_width=True,
                    hide_index=True
                )

                # ─── EXPORT EXCEL ─────────────────────────────────────────────
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Prospects")
                    ws = writer.sheets["Prospects"]
                    widths = [30, 35, 15, 16, 35, 28, 22, 30, 45, 15, 25]
                    for i, w in enumerate(widths):
                        ws.column_dimensions[chr(65 + i)].width = w

                progress.progress(100, text="✅ Terminé !")

                st.download_button(
                    label=f"📥 Télécharger les {total} prospects — Excel",
                    data=buffer.getvalue(),
                    file_name=f"prospects_{ville.lower().replace(' ', '_')}_{type_commerce}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        except requests.Timeout:
            st.error("❌ Trop lent. Réduis le nombre de résultats ou essaie une ville plus petite.")
            progress.empty()
        except Exception as e:
            st.error(f"❌ Erreur inattendue : {str(e)}")
            progress.empty()

# ─── FOOTER ──────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<p style='text-align:center;color:#2a2a2a;font-size:0.75rem'>"
    "Données OpenStreetMap — libres et mises à jour en temps réel"
    "</p>",
    unsafe_allow_html=True
)
