import streamlit as st
import google.generativeai as genai
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io
import pandas as pd
from datetime import datetime
import json
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from PIL import Image

# ==========================================
# 1. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="Aplikasi RHK PKH Pro (Cloud Edition)", layout="wide")

# ==========================================
# 2. DEFINISI CONFIG
# ==========================================
CONFIG_LAPORAN = {
    "RHK 1 – Laporan Penyaluran bansos": ["Laporan Penyaluran Bantuan Sosial"],
    "RHK 2 – Laporan pertemuan P2K2": [
        "Modul Ekonomi 1: Mengelola Keuangan Keluarga", "Modul Ekonomi 2: Cermat Meminjam", "Modul Ekonomi 3: Memulai Usaha",
        "Modul Kesehatan 1: Gizi Ibu Hamil", "Modul Kesehatan 2: Gizi Balita", "Modul Kesehatan 3: Kesakitan Anak",
        "Modul Pengasuhan 1: Menjadi Orangtua Baik", "Modul Perlindungan 1: Anti Kekerasan Anak"
    ],
    "RHK 3 – Laporan Verifikasi Komitmen data KPM": ["Verifikasi Pendidikan (Sekolah)", "Verifikasi Kesehatan (Posyandu)", "Verifikasi Kesos"],
    "RHK 4 – Rekapitulasi Data KPM graduasi": ["Laporan Graduasi Mandiri"], 
    "RHK 5 – Laporan Data Verifikasi, Validasi": ["Laporan Pemutakhiran Data KPM"],
    "RHK 6 – Persentase penyelesaian laporan kasus adaptif": ["Laporan Penanganan Kasus (Case Management)"],
    "RHK 7 – Laporan Bulanan ASN PPPK": ["Laporan Kinerja Bulanan ASN PPPK"],
    "RHK 8 – Laporan pelaksana Tugas direktif": ["Tugas Direktif Pimpinan"],
    "RHK 9 – Presentase Penyelesaian Penugasan Direktif": ["Evaluasi Penyelesaian Tugas"]
}

# Self-healing session
if 'selected_rhk' in st.session_state:
    if st.session_state['selected_rhk'] is not None:
        if st.session_state['selected_rhk'] not in CONFIG_LAPORAN:
            st.session_state.clear()
            st.rerun()

DAFTAR_USER = {"admin": "admin123", "pendamping": "pkh2026", "user": "user"}

# ==========================================
# 3. KONEKSI GOOGLE DRIVE & SHEETS
# ==========================================
def init_google_services():
    try:
        # Load credentials dari secrets
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
        # Client Sheets
        client_sheets = gspread.authorize(creds)
        
        # Client Drive (untuk upload file)
        service_drive = build('drive', 'v3', credentials=creds)
        
        return client_sheets, service_drive
    except Exception as e:
        st.error(f"Gagal koneksi Google Services: {e}")
        return None, None

