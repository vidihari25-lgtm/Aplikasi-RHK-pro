import streamlit as st
import google.generativeai as genai
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
import io
import pandas as pd
import sqlite3
import os
from PIL import Image
import tempfile

# ==========================================
# 1. KONFIGURASI & INISIALISASI STATE
# ==========================================
st.set_page_config(page_title="Aplikasi RHK PKH Pro", layout="wide")

# --- INISIALISASI STATE AGAR TIDAK KEYERROR ---
def init_state():
    defaults = {
        'page': 'home',
        'selected_rhk': None,
        'rhk2_queue': [], 'rhk4_queue': [], 'rhk7_queue': [],
        'generated_file_data': None,
        'rhk3_results': None,
        'rhk2_results': [], 'rhk4_results': [], 'rhk7_results': [],
        'bln_val': "JANUARI", 'th_val': "2026",
        'tgl_val': "30 Januari 2026",
        'kop_bytes': None, 'ttd_bytes': None,
        'password_correct': False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ==========================================
# 2. SISTEM KEAMANAN & API KEY
# ==========================================
# Ganti user/pass disini jika mau
DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

def get_api_key_safe():
    # 1. Cek Streamlit Secrets (Prioritas)
    if "GOOGLE_API_KEY" in st.secrets:
        return st.secrets["GOOGLE_API_KEY"]
    
    # 2. Cek Environment Variable (Cadangan)
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY")
        
    return None

FINAL_API_KEY = get_api_key_safe()

# ==========================================
# 3. FUNGSI DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect('riwayat_v45.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS riwayat (id INTEGER PRIMARY KEY, tgl TEXT, rhk TEXT, judul TEXT, lokasi TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (
        id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, 
        prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
    c.execute('SELECT count(*) FROM user_settings')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO user_settings (id, nama, nip, kpm, prov, kab, kec, kel) VALUES (1, ?, ?, ?, ?, ?, ?, ?)',
                  ("Vidi Hari Suci", "123456", 250, "Lampung", "Lampung Tengah", "Punggur", "Mojopahit"))
    conn.commit(); conn.close()

def get_user_settings():
    try:
        conn = sqlite3.connect('riwayat_v45.db')
        c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone()
        conn.close()
        return data if data else ("User", "-", 0, "-", "-", "-", "-")
    except:
        return ("User", "-", 0, "-", "-", "-", "-")

def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
    conn = sqlite3.connect('riwayat_v45.db')
    c = conn.cursor()
    c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
    conn.commit(); conn.close()

def simpan_riwayat(rhk, judul, lokasi):
    try:
        conn = sqlite3.connect('riwayat_v45.db')
        c = conn.cursor()
        tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute('INSERT INTO riwayat (tgl, rhk, judul, lokasi) VALUES (?, ?, ?, ?)', (tgl, rhk, judul, lokasi))
        conn.commit(); conn.close()
    except: pass

# ==========================================
# 4. FUNGSI PENDUKUNG (FOTO, PDF, WORD)
# ==========================================
BASE_ARSIP = "Arsip_Foto_Kegiatan"

def compress_image(uploaded_file, quality=70, max_width=800):
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        if image.mode in ("RGBA", "P"): image = image.convert("RGB")
        if image.width > max_width:
            ratio = max_width / float(image.width)
            new_height = int((float(image.height) * float(ratio)))
            image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0); uploaded_file.seek(0)
        return output
    except:
        uploaded_file.seek(0)
        return uploaded_file 

def get_archived_photos(rhk, periode):
    return [] # Placeholder agar tidak error path di cloud

def safe_str(data):
    if data is None: return "-"
    if isinstance(data, dict): return str(list(data.values())[0])
    if isinstance(data, list): return "\n".join([str(x) for x in data])
    return str(data)

def clean_text_for_pdf(text):
    text = safe_str(text)
    replacements = {'\u2013': '-', '\u2014': '-', '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2022': '-', '\u2026': '...'}
    for k, v in replacements.items(): text = text.replace(k, v)
    return text.encode('latin-1', 'replace').decode('latin-1')

