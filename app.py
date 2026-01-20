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
# 1. KONFIGURASI & INISIALISASI
# ==========================================
st.set_page_config(page_title="Aplikasi RHK PKH Pro", layout="wide")

# --- INISIALISASI STATE ---
if 'page' not in st.session_state: st.session_state['page'] = 'home'
if 'selected_rhk' not in st.session_state: st.session_state['selected_rhk'] = None
if 'rhk2_queue' not in st.session_state: st.session_state['rhk2_queue'] = []
if 'rhk4_queue' not in st.session_state: st.session_state['rhk4_queue'] = []
if 'rhk7_queue' not in st.session_state: st.session_state['rhk7_queue'] = []
if 'generated_file_data' not in st.session_state: st.session_state['generated_file_data'] = None
if 'rhk3_results' not in st.session_state: st.session_state['rhk3_results'] = None
if 'rhk2_results' not in st.session_state: st.session_state['rhk2_results'] = []
if 'rhk4_results' not in st.session_state: st.session_state['rhk4_results'] = []
if 'rhk7_results' not in st.session_state: st.session_state['rhk7_results'] = []
if 'bln_val' not in st.session_state: st.session_state['bln_val'] = "JANUARI"
if 'th_val' not in st.session_state: st.session_state['th_val'] = "2026"
if 'tgl_val' not in st.session_state: st.session_state['tgl_val'] = "30 Januari 2026"
if 'kop_bytes' not in st.session_state: st.session_state['kop_bytes'] = None
if 'ttd_bytes' not in st.session_state: st.session_state['ttd_bytes'] = None
if 'db_kpm' not in st.session_state: st.session_state['db_kpm'] = None
if 'graduasi_raw' not in st.session_state: st.session_state['graduasi_raw'] = None
if 'graduasi_fix' not in st.session_state: st.session_state['graduasi_fix'] = None
if 'password_correct' not in st.session_state: st.session_state['password_correct'] = False

# ==========================================
# 2. LOGIKA API KEY (SAFE MODE)
# ==========================================
def get_api_key():
    if "GOOGLE_API_KEY" in st.secrets:
        return st.secrets["GOOGLE_API_KEY"]
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY")
    return "MASUKKAN_KEY_JIKA_DI_LOCAL_COMPUTER"

FINAL_API_KEY = get_api_key()

# ==========================================
# 3. DATABASE & USER CONFIG
# ==========================================
if "users" in st.secrets:
    DAFTAR_USER = st.secrets["users"]
else:
    DAFTAR_USER = {"admin": "admin123", "pendamping": "pkh2026", "user": "user"}

CONFIG_LAPORAN = {
    "RHK 1 – LAPORAN PENYALURAN": ["Laporan Penyaluran Bantuan Sosial"],
    "RHK 2 – LAPORAN P2K2 (FDS)": [
        "Modul Ekonomi 1: Mengelola Keuangan Keluarga", "Modul Ekonomi 2: Cermat Meminjam Dan Menabung", "Modul Ekonomi 3: Memulai Usaha",
        "Modul Kesehatan 1: Pentingnya Gizi Ibu Hamil", "Modul Kesehatan 2: Pentingnya Gizi Ibu Menyusui & Balita", "Modul Kesehatan 3: Kesakitan Anak & Kesling",
        "Modul Kesehatan 4: Permainan Anak", "Modul Kesejahteraan 1: Disabilitas Berat", "Modul Kesejahteraan 2: Kesejahteraan Lanjut Usia",
        "Modul Pengasuhan 1: Menjadi Orangtua Lebih Baik", "Modul Pengasuhan 2: Perilaku Anak", "Modul Pengasuhan 3: Cara Anak Usia Dini Belajar",
        "Modul Pengasuhan 4: Membantu Anak Sukses Sekolah", "Modul Perlindungan 1: Pencegahan Kekerasan Anak", "Modul Perlindungan 2: Penelantaran & Eksploitasi Anak"
    ],
    "RHK 3 – TARGET GRADUASI MANDIRI": ["Laporan Graduasi Mandiri"], 
    "RHK 4 – KEGIATAN PEMUTAKHIRAN": [
        "Verifikasi Fasilitas Pendidikan", 
        "Verifikasi Fasilitas Kesehatan", 
        "Verifikasi Kesejahteraan Sosial"
    ],
    "RHK 5 – KPM YANG DIMUTAKHIRKAN": ["Laporan Hasil Pemutakhiran Data KPM"],
    "RHK 6 – LAPORAN KASUS ADAPTIF": ["Laporan Penanganan Kasus (Case Management)"],
    "RHK 7 – LAPORAN DIREKTIF": ["Tugas Direktif Pimpinan (A)", "Tugas Direktif Pimpinan (B)"]
}