# Fungsi Upload ke Drive
def upload_to_drive(file_obj, filename, folder_id, mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'):
    try:
        _, drive_service = init_google_services()
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink'), file.get('id')
    except Exception as e:
        st.error(f"Gagal upload ke Drive: {e}")
        return None, None

# Fungsi Ambil Data User dari Sheets (Pengganti SQLite)
# Cari fungsi ini di kode Anda dan TIMPA/GANTI dengan yang ini:

def get_user_settings_sheet():
    # Data Default (Cadangan jika database error)
    default_data = ("Pendamping PKH", "19xxxx", 100, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan")
    
    try:
        client, _ = init_google_services()
        if client is None: return default_data # Cek jika koneksi gagal total

        sheet_name = st.secrets["general"]["SHEET_NAME"]
        try:
            sh = client.open(sheet_name)
            wks = sh.sheet1
        except Exception as e:
            # Jika Sheet tidak ketemu, jangan return None, tapi return Default!
            st.warning(f"⚠️ Database '{sheet_name}' belum ditemukan/dishare. Menggunakan mode Offline sementara.")
            return default_data 
        
        records = wks.get_all_records()
        if not records:
            return default_data
        
        u = records[0]
        # Pastikan urutan return sesuai dengan variabel penerima
        return (u.get('nama', ''), str(u.get('nip', '')), u.get('kpm', 0), 
                u.get('prov', ''), u.get('kab', ''), u.get('kec', ''), u.get('kel', ''))

    except Exception as e:
        st.error(f"Error Database Global: {e}")
        return default_data

# ==========================================
# 4. SISTEM LOGIN & AI
# ==========================================
try:
    GOOGLE_API_KEY = st.secrets["general"]["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"Cek secrets.toml: {e}")
    st.stop()

def check_password():
    if st.session_state.get("password_correct", False): return True
    
    st.markdown("<br><h1 style='text-align: center;'>🔐 LOGIN APP RHK (CLOUD)</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            input_user = st.text_input("Username")
            input_pass = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN", type="primary"):
                if input_user in DAFTAR_USER and DAFTAR_USER[input_user] == input_pass:
                    st.session_state["password_correct"] = True
                    st.session_state["username"] = input_user
                    st.rerun()
                else: st.error("Salah!")
    return False

if check_password():

    # ==========================================
    # 5. STATE & INIT
    # ==========================================
    with st.sidebar:
        st.write(f"👤 User: **{st.session_state.get('username', 'User')}**")
        if st.button("Log Out"):
            st.session_state.clear(); st.rerun()

    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 
            'rhk2_queue', 'rhk2_results', 'generated_file_data']
    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'

    # LOAD DATA USER DARI SHEETS
    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings_sheet()

    # --- Image Compression ---
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

    # --- AI Generator ---
    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, ket_info=""):
        prompt = f"""
        Role: Pendamping PKH. Buat JSON Laporan Kegiatan.
        Data: {topik} | {detail} | {lokasi_lengkap} | {bulan}
        Catatan: {ket_info}
        Output JSON (lowercase key):
        {{ "gambaran_umum": "...", "maksud_tujuan": "...", "ruang_lingkup": "...", "dasar_hukum": ["..."], "kegiatan": ["..."], "hasil": ["..."], "kesimpulan": "...", "penutup": "..." }}
        """
        try:
            response = model.generate_content(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except: return None

    # --- Word Creator ---
    def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None):
        if not data: return None
        doc = Document()
        # (Kode formatting Word sama seperti sebelumnya, disingkat disini agar muat)
        # ... [Kode formatting word tetap sama] ...
        
        # INSERT LOGIC SINGKAT UNTUK WORD
        p = doc.add_paragraph(f"LAPORAN {meta['judul']}\n{meta['bulan']}"); p.alignment = 1
        
        doc.add_paragraph("A. Pendahuluan", style='Heading 1')
        doc.add_paragraph(data.get('gambaran_umum', '-'))
        doc.add_paragraph("B. Kegiatan", style='Heading 1')
        for k in data.get('kegiatan', []): doc.add_paragraph(f"- {k}")
        doc.add_paragraph("C. Hasil", style='Heading 1')
        for h in data.get('hasil', []): doc.add_paragraph(f"- {h}")
        
        doc.add_paragraph("\n")
        t = doc.add_table(1, 2); t.cell(0,1).text = f"{meta['kab']}, {meta['tgl']}\n\n\n{meta['nama']}"

        if imgs:
            doc.add_page_break()
            doc.add_paragraph("DOKUMENTASI", style='Heading 1')
            for img in imgs:
                try: doc.add_picture(compress_image(img), width=Inches(3.0))
                except: pass
        
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio

    # ==========================================
    # 6. LOGIKA UI
    # ==========================================
    
    # --- SIDEBAR: PROFIL & CONFIG ---
    with st.sidebar:
        with st.expander("👤 Edit Profil (Cloud)", expanded=False):
            with st.form("profil_form"):
                nama = st.text_input("Nama", u_nama)
                nip = st.text_input("NIP", u_nip)
                kpm = st.number_input("Jml KPM", value=int(u_kpm))
                prov = st.text_input("Provinsi", u_prov)
                kab = st.text_input("Kabupaten", u_kab)
                kec = st.text_input("Kecamatan", u_kec)
                kel = st.text_input("Kelurahan", u_kel)
                if st.form_submit_button("Simpan ke Database"):
                    if save_user_settings_sheet(nama, nip, kpm, prov, kab, kec, kel):
                        st.success("Tersimpan di Google Sheets!")
                        st.rerun()
        
        st.markdown("---")
        # Tanggal & Kop (Tetap pakai session state karena sifatnya sementara per sesi)
        st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET"], key="bln_val")
        st.text_input("Tahun", "2026", key="th_val")
        st.text_input("Tanggal Surat", key="tgl_val") # User input manual lebih aman
        kop = st.file_uploader("Kop Surat (Sementara)", type=['png','jpg'], key="kop_up")
        if kop: st.session_state['kop_bytes'] = kop.getvalue()
        ttd = st.file_uploader("Tanda Tangan (Sementara)", type=['png','jpg'], key="ttd_up")
        if ttd: st.session_state['ttd_bytes'] = ttd.getvalue()

    # --- HALAMAN UTAMA ---
    def show_dashboard():
        st.title("📂 RHK PKH Pro (Connected to Drive)")
        st.info(f"Database: {st.secrets['general']['SHEET_NAME']} | Drive Folder ID: ...{st.secrets['general']['DRIVE_FOLDER_ID'][-5:]}")
        
        cols = st.columns(3)
        for i, rhk in enumerate(CONFIG_LAPORAN.keys()):
            with cols[i % 3]:
                if st.button(f"{rhk.split('–')[0]}", key=f"nav_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'; st.rerun()

    def show_detail():
        rhk = st.session_state.get('selected_rhk')
        if rhk not in CONFIG_LAPORAN: st.session_state['page'] = 'home'; st.rerun()

        st.button("⬅️ Kembali", on_click=lambda: st.session_state.update({'page': 'home'}))
        st.subheader(f"📝 {rhk}")
        
        meta = {'bulan': f"{st.session_state.bln_val} {st.session_state.th_val}", 
                'nama': u_nama, 'nip': u_nip, 'kab': u_kab, 'tgl': st.session_state.tgl_val, 
                'judul': rhk.split('–')[-1].upper()}

        # CONTOH IMPLEMENTASI STANDAR (RHK 1 dll)
        with st.form("gen_form"):
            kegiatan = st.selectbox("Sub Kegiatan", CONFIG_LAPORAN[rhk])
            ket = st.text_area("Detail/Lokasi")
            fotos = st.file_uploader("Foto Dokumentasi", accept_multiple_files=True)
            
            if st.form_submit_button("🚀 Generate & Upload ke Drive"):
                if not fotos:
                    st.error("Upload foto dulu!")
                else:
                    with st.spinner("Menganalisis dengan AI & Membuat Dokumen..."):
                        # 1. Generate Konten
                        jd = generate_isi_laporan(rhk, kegiatan, u_kpm, "Peserta", meta['bulan'], f"{u_kel}, {u_kec}", ket)
                        
                        if jd:
                            # 2. Buat Word
                            img_bytes = [io.BytesIO(f.getvalue()) for f in fotos]
                            docx_file = create_word_doc(jd, meta, img_bytes, st.session_state['kop_bytes'], st.session_state['ttd_bytes'])
                            
                            # 3. Upload ke Drive
                            st.info("Sedang mengupload ke Google Drive...")
                            nama_file = f"Laporan_{kegiatan}_{meta['bulan']}_{datetime.now().strftime('%H%M%S')}.docx"
                            folder_id = st.secrets["general"]["DRIVE_FOLDER_ID"]
                            
                            link, file_id = upload_to_drive(docx_file, nama_file, folder_id)
                            
                            if link:
                                st.success(f"✅ Berhasil! File tersimpan di Google Drive.")
                                st.markdown(f"**[📂 Buka File di Google Drive]({link})**")
                                
                                # Simpan juga foto mentah ke Drive (Opsional)
                                for idx, f in enumerate(fotos):
                                    f.seek(0)
                                    upload_to_drive(f, f"FOTO_{kegiatan}_{idx}.jpg", folder_id, mime_type='image/jpeg')
                                st.success("Foto-foto mentah juga telah diarsipkan di Drive.")
                                
                                # Tombol Download Lokal (Backup)
                                docx_file.seek(0)
                                st.download_button("⬇️ Download Backup Lokal", docx_file, nama_file)
                            else:
                                st.error("Gagal upload ke Drive.")

    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail()

