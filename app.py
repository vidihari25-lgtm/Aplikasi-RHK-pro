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
st.set_page_config(page_title="Aplikasi RHK PKH Pro 2.0", layout="wide")

# ==========================================
# 2. DEFINISI CONFIG (GLOBAL)
# ==========================================
CONFIG_LAPORAN = {
    "RHK 1 – Laporan Penyaluran bansos": [
        "Melakukan edukasi dan sosialisasi pencairan secara tunai dan non tunai",
        "Melaksanakan Supervisi Permasalahan Bantuan Sosial",
        "Melaksanakan Monitoring/Pemantauan Penyaluran Bantuan Sosial",
        "Melaksanakan Penelitian penyaluran bantuan Sosial"
    ],
    "RHK 2 – Laporan pertemuan P2K2": [
        "Melaksanakan Pertemuan Peningkatan Kemampuan Keluarga (P2K2)"
    ],
    "RHK 3 – Laporan Verifikasi Komitmen dan Pendampingan KPM": [
        "Melaksanakan Verifikasi Komitmen Pendidikan,Kesehatan dan Kesejahteraan Sosial",
        "Melakukan pendampingan, mediasi, dan fasilitasi kepada KPM PKH dalam proses perubahan perilaku, pola pikir yang mandiri dan produktif"
    ],
    "RHK 4 – Rekapitulasi Data KPM graduasi": [
        "Melakukan usulan KPM Graduasi mandiri dan Pemberdayaan PPSE"
    ],
    "RHK 5 – Laporan Data Verifikasi, Validasi dan pemutakhiran data KPM": [
        "Melaksanakan Pemutakhiran Data",
        "Melaksanakan proses bisnis PKH yang meliputi verifikasi validasi calon penerima bantuan sosial"
    ],
    "RHK 6 – persentase penyelesaian laporan kasus adaptif": [
        "Melaksanakan Respon Kasus/Pengaduan/kebencanaan/Kerentanan"
    ],
    "RHK 7 – Laporan Bulanan ASN PPPK": [
        "Membuat laporan bulanan pelaksanaan PKH dan laporan lainnya."
    ],
    "RHK 8 – laporan pelaksana Tugas direktif": [
        "Melaksanakan Tindak Lanjut Hasil Pemeriksaan (TLHP)",
        "Melakukan sosialisasi kebijakan dan bisnis proses PKH kepada aparat pemerintah tingkat kecamatan, desa/ kelurahan, KPM PKH, dan masyarakat umum secara berkala melalui Pertemuan atau media sosial dll",
        "Mengikuti Rapat Koordinasi, Sosialisasi Kebijakan Proses Bisnis PKH dan Penguatan Kapasitas SDM.",
        "Tugas Lainnya (Penugasan lainnya program Kementrian Sosial)"
    ],
    "RHK 9 – Presentase Penyelesaian Penugasan Direktif Pimpinan": [
        "Berperan aktif dalam memanfaatkan, menggunakan, melibatkan dan menyebarkan Media Sosial untuk menyampaikan semua program di Kementerian Sosial"
    ]
}

DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# --- RESET SESSION JIKA CONFIG BERUBAH ---
if 'selected_rhk' in st.session_state:
    if st.session_state['selected_rhk'] is not None:
        if st.session_state['selected_rhk'] not in CONFIG_LAPORAN:
            st.session_state.clear()
            st.rerun()

# ==========================================
# 3. HELPER FUNCTIONS (IMAGE, TEXT, DB)
# ==========================================

def init_db():
    conn = sqlite3.connect('rhk_pro_fixed.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
    c.execute('SELECT count(*) FROM user_settings')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO user_settings (id, nama, nip, kpm, prov, kab, kec, kel) VALUES (1, ?, ?, ?, ?, ?, ?, ?)', ("Pendamping PKH", "19xxxx", 100, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan"))
    conn.commit(); conn.close()

def get_user_settings():
    conn = sqlite3.connect('rhk_pro_fixed.db'); c = conn.cursor()
    c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
    data = c.fetchone(); conn.close(); return data

def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
    conn = sqlite3.connect('rhk_pro_fixed.db'); c = conn.cursor()
    c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
    conn.commit(); conn.close()

def compress_image(uploaded_file, quality=60, max_width=600):
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

def clean_text_for_pdf(text):
    if text is None: return "-" 
    text = str(text) 
    text = text.replace('\u2013', '-').replace('\u201c', '"').replace('\u201d', '"')
    # Replace karakter aneh lainnya jika perlu
    return text.encode('latin-1', 'replace').decode('latin-1')

# ==========================================
# 4. GENERATOR AI & DOKUMEN
# ==========================================

# Setup AI
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"Gagal konfigurasi AI: {e}")