def init_db():
    conn = sqlite3.connect('riwayat_v49.db')
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
        conn = sqlite3.connect('riwayat_v49.db')
        c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone()
        conn.close()
        return data if data else ("User", "-", 0, "-", "-", "-", "-")
    except:
        return ("User", "-", 0, "-", "-", "-", "-")

def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
    conn = sqlite3.connect('riwayat_v49.db')
    c = conn.cursor()
    c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
    conn.commit(); conn.close()

def simpan_riwayat(rhk, judul, lokasi):
    try:
        conn = sqlite3.connect('riwayat_v49.db')
        c = conn.cursor()
        tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute('INSERT INTO riwayat (tgl, rhk, judul, lokasi) VALUES (?, ?, ?, ?)', (tgl, rhk, judul, lokasi))
        conn.commit(); conn.close()
    except: pass

# ==========================================
# 4. FUNGSI PENDUKUNG (GLOBAL)
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
    except Exception as e:
        uploaded_file.seek(0)
        return uploaded_file 

def get_folder_path(rhk_name, periode_str):
    try:
        if not periode_str or " " not in periode_str: b="UMUM"; t="2026"
        else: parts=periode_str.split(" "); b=parts[0]; t=parts[1]
    except: b="UMUM"; t="2026"
    clean_rhk = rhk_name.replace("–", "-").strip()
    return os.path.join(BASE_ARSIP, t, b, clean_rhk)

def count_archived_photos():
    total = 0
    if os.path.exists(BASE_ARSIP):
        for root, dirs, files in os.walk(BASE_ARSIP):
            total += len([f for f in files if f.lower().endswith(('.png','.jpg','.jpeg'))])
    return total

def auto_save_photo_local(uploaded_file_obj, rhk_name, periode_str):
    try:
        target_folder = get_folder_path(rhk_name, periode_str)
        if not os.path.exists(target_folder): os.makedirs(target_folder)
        compressed_bytes = compress_image(uploaded_file_obj)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = uploaded_file_obj.name.replace(" ", "_")
        final_name = f"{timestamp}_{clean_name}"
        with open(os.path.join(target_folder, final_name), "wb") as f:
            f.write(compressed_bytes.getvalue())
        return True
    except: return False

