import streamlit as st
import google.generativeai as genai
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
import io
import pandas as pd
import sqlite3
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

# --- DAFTAR USER & PASSWORD ---
DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# ==========================================
# 2. SISTEM KEAMANAN & LOGIN
# ==========================================

# --- API KEY DARI SECRETS (AMAN) ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except FileNotFoundError:
    st.error("🚨 File .streamlit/secrets.toml tidak ditemukan! Harap buat file tersebut dan isi GOOGLE_API_KEY.")
    st.stop()
except KeyError:
    st.error("🚨 Key 'GOOGLE_API_KEY' tidak ditemukan di secrets.toml.")
    st.stop()

# Konfigurasi AI
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    # MODEL SESUAI PERMINTAAN: gemini-flash-latest
    model = genai.GenerativeModel('gemini-flash-latest')
except Exception as e:
    st.error(f"Gagal konfigurasi AI: {e}")

# --- FUNGSI CEK PASSWORD (PERSISTENT REFRESH) ---
def check_password():
    """Mengembalikan True jika user berhasil login."""
    
    # 1. Cek Memory Session
    if st.session_state.get("password_correct", False):
        return True

    # 2. Cek URL (Agar tahan Refresh)
    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True
        st.session_state["username"] = qp.get("user")
        return True

    # TAMPILAN HALAMAN LOGIN
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_user = st.text_input("Username", key="login_user")
        input_pass = st.text_input("Password", type="password", key="login_pass")
        
        if st.button("MASUK / LOGIN", type="primary", use_container_width=True):
            if input_user in DAFTAR_USER and DAFTAR_USER[input_user] == input_pass:
                # Set Session
                st.session_state["password_correct"] = True
                st.session_state["username"] = input_user
                
                # Set URL Param (Persistence)
                st.query_params["auth"] = "valid"
                st.query_params["user"] = input_user
                
                st.rerun()
            else:
                st.error("😕 Username atau Password Salah!")
                
    return False

