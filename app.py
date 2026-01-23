import streamlit as st
import google.generativeai as genai
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
import io
import pandas as pd
import sqlite3
import zipfile
from datetime import datetime
import time
import os
from PIL import Image
import tempfile
import json
import re

# ==========================================
# 1. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="Aplikasi RHK PKH Pro", layout="wide")

# --- INISIALISASI STATE (Mencegah KeyError) ---
if 'init_done' not in st.session_state:
    st.session_state['init_done'] = True
    st.session_state['page'] = 'home'
    st.session_state['selected_rhk'] = None
    st.session_state['rhk2_queue'] = []
    st.session_state['rhk4_queue'] = []
    st.session_state['rhk7_queue'] = []
    st.session_state['generated_file_data'] = None
    st.session_state['rhk3_results'] = None
    st.session_state['rhk2_results'] = []
    st.session_state['rhk4_results'] = []
    st.session_state['rhk7_results'] = []
    st.session_state['bln_val'] = "JANUARI"
    st.session_state['th_val'] = "2026"
    st.session_state['tgl_val'] = "30 Januari 2026"
    st.session_state['kop_bytes'] = None
    st.session_state['ttd_bytes'] = None
    st.session_state['graduasi_raw'] = None
    st.session_state['graduasi_fix'] = None
    st.session_state['password_correct'] = False
    st.session_state['username'] = ""

# ==========================================
# 2. LOGIKA API KEY & DATABASE
# ==========================================
def get_api_key():
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_API_KEY"]
    except: pass
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY")
    return "MASUKKAN_KEY_JIKA_DI_LOCAL"

FINAL_API_KEY = get_api_key()

# USER LOGIN
try:
    if "users" in st.secrets: DAFTAR_USER = st.secrets["users"]
    else: DAFTAR_USER = {"admin": "admin123", "pendamping": "pkh2026", "user": "user"}
except: DAFTAR_USER = {"admin": "admin123", "pendamping": "pkh2026", "user": "user"}

CONFIG_LAPORAN = {
    "RHK 1 – LAPORAN PENYALURAN": ["Laporan Penyaluran Bantuan Sosial"],
    "RHK 2 – LAPORAN P2K2 (FDS)": ["Modul Ekonomi", "Modul Kesehatan", "Modul Pengasuhan", "Modul Perlindungan", "Modul Kesejahteraan"],
    "RHK 3 – TARGET GRADUASI MANDIRI": ["Laporan Graduasi Mandiri"], 
    "RHK 4 – KEGIATAN PEMUTAKHIRAN": ["Verifikasi Pendidikan", "Verifikasi Kesehatan", "Verifikasi Kesos"],
    "RHK 5 – KPM YANG DIMUTAKHIRKAN": ["Laporan Hasil Pemutakhiran"],
    "RHK 6 – LAPORAN KASUS ADAPTIF": ["Laporan Case Management"],
    "RHK 7 – LAPORAN DIREKTIF": ["Tugas Direktif Pimpinan"]
}