# ==========================================
# 5. ENGINE AI (DENGAN FALLBACK)
# ==========================================
def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, ket_info=""):
    if not FINAL_API_KEY:
        st.error("⚠️ API Key tidak ditemukan! Masukkan di Secrets.")
        return None

    genai.configure(api_key=FINAL_API_KEY)
    
    # STRATEGI MODEL: Coba Flash dulu, kalau error coba Pro
    models_to_try = ['gemini-1.5-flash', 'gemini-pro']
    
    prompt = f"""
    Role: Pendamping PKH. Buat JSON Laporan.
    DATA: RHK: {topik}, Kegiatan: {detail}, Lokasi: {lokasi_lengkap}, Bulan: {bulan}, Note: {ket_info}
    Output JSON Wajib (lowercase): {{ "gambaran_umum": "...", "maksud_tujuan": "...", "ruang_lingkup": "...", "dasar_hukum": ["..."], "kegiatan": ["..."], "hasil": ["..."], "kesimpulan": "...", "saran": ["..."], "penutup": "..." }}
    """

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            import json
            return json.loads(response.text.replace("```json", "").replace("```", "").strip())
        except Exception as e:
            continue # Coba model berikutnya jika gagal
            
    st.error("❌ Gagal generate dengan semua model AI. Cek kuota API atau koneksi.")
    return None

def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        doc = Document()
        style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        
        if kop: 
            try: doc.add_picture(io.BytesIO(kop), width=Inches(6.2))
            except: pass
        
        doc.add_paragraph(f"\nLAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}").alignment = 1
        doc.add_paragraph(" ")

        def add_item(title, content, is_list=False):
            doc.add_paragraph(title, style='Heading 2')
            if is_list and isinstance(content, list):
                for item in content: doc.add_paragraph(f"- {safe_str(item)}")
            else:
                doc.add_paragraph(safe_str(content)).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        doc.add_paragraph("A. Pendahuluan", style='Heading 1')
        add_item("1. Gambaran Umum", data.get('gambaran_umum'))
        add_item("2. Maksud dan Tujuan", data.get('maksud_tujuan'))
        add_item("3. Ruang Lingkup", data.get('ruang_lingkup'))
        add_item("4. Dasar Hukum", data.get('dasar_hukum'), True)

        doc.add_paragraph("B. Pelaksanaan", style='Heading 1')
        add_item("Uraian Kegiatan", data.get('kegiatan'), True)

        doc.add_paragraph("C. Hasil", style='Heading 1')
        if kpm_data: doc.add_paragraph(f"KPM: {kpm_data.get('Nama')}")
        add_item("Hasil Capaian", data.get('hasil'), True)

        doc.add_paragraph("D. Penutup", style='Heading 1')
        add_item("Kesimpulan", data.get('kesimpulan'))
        add_item("Saran", data.get('saran'), True)
        add_item("Penutup", data.get('penutup'))

        p = doc.add_paragraph(f"\n\nDibuat di {meta['kab']}\nTanggal {meta['tgl']}\nPendamping PKH\n")
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if ttd: 
            try: p.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
            except: pass
        p.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}")

        bio = io.BytesIO(); doc.save(bio); return bio
    except Exception as e:
        return None

def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        pdf = FPDF(); pdf.set_margins(25, 20, 25); pdf.add_page(); pdf.set_font("Times", size=12)
        
        if kop:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pth=tmp.name
                pdf.image(pth, x=10, y=10, w=190); os.unlink(pth)
            except: pass
        
        pdf.ln(30); pdf.set_font("Times", "B", 14)
        pdf.multi_cell(0, 6, f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}", align='C'); pdf.ln(10)
        
        pdf.set_font("Times", "", 12)
        def add_sec(title, body):
            pdf.set_font("Times", "B", 12); pdf.cell(0, 8, title, ln=True); pdf.set_font("Times", "", 12)
            if isinstance(body, list):
                for x in body: pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(x)}")
            else: pdf.multi_cell(0, 6, clean_text_for_pdf(body))
            pdf.ln(2)

        add_sec("A. Pendahuluan", data.get('gambaran_umum'))
        add_sec("B. Pelaksanaan", data.get('kegiatan'))
        add_sec("C. Hasil", data.get('hasil'))
        add_sec("D. Penutup", data.get('penutup'))

        pdf.ln(10); start_x = 110; pdf.set_x(start_x)
        pdf.multi_cell(80, 5, f"Dibuat di {meta['kab']}\nTanggal {meta['tgl']}\nPendamping PKH", align='C')
        pdf.ln(20)
        pdf.set_x(start_x); pdf.multi_cell(80, 5, f"{meta['nama']}\nNIP. {meta['nip']}", align='C')
        
        return pdf.output(dest='S').encode('latin-1')
    except: return None

