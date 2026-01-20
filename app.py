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

# ==========================================
# 1. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="Aplikasi RHK PKH Pro", layout="wide")

# --- INISIALISASI STATE (Mencegah KeyError/NameError) ---
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
# 2. FUNGSI-FUNGSI (GLOBAL)
# ==========================================
def get_api_key():
    """Mendeteksi API Key dari Secrets (Prioritas)"""
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_API_KEY"]
    except:
        pass
    # Cek Environment Variable (Cadangan)
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY")
    return None

FINAL_API_KEY = get_api_key()

def init_db():
    conn = sqlite3.connect('riwayat_v50.db')
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
        conn = sqlite3.connect('riwayat_v50.db')
        c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone()
        conn.close()
        return data if data else ("User", "-", 0, "-", "-", "-", "-")
    except: return ("User", "-", 0, "-", "-", "-", "-")

def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
    conn = sqlite3.connect('riwayat_v50.db')
    c = conn.cursor()
    c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
    conn.commit(); conn.close()

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

def reset_states():
    st.session_state['rhk2_queue'] = []
    st.session_state['rhk4_queue'] = []
    st.session_state['rhk7_queue'] = []
    st.session_state['generated_file_data'] = None
    st.session_state['rhk3_results'] = None
    st.session_state['rhk2_results'] = []
    st.session_state['rhk4_results'] = []
    st.session_state['rhk7_results'] = []

def update_tanggal_surat():
    day = "28" if st.session_state['bln_val'] == "FEBRUARI" else "30"
    st.session_state['tgl_val'] = f"{day} {st.session_state['bln_val'].title()} {st.session_state['th_val']}"

# --- ENGINE AI ---
def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, ket_info=""):
    if not FINAL_API_KEY:
        st.error("⚠️ API Key tidak ditemukan! Harap isi di Secrets.")
        return None

    try:
        genai.configure(api_key=FINAL_API_KEY)
        # Prioritas Model: Flash Latest -> 1.5 Flash -> Pro
        models_to_try = ['gemini-flash-latest', 'gemini-1.5-flash', 'gemini-pro']
        
        prompt = f"""
        Role: Pendamping PKH Profesional.
        Buat JSON Laporan Kegiatan.
        KONTEKS: RHK: {topik} | Nama Kegiatan: {detail} | Lokasi: {lokasi_lengkap} | Periode: {bulan}
        CATATAN USER: {ket_info}
        
        Output JSON Wajib (lowercase key):
        {{
            "gambaran_umum": "Paragraf panjang kondisi umum wilayah dan KPM...",
            "maksud_tujuan": "Paragraf gabungan maksud dan tujuan...",
            "ruang_lingkup": "Jelaskan ruang lingkup...",
            "dasar_hukum": ["Permensos No. 1 Tahun 2018", "Pedoman Umum PKH 2021"],
            "kegiatan": ["Uraian kegiatan detail...", "Detail tentang {ket_info}..."],
            "hasil": ["Hasil 1...", "Hasil 2..."],
            "kesimpulan": "Paragraf kesimpulan...",
            "saran": ["Saran 1...", "Saran 2..."],
            "penutup": "Kalimat penutup formal..."
        }}
        """
        
        response_text = None
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                response_text = response.text
                break
            except: continue
        
        if not response_text:
            st.error("❌ Gagal Generate (Model Busy/Quota Exceeded). Coba lagi nanti.")
            return None

        import json
        return json.loads(response_text.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        st.error(f"Error System: {str(e)}")
        return None

def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        doc = Document()
        style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        if kop: 
            try: p = doc.add_paragraph(); p.alignment = 1; p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
            except: pass
        doc.add_paragraph(" "); p = doc.add_paragraph(); p.alignment = 1
        p.add_run(f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}").bold = True
        doc.add_paragraph(" ")

        def add_item(title, content):
            doc.add_paragraph(title, style='Heading 1')
            if isinstance(content, list):
                for x in content: doc.add_paragraph(f"- {safe_str(x)}")
            else: doc.add_paragraph(safe_str(content)).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        add_item("A. Pendahuluan", data.get('gambaran_umum'))
        add_item("B. Pelaksanaan", data.get('kegiatan'))
        if kpm_data: doc.add_paragraph(f"Nama KPM: {kpm_data.get('Nama')}")
        add_item("C. Hasil", data.get('hasil'))
        add_item("D. Penutup", data.get('penutup'))

        p = doc.add_paragraph(f"\n\nDibuat di {meta['kab']}\nTanggal {meta['tgl']}\nPendamping PKH\n"); p.alignment = 1
        if ttd:
            try: p.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
            except: p.add_run("\n\n\n")
        else: p.add_run("\n\n\n")
        p.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}").bold = True
        
        bio = io.BytesIO(); doc.save(bio); return bio
    except: return None

