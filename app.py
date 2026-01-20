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

# --- DAFTAR USER & PASSWORD (EDIT DISINI) ---
DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# --- SISTEM KEAMANAN (LOGIN DENGAN URL PERSISTENCE) ---
def check_password():
    """Mengembalikan True jika user berhasil login."""
    
    # 1. Cek apakah di memori aplikasi sudah login?
    if st.session_state.get("password_correct", False):
        return True

    # 2. Cek URL Browser (Agar tahan Refresh)
    # Jika URL mengandung data login yang valid, otomatis login kembali
    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True
        st.session_state["username"] = qp.get("user")
        return True

    # TAMPILAN HALAMAN LOGIN
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Silakan masukkan akun Pendamping PKH Anda</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Input Username & Password
        input_user = st.text_input("Username", key="login_user")
        input_pass = st.text_input("Password", type="password", key="login_pass")
        
        # TOMBOL LOGIN
        if st.button("MASUK / LOGIN", type="primary", use_container_width=True):
            if input_user in DAFTAR_USER and DAFTAR_USER[input_user] == input_pass:
                # Set Session State
                st.session_state["password_correct"] = True
                st.session_state["username"] = input_user
                
                # UPDATE URL AGAR TAHAN REFRESH
                st.query_params["auth"] = "valid"
                st.query_params["user"] = input_user
                
                st.rerun()
            else:
                st.error("😕 Username atau Password Salah!")
                
    return False