def init_db():
    conn = sqlite3.connect('riwayat_v53.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS riwayat (id INTEGER PRIMARY KEY, tgl TEXT, rhk TEXT, judul TEXT, lokasi TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
    c.execute('SELECT count(*) FROM user_settings')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO user_settings (id, nama, nip, kpm, prov, kab, kec, kel) VALUES (1, ?, ?, ?, ?, ?, ?, ?)', ("User Demo", "123456", 100, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan"))
    conn.commit(); conn.close()

def get_user_settings():
    try:
        conn = sqlite3.connect('riwayat_v53.db'); c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone(); conn.close(); return data if data else ("User", "-", 0, "-", "-", "-", "-")
    except: return ("User", "-", 0, "-", "-", "-", "-")

def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
    conn = sqlite3.connect('riwayat_v53.db'); c = conn.cursor()
    c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
    conn.commit(); conn.close()

def simpan_riwayat(rhk, judul, lokasi):
    try:
        conn = sqlite3.connect('riwayat_v53.db'); c = conn.cursor()
        tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute('INSERT INTO riwayat (tgl, rhk, judul, lokasi) VALUES (?, ?, ?, ?)', (tgl, rhk, judul, lokasi))
        conn.commit(); conn.close()
    except: pass

# ==========================================
# 3. FUNGSI PENDUKUNG (GAMBAR & DOC)
# ==========================================
def compress_image(uploaded_file):
    try:
        uploaded_file.seek(0); image = Image.open(uploaded_file)
        if image.mode in ("RGBA", "P"): image = image.convert("RGB")
        image.thumbnail((800, 800)); output = io.BytesIO()
        image.save(output, format="JPEG", quality=70); output.seek(0)
        return output
    except: uploaded_file.seek(0); return uploaded_file 

def reset_states():
    for k in ['rhk2_queue','rhk4_queue','rhk7_queue','generated_file_data','rhk3_results']:
        st.session_state[k] = [] if 'queue' in k else None

def update_tanggal():
    d = "28" if st.session_state['bln_val'] == "FEBRUARI" else "30"
    st.session_state['tgl_val'] = f"{d} {st.session_state['bln_val'].title()} {st.session_state['th_val']}"

def get_archived_photos(rhk, periode): return [] # Placeholder
def load_photo_from_disk(rhk, periode, filename): return None # Placeholder
def auto_save_photo_local(f, rhk, periode): pass # Placeholder

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

# --- ENGINE AI ---
def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi, ket_info=""):
    if not FINAL_API_KEY: st.error("⚠️ API Key Kosong!"); return None
    try:
        genai.configure(api_key=FINAL_API_KEY)
        # Mencoba berbagai model untuk menghindari error 404
        models_to_try = ['gemini-flash-latest', 'gemini-1.5-flash', 'gemini-pro']
        
        prompt = f"""
        Role: Pendamping PKH. Buat JSON Laporan.
        DATA: RHK: {topik}, Kegiatan: {detail}, Lokasi: {lokasi}, Bulan: {bulan}, Info: {ket_info}
        Output JSON Wajib (lowercase keys): {{ "gambaran_umum": "...", "maksud_tujuan": "...", "ruang_lingkup": "...", "dasar_hukum": ["..."], "kegiatan": ["..."], "hasil": ["..."], "kesimpulan": "...", "saran": ["..."], "penutup": "..." }}
        """
        
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                res = model.generate_content(prompt)
                return json.loads(res.text.replace("```json", "").replace("```", "").strip())
            except: continue
            
        st.error("Gagal menghubungi semua model AI. Cek kuota API atau update requirements.txt.")
        return None
    except: return None

# --- DOC GENERATOR ---
def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        doc = Document(); style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        if kop: 
            try: doc.add_picture(io.BytesIO(kop), width=Inches(6.2))
            except: pass
        doc.add_paragraph(f"\nLAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}").alignment = 1
        
        def add_item(t, c):
            doc.add_paragraph(t, style='Heading 1')
            if isinstance(c, list): 
                for x in c: doc.add_paragraph(f"- {str(x)}")
            else: doc.add_paragraph(str(c)).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            
        add_item("A. Pendahuluan", data.get('gambaran_umum', '-'))
        add_item("B. Pelaksanaan", data.get('kegiatan', '-'))
        if kpm_data: doc.add_paragraph(f"Nama KPM: {kpm_data.get('Nama', '-')}")
        add_item("C. Hasil", data.get('hasil', '-'))
        add_item("D. Penutup", data.get('penutup', '-'))
        
        p = doc.add_paragraph(f"\n\nDibuat di {meta['kab']}\nTanggal {meta['tgl']}\nPendamping PKH\n"); p.alignment = 1
        if ttd: 
            try: p.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
            except: p.add_run("\n\n\n")
        else: p.add_run("\n\n\n")
        p.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}").bold = True
        
        # Foto
        if imgs:
            doc.add_page_break()
            doc.add_paragraph("LAMPIRAN DOKUMENTASI").alignment = 1
            for i, img_data in enumerate(imgs):
                try: 
                    img_data.seek(0)
                    doc.add_picture(img_data, width=Inches(3.0))
                except: pass

        bio = io.BytesIO(); doc.save(bio); return bio
    except: return None