def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        pdf = FPDF(); pdf.set_margins(25, 20, 25); pdf.add_page(); pdf.set_font("Times", size=12)
        if kop:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pth=tmp.name
                pdf.image(pth, x=10, y=10, w=190); os.unlink(pth)
            except: pdf.ln(10)
        else: pdf.ln(10)
        
        pdf.set_font("Times", "B", 14); pdf.multi_cell(0, 6, f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}", align='C'); pdf.ln(10)
        
        def add_sec(title, body):
            pdf.set_font("Times", "B", 12); pdf.cell(0, 8, title, ln=True); pdf.set_font("Times", "", 12)
            if isinstance(body, list): 
                for x in body: pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(x)}")
            else: pdf.multi_cell(0, 6, clean_text_for_pdf(body), align='J')
            pdf.ln(2)

        add_sec("A. Pendahuluan", data.get('gambaran_umum'))
        add_sec("B. Pelaksanaan", data.get('kegiatan'))
        if kpm_data: pdf.cell(0, 6, f"Nama KPM: {kpm_data.get('Nama')}", ln=True)
        add_sec("C. Hasil", data.get('hasil'))
        add_sec("D. Penutup", data.get('penutup'))

        pdf.ln(10); x_start = 120; pdf.set_x(x_start)
        pdf.multi_cell(0, 5, f"Dibuat di {meta['kab']}\nTanggal {meta['tgl']}\nPendamping PKH", align='C'); pdf.ln(20)
        pdf.set_x(x_start); pdf.multi_cell(0, 5, f"{meta['nama']}\nNIP. {meta['nip']}", align='C')
        return pdf.output(dest='S').encode('latin-1')
    except: return None