# ==========================================
# 6. UI UTAMA (MAIN APP)
# ==========================================
def main():
    # --- CEK LOGIN ---
    if not st.session_state['password_correct']:
        st.markdown("<h2 style='text-align: center;'>🔐 Login Aplikasi RHK</h2>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.button("Masuk", use_container_width=True):
                if u in DAFTAR_USER and DAFTAR_USER[u] == p:
                    st.session_state['password_correct'] = True
                    st.session_state['username'] = u
                    st.rerun()
                else: st.error("Username/Password Salah")
        return

    # --- JIKA SUDAH LOGIN ---
    init_db()
    with st.sidebar:
        st.write(f"Halo, **{st.session_state.get('username')}**")
        if st.button("Logout"):
            st.session_state['password_correct'] = False
            st.rerun()
        st.divider()
        
        # PROFIL INPUT
        u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
        nama = st.text_input("Nama", u_nama)
        nip = st.text_input("NIP", u_nip)
        kpm = st.number_input("KPM", value=u_kpm)
        prov = st.text_input("Provinsi", u_prov)
        kab = st.text_input("Kabupaten", u_kab)
        kec = st.text_input("Kecamatan", u_kec)
        kel = st.text_input("Kelurahan", u_kel)
        
        c1, c2 = st.columns(2)
        with c1: st.session_state['th_val'] = st.selectbox("Tahun", ["2026", "2027"])
        with c2: st.session_state['bln_val'] = st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"])
        
        st.session_state['tgl_val'] = st.text_input("Tgl Surat", st.session_state['tgl_val'])
        
        k = st.file_uploader("Kop Surat", type=['png','jpg'])
        if k: st.session_state['kop_bytes'] = k.getvalue()
        
        t = st.file_uploader("TTD", type=['png','jpg'])
        if t: st.session_state['ttd_bytes'] = t.getvalue()
        
        if st.button("Simpan Profil"):
            save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
            st.success("Tersimpan!")

    # --- KONTEN UTAMA ---
    if st.session_state['page'] == 'home':
        st.title("📂 Menu Utama")
        CONFIG_LAPORAN = {
            "RHK 1": "Penyaluran Bantuan", "RHK 2": "P2K2 (FDS)", "RHK 3": "Graduasi", 
            "RHK 4": "Pemutakhiran", "RHK 5": "Data KPM", "RHK 6": "Kasus", "RHK 7": "Direktif"
        }
        cols = st.columns(4)
        for i, (k, v) in enumerate(CONFIG_LAPORAN.items()):
            with cols[i % 4]:
                if st.button(f"{k}\n{v}", use_container_width=True):
                    st.session_state['selected_rhk'] = f"{k} – {v}"
                    st.session_state['page'] = 'detail'
                    st.rerun()

    elif st.session_state['page'] == 'detail':
        rhk = st.session_state['selected_rhk']
        if st.button("🏠 Kembali ke Menu"):
            st.session_state['page'] = 'home'
            st.rerun()
            
        st.subheader(f"Formulir: {rhk}")
        judul = st.text_input("Judul Laporan", value=f"Laporan {rhk}")
        ket = st.text_area("Keterangan Kegiatan", height=100)
        
        if st.button("🚀 GENERATE LAPORAN", type="primary"):
            if not FINAL_API_KEY:
                st.error("API Key belum disetting di Secrets!")
            else:
                with st.spinner("Sedang membuat laporan dengan AI..."):
                    # PREPARE META
                    meta = {
                        'judul': judul, 'bulan': f"{st.session_state['bln_val']} {st.session_state['th_val']}",
                        'nama': nama, 'nip': nip, 'kab': kab, 'tgl': st.session_state['tgl_val']
                    }
                    loc = f"Desa {kel}, Kec {kec}, Kab {kab}"
                    
                    # GENERATE CONTENT
                    data = generate_isi_laporan(rhk, judul, kpm, "Peserta", meta['bulan'], loc, ket_info=ket)
                    
                    if data:
                        w = create_word_doc(data, meta, [], st.session_state['kop_bytes'], st.session_state['ttd_bytes'])
                        p = create_pdf_doc(data, meta, [], st.session_state['kop_bytes'], st.session_state['ttd_bytes'])
                        st.session_state['generated_file_data'] = {'w': w, 'p': p}
                        st.success("Selesai!")
        
        if st.session_state['generated_file_data']:
            files = st.session_state['generated_file_data']
            c1, c2 = st.columns(2)
            c1.download_button("Download Word", files['w'], "Laporan.docx")
            c2.download_button("Download PDF", files['p'], "Laporan.pdf")

if __name__ == "__main__":
    main()