def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Times", size=12)
        if kop:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pth=tmp.name
                pdf.image(pth, x=10, y=10, w=190); os.unlink(pth)
            except: pdf.ln(10)
        else: pdf.ln(10)
        
        pdf.set_font("Times", "B", 14); pdf.multi_cell(0, 6, f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}", align='C'); pdf.ln(10)
        
        pdf.set_font("Times", "", 12)
        def add_sec(t, c):
            pdf.set_font("Times", "B", 12); pdf.cell(0, 8, t, ln=True); pdf.set_font("Times", "", 12)
            val = "\n".join([f"- {x}" for x in c]) if isinstance(c, list) else str(c)
            pdf.multi_cell(0, 6, val.encode('latin-1', 'replace').decode('latin-1'), align='J'); pdf.ln(2)

        add_sec("A. Pendahuluan", data.get('gambaran_umum'))
        add_sec("B. Pelaksanaan", data.get('kegiatan'))
        if kpm_data: pdf.cell(0, 6, f"KPM: {kpm_data.get('Nama')}", ln=True)
        add_sec("C. Hasil", data.get('hasil'))
        add_sec("D. Penutup", data.get('penutup'))
        
        pdf.ln(10); start_x = 120; pdf.set_x(start_x)
        pdf.multi_cell(0, 5, f"Dibuat di {meta['kab']}\nTanggal {meta['tgl']}\nPendamping PKH", align='C'); pdf.ln(20)
        pdf.set_x(start_x); pdf.multi_cell(0, 5, f"{meta['nama']}\nNIP. {meta['nip']}", align='C')
        return pdf.output(dest='S').encode('latin-1')
    except: return None