# JALANKAN APP JIKA LOGIN SUKSES
if check_password():

    # ==========================================
    # 3. SETUP & INIT STATE
    # ==========================================

    # --- TOMBOL LOGOUT ---
    with st.sidebar:
        st.write(f"👤 Login: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout", type="secondary"):
            st.session_state["password_correct"] = False
            st.query_params.clear() # Hapus jejak URL
            st.rerun()

    # --- INIT SESSION STATE ---
    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 
            'graduasi_raw', 'graduasi_fix', 'generated_file_data', 
            'rhk3_results', 'rhk2_queue', 'rhk2_results', 
            'rhk4_queue', 'rhk4_results', 'rhk7_queue', 'rhk7_results',
            'tgl_val', 'bln_val', 'th_val'] 

    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    # --- LOGIKA PERSISTENCE HALAMAN ---
    # Mengembalikan user ke halaman terakhir saat refresh
    if "page" in st.query_params:
        st.session_state['page'] = st.query_params["page"]
    if "rhk" in st.query_params:
        st.session_state['selected_rhk'] = st.query_params["rhk"]

    # Default Values
    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk4_queue'] is None: st.session_state['rhk4_queue'] = []
    if st.session_state['rhk7_queue'] is None: st.session_state['rhk7_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'

    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    if not st.session_state['tgl_val']: st.session_state['tgl_val'] = "30 Januari 2026"

    # ==========================================
    # 4. DATABASE & TOOLS
    # ==========================================
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
        "RHK 4 – KEGIATAN PEMUTAKHIRAN": ["Verifikasi Fasilitas Pendidikan", "Verifikasi Fasilitas Kesehatan", "Verifikasi Kesejahteraan Sosial"],
        "RHK 5 – KPM YANG DIMUTAKHIRKAN": ["Laporan Hasil Pemutakhiran Data KPM"],
        "RHK 6 – LAPORAN KASUS ADAPTIF": ["Laporan Penanganan Kasus (Case Management)"],
        "RHK 7 – LAPORAN DIREKTIF": ["Tugas Direktif Pimpinan (A)", "Tugas Direktif Pimpinan (B)"]
    }

    def init_db():
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS riwayat (id INTEGER PRIMARY KEY, tgl TEXT, rhk TEXT, judul TEXT, lokasi TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_settings (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
        c.execute('SELECT count(*) FROM user_settings')
        if c.fetchone()[0] == 0:
            c.execute('INSERT INTO user_settings (id, nama, nip, kpm, prov, kab, kec, kel) VALUES (1, ?, ?, ?, ?, ?, ?, ?)', ("Vidi Hari Suci", "123456", 250, "Lampung", "Lampung Tengah", "Punggur", "Mojopahit"))
        conn.commit(); conn.close()

    def get_user_settings():
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
        c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone(); conn.close(); return data

    def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
        c = conn.cursor()
        c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
        conn.commit(); conn.close()

    def simpan_riwayat(rhk, judul, lokasi):
        try:
            conn = sqlite3.connect('riwayat_v40_finalbtn.db')
            c = conn.cursor()
            tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute('INSERT INTO riwayat (tgl, rhk, judul, lokasi) VALUES (?, ?, ?, ?)', (tgl, rhk, judul, lokasi))
            conn.commit(); conn.close()
        except: pass

    init_db()

    # --- IMAGE HANDLING ---
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
        except: uploaded_file.seek(0); return uploaded_file 

    def get_folder_path(rhk_name, periode_str):
        try: parts=periode_str.split(" "); b=parts[0]; t=parts[1]
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
            with open(os.path.join(target_folder, final_name), "wb") as f: f.write(compressed_bytes.getvalue())
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

    # --- TEXT TOOLS ---
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

    # ==========================================
    # 5. ENGINE AI (ROBUST PARSING)
    # ==========================================
    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, analisis="", app_info="", ket_info=""):
        max_retries = 3
        prompt = f"""
        Role: Pendamping PKH Profesional.
        Buat JSON Laporan Kegiatan.
        KONTEKS:
        - RHK: {topik} | Nama Kegiatan: {detail} 
        - Lokasi: {lokasi_lengkap} | Periode: {bulan}
        - CATATAN USER (Topik Utama): {ket_info} (Wajib dimasukkan ke narasi).
        Output JSON Wajib (lowercase key):
        {{
            "gambaran_umum": "Paragraf panjang kondisi umum wilayah...",
            "maksud_tujuan": "Paragraf maksud tujuan...",
            "ruang_lingkup": "Jelaskan ruang lingkup...",
            "dasar_hukum": ["Permensos No. 1 Tahun 2018", "Pedoman Umum PKH 2021"],
            "kegiatan": ["Uraian kegiatan 1 detail...", "Detail {ket_info}..."],
            "hasil": ["Hasil 1...", "Hasil 2..."],
            "kesimpulan": "Paragraf kesimpulan...",
            "saran": ["Saran 1...", "Saran 2..."],
            "penutup": "Kalimat penutup formal..."
        }}
        """
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                text = response.text
                # Clean Markdown
                clean_text = text.replace("```json", "").replace("```", "").strip()
                try: return json.loads(clean_text)
                except:
                    # Regex Fallback
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match: return json.loads(match.group())
                    else: raise ValueError("No JSON found")
            except:
                if attempt < max_retries - 1: time.sleep(2); continue
                else: return None
        return None

    # ==========================================
    # 6. DOCUMENT GENERATORS (Word & PDF)
    # ==========================================
    def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        doc = Document()
        for s in doc.sections: s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
        style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        
        if kop: 
            p = doc.add_paragraph(); p.alignment = 1
            p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
        
        doc.add_paragraph(" ")
        p = doc.add_paragraph(); p.alignment = 1
        run = p.add_run(f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}")
        run.bold = True; run.font.size = Pt(14)
        doc.add_paragraph(" ")

        def add_p_indent(text, bold=False):
            safe_text = safe_str(text)
            for p_text in safe_text.split('\n'):
                if p_text.strip():
                    p = doc.add_paragraph()
                    p.paragraph_format.first_line_indent = Cm(1.27) 
                    p.paragraph_format.left_indent = Cm(0) 
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    run = p.add_run(p_text.strip())
                    if bold: run.bold = True

        def add_numbered_item(number, text):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75) 
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
            p = doc.add_paragraph(f"Fokus Kegiatan: {extra_info['desc']}"); p.paragraph_format.left_indent = Cm(0.5); p.runs[0].italic = True
        for item in data.get('kegiatan', []): add_p_indent(safe_str(item).replace('\n', ' '))

        doc.add_paragraph("C. Hasil yang dicapai", style='Heading 1')
        
        # --- PERUBAHAN TAMPILAN WORD (TABEL RAPI) ---
        if kpm_data and isinstance(kpm_data, dict):
            # Gunakan Tabel agar alignment titik dua (:) rapi
            p = doc.add_paragraph()
            p.add_run("Profil KPM:").bold = True
            
            table = doc.add_table(rows=0, cols=3)
            table.autofit = False
            # Atur lebar kolom: Label, Titik Dua, Value
            table.columns[0].width = Cm(5.5)
            table.columns[1].width = Cm(0.5)
            table.columns[2].width = Cm(10.0)
            
            fields_to_show = [
                ("Nama", kpm_data.get('Nama', '-')),
                ("NIK", kpm_data.get('NIK', '-')),
                ("Alamat", kpm_data.get('Alamat', '-')),
                ("Kategori Kesejahteraan", kpm_data.get('Kategori', '-')),
                ("Status", kpm_data.get('Status', '-')),
                ("Jenis Graduasi", kpm_data.get('Jenis Graduasi', '-')),
                ("Tahun Bergabung PKH", kpm_data.get('Tahun Bergabung', '-')),
                ("Jumlah Anggota Keluarga", kpm_data.get('Jumlah Anggota', '-')),
                ("Alasan Graduasi", kpm_data.get('Alasan', '-'))
            ]
            
            for label, val in fields_to_show:
                row_cells = table.add_row().cells
                row_cells[0].text = label
                row_cells[1].text = ":"
                row_cells[2].text = safe_str(val)
                
            doc.add_paragraph(" ") # Spasi setelah tabel
        # -----------------------------------------------

        for i, item in enumerate(data.get('hasil', []), 1): add_numbered_item(i, item)

        doc.add_paragraph("D. Kesimpulan dan Saran", style='Heading 1')
        add_p_indent(data.get('kesimpulan'))
        doc.add_paragraph("Adapun yang dapat kami sarankan sebagai berikut:")
        for item in data.get('saran', []):
            p = doc.add_paragraph(f"- {safe_str(item)}")
            p.paragraph_format.left_indent = Cm(1.0)

        doc.add_paragraph("E. Penutup", style='Heading 1')
        add_p_indent(data.get('penutup'))
        doc.add_paragraph(" "); doc.add_paragraph(" ")

        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        table.columns[0].width = Inches(3.5)
        table.columns[1].width = Inches(3.0)
        cell_kanan = table.cell(0, 1)
        p_ttd = cell_kanan.paragraphs[0]; p_ttd.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        p_ttd.add_run(f"Dibuat di {meta['kab']}\nPada Tanggal {meta['tgl']}\nPendamping PKH / Layanan Operasional\n")
        if ttd: p_ttd.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8)); p_ttd.add_run("\n")
        else: p_ttd.add_run("\n\n\n")
        p_ttd.add_run(f"\n{meta['nama']}\n").bold = True; p_ttd.add_run(f"NIP. {meta['nip']}")

        doc.add_page_break()
        p_lamp = doc.add_paragraph("LAMPIRAN DOKUMENTASI"); p_lamp.alignment = 1; p_lamp.runs[0].bold = True
        doc.add_paragraph(" ")
        if imgs:
            rows = (len(imgs) + 1) // 2
            tbl_img = doc.add_table(rows=rows, cols=2); tbl_img.autofit = True
            for i, img_data in enumerate(imgs):
                try:
                    row_idx = i // 2; col_idx = i % 2
                    cell = tbl_img.cell(row_idx, col_idx)
                    p_img = cell.paragraphs[0]; p_img.alignment = 1
                    img_data.seek(0); img_comp = compress_image(img_data)
                    p_img.add_run().add_picture(img_comp, width=Inches(2.8))
                    p_img.add_run(f"\n{meta['judul']} - Foto {i+1}")
                except: pass
        bio = io.BytesIO(); doc.save(bio); return bio

    def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        pdf = FPDF(); pdf.set_margins(25, 20, 25); pdf.add_page(); pdf.set_font("Times", size=12)
        def J(txt): pdf.multi_cell(0, 6, clean_text_for_pdf(txt), align='J')
        def TXT(s): return clean_text_for_pdf(s)
        def J_indent(txt): pdf.multi_cell(0, 6, "        " + clean_text_for_pdf(txt), align='J')

        if kop:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pth=tmp.name
            pdf.image(pth, x=10, y=10, w=190); os.unlink(pth); pdf.ln(35)
        else: pdf.ln(10)

        pdf.set_font("Times", "B", 14)
        pdf.cell(0, 6, "LAPORAN", ln=True, align='C')
        pdf.cell(0, 6, "TENTANG", ln=True, align='C')
        pdf.cell(0, 6, TXT(meta['judul'].upper()), ln=True, align='C')
        pdf.cell(0, 6, TXT(meta['bulan'].upper()), ln=True, align='C'); pdf.ln(10)

        pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "A. Pendahuluan", ln=True)
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "1. Gambaran Umum", ln=True)
        pdf.set_font("Times", "", 12); J_indent(f"Lokasi Pelaksanaan: Kelurahan {meta['kel']}, Kecamatan {meta['kec']}, {meta['kab']}, {meta['prov']}.")
        J_indent(safe_str(data.get('gambaran_umum')))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "2. Maksud dan Tujuan", ln=True)
        pdf.set_font("Times", "", 12); J_indent(safe_str(data.get('maksud_tujuan')))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "3. Ruang Lingkup", ln=True)
        pdf.set_font("Times", "", 12); J_indent(safe_str(data.get('ruang_lingkup')))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0, 6, "4. Dasar", ln=True)
        pdf.set_font("Times", "", 12)
        for i, item in enumerate(data.get('dasar_hukum', []), 1):
            pdf.cell(10, 6, f"{i}.", 0, 0); pdf.multi_cell(0, 6, TXT(item))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "B. Kegiatan yang dilaksanakan", ln=True)
        pdf.set_font("Times", "", 12)
        if extra_info and extra_info.get('desc'):
            pdf.set_font("Times", "I", 12); J(f"Fokus Kegiatan: {extra_info['desc']}"); pdf.set_font("Times", "", 12)
        for item in data.get('kegiatan', []): J_indent(safe_str(item).replace('\n', ' ')); pdf.ln(2)

        pdf.ln(2); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "C. Hasil yang dicapai", ln=True)
        pdf.set_font("Times", "", 12)
        
        # --- PERUBAHAN TAMPILAN PDF (ALIGNMENT RAPI) ---
        if kpm_data and isinstance(kpm_data, dict):
            fields_to_show = [
                ("Nama", kpm_data.get('Nama', '-')),
                ("NIK", kpm_data.get('NIK', '-')),
                ("Alamat", kpm_data.get('Alamat', '-')),
                ("Kategori Kesejahteraan", kpm_data.get('Kategori', '-')),
                ("Status", kpm_data.get('Status', '-')),
                ("Jenis Graduasi", kpm_data.get('Jenis Graduasi', '-')),
                ("Tahun Bergabung PKH", kpm_data.get('Tahun Bergabung', '-')),
                ("Jumlah Anggota Keluarga", kpm_data.get('Jumlah Anggota', '-')),
                ("Alasan Graduasi", kpm_data.get('Alasan', '-'))
            ]
            
            for label, val in fields_to_show:
                pdf.cell(50, 6, TXT(label), 0, 0) # Label (width 50)
                pdf.cell(5, 6, ":", 0, 0)       # Separator (width 5)
                pdf.multi_cell(0, 6, TXT(safe_str(val)), 0, 1) # Value (sisa)
            
            pdf.ln(2)
        # -----------------------------------------------

        for i, item in enumerate(data.get('hasil', []), 1):
            pdf.cell(10, 6, f"{i}.", 0, 0); pdf.multi_cell(0, 6, TXT(item))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "D. Kesimpulan dan Saran", ln=True)
        pdf.set_font("Times", "", 12)
        J_indent(safe_str(data.get('kesimpulan')))
        pdf.cell(0, 6, "Adapun saran kami:", ln=True)
        for item in data.get('saran', []):
            pdf.cell(10, 6, "-", 0, 0); pdf.multi_cell(0, 6, TXT(item))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "E. Penutup", ln=True)
        pdf.set_font("Times", "", 12); J_indent(safe_str(data.get('penutup')))

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

    # ==========================================
    # 7. UI PAGES
    # ==========================================
    def update_tanggal_surat():
        bln = st.session_state.get('bln_val', 'JANUARI')
        th = st.session_state.get('th_val', '2026')
        day = "28" if bln == "FEBRUARI" else "30"
        st.session_state.tgl_val = f"{day} {bln.title()} {th}"

    def render_sidebar():
        u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
        st.sidebar.header("👤 Profil Pendamping")
        nama = st.sidebar.text_input("Nama Lengkap", u_nama, key="nama_val")
        nip = st.sidebar.text_input("NIP", u_nip, key="nip_val")
        kpm = st.sidebar.number_input("Total KPM Dampingan", min_value=0, value=u_kpm, key="kpm_global_val")
        
        st.sidebar.markdown("### 🌍 Wilayah")
        prov = st.sidebar.text_input("Provinsi", u_prov, key="prov_val")
        kab = st.sidebar.text_input("Kabupaten", u_kab, key="kab_val")
        kec = st.sidebar.text_input("Kecamatan", u_kec, key="kec_val")
        kel = st.sidebar.text_input("Kelurahan", u_kel, key="kel_val")
        
        st.sidebar.markdown("### 📅 Periode")
        c1, c2 = st.sidebar.columns([1, 1.5])
        with c1:
            st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal_surat)
        with c2:
            BULAN = ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]
            st.selectbox("Bulan", BULAN, key="bln_val", on_change=update_tanggal_surat)
        
        st.sidebar.text_input("Tanggal Surat", key="tgl_val")
        st.sidebar.markdown("---")
        st.sidebar.info(f"📂 **Arsip Foto:** {count_archived_photos()} File")
        
        st.sidebar.header("🖼️ Atribut")
        k = st.sidebar.file_uploader("Kop Surat", type=['png','jpg'])
        t = st.sidebar.file_uploader("Tanda Tangan", type=['png','jpg'])
        if st.sidebar.button("💾 SIMPAN PROFIL"):
            save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
            if k: st.session_state['kop_bytes'] = k.getvalue()
            if t: st.session_state['ttd_bytes'] = t.getvalue()
            st.sidebar.success("Profil Tersimpan!")

    def show_dashboard():
        st.markdown("""<style>div.stButton>button{width:100%;height:160px;font-size:15px;font-weight:bold;border-radius:15px;box-shadow:0 4px 6px rgba(0,0,0,0.1);}</style>""", unsafe_allow_html=True)
        st.title("📂 Aplikasi RHK PKH Pro"); st.markdown("### Menu Utama")
        rhk_keys = list(CONFIG_LAPORAN.keys()); cols = st.columns(4)
        for i, rhk in enumerate(rhk_keys):
            icon = "💸" if "RHK 1" in rhk else "📚" if "RHK 2" in rhk else "🎓" if "RHK 3" in rhk else "📝" if "RHK 4" in rhk else "👥" if "RHK 5" in rhk else "🆘" if "RHK 6" in rhk else "📢"
            label = f"{icon}\n{rhk.split('–')[0].strip()}\n{rhk.split('–')[-1].strip()}"
            with cols[i % 4]:
                if st.button(label, key=f"btn_{i}"):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'
                    st.query_params["page"] = "detail"; st.query_params["rhk"] = rhk
                    reset_states(); st.rerun()

    def show_detail_page():
        current_rhk = st.session_state['selected_rhk']
        with st.container():
            nav_cols = st.columns(8)
            if nav_cols[0].button("🏠 HOME"):
                st.session_state['page'] = 'home'; st.query_params["page"] = "home"
                if "rhk" in st.query_params: del st.query_params["rhk"]
                reset_states(); st.rerun()
            
            rhk_keys = list(CONFIG_LAPORAN.keys()); col_idx = 1
            for rhk in rhk_keys:
                if rhk != current_rhk:
                    if col_idx < 8 and nav_cols[col_idx].button(rhk.split("–")[0].strip(), key=f"nav_{rhk}"):
                        st.session_state['selected_rhk'] = rhk; st.query_params["rhk"] = rhk
                        reset_states(); st.rerun()
                    col_idx += 1
        
        st.divider(); st.subheader(f"{current_rhk}")
        default_judul = "KEGIATAN PENYALURAN BANTUAN SOSIAL" if "RHK 1" in current_rhk else "PELAKSANAAN P2K2 (FDS)" if "RHK 2" in current_rhk else "PELAKSANAAN GRADUASI MANDIRI" if "RHK 3" in current_rhk else "KEGIATAN PEMUTAKHIRAN DATA" if "RHK 4" in current_rhk else "KEGIATAN PEMUTAKHIRAN DATA KPM" if "RHK 5" in current_rhk else "PENANGANAN KASUS" if "RHK 6" in current_rhk else "PELAKSANAAN TUGAS DIREKTIF"
        judul_kop = st.text_input("Judul Kop Laporan (Bisa Diedit):", value=default_judul)
        st.divider()

        meta = {
            'bulan': f"{st.session_state.get('bln_val')} {st.session_state.get('th_val')}",
            'kpm': st.session_state['kpm_global_val'], 'nama': st.session_state['nama_val'], 'nip': st.session_state['nip_val'],
            'prov': st.session_state['prov_val'], 'kab': st.session_state['kab_val'], 'kec': st.session_state['kec_val'], 'kel': st.session_state['kel_val'],
            'tgl': st.session_state['tgl_val'], 'judul': judul_kop
        }
        lokasi_lengkap = f"Desa/Kel {meta['kel']}, Kec. {meta['kec']}, {meta['kab']}, {meta['prov']}"
        kop = st.session_state['kop_bytes']; ttd = st.session_state['ttd_bytes']

        is_rhk3 = (current_rhk == "RHK 3 – TARGET GRADUASI MANDIRI")
        is_queue_rhk = (current_rhk in ["RHK 2 – LAPORAN P2K2 (FDS)", "RHK 4 – KEGIATAN PEMUTAKHIRAN", "RHK 7 – LAPORAN DIREKTIF"])

        def render_photo_manager(key_suffix):
            st.write("#### 📸 Dokumentasi Kegiatan")
            t1, t2 = st.tabs(["📤 Upload Baru", "🗂️ Arsip"]); sel = []
            with t1:
                new = st.file_uploader("Pilih Foto", type=['jpg','png','jpeg'], accept_multiple_files=True, key=f"up_{key_suffix}")
                if new: sel = [io.BytesIO(f.getvalue()) for f in new]
            with t2:
                saved = get_archived_photos(current_rhk, meta['bulan'])
                if saved:
                    for n in st.multiselect("Pilih dari Arsip:", saved, key=f"ms_{key_suffix}"): sel.append(load_photo_from_disk(current_rhk, meta['bulan'], n))
                else: st.info("Arsip kosong.")
            return sel, new

        if is_rhk3:
            st.info("ℹ️ RHK 3: Pilih KPM dari Excel.")
            
            # --- TEMPLATE DIPERBARUI SESUAI GAMBAR ---
            template_df = pd.DataFrame({
                "Nama": ["ARJO SARDI"], 
                "NIK": ["180206xxx"], 
                "Alamat": ["Dusun 1, Kampung Mojopahit"], 
                "Kategori": ["Sejahtera"], 
                "Status": ["Lulus Graduasi Mandiri"],
                "Jenis Graduasi": ["Sukarela"],
                "Tahun Bergabung": ["2018"],
                "Jumlah Anggota": ["4 Orang"],
                "Alasan": ["Sudah merasa mampu"]
            })
            
            # --- DOWNLOAD XLSX ---
            buffer = io.BytesIO()
            template_df.to_excel(buffer, index=False)
            buffer.seek(0)
            st.download_button("📥 Template Excel (XLSX)", data=buffer, file_name="template_graduasi.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
            upl = st.file_uploader("Upload Excel Graduasi", type=['xlsx', 'csv'])
            if upl:
                try: 
                    st.session_state['graduasi_raw'] = pd.read_csv(upl) if upl.name.endswith('.csv') else pd.read_excel(upl)
                except: st.error("Gagal baca Excel.")
            
            if st.session_state['graduasi_raw'] is not None:
                df = st.session_state['graduasi_raw']
                if 'Pilih' not in df.columns: df.insert(0, "Pilih", False)
                ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                if st.button("💾 Simpan Pilihan"):
                    st.session_state['graduasi_fix'] = ed[ed['Pilih'] == True].to_dict('records')
                    st.success(f"Tersimpan: {len(st.session_state['graduasi_fix'])} KPM")

            ket_global = st.text_area("Keterangan Tambahan (Opsional):", placeholder="Contoh: Graduasi mandiri...", height=80)
            photos, new_ups = render_photo_manager("rhk3")

            if st.button("🚀 Buat Laporan Graduasi", type="primary"):
                kpms = st.session_state.get('graduasi_fix', [])
                if not kpms: st.error("Pilih KPM dulu!"); st.stop()
                if new_ups: [auto_save_photo_local(f, current_rhk, meta['bulan']) for f in new_ups]
                
                res = []; prog = st.progress(0); stat = st.empty()
                for i, kpm in enumerate(kpms):
                    nm = str(kpm.get('Nama', 'KPM')); stat.text(f"⏳ Memproses {nm}...")
                    data = generate_isi_laporan(current_rhk, f"Laporan Graduasi: {nm}", meta['kpm'], nm, meta['bulan'], lokasi_lengkap, ket_info=ket_global)
                    if data:
                        ex = {'desc': f"KPM: {nm}. {ket_global}"}
                        [p.seek(0) for p in photos]
                        res.append({'nama': nm, 'word': create_word_doc(data, meta, photos, kop, ttd, ex, kpm).getvalue(), 'pdf': create_pdf_doc(data, meta, photos, kop, ttd, ex, kpm)})
                    prog.progress((i+1)/len(kpms))
                st.session_state['rhk3_results'] = res; st.success("Selesai!"); st.rerun()

            if st.session_state.get('rhk3_results'):
                st.write("### 📥 Download:"); r = st.session_state['rhk3_results']
                for i, x in enumerate(r):
                    c1,c2,c3=st.columns([3,1,1]); c1.write(f"📄 **{x['nama']}**")
                    c2.download_button("Word", x['word'], f"{x['nama']}.docx", key=f"w3{i}")
                    c3.download_button("PDF", x['pdf'], f"{x['nama']}.pdf", key=f"p3{i}")

        elif is_queue_rhk:
            q_key = 'rhk2_queue' if "RHK 2" in current_rhk else 'rhk4_queue' if "RHK 4" in current_rhk else 'rhk7_queue'
            r_key = 'rhk2_results' if "RHK 2" in current_rhk else 'rhk4_results' if "RHK 4" in current_rhk else 'rhk7_results'
            
            with st.container(border=True):
                st.write("#### ➕ Tambah Antrian")
                modul = st.text_input("Nama Kegiatan:", placeholder="Contoh: Rapat...") if "RHK 7" in current_rhk else st.selectbox("Pilih Laporan:", CONFIG_LAPORAN[current_rhk])
                app = st.selectbox("Aplikasi:", ["SIKS-NG", "ESDM-PKH", "SIKMA Mobile"]) if "RHK 4" in current_rhk else ""
                ket = st.text_area("Keterangan (Opsional):", height=80)
                photos, new_ups = render_photo_manager("q")
                
                if st.button("Simpan ke Antrian"):
                    if not photos: st.error("Wajib ada foto!")
                    else:
                        if new_ups: [auto_save_photo_local(f, current_rhk, meta['bulan']) for f in new_ups]
                        st.session_state[q_key].append({"modul": modul, "foto": photos, "foto_count": len(photos), "app": app, "desc": ket})
                        st.success("Masuk antrian!"); time.sleep(0.5); st.rerun()

            q = st.session_state[q_key]
            if q:
                st.write(f"### 📋 Antrian ({len(q)})")
                for idx, x in enumerate(q): st.write(f"{idx+1}. **{x['modul']}** ({x['foto_count']} Foto)")
                c1, c2 = st.columns(2)
                if c1.button("🗑️ Hapus Semua"): st.session_state[q_key] = []; st.rerun()
                if c2.button("🚀 GENERATE SEMUA", type="primary"):
                    res = []; prog = st.progress(0); stat = st.empty()
                    for i, item in enumerate(q):
                        nm = item['modul']; stat.text(f"⏳ Proses {nm}...")
                        dtl = f"Kegiatan: {nm}. {item.get('desc')}"
                        
                        if "RHK 7" in current_rhk:
                            # 2 Laporan per item (A & B)
                            da = generate_isi_laporan(current_rhk, f"{nm} (Pelaksanaan)", meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "", item.get('app'), dtl)
                            if da:
                                [f.seek(0) for f in item['foto']]
                                res.append({'nama': f"{nm} (A)", 'word': create_word_doc(da, meta, item['foto'], kop, ttd, {'desc':dtl}).getvalue(), 'pdf': create_pdf_doc(da, meta, item['foto'], kop, ttd, {'desc':dtl})})
                            
                            db = generate_isi_laporan(current_rhk, f"{nm} (Hasil)", meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "Evaluasi", item.get('app'), dtl)
                            if db:
                                [f.seek(0) for f in item['foto']]
                                res.append({'nama': f"{nm} (B)", 'word': create_word_doc(db, meta, item['foto'], kop, ttd, {'desc':dtl}).getvalue(), 'pdf': create_pdf_doc(db, meta, item['foto'], kop, ttd, {'desc':dtl})})
                        else:
                            d = generate_isi_laporan(current_rhk, nm, meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "", item.get('app'), dtl)
                            if d:
                                [f.seek(0) for f in item['foto']]
                                res.append({'nama': nm, 'word': create_word_doc(d, meta, item['foto'], kop, ttd, {'desc':dtl}).getvalue(), 'pdf': create_pdf_doc(d, meta, item['foto'], kop, ttd, {'desc':dtl})})
                        prog.progress((i+1)/len(q))
                    st.session_state[r_key] = res; st.success("Selesai!"); st.rerun()

            r = st.session_state.get(r_key)
            if r:
                st.write("### 📥 Download:"); 
                for i, x in enumerate(r):
                    c1,c2,c3=st.columns([3,1,1]); c1.write(f"📘 **{x['nama']}**")
                    c2.download_button("Word", x['word'], f"{x['nama']}.docx", key=f"wq{i}")
                    c3.download_button("PDF", x['pdf'], f"{x['nama']}.pdf", key=f"pq{i}")

        else: # RHK 1, 5, 6
            sub = CONFIG_LAPORAN[current_rhk]
            judul_keg = sub[0] if len(sub)==1 else st.text_input("Nama Kegiatan:", value=sub[0])
            if len(sub)==1: st.info(f"📌 **Kegiatan:** {judul_keg}")
            
            ket = st.text_area("Keterangan (Opsional):", height=80)
            photos, new_ups = render_photo_manager("std")

            if st.button("🚀 Buat Laporan", type="primary"):
                if new_ups: [auto_save_photo_local(f, current_rhk, meta['bulan']) for f in new_ups]
                full_desc = f"Kegiatan: {judul_keg}. {ket}"
                with st.spinner("Memproses AI..."):
                    d = generate_isi_laporan(current_rhk, judul_keg, meta['kpm'], f"{meta['kpm']} Peserta", meta['bulan'], lokasi_lengkap, ket_info=full_desc)
                    if d:
                        [p.seek(0) for p in photos]
                        w = create_word_doc(d, meta, photos, kop, ttd, {'desc':full_desc}).getvalue()
                        [p.seek(0) for p in photos]
                        p = create_pdf_doc(d, meta, photos, kop, ttd, {'desc':full_desc})
                        st.session_state['generated_file_data'] = {'name': current_rhk, 'word': w, 'pdf': p}
                        simpan_riwayat(current_rhk, "Generated", meta['kel'])
                        st.success("Berhasil!"); st.rerun()
                    else: st.error("Gagal generate konten AI.")

            f = st.session_state.get('generated_file_data')
            if f:
                c1,c2=st.columns(2)
                c1.download_button("📄 Word", f['word'], f"{f['name']}.docx")
                c2.download_button("📕 PDF", f['pdf'], f"{f['name']}.pdf")

    # ==========================================
    # 8. ROUTING
    # ==========================================
    render_sidebar()
    if st.session_state['page'] == 'home': show_dashboard()
    elif st.session_state['page'] == 'detail': show_detail_page()