# ==========================================
# 5. UI UTAMA (LOGIN & MAIN)
# ==========================================
def main_app():
    # DAFTAR USER (Ambil dari Secrets jika ada)
    try:
        if "users" in st.secrets: USERS = st.secrets["users"]
        else: USERS = {"admin": "admin123", "pendamping": "pkh2026"}
    except: USERS = {"admin": "admin123", "pendamping": "pkh2026"}

    # --- LOGIN LOGIC (Anti-Duplicate ID) ---
    if not st.session_state['password_correct']:
        st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.button("MASUK", type="primary", use_container_width=True):
                if u in USERS and USERS[u] == p:
                    st.session_state['password_correct'] = True
                    st.session_state['username'] = u
                    st.rerun()
                else: st.error("Username/Password Salah")
        return # STOP DISINI JIKA BELUM LOGIN

    # --- APLIKASI UTAMA (Hanya jalan jika sudah login) ---
    init_db()
    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()

    with st.sidebar:
        st.write(f"👤 Login: **{st.session_state['username']}**")
        if st.button("🔒 Logout"):
            st.session_state['password_correct'] = False
            st.rerun()
        
        st.divider()
        st.header("Profil Pendamping")
        nama = st.text_input("Nama", u_nama)
        nip = st.text_input("NIP", u_nip)
        kpm = st.number_input("KPM", value=u_kpm)
        prov = st.text_input("Provinsi", u_prov)
        kab = st.text_input("Kabupaten", u_kab)
        kec = st.text_input("Kecamatan", u_kec)
        kel = st.text_input("Kelurahan", u_kel)
        
        c1, c2 = st.columns(2)
        with c1: st.session_state['th_val'] = st.selectbox("Tahun", ["2026", "2027"])
        with c2: st.session_state['bln_val'] = st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], on_change=update_tanggal_surat)
        
        st.session_state['tgl_val'] = st.text_input("Tgl Surat", st.session_state['tgl_val'])
        
        k = st.file_uploader("Kop Surat", type=['png','jpg'])
        if k: st.session_state['kop_bytes'] = k.getvalue()
        t = st.file_uploader("TTD", type=['png','jpg'])
        if t: st.session_state['ttd_bytes'] = t.getvalue()
        
        if st.button("Simpan Profil"):
            save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
            st.success("Tersimpan!")

    # --- ROUTING HALAMAN ---
    if st.session_state['page'] == 'home':
        st.title("📂 Menu Utama RHK")
        CONFIG = {
            "RHK 1": "Penyaluran Bantuan", "RHK 2": "P2K2 (FDS)", "RHK 3": "Graduasi Mandiri", 
            "RHK 4": "Pemutakhiran Data", "RHK 5": "Verifikasi KPM", "RHK 6": "Case Management", "RHK 7": "Tugas Direktif"
        }
        cols = st.columns(4)
        for i, (k, v) in enumerate(CONFIG.items()):
            with cols[i % 4]:
                if st.button(f"{k}\n{v}", use_container_width=True, key=f"menu_{i}"):
                    st.session_state['selected_rhk'] = f"{k} – {v}"
                    st.session_state['page'] = 'detail'
                    reset_states()
                    st.rerun()
        st.markdown("---")
        st.caption("Copyright © 2026 VHS | All Rights Reserved")

    elif st.session_state['page'] == 'detail':
        rhk = st.session_state['selected_rhk']
        if st.button("🏠 Kembali"):
            st.session_state['page'] = 'home'
            st.rerun()
        
        st.subheader(f"Formulir: {rhk}")
        judul = st.text_input("Judul Laporan", value=f"Laporan {rhk}")
        
        # --- KHUSUS RHK 3 (GRADUASI) ---
        if "RHK 3" in rhk:
            st.info("ℹ️ Silakan download template Excel di bawah ini, isi data KPM, lalu upload kembali.")
            
            # FITUR DOWNLOAD TEMPLATE EXCEL
            sample_data = pd.DataFrame([
                {"Nama": "Siti Aminah", "NIK": "1234567890", "Alamat": "Dusun Melati", "Kategori": "PKH Murni", "Status": "Graduasi Sejahtera", "Alasan": "Sudah Mampu"}
            ])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                sample_data.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Download Template Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name="Template_Graduasi.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            upl = st.file_uploader("Upload Data KPM (Excel/CSV)", type=['xlsx', 'csv'])
            if upl:
                try:
                    df = pd.read_excel(upl) if upl.name.endswith('.xlsx') else pd.read_csv(upl)
                    df.insert(0, "Pilih", False)
                    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                    if st.button("Simpan Pilihan"):
                        st.session_state['graduasi_fix'] = edited[edited['Pilih']==True].to_dict('records')
                        st.success("Data Tersimpan!")
                except: st.error("Format file salah.")

        ket = st.text_area("Keterangan Tambahan (Opsional):", height=100)
        
        if st.button("🚀 GENERATE LAPORAN", type="primary"):
            kpms = st.session_state.get('graduasi_fix', []) if "RHK 3" in rhk else [None]
            
            if "RHK 3" in rhk and not kpms:
                st.error("Pilih data KPM dulu!")
            else:
                progress = st.progress(0); status = st.empty()
                results_w = []; results_p = []
                
                for i, kpm_item in enumerate(kpms):
                    target_name = kpm_item['Nama'] if kpm_item else "Kegiatan"
                    status.info(f"⏳ Sedang memproses: **{target_name}**... (Mohon tunggu)")
                    time.sleep(2) # DELAY AGAR TIDAK SPAM
                    
                    meta = {
                        'judul': judul, 'bulan': f"{st.session_state['bln_val']} {st.session_state['th_val']}",
                        'nama': nama, 'nip': nip, 'kab': kab, 'tgl': st.session_state['tgl_val']
                    }
                    loc = f"Desa {kel}, Kec {kec}, Kab {kab}"
                    
                    data = generate_isi_laporan(rhk, judul, kpm, "Peserta", meta['bulan'], loc, ket_info=ket)
                    
                    if data:
                        w = create_word_doc(data, meta, [], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], kpm_data=kpm_item)
                        p = create_pdf_doc(data, meta, [], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], kpm_data=kpm_item)
                        if "RHK 3" in rhk:
                            # Jika banyak file (Graduasi), simpan di list dulu (belum implementasi zip disini agar simple)
                            st.session_state['generated_file_data'] = {'w': w, 'p': p} 
                        else:
                            st.session_state['generated_file_data'] = {'w': w, 'p': p}
                    
                    progress.progress((i+1)/len(kpms))
                
                status.success("✅ Selesai!")
        
        if st.session_state['generated_file_data']:
            files = st.session_state['generated_file_data']
            c1, c2 = st.columns(2)
            c1.download_button("Download Word", files['w'], "Laporan.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            c2.download_button("Download PDF", files['p'], "Laporan.pdf", "application/pdf")

# ==========================================
# 6. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    main_app()