# ==========================================
# 4. TAMPILAN UTAMA
# ==========================================
def check_password():
    if st.session_state.get("password_correct", False): return True
    st.markdown("<br><br><h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        u = st.text_input("Username"); p = st.text_input("Password", type="password")
        if st.button("MASUK / LOGIN", type="primary", use_container_width=True):
            if u in DAFTAR_USER and DAFTAR_USER[u] == p:
                st.session_state['password_correct'] = True; st.session_state['username'] = u; st.rerun()
            else: st.error("Login Gagal!")
    return False

def main_app():
    # --- LOGOUT ---
    with st.sidebar:
        st.write(f"👤 Login: **{st.session_state.get('username')}**")
        if st.button("🔒 Logout", type="secondary"):
            st.session_state["password_correct"] = False; st.rerun()

    init_db(); u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
    
    st.sidebar.header("👤 Profil")
    nama = st.sidebar.text_input("Nama", u_nama); nip = st.sidebar.text_input("NIP", u_nip)
    kpm = st.sidebar.number_input("KPM", value=u_kpm)
    
    st.sidebar.markdown("### 🌍 Wilayah")
    prov = st.sidebar.text_input("Provinsi", u_prov); kab = st.sidebar.text_input("Kabupaten", u_kab)
    kec = st.sidebar.text_input("Kecamatan", u_kec); kel = st.sidebar.text_input("Kelurahan", u_kel)
    
    st.sidebar.markdown("### 📅 Periode")
    c1, c2 = st.sidebar.columns([1, 1.5])
    with c1: st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal)
    with c2: st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], on_change=update_tanggal)
    
    st.sidebar.text_input("Tanggal Surat", key="tgl_val")
    st.sidebar.markdown("---")
    
    st.sidebar.header("🖼️ Atribut")
    k = st.sidebar.file_uploader("Kop Surat", type=['png','jpg']); t = st.sidebar.file_uploader("Tanda Tangan", type=['png','jpg'])
    if st.sidebar.button("💾 SIMPAN PROFIL"):
        save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
        if k: st.session_state['kop_bytes'] = k.getvalue()
        if t: st.session_state['ttd_bytes'] = t.getvalue()
        st.sidebar.success("Tersimpan!")

    # --- HOME PAGE ---
    if st.session_state['page'] == 'home':
        st.markdown(f"## 👋 Selamat Datang, {st.session_state['username']}!")
        st.markdown("### Menu Utama")
        
        cols = st.columns(4); rhk_keys = list(CONFIG_LAPORAN.keys())
        for i, rhk in enumerate(rhk_keys):
            icon = "📄"; parts = rhk.split("–"); label = f"{icon}\n{parts[0].strip()}\n{parts[-1].strip()}"
            with cols[i % 4]:
                if st.button(label, key=f"btn_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'; reset_states(); st.rerun()

    # --- DETAIL PAGE ---
    elif st.session_state['page'] == 'detail':
        rhk = st.session_state['selected_rhk']
        
        c_nav1, c_nav2 = st.columns([1, 6])
        if c_nav1.button("🏠 KEMBALI"): st.session_state['page'] = 'home'; st.rerun()
        c_nav2.markdown(f"### 📝 {rhk}")
        st.divider()
        
        judul = st.text_input("Judul Laporan", value=f"Laporan {rhk}")
        
        # --- FITUR KHUSUS RHK 3: DOWNLOAD EXCEL (Update) ---
        if "RHK 3" in rhk:
            st.info("ℹ️ Khusus Graduasi: Gunakan Template Excel di bawah ini.")
            
            # Buat Template Excel
            tpl = pd.DataFrame([{"Nama": "Contoh Nama", "NIK": "12345", "Alamat": "Desa X", "Status": "Graduasi", "Alasan": "Mampu"}])
            buf = io.BytesIO(); 
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: tpl.to_excel(w, index=False)
            
            c1, c2 = st.columns(2)
            c1.download_button("📥 Download Template Excel", buf.getvalue(), "Template_Graduasi.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
            upl = st.file_uploader("Upload Data Excel", type=['xlsx'])
            if upl:
                try: 
                    df = pd.read_excel(upl); df.insert(0, "Pilih", False)
                    ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                    if st.button("💾 Simpan Data Terpilih"):
                        st.session_state['graduasi_fix'] = ed[ed['Pilih']==True].to_dict('records'); st.success("Data Siap!")
                except: st.error("Format File Salah.")

        ket = st.text_area("Keterangan Tambahan (Opsional):", height=100)
        
        # FOTO MANAGER
        st.write("#### 📸 Dokumentasi")
        u_fotos = st.file_uploader("Upload Foto", type=['jpg','png'], accept_multiple_files=True)
        photos = [io.BytesIO(f.getvalue()) for f in u_fotos] if u_fotos else []

        if st.button("🚀 GENERATE SEKARANG", type="primary"):
            kpms = st.session_state.get('graduasi_fix', []) if "RHK 3" in rhk else [None]
            if "RHK 3" in rhk and not kpms: st.error("Pilih data KPM dulu!")
            else:
                prog = st.progress(0); info = st.empty()
                for i, kpm in enumerate(kpms):
                    nm = kpm['Nama'] if kpm else "Kegiatan"
                    info.info(f"⏳ Memproses: {nm}...")
                    time.sleep(2)
                    
                    meta = {'judul': judul, 'bulan': f"{st.session_state['bln_val']} {st.session_state['th_val']}", 'nama': nama, 'nip': nip, 'kab': kab, 'tgl': st.session_state['tgl_val']}
                    data = generate_isi_laporan(rhk, judul, kpm, "Peserta", meta['bulan'], f"{kel}, {kec}", ket_info=ket)
                    
                    if data:
                        w = create_word_doc(data, meta, photos, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], kpm_data=kpm)
                        p = create_pdf_doc(data, meta, photos, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], kpm_data=kpm)
                        st.session_state['generated_file_data'] = {'w': w, 'p': p}
                    
                    prog.progress((i+1)/len(kpms))
                st.success("Selesai!"); st.rerun()

        if st.session_state['generated_file_data']:
            f = st.session_state['generated_file_data']
            st.divider()
            c1, c2 = st.columns(2)
            c1.download_button("Download Word", f['w'], "Laporan.docx")
            c2.download_button("Download PDF", f['p'], "Laporan.pdf")

# ==========================================
# 5. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    if check_password(): main_app()