def get_archived_photos(rhk_name, periode_str):
    target_folder = get_folder_path(rhk_name, periode_str)
    if os.path.exists(target_folder):
        files = [f for f in os.listdir(target_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        files.sort(reverse=True)
        return files
    return []

def load_photo_from_disk(rhk_name, periode_str, filename):
    path = os.path.join(get_folder_path(rhk_name, periode_str), filename)
    with open(path, "rb") as f: return io.BytesIO(f.read())

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
    bln = st.session_state.get('bln_val', 'JANUARI')
    th = st.session_state.get('th_val', '2026')
    if bln is None: bln = "JANUARI"
    if th is None: th = "2026"
    day = "28" if bln == "FEBRUARI" else "30"
    st.session_state.tgl_val = f"{day} {bln.title()} {th}"

# ==========================================
# 5. GENERATOR DOKUMEN (AI: FLASH LATEST)
# ==========================================
def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, analisis="", app_info="", ket_info=""):
    if not FINAL_API_KEY or "MASUKKAN" in FINAL_API_KEY:
        st.error("⚠️ API Key Google tidak ditemukan di Secrets! Harap isi Secrets di Streamlit Cloud.")
        return None

    try:
        genai.configure(api_key=FINAL_API_KEY)
        # Prioritas Model: Flash Latest
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
        error_logs = []

        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                response_text = response.text
                break
            except Exception as e:
                error_logs.append(f"{model_name}: {str(e)}")
                continue
        
        if not response_text:
            st.error(f"❌ Gagal Generate. Detail Error:\n{error_logs}")
            return None

        import json
        return json.loads(response_text.replace("```json", "").replace("```", "").strip())
        
    except Exception as e:
        st.error(f"Error Sistem: {str(e)}")
        return None

def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        doc = Document()
        for s in doc.sections: s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
        style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        
        if kop: 
            try:
                p = doc.add_paragraph(); p.alignment = 1
                p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
            except: pass
        
        doc.add_paragraph(" ")
        p = doc.add_paragraph(); p.alignment = 1
        run = p.add_run(f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}")
        run.bold = True; run.font.size = Pt(14)
        doc.add_paragraph(" ")

        def add_p_indent(text, bold=False):
            safe_text = safe_str(text); paragraphs = safe_text.split('\n')
            for p_text in paragraphs:
                if p_text.strip():
                    p = doc.add_paragraph(); p.paragraph_format.first_line_indent = Cm(1.27)
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    run = p.add_run(p_text.strip())
                    if bold: run.bold = True

        def add_numbered_item(number, text):
            p = doc.add_paragraph(); p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.first_line_indent = Cm(-0.75)
            p.add_run(f"{number}.\t{safe_str(text)}") 

        doc.add_paragraph("A. Pendahuluan", style='Heading 1')
        doc.add_paragraph("1. Gambaran Umum", style='Heading 2')
        add_p_indent(f"Lokasi Pelaksanaan: Kelurahan {meta['kel']}, Kecamatan {meta['kec']}, {meta['kab']}, {meta['prov']}.")
        add_p_indent(data.get('gambaran_umum'))
        
        doc.add_paragraph("2. Maksud dan Tujuan", style='Heading 2')
        add_p_indent(data.get('maksud_tujuan'))
        
        doc.add_paragraph("3. Ruang Lingkup", style='Heading 2')
        add_p_indent(data.get('ruang_lingkup'))
        
        doc.add_paragraph("4. Dasar", style='Heading 2')
        for i, item in enumerate(data.get('dasar_hukum', []), 1): add_numbered_item(i, item)

        doc.add_paragraph("B. Kegiatan yang dilaksanakan", style='Heading 1')
        if extra_info and extra_info.get('desc'):
            p = doc.add_paragraph(f"Fokus: {extra_info['desc']}"); p.runs[0].italic = True
        for item in data.get('kegiatan', []):
            add_p_indent(safe_str(item).replace('\n', ' '))

        doc.add_paragraph("C. Hasil yang dicapai", style='Heading 1')
        if kpm_data and isinstance(kpm_data, dict):
            doc.add_paragraph(f"Profil KPM: {kpm_data.get('Nama')} (NIK: {kpm_data.get('NIK')})")
        for i, item in enumerate(data.get('hasil', []), 1): add_numbered_item(i, item)

        doc.add_paragraph("D. Kesimpulan dan Saran", style='Heading 1')
        add_p_indent(data.get('kesimpulan'))
        doc.add_paragraph("Adapun saran kami:")
        for item in data.get('saran', []): p = doc.add_paragraph(f"- {safe_str(item)}"); p.paragraph_format.left_indent = Cm(1.0)

        doc.add_paragraph("E. Penutup", style='Heading 1')
        add_p_indent(data.get('penutup'))
        doc.add_paragraph(" "); doc.add_paragraph(" ")

        table = doc.add_table(rows=1, cols=2); table.autofit = False
        table.columns[0].width = Inches(3.5); table.columns[1].width = Inches(3.0)
        cell_kanan = table.cell(0, 1); p_ttd = cell_kanan.paragraphs[0]; p_ttd.alignment = 1
        p_ttd.add_run(f"Dibuat di {meta['kab']}\nPada Tanggal {meta['tgl']}\nPendamping PKH\n")
        if ttd: 
            try: p_ttd.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8)); p_ttd.add_run("\n")
            except: p_ttd.add_run("\n\n\n")
        else: p_ttd.add_run("\n\n\n")
        p_ttd.add_run(f"\n{meta['nama']}\n").bold = True; p_ttd.add_run(f"NIP. {meta['nip']}")

        doc.add_page_break()
        p_lamp = doc.add_paragraph("LAMPIRAN DOKUMENTASI"); p_lamp.alignment = 1; p_lamp.runs[0].bold = True
        if imgs:
            tbl_img = doc.add_table(rows=(len(imgs)+1)//2, cols=2); tbl_img.autofit = True
            for i, img_data in enumerate(imgs):
                try:
                    cell = tbl_img.cell(i//2, i%2); p_img = cell.paragraphs[0]; p_img.alignment = 1
                    img_data.seek(0); img_comp = compress_image(img_data)
                    p_img.add_run().add_picture(img_comp, width=Inches(2.8))
                    p_img.add_run(f"\n{meta['judul']} - Foto {i+1}")
                except: pass
        bio = io.BytesIO(); doc.save(bio); return bio
    except Exception as e:
        return None

def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    try:
        pdf = FPDF(); pdf.set_margins(25, 20, 25); pdf.add_page(); pdf.set_font("Times", size=12)
        def J_indent(txt): pdf.multi_cell(0, 6, "       " + clean_text_for_pdf(txt), align='J')
        def TXT(s): return clean_text_for_pdf(s)

        if kop:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pth=tmp.name
                pdf.image(pth, x=10, y=10, w=190); os.unlink(pth); pdf.ln(35)
            except: pdf.ln(10)
        else: pdf.ln(10)

        pdf.set_font("Times", "B", 14)
        pdf.cell(0, 6, "LAPORAN", ln=True, align='C')
        pdf.cell(0, 6, "TENTANG", ln=True, align='C')
        pdf.cell(0, 6, TXT(meta['judul'].upper()), ln=True, align='C')
        pdf.cell(0, 6, TXT(meta['bulan'].upper()), ln=True, align='C'); pdf.ln(10)

        pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "A. Pendahuluan", ln=True)
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "1. Gambaran Umum", ln=True); pdf.set_font("Times", "", 12)
        J_indent(f"Lokasi Pelaksanaan: Kelurahan {meta['kel']}, Kecamatan {meta['kec']}, {meta['kab']}, {meta['prov']}.")
        J_indent(safe_str(data.get('gambaran_umum')))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "2. Maksud dan Tujuan", ln=True); pdf.set_font("Times", "", 12)
        J_indent(safe_str(data.get('maksud_tujuan')))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "3. Ruang Lingkup", ln=True); pdf.set_font("Times", "", 12)
        J_indent(safe_str(data.get('ruang_lingkup')))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "4. Dasar", ln=True); pdf.set_font("Times", "", 12)
        for i, item in enumerate(data.get('dasar_hukum', []), 1):
            pdf.cell(10, 6, f"{i}.", 0, 0); pdf.multi_cell(0, 6, TXT(item))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "B. Kegiatan yang dilaksanakan", ln=True); pdf.set_font("Times", "", 12)
        if extra_info and extra_info.get('desc'): pdf.multi_cell(0, 6, TXT(f"Fokus: {extra_info['desc']}"))
        for item in data.get('kegiatan', []): J_indent(safe_str(item).replace('\n', ' ')); pdf.ln(2)

        pdf.ln(2); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "C. Hasil yang dicapai", ln=True); pdf.set_font("Times", "", 12)
        if kpm_data: pdf.cell(0, 6, TXT(f"KPM: {kpm_data.get('Nama')}"), ln=True)
        for i, item in enumerate(data.get('hasil', []), 1):
            pdf.cell(10, 6, f"{i}.", 0, 0); pdf.multi_cell(0, 6, TXT(item))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "D. Kesimpulan dan Saran", ln=True); pdf.set_font("Times", "", 12)
        J_indent(safe_str(data.get('kesimpulan')))
        pdf.cell(0, 6, "Adapun saran kami:", ln=True)
        for item in data.get('saran', []): pdf.cell(10, 6, "-", 0, 0); pdf.multi_cell(0, 6, TXT(item))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "E. Penutup", ln=True); pdf.set_font("Times", "", 12)
        J_indent(safe_str(data.get('penutup')))

        pdf.ln(10); start_x = 110; pdf.set_x(start_x)
        pdf.cell(80, 5, TXT(f"Dibuat di {meta['kab']}"), ln=True, align='C')
        pdf.set_x(start_x); pdf.cell(80, 5, TXT(f"Pada Tanggal {meta['tgl']}"), ln=True, align='C')
        pdf.set_x(start_x); pdf.cell(80, 5, "Pendamping PKH", ln=True, align='C')
        
        if ttd:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(ttd); pth=tmp.name
            pdf.image(pth, x=start_x+25, y=pdf.get_y(), h=25); os.unlink(pth); pdf.ln(25)
        else: pdf.ln(25)
        
        pdf.set_x(start_x); pdf.set_font("Times", "B", 12); pdf.cell(80, 5, TXT(meta['nama']), ln=True, align='C')
        pdf.set_x(start_x); pdf.set_font("Times", "", 12); pdf.cell(80, 5, TXT(f"NIP. {meta['nip']}"), ln=True, align='C')
        return pdf.output(dest='S').encode('latin-1')
    except Exception as e:
        return None

