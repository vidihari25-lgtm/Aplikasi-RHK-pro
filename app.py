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
# 2. DEFINISI CONFIG (DITARUH DI ATAS AGAR AMAN)
# ==========================================
# UPDATE: Disesuaikan dengan Tabel Indikator Kinerja Individu & Pilihan Laporan Harian
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

# --- PERBAIKAN VITAL: RESET SESI OTOMATIS (SELF-HEALING) ---
# Kode ini mendeteksi jika browser menyimpan nama RHK lama yang tidak ada di config baru
if 'selected_rhk' in st.session_state:
    if st.session_state['selected_rhk'] is not None:
        if st.session_state['selected_rhk'] not in CONFIG_LAPORAN:
            # Jika RHK di memori tidak dikenali, hapus semua memori
            st.session_state.clear()
            st.rerun()

# --- DAFTAR USER & PASSWORD ---
DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# ==========================================
# 3. SISTEM KEAMANAN & LOGIN
# ==========================================

try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except FileNotFoundError:
    st.error("🚨 File .streamlit/secrets.toml tidak ditemukan!")
    st.stop()
except KeyError:
    st.error("🚨 Key 'GOOGLE_API_KEY' tidak ditemukan di secrets.toml.")
    st.stop()

# --- KONFIGURASI AI (GEMINI 2.0 FLASH) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"Gagal konfigurasi AI: {e}")

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

    # ==========================================
    # 4. SETUP & INIT STATE
    # ==========================================

    with st.sidebar:
        st.write(f"👤 User: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout", type="primary"):
            st.session_state["password_correct"] = False
            st.query_params.clear()
            st.rerun()

    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 
            'graduasi_raw', 'graduasi_fix', 'generated_file_data', 
            'rhk2_queue', 'rhk2_results', 
            'rhk3_queue', 'rhk3_results', 
            'rhk4_graduasi_results',
            'rhk8_queue', 'rhk8_results', 
            'tgl_val', 'bln_val', 'th_val'] 

    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk3_queue'] is None: st.session_state['rhk3_queue'] = []
    if st.session_state['rhk8_queue'] is None: st.session_state['rhk8_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'
    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    if not st.session_state['tgl_val']: st.session_state['tgl_val'] = "30 Januari 2026"

    # --- Database Sederhana ---
    def init_db():
        conn = sqlite3.connect('rhk_pro_fixed.db') # Ganti nama DB biar fresh
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

    init_db()

    # --- Tools Gambar ---
    BASE_ARSIP = "Arsip_Foto_Kegiatan"
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

    def auto_save_photo_local(uploaded_file_obj, rhk_name, periode_str):
        try:
            clean_rhk = re.sub(r'[\\/*?:"<>|]', "", rhk_name.split("–")[0].strip())
            parts=periode_str.split(" "); b=parts[0]; t=parts[1]
            target_folder = os.path.join(BASE_ARSIP, t, b, clean_rhk)
            if not os.path.exists(target_folder): os.makedirs(target_folder)
            clean_name = uploaded_file_obj.name.replace(" ", "_")
            final_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_name}"
            with open(os.path.join(target_folder, final_name), "wb") as f: f.write(uploaded_file_obj.getvalue())
            return True
        except: return False

    # --- TEXT & PDF TOOLS (DIPERBAIKI UNTUK ATTRIBUTE ERROR) ---
    def clean_text_for_pdf(text):
        if text is None: return "-" # Handle None biar gak error
        text = str(text) # Paksa jadi string
        text = text.replace('\u2013', '-').replace('\u201c', '"').replace('\u201d', '"')
        return text.encode('latin-1', 'replace').decode('latin-1')

    # ==========================================
    # 5. GENERATOR AI (GEMINI 2.0 FLASH)
    # ==========================================
    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, ket_info=""):
        prompt = f"""
        Role: Pendamping PKH. Buat JSON Laporan Kegiatan.
        Data: {topik} | {detail} | {lokasi_lengkap} | {bulan}
        Catatan: {ket_info}
        
        Output JSON (lowercase key):
        {{
            "gambaran_umum": "Paragraf...",
            "maksud_tujuan": "Paragraf...",
            "ruang_lingkup": "Paragraf...",
            "dasar_hukum": ["Aturan 1", "Aturan 2"],
            "kegiatan": ["Detail 1...", "Detail 2..."],
            "hasil": ["Hasil 1...", "Hasil 2..."],
            "kesimpulan": "Paragraf...",
            "saran": ["Saran 1...", "Saran 2..."],
            "penutup": "Paragraf..."
        }}
        """
        try:
            response = model.generate_content(prompt)
            # Pembersihan Markdown jika AI nakal
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            return None # Return None biar nanti dihandle

    # ==========================================
    # 6. PEMBUAT DOKUMEN (Word & PDF)
    # ==========================================
    def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        # --- FIX VITAL: CEK DATA KOSONG ---
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
            if content is None: content = "-" # Handle None
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

    # --- FUNGSI BARU: CREATE PDF DOC ---
    def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        if data is None: return None
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        pdf.set_margins(25, 20, 25)

        # 1. KOP SURAT
        if kop:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(kop)
                tmp_path = tmp.name
            try:
                # Adjust width and position similar to Word
                pdf.image(tmp_path, x=10, y=10, w=190)
                pdf.ln(35) # Spasi setelah kop
            except: pass
            finally:
                if os.path.exists(tmp_path): os.remove(tmp_path)
        else:
            pdf.ln(10)

        # 2. JUDUL
        pdf.set_font("Arial", "B", 12)
        title_text = f"LAPORAN\nTENTANG\n{clean_text_for_pdf(meta['judul'].upper())}\n{clean_text_for_pdf(meta['bulan'].upper())}"
        pdf.multi_cell(0, 6, title_text, align='C')
        pdf.ln(10)

        # Helper Section
        def add_section_pdf(title, content, is_list=False):
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 8, clean_text_for_pdf(title), ln=True)
            pdf.set_font("Arial", "", 11)
            
            if content is None: content = "-"
            if is_list and isinstance(content, list):
                for item in content:
                    pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(item)}")
            else:
                pdf.multi_cell(0, 6, clean_text_for_pdf(content))
            pdf.ln(3)

        # 3. ISI LAPORAN
        add_section_pdf("A. Pendahuluan", data.get('gambaran_umum'))
        add_section_pdf("B. Maksud & Tujuan", data.get('maksud_tujuan'))

        # C. Pelaksanaan
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "C. Pelaksanaan Kegiatan", ln=True)
        pdf.set_font("Arial", "", 11)
        if extra_info:
            pdf.set_font("Arial", "I", 10)
            pdf.multi_cell(0, 6, f"Catatan: {clean_text_for_pdf(extra_info)}")
            pdf.set_font("Arial", "", 11)
        
        keg = data.get('kegiatan', [])
        if keg:
            for k in keg:
                pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(k)}")
        pdf.ln(3)

        # Data KPM (Jika Ada)
        if kpm_data:
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 8, "Data KPM Terkait:", ln=True)
            pdf.set_font("Arial", "", 10)
            for k, v in kpm_data.items():
                pdf.cell(60, 6, clean_text_for_pdf(k), border=1)
                pdf.multi_cell(0, 6, clean_text_for_pdf(v), border=1)
            pdf.ln(5)

        add_section_pdf("D. Hasil", data.get('hasil'), True)
        add_section_pdf("E. Penutup", data.get('penutup'))

        # 4. TANDA TANGAN
        pdf.ln(10)
        pdf.set_font("Arial", "", 11)
        # Posisi TTD di Kanan
        x_right = 110
        pdf.set_x(x_right)
        pdf.multi_cell(80, 6, f"{clean_text_for_pdf(meta['kab'])}, {clean_text_for_pdf(meta['tgl'])}\nPengelola Layanan Operasional", align='C')
        
        if ttd:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_ttd:
                tmp_ttd.write(ttd)
                ttd_path = tmp_ttd.name
            try:
                pdf.image(ttd_path, x=x_right+15, y=pdf.get_y(), w=50)
                pdf.ln(25) # Space for image height
            except: pdf.ln(25)
            finally:
                if os.path.exists(ttd_path): os.remove(ttd_path)
        else:
            pdf.ln(25)
        
        pdf.set_x(x_right)
        pdf.multi_cell(80, 6, f"\n{clean_text_for_pdf(meta['nama'])}\nNIP. {clean_text_for_pdf(meta['nip'])}", align='C')

        # 5. DOKUMENTASI
        if imgs:
            pdf.add_page()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, "DOKUMENTASI", ln=True, align='C')
            for img_bytes in imgs:
                # Compress image first to avoid huge PDF
                compressed = compress_image(img_bytes)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_img:
                    tmp_img.write(compressed.getvalue())
                    img_path = tmp_img.name
                try:
                    # Centered Image
                    pdf.image(img_path, x=35, w=140) 
                    pdf.ln(5)
                except: pass
                finally:
                    if os.path.exists(img_path): os.remove(img_path)

        # Return Bytes
        return pdf.output(dest='S').encode('latin-1')

    # ==========================================
    # 7. LOGIKA UI
    # ==========================================
    def update_tanggal():
        st.session_state.tgl_val = f"30 {st.session_state.bln_val.title()} {st.session_state.th_val}"

    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
    with st.sidebar:
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
        kop = st.file_uploader("Kop Surat", type=['png','jpg'], key="kop_up")
        if kop: st.session_state['kop_bytes'] = kop.getvalue()
        ttd = st.file_uploader("Tanda Tangan", type=['png','jpg'], key="ttd_up")
        if ttd: st.session_state['ttd_bytes'] = ttd.getvalue()

    def show_dashboard():
        st.title("📂 Aplikasi RHK PKH Pro (Versi Stabil)"); cols = st.columns(3)
        for i, rhk in enumerate(CONFIG_LAPORAN.keys()):
            with cols[i % 3]:
                st.markdown(f"""<div style="background-color:#f0f2f6; padding:15px; border-radius:10px; margin-bottom:10px; border:1px solid #d1d5db;"><b>{rhk.split('–')[0]}</b><br><small>{rhk.split('–')[-1]}</small></div>""", unsafe_allow_html=True)
                if st.button(f"Buka {rhk.split('–')[0]}", key=f"nav_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'; st.rerun()

    def show_detail():
        rhk = st.session_state.get('selected_rhk')
        # --- DOUBLE CHECK: Mencegah KeyError di tengah jalan ---
        if rhk not in CONFIG_LAPORAN:
            st.warning("🔄 Refreshing session..."); st.session_state['page'] = 'home'; st.rerun(); return

        c1, c2 = st.columns([1, 6])
        if c1.button("⬅️ Kembali", use_container_width=True): st.session_state['page'] = 'home'; st.rerun()
        c2.markdown(f"### 📝 {rhk}")
        
        meta = {'bulan': f"{st.session_state.bln_val} {st.session_state.th_val}", 'nama': u_nama, 'nip': u_nip, 'kab': u_kab, 'kec': u_kec, 'kel': u_kel, 'tgl': st.session_state.tgl_val, 'judul': rhk.split('–')[-1].upper()}
        lokasi = f"{u_kel}, {u_kec}, {u_kab}"
        
        # --- LOGIKA TAMPILAN BERDASARKAN JENIS RHK ---
        
        # TYPE 1: ANTRIAN (RHK 2, 3, 8)
        if "RHK 2" in rhk or "RHK 3" in rhk or "RHK 8" in rhk:
            q_key = 'rhk2_queue' if "RHK 2" in rhk else ('rhk3_queue' if "RHK 3" in rhk else 'rhk8_queue')
            r_key = q_key.replace('queue', 'results')
            st.info("💡 **Mode Antrian:** Masukkan kegiatan satu per satu, lalu klik 'Generate Semua'.")
            
            with st.form("queue_form", clear_on_submit=True):
                # Try-except di widget untuk keamanan ekstra
                try: kegiatan = st.selectbox("Sub-Kegiatan", CONFIG_LAPORAN[rhk])
                except: kegiatan = "Kegiatan Umum"
                
                ket_q = st.text_input("Keterangan", placeholder="Detail lokasi/peserta...")
                fotos = st.file_uploader("Foto", accept_multiple_files=True, type=['jpg','png'])
                if st.form_submit_button("➕ Tambah"):
                    if not fotos: st.error("❌ Foto wajib!")
                    else:
                        st.session_state[q_key].append({"kegiatan": kegiatan, "ket": ket_q, "fotos": [io.BytesIO(f.getvalue()) for f in fotos]})
                        st.success("Masuk antrian!"); st.rerun()
            
            queue = st.session_state[q_key]
            if queue:
                st.write(f"**Antrian ({len(queue)} Item):**")
                for i, q in enumerate(queue): st.text(f"{i+1}. {q['kegiatan']} - {q['ket']}")
                if st.button("🚀 GENERATE SEMUA", type="primary"):
                    results = []; bar = st.progress(0)
                    for i, item in enumerate(queue):
                        jd = generate_isi_laporan(rhk, item['kegiatan'], u_kpm, "Peserta", meta['bulan'], lokasi, item['ket'])
                        if jd: 
                            w = create_word_doc(jd, meta, item['fotos'], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], item['ket'])
                            # TAMBAHAN PDF
                            p = create_pdf_doc(jd, meta, item['fotos'], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], item['ket'])
                            if w: results.append({"judul": item['kegiatan'], "file": w, "file_pdf": p})
                        bar.progress((i + 1) / len(queue))
                    st.session_state[r_key] = results; st.success("Selesai!"); st.rerun()
            
            if st.session_state.get(r_key):
                st.write("### 📥 Download Hasil")
                for i, r in enumerate(st.session_state[r_key]):
                    c_dl1, c_dl2 = st.columns(2)
                    with c_dl1:
                        st.download_button(f"📄 Word: {r['judul']}", r['file'], f"{r['judul']}.docx", key=f"dl_w_{i}", use_container_width=True)
                    with c_dl2:
                        if r.get('file_pdf'):
                            st.download_button(f"📕 PDF: {r['judul']}", r['file_pdf'], f"{r['judul']}.pdf", key=f"dl_p_{i}", use_container_width=True)

        # TYPE 2: GRADUASI (RHK 4)
        elif "RHK 4" in rhk:
            st.info("ℹ️ **Mode Graduasi:** Upload Excel KPM.")
            # Template Button
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
                            for i, nm in enumerate(sel_kpm):
                                row = df[df['Nama'] == nm].iloc[0].to_dict()
                                jd = generate_isi_laporan(rhk, f"Graduasi {nm}", 1, nm, meta['bulan'], lokasi, f"Graduasi {nm}")
                                if jd:
                                    w = create_word_doc(jd, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], f"Graduasi {nm}", row)
                                    # TAMBAHAN PDF
                                    p = create_pdf_doc(jd, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], f"Graduasi {nm}", row)
                                    if w: res.append({"judul": nm, "file": w, "file_pdf": p})
                                bar.progress((i+1)/len(sel_kpm))
                            st.session_state['rhk4_graduasi_results'] = res; st.rerun()
                except: st.error("Format Excel Salah")
            
            if st.session_state.get('rhk4_graduasi_results'):
                for i, r in enumerate(st.session_state['rhk4_graduasi_results']):
                    c_dl1, c_dl2 = st.columns(2)
                    with c_dl1:
                        st.download_button(f"📥 Word: {r['judul']}", r['file'], f"Graduasi_{r['judul']}.docx", key=f"dlg_w_{i}", use_container_width=True)
                    with c_dl2:
                        if r.get('file_pdf'):
                            st.download_button(f"📥 PDF: {r['judul']}", r['file_pdf'], f"Graduasi_{r['judul']}.pdf", key=f"dlg_p_{i}", use_container_width=True)

        # TYPE 3: STANDAR (RHK 1, 5, 6, 7, 9)
        else:
            with st.form("std_form"):
                try: jk = st.selectbox("Kegiatan", CONFIG_LAPORAN[rhk])
                except: jk = "Kegiatan Umum"
                ka = st.text_area("Keterangan")
                ft = st.file_uploader("Foto", accept_multiple_files=True)
                if st.form_submit_button("🚀 BUAT LAPORAN", type="primary"):
                    if not ft: st.error("Foto wajib!")
                    else:
                        with st.status("Sedang bekerja..."):
                            jd = generate_isi_laporan(rhk, jk, u_kpm, "Peserta", meta['bulan'], lokasi, ka)
                            if jd:
                                imgs_data = [io.BytesIO(f.getvalue()) for f in ft]
                                w = create_word_doc(jd, meta, imgs_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], ka)
                                # TAMBAHAN PDF
                                p = create_pdf_doc(jd, meta, imgs_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], ka)
                                if w:
                                    st.session_state['generated_file_data'] = {"name": f"Laporan {jk}", "file": w, "file_pdf": p}
                                    st.rerun()
                            else: st.error("Gagal koneksi AI, coba lagi.")
            
            if st.session_state.get('generated_file_data'):
                f = st.session_state['generated_file_data']
                st.success("Selesai!")
                c_dl1, c_dl2 = st.columns(2)
                with c_dl1:
                    st.download_button("📥 Download Word", f['file'], f"{f['name']}.docx", type="primary", use_container_width=True)
                with c_dl2:
                    if f.get('file_pdf'):
                        st.download_button("📕 Download PDF", f['file_pdf'], f"{f['name']}.pdf", type="secondary", use_container_width=True)

    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail()