def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, ket_info=""):
    # UPDATE PROMPT: Menambahkan instruksi bahasa birokrasi
    prompt = f"""
    Role: Pendamping PKH Profesional Kemensos RI.
    Tugas: Buat JSON konten Laporan Kegiatan Bulanan.
    
    Konteks Data:
    - Topik: {topik}
    - Detail Kegiatan: {detail}
    - Lokasi & Waktu: {lokasi_lengkap}, Bulan {bulan}
    - Catatan Tambahan User: {ket_info}
    
    Instruksi Gaya Bahasa:
    - Gunakan bahasa Indonesia yang baku, formal, dan bergaya birokrasi pemerintahan.
    - Objektif, jelas, dan menggunakan istilah teknis pekerjaan sosial (KPM, Graduasi, P2K2, Termin, DTKS, SIKS-NG).
    - Hindari pengulangan kalimat yang tidak perlu.
    
    Output JSON (lowercase key):
    {{
        "gambaran_umum": "Paragraf pendahuluan...",
        "maksud_tujuan": "Paragraf tujuan kegiatan...",
        "ruang_lingkup": "Paragraf ruang lingkup...",
        "dasar_hukum": ["Undang-Undang terkait...", "Permensos terkait..."],
        "kegiatan": ["Rincian proses kegiatan 1...", "Rincian proses kegiatan 2..."],
        "hasil": ["Hasil konkret 1...", "Hasil konkret 2..."],
        "kesimpulan": "Paragraf kesimpulan...",
        "saran": ["Saran tindak lanjut 1...", "Saran tindak lanjut 2..."],
        "penutup": "Paragraf penutup..."
    }}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        # UPDATE: Error Handling lebih spesifik
        if "429" in str(e):
            st.error("⚠️ Kuota AI Penuh (Rate Limit). Tunggu 1 menit sebelum mencoba lagi.")
        else:
            st.error(f"Error AI: {e}")
        return None

def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    if data is None: return None
    doc = Document()
    for s in doc.sections: 
        s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
    
    if kop: 
        try:
            p = doc.add_paragraph(); p.alignment = 1
            p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
        except: pass
    
    p = doc.add_paragraph(f"\nLAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}"); p.alignment = 1; p.runs[0].bold = True
    
    def add_section(title, content, is_list=False):
        doc.add_paragraph(title, style='Heading 1')
        if content is None: content = "-"
        if is_list:
            if isinstance(content, list):
                for item in content: doc.add_paragraph(str(item), style='List Bullet')
            else: doc.add_paragraph(str(content), style='List Bullet')
        else:
            doc.add_paragraph(str(content)).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    add_section("A. Pendahuluan", data.get('gambaran_umum', '-'))
    add_section("B. Maksud & Tujuan", data.get('maksud_tujuan', '-'))
    
    doc.add_paragraph("C. Pelaksanaan Kegiatan", style='Heading 1')
    if extra_info: doc.add_paragraph(f"Catatan: {extra_info}", style='Quote')
    keg = data.get('kegiatan', [])
    if keg:
        for k in keg: doc.add_paragraph(str(k), style='List Bullet')

    if kpm_data:
        doc.add_paragraph("Data KPM Terkait:", style='Heading 2')
        table = doc.add_table(rows=1, cols=2); table.style = 'Table Grid'
        for k, v in kpm_data.items():
            row = table.add_row().cells
            row[0].text = str(k); row[1].text = str(v)
        doc.add_paragraph("\n")

    add_section("D. Hasil", data.get('hasil', []), True)
    add_section("E. Penutup", data.get('penutup', '-'))

    doc.add_paragraph("\n\n")
    table = doc.add_table(rows=1, cols=2); table.autofit = False
    table.columns[0].width = Inches(3); table.columns[1].width = Inches(3)
    c2 = table.cell(0, 1).paragraphs[0]; c2.alignment = 1
    c2.add_run(f"{meta['kab']}, {meta['tgl']}\nPengelola Layanan Operasional\n\n")
    if ttd: 
        try: c2.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
        except: pass
    c2.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}")

    if imgs:
        doc.add_page_break()
        doc.add_paragraph("DOKUMENTASI", style='Heading 1').alignment = 1
        for img in imgs:
            try:
                doc.add_paragraph().alignment = 1
                doc.add_picture(compress_image(img), width=Inches(3.5))
            except: pass
    
    bio = io.BytesIO(); doc.save(bio); return bio

# --- FUNGSI PDF DIPERBAIKI (UPDATED KOP 80%) ---
def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
    if data is None: return None
    
    # 1. Setup Halaman A4
    pdf = FPDF('P', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # 2. KOP SURAT (Revisi: Lebar 80% dari A4)
    if kop:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(kop)
            tmp.flush()
            tmp_path = tmp.name
        try:
            # Hitung Dimensi
            # Lebar A4 = 210mm
            # Lebar Kop 80% = 210 * 0.8 = 168mm
            # Posisi X agar tengah = (210 - 168) / 2 = 21mm
            
            w_kop = 210 * 0.8
            x_kop = (210 - w_kop) / 2
            
            # Pasang Gambar
            pdf.image(tmp_path, x=x_kop, y=0, w=w_kop)
            
            # Paksa kursor turun 38mm agar tidak menimpa kop (atur sesuai tinggi kop visual)
            pdf.set_y(38) 
        except: 
            pdf.ln(10)
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)
    else:
        pdf.ln(10)

    # 3. JUDUL
    pdf.set_font("Arial", "B", 12)
    title_text = f"LAPORAN\nTENTANG\n{clean_text_for_pdf(meta['judul'].upper())}\n{clean_text_for_pdf(meta['bulan'].upper())}"
    pdf.multi_cell(0, 6, title_text, align='C')
    pdf.ln(8)

    # Helper Section
    def add_section_pdf(title, content, is_list=False):
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 7, clean_text_for_pdf(title), ln=True)
        pdf.set_font("Arial", "", 11)
        
        if content is None: content = "-"
        
        if is_list and isinstance(content, list):
            for item in content:
                pdf.set_x(25) # Indentasi
                pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(item)}")
        else:
            pdf.multi_cell(0, 6, clean_text_for_pdf(str(content)))
        pdf.ln(3)

    # Isi Laporan
    add_section_pdf("A. Pendahuluan", data.get('gambaran_umum'))
    add_section_pdf("B. Maksud & Tujuan", data.get('maksud_tujuan'))

    # C. Pelaksanaan
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 7, "C. Pelaksanaan Kegiatan", ln=True)
    pdf.set_font("Arial", "", 11)
    if extra_info:
        pdf.set_font("Arial", "I", 10)
        pdf.multi_cell(0, 6, f"Catatan: {clean_text_for_pdf(extra_info)}")
        pdf.set_font("Arial", "", 11)
    
    keg = data.get('kegiatan', [])
    if keg:
        for k in keg:
            pdf.set_x(25)
            pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(k)}")
    pdf.ln(3)

    if kpm_data:
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 7, "Data KPM Terkait:", ln=True)
        pdf.set_font("Arial", "", 10)
        col_w = 85
        for k, v in kpm_data.items():
            pdf.cell(col_w, 6, clean_text_for_pdf(str(k)), border=1)
            pdf.cell(col_w, 6, clean_text_for_pdf(str(v)), border=1, ln=True)
        pdf.ln(5)

    add_section_pdf("D. Hasil", data.get('hasil', True))
    add_section_pdf("E. Penutup", data.get('penutup'))

    # 4. TANDA TANGAN (Layout Kanan)
    if pdf.get_y() > 220: pdf.add_page()
    else: pdf.ln(10)
    
    pdf.set_font("Arial", "", 11)
    x_block = 130 # Koordinat X untuk blok kanan
    w_block = 60  # Lebar blok tanda tangan
    
    # Tanggal & Jabatan
    pdf.set_x(x_block)
    pdf.multi_cell(w_block, 6, f"{clean_text_for_pdf(meta['kab'])}, {clean_text_for_pdf(meta['tgl'])}", align='C')
    pdf.set_x(x_block)
    pdf.multi_cell(w_block, 6, "Pengelola Layanan Operasional", align='C')
    
    # Gambar TTD
    if ttd:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_ttd:
            tmp_ttd.write(ttd)
            tmp_ttd.flush()
            tmp_ttd.flush()
            ttd_path = tmp_ttd.name
        try:
            y_img = pdf.get_y()
            # Gambar ditaruh di tengah blok, tinggi fix 25mm
            pdf.image(ttd_path, x=x_block + 5, y=y_img, h=25)
            pdf.set_y(y_img + 27)
        except: pdf.ln(25)
        finally:
            if os.path.exists(ttd_path): os.remove(ttd_path)
    else:
        pdf.ln(25)
    
    # Nama & NIP
    pdf.set_x(x_block)
    pdf.set_font("Arial", "BU", 11)
    pdf.cell(w_block, 6, clean_text_for_pdf(meta['nama']), ln=True, align='C')
    
    pdf.set_x(x_block)
    pdf.set_font("Arial", "", 11)
    pdf.cell(w_block, 6, f"NIP. {clean_text_for_pdf(meta['nip'])}", ln=True, align='C')

    # 5. DOKUMENTASI
    if imgs:
        pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "DOKUMENTASI KEGIATAN", ln=True, align='C')
        pdf.ln(5)
        for img_bytes in imgs:
            compressed = compress_image(img_bytes)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_img:
                tmp_img.write(compressed.getvalue())
                tmp_img.flush()
                img_path = tmp_img.name
            try:
                x_center = (210 - 120) / 2
                pdf.image(img_path, x=x_center, w=120)
                pdf.ln(5)
            except: pass
            finally:
                if os.path.exists(img_path): os.remove(img_path)

    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 5. UI & LOGIC UTAMA
# ==========================================

def check_password():
    if st.session_state.get("password_correct", False): return True
    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True; st.session_state["username"] = qp.get("user"); return True

    st.markdown("<br><br><h1 style='text-align: center;'>🔐 LOGIN APP RHK</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            input_user = st.text_input("Username")
            input_pass = st.text_input("Password", type="password")
            if st.form_submit_button("MASUK / LOGIN", type="primary", use_container_width=True):
                if input_user in DAFTAR_USER and DAFTAR_USER[input_user] == input_pass:
                    st.session_state["password_correct"] = True
                    st.session_state["username"] = input_user
                    st.query_params["auth"] = "valid"; st.query_params["user"] = input_user
                    st.rerun()
                else: st.error("😕 Username atau Password Salah!")
    return False

if check_password():
    # SETUP STATE
    init_db()
    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 
            'rhk2_queue', 'rhk2_results', 
            'rhk3_queue', 'rhk3_results', 
            'rhk4_graduasi_results',
            'rhk8_queue', 'rhk8_results', 
            'generated_file_data', 'tgl_val', 'bln_val', 'th_val'] 
    
    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk3_queue'] is None: st.session_state['rhk3_queue'] = []
    if st.session_state['rhk8_queue'] is None: st.session_state['rhk8_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'
    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    if not st.session_state['tgl_val']: st.session_state['tgl_val'] = "30 Januari 2026"

    # UI SIDEBAR
    def update_tanggal():
        st.session_state.tgl_val = f"30 {st.session_state.bln_val.title()} {st.session_state.th_val}"

    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
    with st.sidebar:
        st.write(f"👤 User: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout", type="primary"):
            st.session_state["password_correct"] = False
            st.query_params.clear()
            st.rerun()
        
        with st.expander("👤 Profil", expanded=False):
            with st.form("profil_form"):
                nama = st.text_input("Nama", u_nama)
                nip = st.text_input("NIP", u_nip)
                kpm = st.number_input("Jml KPM", value=u_kpm)
                prov = st.text_input("Provinsi", u_prov)
                kab = st.text_input("Kabupaten", u_kab)
                kec = st.text_input("Kecamatan", u_kec)
                kel = st.text_input("Kelurahan", u_kel)
                if st.form_submit_button("Simpan Profil"):
                    save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
                    st.success("Tersimpan!"); st.rerun()

        st.markdown("---")
        st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], key="bln_val", on_change=update_tanggal)
        st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal)
        st.text_input("Tanggal Surat", key="tgl_val")
        st.markdown("---")
        st.file_uploader("Kop Surat (JPG/PNG)", type=['png','jpg'], key="kop_up")
        if st.session_state.get('kop_up'): st.session_state['kop_bytes'] = st.session_state['kop_up'].getvalue()
        
        st.file_uploader("Tanda Tangan (JPG/PNG)", type=['png','jpg'], key="ttd_up")
        if st.session_state.get('ttd_up'): st.session_state['ttd_bytes'] = st.session_state['ttd_up'].getvalue()

    # UI MAIN
    def show_dashboard():
        st.title("📂 Aplikasi RHK PKH Pro 2.0"); cols = st.columns(3)
        for i, rhk in enumerate(CONFIG_LAPORAN.keys()):
            with cols[i % 3]:
                st.markdown(f"""<div style="background-color:#f0f2f6; padding:15px; border-radius:10px; margin-bottom:10px; border:1px solid #d1d5db;"><b>{rhk.split('–')[0]}</b><br><small>{rhk.split('–')[-1]}</small></div>""", unsafe_allow_html=True)
                if st.button(f"Buka {rhk.split('–')[0]}", key=f"nav_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'; st.rerun()

    def show_detail():
        rhk = st.session_state.get('selected_rhk')
        if rhk not in CONFIG_LAPORAN:
            st.warning("🔄 Refreshing session..."); st.session_state['page'] = 'home'; st.rerun(); return

        c1, c2 = st.columns([1, 6])
        if c1.button("⬅️ Kembali", use_container_width=True): st.session_state['page'] = 'home'; st.rerun()
        c2.markdown(f"### 📝 {rhk}")
        
        meta = {'bulan': f"{st.session_state.bln_val} {st.session_state.th_val}", 'nama': u_nama, 'nip': u_nip, 'kab': u_kab, 'kec': u_kec, 'kel': u_kel, 'tgl': st.session_state.tgl_val, 'judul': rhk.split('–')[-1].upper()}
        lokasi = f"{u_kel}, {u_kec}, {u_kab}"
        
        # LOGIKA TAMPILAN
        if "RHK 2" in rhk or "RHK 3" in rhk or "RHK 8" in rhk:
            q_key = 'rhk2_queue' if "RHK 2" in rhk else ('rhk3_queue' if "RHK 3" in rhk else 'rhk8_queue')
            r_key = q_key.replace('queue', 'results')
            st.info("💡 **Mode Antrian:** Masukkan kegiatan satu per satu, lalu klik 'Generate Semua'.")
            
            # --- UPDATE: DATA MODUL P2K2 ---
            DATA_P2K2 = {
                "Modul Ekonomi": [
                    "1. Mengelola Keuangan Keluarga",
                    "2. Cermat Meminjam dan Menabung",
                    "3. Memulai Usaha"
                ],
                "Modul Kesehatan dan Gizi": [
                    "1. Pentingnya Gizi dan Layanan Ibu Hamil",
                    "2. Pentingnya Gizi Untuk Ibu Menyusui dan Balita",
                    "3. Kesakitan pada Anak dan Kesehatan Lingkungan"
                ],
                "Modul Kesejahteraan": [
                    "1. Pelayanan bagi Penyandang Disabilitas Berat",
                    "2. Pentingnya Kesejahteraan Lanjut Usia"
                ],
                "Modul Pengasuhan dan Pendidikan": [
                    "1. Menjadi Orang Tua yang Lebih Baik",
                    "2. Memahami Perilaku Anak",
                    "3. Memahami Cara Anak Usia Dini Belajar",
                    "4. Membantu Anak Sukses di Sekolah"
                ],
                "Modul Perlindungan Anak": [
                    "1. Pencegahan Kekerasan Terhadap Anak",
                    "2. Penelantaran dan Eksploitasi Anak"
                ],
                "Modul Stunting": [
                    "1. Pencegahan dan Penanganan Stunting",
                    "2. Dukungan Pemenuhan Kesejahteraan Bayi Baru Lahir dan Ibu Menyusui"
                ]
            }

            # --- KHUSUS RHK 2 (MODUL P2K2) ---
            if "RHK 2" in rhk:
                # Selectbox ditaruh DI LUAR form agar interaktif (Modul -> Sesi berubah otomatis)
                kegiatan = st.selectbox("Sub-Kegiatan", CONFIG_LAPORAN[rhk])
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    # Pilih Modul
                    pilih_modul = st.selectbox("Pilih Modul P2K2", list(DATA_P2K2.keys()), key="p2k2_modul_sel")
                with col_m2:
                    # Pilih Sesi (Otomatis berubah sesuai Modul yang dipilih)
                    opsi_sesi = DATA_P2K2.get(pilih_modul, ["-"])
                    pilih_sesi = st.selectbox("Pilih Sesi", opsi_sesi, key="p2k2_sesi_sel")

                # Form Sisanya (Keterangan & Foto)
                with st.form("queue_form_rhk2", clear_on_submit=True):
                    ket_q = st.text_input("Keterangan Tambahan", placeholder="Nama Kelompok / Lokasi / Jumlah Peserta...")
                    fotos = st.file_uploader("Foto Kegiatan", accept_multiple_files=True, type=['jpg','png'])
                    
                    if st.form_submit_button("➕ Tambah ke Antrian"):
                        if not fotos:
                            st.error("❌ Foto wajib diupload!")
                        else:
                            # Gabungkan Modul & Sesi ke dalam judul/keterangan agar masuk laporan
                            final_judul = f"{kegiatan} - {pilih_modul}"
                            final_ket = f"Materi: {pilih_sesi}. Keterangan: {ket_q}"
                            
                            st.session_state[q_key].append({
                                "kegiatan": final_judul, 
                                "ket": final_ket, 
                                "fotos": [io.BytesIO(f.getvalue()) for f in fotos]
                            })
                            st.success(f"Berhasil: {pilih_sesi} ditambahkan!")
                            st.rerun()

            # --- UNTUK RHK 3 DAN RHK 8 (FORMAT LAMA) ---
            else:
                with st.form("queue_form", clear_on_submit=True):
                    try: kegiatan = st.selectbox("Sub-Kegiatan", CONFIG_LAPORAN[rhk])
                    except: kegiatan = "Kegiatan Umum"
                    ket_q = st.text_input("Keterangan", placeholder="Detail lokasi/peserta...")
                    fotos = st.file_uploader("Foto", accept_multiple_files=True, type=['jpg','png'])
                    if st.form_submit_button("➕ Tambah"):
                        if not fotos: st.error("❌ Foto wajib!")
                        else:
                            st.session_state[q_key].append({"kegiatan": kegiatan, "ket": ket_q, "fotos": [io.BytesIO(f.getvalue()) for f in fotos]})
                            st.success("Masuk antrian!"); st.rerun()
            
            # --- TAMPILAN ANTRIAN (DENGAN FITUR HAPUS) ---
            queue = st.session_state[q_key]
            if queue:
                st.write(f"**Antrian ({len(queue)} Item):**")
                
                # Loop dengan fitur Hapus
                for i, q in enumerate(queue):
                    col_txt, col_del = st.columns([0.85, 0.15])
                    with col_txt:
                        st.text(f"{i+1}. {q['kegiatan']} - {q['ket']}")
                    with col_del:
                        if st.button("🗑️ Hapus", key=f"del_{q_key}_{i}"):
                            st.session_state[q_key].pop(i)
                            st.rerun()

                if st.button("🚀 GENERATE SEMUA", type="primary"):
                    results = []; bar = st.progress(0)
                    with st.spinner("Sedang menghubungi AI dan menyusun dokumen..."):
                        for i, item in enumerate(queue):
                            # Panggil AI generate
                            jd = generate_isi_laporan(rhk, item['kegiatan'], u_kpm, "Peserta", meta['bulan'], lokasi, item['ket'])
                            if jd: 
                                w = create_word_doc(jd, meta, item['fotos'], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], item['ket'])
                                p = create_pdf_doc(jd, meta, item['fotos'], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], item['ket'])
                                if w: results.append({"judul": item['kegiatan'], "file": w, "file_pdf": p})
                            bar.progress((i + 1) / len(queue))
                    st.session_state[r_key] = results; st.success("Selesai!"); st.rerun()
            
            if st.session_state.get(r_key):
                st.write("### 📥 Download Hasil")
                for i, r in enumerate(st.session_state[r_key]):
                    c1, c2 = st.columns(2)
                    with c1: st.download_button(f"📄 Word: {r['judul']}", r['file'], f"{r['judul']}.docx", key=f"dw{i}", use_container_width=True)
                    with c2: 
                        if r.get('file_pdf'): st.download_button(f"📕 PDF: {r['judul']}", r['file_pdf'], f"{r['judul']}.pdf", key=f"dp{i}", use_container_width=True)

        elif "RHK 4" in rhk:
            st.info("ℹ️ **Mode Graduasi:** Upload Excel KPM.")
            df_tmpl = pd.DataFrame({"Nama": ["Budi"], "NIK": ["123"], "Alamat": ["Desa A"], "Kategori": ["PKH"], "Status": ["Graduasi"], "Alasan": ["Mampu"]})
            buf = io.BytesIO(); df_tmpl.to_excel(buf, index=False); buf.seek(0)
            st.download_button("📥 Template Excel", buf, "Template.xlsx")
            
            upl = st.file_uploader("Upload Excel", type=['xlsx'])
            if upl:
                try:
                    df = pd.read_excel(upl)
                    sel_kpm = st.multiselect("Pilih KPM", df['Nama'].tolist()) if 'Nama' in df.columns else []
                    if sel_kpm:
                        photos = st.file_uploader("Foto", accept_multiple_files=True)
                        if st.button("🚀 Generate") and photos:
                            res = []; p_data = [io.BytesIO(f.getvalue()) for f in photos]; bar = st.progress(0)
                            with st.spinner("Memproses data graduasi..."):
                                for i, nm in enumerate(sel_kpm):
                                    row = df[df['Nama'] == nm].iloc[0].to_dict()
                                    jd = generate_isi_laporan(rhk, f"Graduasi {nm}", 1, nm, meta['bulan'], lokasi, f"Graduasi {nm}")
                                    if jd:
                                        w = create_word_doc(jd, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], f"Graduasi {nm}", row)
                                        p = create_pdf_doc(jd, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], f"Graduasi {nm}", row)
                                        if w: res.append({"judul": nm, "file": w, "file_pdf": p})
                                    bar.progress((i+1)/len(sel_kpm))
                            st.session_state['rhk4_graduasi_results'] = res; st.rerun()
                except: st.error("Format Excel Salah")
            
            if st.session_state.get('rhk4_graduasi_results'):
                for i, r in enumerate(st.session_state['rhk4_graduasi_results']):
                    c1, c2 = st.columns(2)
                    with c1: st.download_button(f"📥 Word: {r['judul']}", r['file'], f"Graduasi_{r['judul']}.docx", key=f"dgw{i}", use_container_width=True)
                    with c2: 
                        if r.get('file_pdf'): st.download_button(f"📥 PDF: {r['judul']}", r['file_pdf'], f"Graduasi_{r['judul']}.pdf", key=f"dgp{i}", use_container_width=True)

        else:
            with st.form("std_form"):
                try: jk = st.selectbox("Kegiatan", CONFIG_LAPORAN[rhk])
                except: jk = "Kegiatan Umum"
                ka = st.text_area("Keterangan")
                ft = st.file_uploader("Foto", accept_multiple_files=True)
                if st.form_submit_button("🚀 BUAT LAPORAN", type="primary"):
                    if not ft: st.error("Foto wajib!")
                    else:
                        with st.spinner("Sedang menghubungi AI dan menyusun dokumen..."):
                            jd = generate_isi_laporan(rhk, jk, u_kpm, "Peserta", meta['bulan'], lokasi, ka)
                            if jd:
                                imgs_data = [io.BytesIO(f.getvalue()) for f in ft]
                                w = create_word_doc(jd, meta, imgs_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], ka)
                                p = create_pdf_doc(jd, meta, imgs_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], ka)
                                if w:
                                    st.session_state['generated_file_data'] = {"name": f"Laporan {jk}", "file": w, "file_pdf": p}
                                    st.rerun()
                            else: st.error("Gagal koneksi AI, coba lagi.")
            
            if st.session_state.get('generated_file_data'):
                f = st.session_state['generated_file_data']
                st.success("Selesai!")
                c1, c2 = st.columns(2)
                with c1: st.download_button("📥 Download Word", f['file'], f"{f['name']}.docx", type="primary", use_container_width=True)
                with c2: 
                    if f.get('file_pdf'): st.download_button("📕 Download PDF", f['file_pdf'], f"{f['name']}.pdf", type="secondary", use_container_width=True)

    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail()