# ==========================================
# 6. UI UTAMA & LOGIN
# ==========================================
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.button("MASUK / LOGIN", type="primary", use_container_width=True):
            if user in DAFTAR_USER and DAFTAR_USER[user] == pwd:
                st.session_state["password_correct"] = True
                st.session_state["username"] = user
                st.rerun()
            else:
                st.error("😕 Username atau Password Salah!")
    return False

def main_app():
    # --- LOGOUT ---
    with st.sidebar:
        st.write(f"👤 Login: **{st.session_state.get('username')}**")
        if st.button("🔒 Logout", type="secondary"):
            st.session_state["password_correct"] = False
            st.rerun()

    init_db()
    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
    
    st.sidebar.header("👤 Profil Pendamping")
    nama = st.sidebar.text_input("Nama Lengkap", u_nama, key="nama_val")
    nip = st.sidebar.text_input("NIP", u_nip, key="nip_val")
    kpm = st.sidebar.number_input("Total KPM", value=u_kpm, key="kpm_global_val")
    
    st.sidebar.markdown("### 🌍 Wilayah")
    prov = st.sidebar.text_input("Provinsi", u_prov, key="prov_val")
    kab = st.sidebar.text_input("Kabupaten", u_kab, key="kab_val")
    kec = st.sidebar.text_input("Kecamatan", u_kec, key="kec_val")
    kel = st.sidebar.text_input("Kelurahan", u_kel, key="kel_val")
    
    st.sidebar.markdown("### 📅 Periode")
    c1, c2 = st.sidebar.columns([1, 1.5])
    with c1: st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal_surat)
    with c2: st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], key="bln_val", on_change=update_tanggal_surat)
    
    st.sidebar.text_input("Tanggal Surat", key="tgl_val")
    st.sidebar.markdown("---")
    st.sidebar.info(f"📂 Arsip: {count_archived_photos()} Foto")
    
    st.sidebar.header("🖼️ Atribut")
    k = st.sidebar.file_uploader("Kop Surat", type=['png','jpg']); t = st.sidebar.file_uploader("Tanda Tangan", type=['png','jpg'])
    if st.sidebar.button("💾 SIMPAN PROFIL"):
        save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
        if k: st.session_state['kop_bytes'] = k.getvalue()
        if t: st.session_state['ttd_bytes'] = t.getvalue()
        st.sidebar.success("Tersimpan!")

    # --- HOME PAGE ---
    if st.session_state['page'] == 'home':
        st.markdown("""<style>div.stButton>button{width:100%;height:140px;font-weight:bold;border-radius:15px;box-shadow:0 4px 6px rgba(0,0,0,0.1);transition:0.3s}div.stButton>button:hover{transform:translateY(-5px);box-shadow:0 8px 12px rgba(0,0,0,0.2);border-color:#ff4b4b}</style>""", unsafe_allow_html=True)
        st.title("📂 Aplikasi RHK PKH Pro")
        st.markdown("### Menu Utama")
        
        cols = st.columns(4); rhk_keys = list(CONFIG_LAPORAN.keys())
        for i, rhk in enumerate(rhk_keys):
            icon = "📄"; parts = rhk.split("–"); label = f"{icon}\n{parts[0].strip()}\n{parts[-1].strip()}"
            with cols[i % 4]:
                if st.button(label, key=f"btn_{i}"):
                    st.session_state['selected_rhk'] = rhk
                    st.session_state['page'] = 'detail'
                    reset_states() 
                    st.rerun()
        
        st.markdown("---")
        st.markdown("<div style='text-align: center; color: grey; font-size: 12px;'>Copyright © 2026 VHS | All Rights Reserved | Kebijakan Privasi</div>", unsafe_allow_html=True)

    # --- DETAIL PAGE ---
    elif st.session_state['page'] == 'detail':
        current_rhk = st.session_state['selected_rhk']
        with st.container():
            st.caption("🚀 Navigasi Cepat:")
            nav_cols = st.columns(8)
            if nav_cols[0].button("🏠 HOME"): 
                st.session_state['page'] = 'home'
                reset_states()
                st.rerun()
                
            rhk_keys = list(CONFIG_LAPORAN.keys()); col_idx = 1
            for rhk in rhk_keys:
                if rhk != current_rhk and col_idx < 8:
                    if nav_cols[col_idx].button(rhk.split("–")[0].strip(), key=f"nav_{rhk}"):
                        st.session_state['selected_rhk'] = rhk
                        reset_states()
                        st.rerun()
                    col_idx += 1
        
        st.divider(); st.subheader(f"{current_rhk}")
        
        # JUDUL OTOMATIS
        def_judul = "KEGIATAN"
        if "RHK 1" in current_rhk: def_judul = "KEGIATAN PENYALURAN BANTUAN SOSIAL"
        elif "RHK 2" in current_rhk: def_judul = "PELAKSANAAN P2K2 (FDS)"
        elif "RHK 3" in current_rhk: def_judul = "PELAKSANAAN GRADUASI MANDIRI"
        elif "RHK 4" in current_rhk: def_judul = "KEGIATAN PEMUTAKHIRAN DATA"
        elif "RHK 5" in current_rhk: def_judul = "KEGIATAN PEMUTAKHIRAN DATA KPM"
        elif "RHK 6" in current_rhk: def_judul = "PENANGANAN KASUS (CASE MANAGEMENT)"
        elif "RHK 7" in current_rhk: def_judul = "PELAKSANAAN TUGAS DIREKTIF"
        
        judul_kop = st.text_input("Judul Kop Laporan (Bisa Diedit):", value=def_judul)
        st.divider()

        meta = {'bulan': f"{st.session_state['bln_val']} {st.session_state['th_val']}", 'kpm': st.session_state['kpm_global_val'], 'nama': st.session_state['nama_val'], 'nip': st.session_state['nip_val'], 'prov': st.session_state['prov_val'], 'kab': st.session_state['kab_val'], 'kec': st.session_state['kec_val'], 'kel': st.session_state['kel_val'], 'tgl': st.session_state['tgl_val'], 'judul': judul_kop}
        lokasi_lengkap = f"Desa/Kel {meta['kel']}, Kec. {meta['kec']}, {meta['kab']}, {meta['prov']}"
        kop = st.session_state['kop_bytes']; ttd = st.session_state['ttd_bytes']

        def render_photo_manager(key_suffix):
            st.write("#### 📸 Dokumentasi Kegiatan")
            t1, t2 = st.tabs(["📤 Upload Baru", "🗂️ Arsip"]); sel = []; nu = None
            with t1:
                nu = st.file_uploader("Pilih Foto", type=['jpg','png','jpeg'], accept_multiple_files=True, key=f"up_{key_suffix}")
                if nu: 
                    for f in nu: sel.append(io.BytesIO(f.getvalue()))
            with t2:
                sf = get_archived_photos(current_rhk, meta['bulan'])
                if not sf: st.info("Arsip kosong.")
                else:
                    sn = st.multiselect("Pilih dari Arsip:", sf, key=f"ms_{key_suffix}")
                    for n in sn: sel.append(load_photo_from_disk(current_rhk, meta['bulan'], n))
            return sel, nu

        if "RHK 3" in current_rhk:
            st.info("ℹ️ RHK 3: Pilih KPM dari Excel.")
            ud = st.file_uploader("Upload Excel Graduasi", type=['xlsx', 'csv'])
            if ud:
                try: st.session_state['graduasi_raw'] = pd.read_csv(ud) if ud.name.endswith('.csv') else pd.read_excel(ud)
                except: st.error("Gagal baca.")
            if st.session_state['graduasi_raw'] is not None:
                df = st.session_state['graduasi_raw']
                if 'Pilih' not in df.columns: df.insert(0, "Pilih", False)
                ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                if st.button("💾 Simpan Pilihan"):
                    st.session_state['graduasi_fix'] = ed[ed['Pilih']==True].to_dict('records'); st.success("Tersimpan!")
            
            ket = st.text_area("Keterangan Tambahan:", height=80); fp, nu = render_photo_manager("rhk3")
            if st.button("🚀 Buat Laporan", type="primary"):
                kpms = st.session_state.get('graduasi_fix', [])
                if not kpms: st.error("Pilih KPM dulu!"); st.stop()
                if nu: 
                    for f in nu: auto_save_photo_local(f, current_rhk, meta['bulan'])
                res = []; prog = st.progress(0); stat = st.empty()
                
                # --- LOOPING DENGAN DELAY & ANIMASI ---
                total_kpm = len(kpms)
                for i, k in enumerate(kpms):
                    nk = str(k.get('Nama', 'KPM'))
                    stat.info(f"⏳ [{i+1}/{total_kpm}] Sedang memproses data: **{nk}**... Mohon tunggu.")
                    
                    time.sleep(2) # DELAY ANTAR REQUEST (2 DETIK)
                    
                    d = generate_isi_laporan(current_rhk, f"Graduasi: {nk}", meta['kpm'], nk, meta['bulan'], lokasi_lengkap, ket_info=ket)
                    if d:
                        ei = {'desc': f"KPM: {nk}. {ket}"}
                        for x in fp: x.seek(0)
                        w = create_word_doc(d, meta, fp, kop, ttd, ei, k)
                        for x in fp: x.seek(0)
                        p = create_pdf_doc(d, meta, fp, kop, ttd, ei, k)
                        res.append({'nama': nk, 'word': w.getvalue(), 'pdf': p})
                    prog.progress((i+1)/total_kpm)
                
                st.session_state['rhk3_results'] = res; st.success("Selesai!"); st.rerun()
            
            if st.session_state['rhk3_results']:
                st.divider(); st.write("### 📥 Download:"); 
                for i, r in enumerate(st.session_state['rhk3_results']):
                    c1, c2, c3 = st.columns([3,1,1]); c1.write(f"📄 **{r['nama']}**")
                    c2.download_button("Word", r['word'], f"Laporan_{r['nama']}.docx", key=f"w3_{i}")
                    c3.download_button("PDF", r['pdf'], f"Laporan_{r['nama']}.pdf", key=f"p3_{i}")

        elif any(x in current_rhk for x in ["RHK 2", "RHK 4", "RHK 7"]):
            qk = 'rhk2_queue' if "RHK 2" in current_rhk else ('rhk4_queue' if "RHK 4" in current_rhk else 'rhk7_queue')
            rk = 'rhk2_results' if "RHK 2" in current_rhk else ('rhk4_results' if "RHK 4" in current_rhk else 'rhk7_results')
            
            with st.container(border=True):
                st.write("#### ➕ Tambah ke Antrian")
                mp = st.text_input("Nama Kegiatan:") if "RHK 7" in current_rhk else st.selectbox("Pilih Laporan:", CONFIG_LAPORAN[current_rhk])
                ap = st.selectbox("Aplikasi:", ["SIKS-NG", "ESDM-PKH", "SIKMA Mobile"]) if "RHK 4" in current_rhk else ""
                kt = st.text_area("Keterangan:", height=80); fp, nu = render_photo_manager("q_rhk")
                if st.button("Simpan ke Antrian"):
                    if not fp: st.error("Wajib ada foto!")
                    elif "RHK 7" in current_rhk and not mp: st.error("Isi nama kegiatan!")
                    else:
                        if nu: 
                            for f in nu: auto_save_photo_local(f, current_rhk, meta['bulan'])
                        st.session_state[qk].append({"modul": mp, "foto": fp, "app": ap, "desc": kt})
                        st.success("Masuk antrian!"); time.sleep(0.5); st.rerun()

            q = st.session_state[qk]
            if len(q) > 0:
                st.divider(); st.write(f"### 📋 Antrian ({len(q)}):")
                for ix, i in enumerate(q): st.write(f"{ix+1}. {i['modul']}")
                c1, c2 = st.columns(2)
                if c1.button("Hapus Antrian"): st.session_state[qk] = []; st.rerun()
                if c2.button("🚀 GENERATE SEMUA", type="primary"):
                    res = []; prog = st.progress(0); stat = st.empty()
                    
                    # --- LOOPING DENGAN DELAY & ANIMASI ---
                    total_q = len(q)
                    for idx, it in enumerate(q):
                        mn = it['modul']
                        stat.info(f"⏳ [{idx+1}/{total_q}] Sedang menghubungi AI untuk: **{mn}**...")
                        
                        time.sleep(2) # DELAY ANTAR REQUEST (2 DETIK)
                        
                        dk = f"Kegiatan: {mn}. {it.get('desc','')}"
                        if "RHK 7" in current_rhk:
                            ei = {'app': it.get('app'), 'desc': f"{dk} (Pelaksanaan)"}
                            da = generate_isi_laporan(current_rhk, f"{mn} (Pelaksanaan)", meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "", it.get('app'), ei['desc'])
                            if da:
                                for f in it['foto']: f.seek(0)
                                w = create_word_doc(da, meta, it['foto'], kop, ttd, ei)
                                for f in it['foto']: f.seek(0)
                                p = create_pdf_doc(da, meta, it['foto'], kop, ttd, ei)
                                res.append({'nama': f"{mn} - Pelaksanaan", 'word': w.getvalue(), 'pdf': p})
                            
                            ei_b = {'app': it.get('app'), 'desc': f"{dk} (Evaluasi)"}
                            db = generate_isi_laporan(current_rhk, f"{mn} (Hasil)", meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "Evaluasi", it.get('app'), ei_b['desc'])
                            if db:
                                for f in it['foto']: f.seek(0)
                                w = create_word_doc(db, meta, it['foto'], kop, ttd, ei_b)
                                for f in it['foto']: f.seek(0)
                                p = create_pdf_doc(db, meta, it['foto'], kop, ttd, ei_b)
                                res.append({'nama': f"{mn} - Hasil", 'word': w.getvalue(), 'pdf': p})
                        else:
                            ei = {'app': it.get('app'), 'desc': dk}
                            d = generate_isi_laporan(current_rhk, judul_kop, meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "", it.get('app'), dk)
                            if d:
                                for f in it['foto']: f.seek(0)
                                w = create_word_doc(d, meta, it['foto'], kop, ttd, ei)
                                for f in it['foto']: f.seek(0)
                                p = create_pdf_doc(d, meta, it['foto'], kop, ttd, ei)
                                res.append({'nama': mn, 'word': w.getvalue(), 'pdf': p})
                        prog.progress((idx+1)/total_q)
                    st.session_state[rk] = res; stat.text("Selesai!"); st.rerun()

            if st.session_state.get(rk):
                st.divider(); st.write("### 📥 Download:"); 
                for i, r in enumerate(st.session_state[rk]):
                    c1, c2, c3 = st.columns([3,1,1]); c1.write(f"📘 **{r['nama']}**")
                    c2.download_button("Word", r['word'], f"{r['nama']}.docx", key=f"wq_{i}")
                    c3.download_button("PDF", r['pdf'], f"{r['nama']}.pdf", key=f"pq_{i}")

        else: # RHK 1, 5, 6
            ds = CONFIG_LAPORAN[current_rhk]
            if any(x in current_rhk for x in ["RHK 1", "RHK 5", "RHK 6"]):
                js = ds[0] if ds else ""; st.info(f"📌 **Nama Kegiatan:** {js}")
            else: js = st.text_input("Nama Kegiatan:", value=ds[0] if ds else "")
            
            kt = st.text_area("Keterangan:", height=80); fp, nu = render_photo_manager("biasa")
            if st.button("🚀 Buat Laporan", type="primary"):
                if nu: 
                    for f in nu: auto_save_photo_local(f, current_rhk, meta['bulan'])
                
                # ANIMASI SINGLE REQUEST
                with st.spinner("⏳ Sedang menghubungi AI & Menyusun Laporan... Mohon tunggu sebentar."):
                    time.sleep(2) # DELAY BUATAN AGAR TERLIHAT PROSESNYA
                    
                    fd = f"Kegiatan: {js}. {kt}"
                    d = generate_isi_laporan(current_rhk, js, meta['kpm'], f"{meta['kpm']} Peserta", meta['bulan'], lokasi_lengkap, ket_info=fd)
                    if d:
                        ei = {'desc': fd}
                        for f in fp: f.seek(0)
                        w = create_word_doc(d, meta, fp, kop, ttd, ei)
                        for f in fp: f.seek(0)
                        p = create_pdf_doc(d, meta, fp, kop, ttd, ei)
                        st.session_state['generated_file_data'] = {'type': 'single', 'word': w.getvalue(), 'pdf': p, 'name': current_rhk}
                        st.success("Berhasil!"); st.rerun()
                    simpan_riwayat(current_rhk, "Generated", meta['kel'])

            if st.session_state.get('generated_file_data'):
                files = st.session_state['generated_file_data']; st.divider()
                c1, c2 = st.columns(2)
                c1.download_button("📄 Download WORD", files['word'], f"{files['name']}.docx", "application/docx")
                c2.download_button("📕 Download PDF", files['pdf'], f"{files['name']}.pdf", "application/pdf")

# ==========================================
# 7. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    if check_password():
        main_app()