# --- JALANKAN APLIKASI HANYA JIKA LOGIN SUKSES ---
if check_password():

    # ==========================================
    # KODE APLIKASI UTAMA
    # ==========================================

    # --- API KEY (Manual Input) ---
    GOOGLE_API_KEY = "Apikeydisini"

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest')
    except: pass

    # --- TOMBOL LOGOUT (SIDEBAR) ---
    with st.sidebar:
        st.write(f"👤 Login sebagai: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout", type="secondary"):
            # Reset status login
            st.session_state["password_correct"] = False
            # BERSIHKAN URL AGAR TIDAK AUTO-LOGIN
            st.query_params.clear()
            st.rerun()

    # --- SESSION STATE ---
    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 'db_kpm', 
            'graduasi_raw', 'graduasi_fix', 'generated_file_data', 
            'rhk3_results', 'rhk2_queue', 'rhk2_results', 
            'rhk4_queue', 'rhk4_results',
            'rhk7_queue', 'rhk7_results',
            'tgl_val', 'bln_val', 'th_val'] 

    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    # --- LOGIKA PERSISTENCE HALAMAN (Agar Refresh Tetap di Halaman) ---
    # Jika URL memiliki parameter page/rhk, kembalikan user ke sana
    if "page" in st.query_params:
        st.session_state['page'] = st.query_params["page"]
    
    if "rhk" in st.query_params:
        st.session_state['selected_rhk'] = st.query_params["rhk"]

    # Init Default
    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk4_queue'] is None: st.session_state['rhk4_queue'] = []
    if st.session_state['rhk7_queue'] is None: st.session_state['rhk7_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'

    # Init Tanggal Default
    if 'bln_val' not in st.session_state or st.session_state['bln_val'] is None: 
        st.session_state['bln_val'] = "JANUARI"
    if 'th_val' not in st.session_state or st.session_state['th_val'] is None: 
        st.session_state['th_val'] = "2026"
    if 'tgl_val' not in st.session_state or st.session_state['tgl_val'] is None: 
        st.session_state['tgl_val'] = "30 Januari 2026"

    # ==========================================
    # 2. CONFIG DATA
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
        "RHK 4 – KEGIATAN PEMUTAKHIRAN": [
            "Verifikasi Fasilitas Pendidikan", 
            "Verifikasi Fasilitas Kesehatan", 
            "Verifikasi Kesejahteraan Sosial"
        ],
        "RHK 5 – KPM YANG DIMUTAKHIRKAN": ["Laporan Hasil Pemutakhiran Data KPM"],
        "RHK 6 – LAPORAN KASUS ADAPTIF": ["Laporan Penanganan Kasus (Case Management)"],
        "RHK 7 – LAPORAN DIREKTIF": ["Tugas Direktif Pimpinan (A)", "Tugas Direktif Pimpinan (B)"]
    }

    # ==========================================
    # 3. DATABASE & TOOLS
    # ==========================================
    def init_db():
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
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
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
        c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone()
        conn.close()
        return data

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

    # --- MANAJEMEN FOTO & KOMPRESI ---
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

    # --- TOOLS ---
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

    # ==========================================
    # 4. ENGINE AI (FORMAT KHUSUS)
    # ==========================================
    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, analisis="", app_info="", ket_info=""):
        max_retries = 3
        
        prompt = f"""
        Role: Pendamping PKH Profesional.
        Buat JSON Laporan Kegiatan.
        
        KONTEKS:
        - RHK: {topik} | Nama Kegiatan: {detail} 
        - Lokasi: {lokasi_lengkap} | Periode: {bulan}
        - CATATAN USER (Topik Utama): {ket_info} (Wajib dimasukkan ke narasi sebagai topik utama).
        
        Output JSON Wajib (lowercase key, sesuaikan dengan struktur baru):
        {{
            "gambaran_umum": "Paragraf panjang tentang kondisi umum wilayah dan KPM...\\nParagraf kedua tentang situasi spesifik...",
            "maksud_tujuan": "Paragraf gabungan yang menjelaskan maksud dan tujuan kegiatan secara mengalir...",
            "ruang_lingkup": "Jelaskan ruang lingkup wilayah (Desa/Kecamatan) dan sasaran KPM...",
            "dasar_hukum": ["Permensos No. 1 Tahun 2018", "Pedoman Umum PKH 2021", "Surat Keputusan terkait"],
            "kegiatan": ["Uraian kegiatan 1 secara detail dan deskriptif (naratif)...", "Detail tentang {ket_info}..."],
            "hasil": ["Hasil 1...", "Hasil 2...", "Hasil 3..."],
            "kesimpulan": "Paragraf kesimpulan...",
            "saran": ["Saran 1...", "Saran 2..."],
            "penutup": "Kalimat penutup formal laporan..."
        }}
        """
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                import json
                return json.loads(response.text.replace("```json", "").replace("```", "").strip())
            except Exception as e:
                if attempt < max_retries - 1: time.sleep(2); continue
                else: return None

    # --- WORD (FORMAT CUSTOM + FIRST LINE INDENT) ---
    def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        doc = Document()
        for s in doc.sections: s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
        style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        
        if kop: 
            p = doc.add_paragraph(); p.alignment = 1
            p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
        
        # JUDUL BAKU
        doc.add_paragraph(" ")
        p = doc.add_paragraph(); p.alignment = 1
        # HARDCODED: LAPORAN TENTANG [JUDUL DARI INPUTAN]
        run = p.add_run(f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}")
        run.bold = True; run.font.size = Pt(14)
        doc.add_paragraph(" ")

        def add_p_indent(text, bold=False):
            safe_text = safe_str(text)
            paragraphs = safe_text.split('\n')
            for p_text in paragraphs:
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
            
        for item in data.get('kegiatan', []):
            clean = safe_str(item).replace('\n', ' ')
            add_p_indent(clean)

        doc.add_paragraph("C. Hasil yang dicapai", style='Heading 1')
        if kpm_data and isinstance(kpm_data, dict):
            doc.add_paragraph(f"Profil KPM: {kpm_data.get('Nama')} (NIK: {kpm_data.get('NIK')})")
            
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
        
        p_ttd.add_run(f"Dibuat di {meta['kab']}\n")
        p_ttd.add_run(f"Pada Tanggal {meta['tgl']}\n")
        p_ttd.add_run(f"Pendamping PKH / Layanan Operasional\n")
        
        if ttd:
            p_ttd.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8)); p_ttd.add_run("\n")
        else: p_ttd.add_run("\n\n\n")
        
        p_ttd.add_run(f"\n{meta['nama']}\n").bold = True
        p_ttd.add_run(f"NIP. {meta['nip']}")

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

    # --- PDF (FORMAT CUSTOM + SIMULASI INDENT) ---
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
        for item in data.get('kegiatan', []):
            J_indent(safe_str(item).replace('\n', ' ')); pdf.ln(2)

        pdf.ln(2); pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "C. Hasil yang dicapai", ln=True)
        pdf.set_font("Times", "", 12)
        if kpm_data and isinstance(kpm_data, dict):
            pdf.cell(0, 6, TXT(f"Profil KPM: {kpm_data.get('Nama')} (NIK: {kpm_data.get('NIK')})"), ln=True)
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
    # 5. UI & LOGIKA UTAMA
    # ==========================================
    def update_tanggal_surat():
        bln = st.session_state.get('bln_val', 'JANUARI')
        th = st.session_state.get('th_val', '2026')
        if bln is None: bln = "JANUARI"
        if th is None: th = "2026"
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
            if 'th_val' not in st.session_state: st.session_state['th_val'] = "2026"
            st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal_surat)
        with c2:
            BULAN = ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", 
                     "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]
            if 'bln_val' not in st.session_state: st.session_state['bln_val'] = "JANUARI"
            st.selectbox("Bulan", BULAN, key="bln_val", on_change=update_tanggal_surat)
        
        if 'tgl_val' not in st.session_state: update_tanggal_surat()
        st.sidebar.text_input("Tanggal Surat", key="tgl_val")
        
        st.sidebar.markdown("---")
        jml_foto = count_archived_photos()
        st.sidebar.info(f"📂 **Arsip Foto:** {jml_foto} File")
        
        st.sidebar.header("🖼️ Atribut")
        k = st.sidebar.file_uploader("Kop Surat", type=['png','jpg'])
        t = st.sidebar.file_uploader("Tanda Tangan", type=['png','jpg'])
        
        if st.sidebar.button("💾 SIMPAN PROFIL"):
            save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
            if k: st.session_state['kop_bytes'] = k.getvalue()
            if t: st.session_state['ttd_bytes'] = t.getvalue()
            st.sidebar.success("Profil Tersimpan!")

    def show_dashboard():
        # CSS: HARD FREEZE HEADER
        st.markdown("""
            <style>
            div[data-testid="stVerticalBlock"] > div:first-child {
                position: sticky; top: 0; z-index: 9999; background: white; 
                padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;
            }
            div.stButton > button {
                width: 100%; height: 160px; white-space: pre-wrap;
                font-size: 15px; font-weight: bold; border-radius: 15px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: all 0.3s;
                display: flex; flex-direction: column; align-items: center;
                justify-content: center; text-align: center;
            }
            div.stButton > button:hover {
                transform: translateY(-5px); box-shadow: 0 8px 12px rgba(0,0,0,0.2); border-color: #ff4b4b;
            }
            </style>
        """, unsafe_allow_html=True)

        with st.container():
            st.title("📂 Aplikasi RHK PKH Pro")
            st.markdown("### Menu Utama")
        
        rhk_keys = list(CONFIG_LAPORAN.keys())
        cols = st.columns(4)
        for i, rhk in enumerate(rhk_keys):
            icon = "📄"
            if "RHK 1" in rhk: icon = "💸"
            elif "RHK 2" in rhk: icon = "📚"
            elif "RHK 3" in rhk: icon = "🎓"
            elif "RHK 4" in rhk: icon = "📝"
            elif "RHK 5" in rhk: icon = "👥"
            elif "RHK 6" in rhk: icon = "🆘"
            elif "RHK 7" in rhk: icon = "📢"
            
            parts = rhk.split("–")
            rhk_code = parts[0].strip()
            rhk_title = parts[-1].strip()
            label = f"{icon}\n{rhk_code}\n{rhk_title}"
            
            with cols[i % 4]:
                if st.button(label, key=f"btn_{i}", use_container_width=True):
                    # Set Session State
                    st.session_state['selected_rhk'] = rhk
                    st.session_state['page'] = 'detail'
                    # UPDATE URL (QUERY PARAMS) untuk Persistence saat Refresh
                    st.query_params["page"] = "detail"
                    st.query_params["rhk"] = rhk
                    
                    st.session_state['rhk2_queue'] = []
                    st.session_state['rhk4_queue'] = []
                    st.session_state['rhk7_queue'] = []
                    st.rerun()
        
        # FOOTER
        st.markdown("---")
        st.markdown(
            "<div style='text-align: center; color: grey; font-size: 12px;'>"
            "Copyright © 2026 VHS | All Rights Reserved | Kebijakan Privasi"
            "</div>",
            unsafe_allow_html=True
        )

    def show_detail_page():
        st.markdown("""
            <style>
            div[data-testid="stVerticalBlock"] > div:first-child {
                position: sticky; top: 0; z-index: 9999; background: white; 
                padding-top: 15px; padding-bottom: 15px; border-bottom: 2px solid #ddd;
            }
            </style>
        """, unsafe_allow_html=True)

        current_rhk = st.session_state['selected_rhk']
        
        with st.container():
            st.caption("🚀 Navigasi Cepat:")
            nav_cols = st.columns(8)
            if nav_cols[0].button("🏠 HOME"):
                st.session_state['page'] = 'home'
                # Update URL kembali ke home
                st.query_params["page"] = "home"
                # Hapus param rhk agar bersih
                if "rhk" in st.query_params: del st.query_params["rhk"]
                
                reset_states()
                st.rerun()
            
            rhk_keys = list(CONFIG_LAPORAN.keys())
            col_idx = 1
            for rhk in rhk_keys:
                if rhk != current_rhk: 
                    short_name = rhk.split("–")[0].strip()
                    if col_idx < 8:
                        if nav_cols[col_idx].button(short_name, key=f"nav_{rhk}"):
                            st.session_state['selected_rhk'] = rhk
                            # Update URL saat pindah RHK
                            st.query_params["rhk"] = rhk
                            reset_states()
                            st.rerun()
                        col_idx += 1
        
        st.divider()
        st.subheader(f"{current_rhk}")
        
        # --- LOGIKA DEFAULT JUDUL KOP SURAT (AWALAN KEGIATAN/PELAKSANAAN) ---
        default_judul = "KEGIATAN"
        if "RHK 1" in current_rhk: default_judul = "KEGIATAN PENYALURAN BANTUAN SOSIAL"
        elif "RHK 2" in current_rhk: default_judul = "PELAKSANAAN P2K2 (FDS)"
        elif "RHK 3" in current_rhk: default_judul = "PELAKSANAAN GRADUASI MANDIRI"
        elif "RHK 4" in current_rhk: default_judul = "KEGIATAN PEMUTAKHIRAN DATA"
        elif "RHK 5" in current_rhk: default_judul = "KEGIATAN PEMUTAKHIRAN DATA KPM"
        elif "RHK 6" in current_rhk: default_judul = "PENANGANAN KASUS (CASE MANAGEMENT)"
        elif "RHK 7" in current_rhk: default_judul = "PELAKSANAAN TUGAS DIREKTIF"
        
        # FITUR JUDUL BISA DIEDIT BEBAS
        judul_kop = st.text_input("Judul Kop Laporan (Bisa Diedit):", value=default_judul)
        
        st.divider()

        b = st.session_state.get('bln_val', 'JANUARI')
        t = st.session_state.get('th_val', '2026')
        periode_gabungan = f"{b} {t}"

        meta = {
            'bulan': periode_gabungan,
            'kpm': st.session_state['kpm_global_val'],
            'nama': st.session_state['nama_val'], 'nip': st.session_state['nip_val'],
            'prov': st.session_state['prov_val'], 'kab': st.session_state['kab_val'],
            'kec': st.session_state['kec_val'], 'kel': st.session_state['kel_val'],
            'tgl': st.session_state['tgl_val'],
            'judul': judul_kop # Menggunakan judul dari inputan
        }
        lokasi_lengkap = f"Desa/Kel {meta['kel']}, Kec. {meta['kec']}, {meta['kab']}, {meta['prov']}"
        kop = st.session_state['kop_bytes']; ttd = st.session_state['ttd_bytes']

        is_rhk3 = (current_rhk == "RHK 3 – TARGET GRADUASI MANDIRI")
        is_rhk2 = (current_rhk == "RHK 2 – LAPORAN P2K2 (FDS)")
        is_rhk4 = (current_rhk == "RHK 4 – KEGIATAN PEMUTAKHIRAN")
        is_rhk7 = (current_rhk == "RHK 7 – LAPORAN DIREKTIF")
        is_rhk1 = (current_rhk == "RHK 1 – LAPORAN PENYALURAN")
        is_rhk5 = (current_rhk == "RHK 5 – KPM YANG DIMUTAKHIRKAN")
        is_rhk6 = (current_rhk == "RHK 6 – LAPORAN KASUS ADAPTIF")
        
        def render_photo_manager(key_suffix):
            st.write("#### 📸 Dokumentasi Kegiatan")
            tab_up, tab_arsip = st.tabs(["📤 Upload Baru", "🗂️ Ambil dari Arsip"])
            selected_photos = []
            new_uploads = None
            
            with tab_up:
                new_uploads = st.file_uploader("Pilih File Foto", type=['jpg','png','jpeg'], accept_multiple_files=True, key=f"up_{key_suffix}")
                if new_uploads:
                    for f in new_uploads: selected_photos.append(io.BytesIO(f.getvalue()))
            
            with tab_arsip:
                saved_files = get_archived_photos(current_rhk, meta['bulan'])
                if not saved_files: st.info(f"Belum ada foto di arsip {meta['bulan']}.")
                else:
                    selected_names = st.multiselect("Pilih Foto Lama:", saved_files, key=f"ms_{key_suffix}")
                    for name in selected_names:
                        selected_photos.append(load_photo_from_disk(current_rhk, meta['bulan'], name))
            return selected_photos, new_uploads

        # --- RHK 3 ---
        if is_rhk3:
            st.info("ℹ️ RHK 3: Pilih KPM dari Excel.")
            template_df = pd.DataFrame({"Nama": ["ARJO"], "NIK": ["123"], "Alamat": ["Dusun A"], "Kategori": ["Sejahtera"], "Status":["Graduasi"], "Alasan":["Mampu"]})
            st.download_button("📥 Template Excel", template_df.to_csv(index=False).encode('utf-8'), "template.csv", "text/csv")
            
            upl_grad = st.file_uploader("Upload Excel Graduasi", type=['xlsx', 'csv'])
            if upl_grad:
                try:
                    if upl_grad.name.endswith('.csv'): df = pd.read_csv(upl_grad)
                    else: df = pd.read_excel(upl_grad)
                    st.session_state['graduasi_raw'] = df
                except: st.error("Gagal baca.")
            
            df_raw = st.session_state['graduasi_raw']
            if df_raw is not None:
                if 'Pilih' not in df_raw.columns: df_raw.insert(0, "Pilih", False)
                edited_df = st.data_editor(df_raw, num_rows="dynamic", use_container_width=True)
                if st.button("💾 Simpan Pilihan KPM"):
                    selected = edited_df[edited_df['Pilih'] == True].to_dict('records')
                    st.session_state['graduasi_fix'] = selected
                    st.success(f"Disimpan: {len(selected)} KPM")
            
            # REVISI: Pastikan label bertuliskan (Opsional)
            ket_global = st.text_area("Keterangan Tambahan (Opsional):", placeholder="Contoh: Graduasi mandiri...", height=80)
            final_photos, new_uploads = render_photo_manager("rhk3")

            if st.button("🚀 Buat Laporan Graduasi", type="primary", use_container_width=True):
                if new_uploads: 
                    for f in new_uploads: auto_save_photo_local(f, current_rhk, meta['bulan'])

                kpms = st.session_state.get('graduasi_fix', [])
                if not kpms: st.error("Pilih KPM dulu!"); st.stop()
                results = []
                progress = st.progress(0); status = st.empty()
                
                for i, kpm in enumerate(kpms):
                    nama_kpm = str(kpm.get('Nama', 'KPM'))
                    status.text(f"⏳ Memproses ({i+1}/{len(kpms)}): {nama_kpm}...")
                    
                    data_isi = generate_isi_laporan(current_rhk, f"Laporan Graduasi: {nama_kpm}", meta['kpm'], nama_kpm, meta['bulan'], lokasi_lengkap, ket_info=ket_global)
                    
                    if data_isi:
                        extra_info = {'desc': f"KPM: {nama_kpm}. {ket_global}"}
                        for fp in final_photos: fp.seek(0)
                        w = create_word_doc(data_isi, meta, final_photos, kop, ttd, extra_info, kpm)
                        for fp in final_photos: fp.seek(0)
                        p = create_pdf_doc(data_isi, meta, final_photos, kop, ttd, extra_info, kpm)
                        results.append({'nama': nama_kpm, 'word': w.getvalue(), 'pdf': p})
                    progress.progress((i+1)/len(kpms))
                
                st.session_state['rhk3_results'] = results
                st.success("Selesai!"); st.rerun()

            if st.session_state.get('rhk3_results'):
                st.divider(); st.write("### 📥 Download Laporan:")
                for i, res in enumerate(st.session_state['rhk3_results']):
                    c1, c2, c3 = st.columns([3,1,1])
                    c1.write(f"📄 **{res['nama']}**")
                    c2.download_button("⬇️ Word", res['word'], f"Laporan_{res['nama']}.docx", key=f"w3_{i}")
                    c3.download_button("⬇️ PDF", res['pdf'], f"Laporan_{res['nama']}.pdf", key=f"p3_{i}")
                    st.write("---")

        elif is_rhk2 or is_rhk4 or is_rhk7:
            if is_rhk2: current_queue_key = 'rhk2_queue'; current_results_key = 'rhk2_results'
            elif is_rhk4: current_queue_key = 'rhk4_queue'; current_results_key = 'rhk4_results'
            else: current_queue_key = 'rhk7_queue'; current_results_key = 'rhk7_results'
            
            info_text = "RHK 2: Modul" if is_rhk2 else ("RHK 4: Jenis Pemutakhiran" if is_rhk4 else "RHK 7: Kegiatan Direktif")
            st.info(f"ℹ️ {info_text} -> Isi Detail -> Upload/Pilih Foto -> Antrikan.")
            
            with st.container(border=True):
                st.write("#### ➕ Tambah ke Antrian")
                if is_rhk7:
                    modul_pilihan = st.text_input("Nama Kegiatan Direktif:", placeholder="Contoh: Rapat Koordinasi Kecamatan")
                else:
                    modul_pilihan = st.selectbox("Pilih Laporan:", CONFIG_LAPORAN[current_rhk])
                
                app_pilihan = ""
                if is_rhk4: app_pilihan = st.selectbox("Aplikasi Digunakan:", ["SIKS-NG", "ESDM-PKH", "SIKMA Mobile"])
                
                # REVISI: Pastikan label bertuliskan (Opsional)
                ket_tambahan = st.text_area("Keterangan Tambahan (Opsional):", placeholder="Contoh: Kegiatan berjalan lancar...", height=80)
                
                final_photos, new_uploads = render_photo_manager("queue_rhk")
                
                if st.button("Simpan ke Antrian"):
                    if not final_photos: st.error("Wajib ada foto (Upload Baru atau Dari Arsip)!")
                    elif (is_rhk7 and not modul_pilihan): st.error("Wajib isi nama kegiatan!")
                    else:
                        if new_uploads:
                            for f in new_uploads: auto_save_photo_local(f, current_rhk, meta['bulan'])
                        
                        entry = {
                            "modul": modul_pilihan, "foto": final_photos, "foto_count": len(final_photos),
                            "app": app_pilihan, "desc": ket_tambahan
                        }
                        st.session_state[current_queue_key].append(entry)
                        st.success(f"Berhasil ditambahkan: {modul_pilihan}")
                        time.sleep(0.5); st.rerun()

            queue = st.session_state[current_queue_key]
            if len(queue) > 0:
                st.divider()
                st.write(f"### 📋 Antrian ({len(queue)} Item):")
                for idx, q in enumerate(queue):
                    info = f"{idx+1}. **{q['modul']}** | {q['foto_count']} Foto"
                    if q.get('app'): info += f" | App: {q['app']}"
                    if q.get('desc'): info += f" | Ket: {q['desc'][:30]}..."
                    st.write(info)
                
                c1, c2 = st.columns(2)
                if c1.button("🗑️ Hapus Antrian"): st.session_state[current_queue_key] = []; st.rerun()
                if c2.button("🚀 GENERATE SEMUA", type="primary"):
                    if GOOGLE_API_KEY == "MASUKKAN_KEY_GOOGLE_ANDA_DISINI": st.error("API Key Kosong!"); st.stop()
                    
                    results = []
                    progress = st.progress(0); status = st.empty()
                    for i, item in enumerate(queue):
                        modul_name = item['modul']
                        status.text(f"⏳ Memproses ({i+1}/{len(queue)}): {modul_name}...")
                        
                        detail_kegiatan = f"Nama Kegiatan/Modul: {modul_name}. {item.get('desc', '')}"
                        
                        if is_rhk7:
                            extra_info = {'app': item.get('app'), 'desc': f"{detail_kegiatan} (Laporan Pelaksanaan)"}
                            data_a = generate_isi_laporan(current_rhk, f"{modul_name} (Pelaksanaan)", meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "", item.get('app'), extra_info['desc'])
                            if data_a:
                                for f in item['foto']: f.seek(0)
                                w = create_word_doc(data_a, meta, item['foto'], kop, ttd, extra_info)
                                for f in item['foto']: f.seek(0)
                                p = create_pdf_doc(data_a, meta, item['foto'], kop, ttd, extra_info)
                                results.append({'nama': f"{modul_name} - Pelaksanaan (A)", 'word': w.getvalue(), 'pdf': p})

                            extra_info_b = {'app': item.get('app'), 'desc': f"{detail_kegiatan} (Laporan Hasil Evaluasi)"}
                            data_b = generate_isi_laporan(current_rhk, f"{modul_name} (Hasil)", meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "Evaluasi", item.get('app'), extra_info_b['desc'])
                            if data_b:
                                for f in item['foto']: f.seek(0)
                                w = create_word_doc(data_b, meta, item['foto'], kop, ttd, extra_info_b)
                                for f in item['foto']: f.seek(0)
                                p = create_pdf_doc(data_b, meta, item['foto'], kop, ttd, extra_info_b)
                                results.append({'nama': f"{modul_name} - Hasil (B)", 'word': w.getvalue(), 'pdf': p})
                        else:
                            extra_info = {'app': item.get('app'), 'desc': detail_kegiatan}
                            data_isi = generate_isi_laporan(current_rhk, modul_name, meta['kpm'], "Peserta", meta['bulan'], lokasi_lengkap, "", item.get('app'), detail_kegiatan)
                            if data_isi:
                                for f in item['foto']: f.seek(0)
                                w = create_word_doc(data_isi, meta, item['foto'], kop, ttd, extra_info)
                                for f in item['foto']: f.seek(0)
                                p = create_pdf_doc(data_isi, meta, item['foto'], kop, ttd, extra_info)
                                results.append({'nama': modul_name, 'word': w.getvalue(), 'pdf': p})
                                
                        progress.progress((i+1)/len(queue))
                    
                    st.session_state[current_results_key] = results
                    status.text("✅ Selesai!"); st.rerun()

            res_data = st.session_state.get(current_results_key)
            if res_data:
                st.divider(); st.write("### 📥 Download Hasil:")
                for i, res in enumerate(res_data):
                    c1, c2, c3 = st.columns([3,1,1])
                    c1.write(f"📘 **{res['nama']}**")
                    c2.download_button("⬇️ Word", res['word'], f"{res['nama']}.docx", key=f"wq_{i}")
                    c3.download_button("⬇️ PDF", res['pdf'], f"{res['nama']}.pdf", key=f"pq_{i}")
                    st.write("---")

        # --- RHK LAIN (BIASA - RHK 1, 5, 6) ---
        else:
            daftar_sub = CONFIG_LAPORAN[current_rhk]
            
            # LOGIKA OTOMATIS: JIKA RHK 1,5,6 -> Judul Spesifik Otomatis dari Config
            if is_rhk1 or is_rhk5 or is_rhk6:
                judul_spesifik = daftar_sub[0] # Ambil yang pertama (default)
                st.info(f"📌 **Nama Kegiatan:** {judul_spesifik}") # Tampilkan sebagai Info statis
            else:
                # Jika ada RHK lain yang butuh input manual
                judul_spesifik = st.text_input("Nama Kegiatan:", value=daftar_sub[0] if daftar_sub else "")
            
            # REVISI: Pastikan label bertuliskan (Opsional)
            ket_umum = st.text_area("Keterangan Tambahan (Opsional):", placeholder="Contoh: Kegiatan berjalan lancar...", height=80)
            final_photos, new_uploads = render_photo_manager("biasa")

            if st.button("🚀 Buat Laporan", type="primary", use_container_width=True):
                if GOOGLE_API_KEY == "MASUKKAN_KEY_GOOGLE_ANDA_DISINI":
                    st.error("API Key Kosong!")
                else:
                    with st.spinner("Memproses..."):
                        if new_uploads:
                            for f in new_uploads: auto_save_photo_local(f, current_rhk, meta['bulan'])

                        lokasi_lengkap = f"Desa/Kel {meta['kel']}, Kec. {meta['kec']}, {meta['kab']}, {meta['prov']}"
                        full_desc = f"Kegiatan: {judul_spesifik}. {ket_umum}"
                        data_isi = generate_isi_laporan(current_rhk, judul_spesifik, meta['kpm'], f"{meta['kpm']} Peserta", meta['bulan'], lokasi_lengkap, ket_info=full_desc)
                        
                        if data_isi:
                            extra_info = {'desc': full_desc}
                            for fp in final_photos: fp.seek(0)
                            w = create_word_doc(data_isi, meta, final_photos, kop, ttd, extra_info)
                            for fp in final_photos: fp.seek(0)
                            p = create_pdf_doc(data_isi, meta, final_photos, kop, ttd, extra_info)
                            st.session_state['generated_file_data'] = {'type': 'single', 'word': w.getvalue(), 'pdf': p, 'name': current_rhk}
                            st.success("✅ Berhasil!"); st.rerun()
                    
                    simpan_riwayat(current_rhk, "Generated", meta['kel'])

            files = st.session_state.get('generated_file_data')
            if files:
                st.divider()
                c1, c2 = st.columns(2)
                c1.download_button("📄 Download WORD", files['word'], f"{files['name']}.docx", "application/docx")
                c2.download_button("📕 Download PDF", files['pdf'], f"{files['name']}.pdf", "application/pdf")

    # ==========================================
    # 6. ROUTING
    # ==========================================
    render_sidebar()
    if st.session_state['page'] == 'home': show_dashboard()
    elif st.session_state['page'] == 'detail': show_detail_page()
