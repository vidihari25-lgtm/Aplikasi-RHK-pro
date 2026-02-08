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
st.set_page_config(page_title="Aplikasi RHK PKH Pro (Safe Mode)", layout="wide")

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
# 3. KONEKSI GOOGLE DRIVE & SHEETS (DENGAN SAFETY NET)
# ==========================================
def init_google_services():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client_sheets = gspread.authorize(creds)
        service_drive = build('drive', 'v3', credentials=creds)
        return client_sheets, service_drive
    except Exception as e:
        return None, None

def upload_to_drive(file_obj, filename, folder_id):
    try:
        _, drive_service = init_google_services()
        if not drive_service: return None, "Gagal koneksi Service Account"

        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(file_obj, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', resumable=True)
        
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink'), None # Sukses
    except Exception as e:
        # Menangkap error quota/permission agar app tidak crash
        return None, str(e)

def get_user_settings_sheet():
    # Data Default (Cadangan)
    default_data = ("Pendamping PKH", "19xxxx", 100, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan")
    
    try:
        client, _ = init_google_services()
        if client is None: return default_data

        sheet_name = st.secrets["general"]["SHEET_NAME"]
        try:
            sh = client.open(sheet_name)
            wks = sh.sheet1
        except:
            # Silent fail: Jika sheet tidak ketemu, pakai default tanpa error merah
            st.toast("⚠️ Database tidak ditemukan. Menggunakan profil default.")
            return default_data
        
        records = wks.get_all_records()
        if not records: return default_data
        
        u = records[0]
        # Pastikan key ada dengan .get()
        return (u.get('nama', ''), str(u.get('nip', '')), u.get('kpm', 0), 
                u.get('prov', ''), u.get('kab', ''), u.get('kec', ''), u.get('kel', ''))
    except:
        return default_data

def save_user_settings_sheet(nama, nip, kpm, prov, kab, kec, kel):
    try:
        client, _ = init_google_services()
        if not client: return False
        
        sheet_name = st.secrets["general"]["SHEET_NAME"]
        sh = client.open(sheet_name)
        wks = sh.sheet1
        
        row_data = [1, nama, "'" + str(nip), kpm, prov, kab, kec, kel]
        if len(wks.get_all_values()) < 2: wks.append_row(row_data)
        else:
            cell_list = wks.range('A2:H2')
            for i, cell in enumerate(cell_list): cell.value = row_data[i]
            wks.update_cells(cell_list)
        return True
    except Exception as e:
        st.error(f"Gagal simpan: {e}")
        return False

# ==========================================
# 4. SISTEM LOGIN & AI
# ==========================================
try:
    GOOGLE_API_KEY = st.secrets["general"]["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("API Key Gemini belum diset.")
    st.stop()

def check_password():
    if st.session_state.get("password_correct", False): return True
    st.markdown("<br><h1 style='text-align: center;'>🔐 LOGIN APP RHK</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user = st.text_input("Username"); pwd = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN", type="primary"):
                if user in DAFTAR_USER and DAFTAR_USER[user] == pwd:
                    st.session_state["password_correct"] = True; st.session_state["username"] = user; st.rerun()
                else: st.error("Salah!")
    return False

if check_password():

    # ==========================================
    # 5. STATE & LOGIC
    # ==========================================
    with st.sidebar:
        st.write(f"👤 User: **{st.session_state.get('username', 'User')}**")
        if st.button("Log Out"): st.session_state.clear(); st.rerun()

    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes']
    for k in keys:
        if k not in st.session_state: st.session_state[k] = None
    if st.session_state['page'] is None: st.session_state['page'] = 'home'

    # Load Data (Aman dari crash)
    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings_sheet()

    def compress_image(uploaded_file):
        try:
            uploaded_file.seek(0); image = Image.open(uploaded_file).convert("RGB")
            image.thumbnail((600, 800)) # Resize biar ringan
            output = io.BytesIO(); image.save(output, format="JPEG", quality=60)
            output.seek(0); uploaded_file.seek(0); return output
        except: uploaded_file.seek(0); return uploaded_file 

    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi, ket=""):
        prompt = f"""Role: Pendamping PKH. Buat JSON Laporan.
        Data: {topik} | {detail} | {lokasi} | {bulan} | {ket}
        Output JSON: {{ "gambaran_umum": "...", "kegiatan": ["..."], "hasil": ["..."], "penutup": "..." }}"""
        try:
            res = model.generate_content(prompt)
            return json.loads(res.text.replace("```json", "").replace("```", "").strip())
        except: return None

    def create_word_doc(data, meta, imgs):
        if not data: return None
        doc = Document()
        p = doc.add_paragraph(f"LAPORAN {meta['judul']}\n{meta['bulan']}"); p.alignment = 1
        
        for k in ['gambaran_umum', 'penutup']:
            doc.add_paragraph(k.replace("_", " ").title(), style='Heading 1')
            doc.add_paragraph(data.get(k, '-'))
        
        doc.add_paragraph("Kegiatan", style='Heading 1')
        for x in data.get('kegiatan', []): doc.add_paragraph(f"- {x}")
        
        doc.add_paragraph("\n")
        doc.add_paragraph(f"{meta['kab']}, {meta['tgl']}\n\n\n{meta['nama']}")

        if imgs:
            doc.add_page_break(); doc.add_paragraph("DOKUMENTASI", style='Heading 1')
            for img in imgs:
                try: doc.add_picture(compress_image(img), width=Inches(3.0))
                except: pass
        
        bio = io.BytesIO(); doc.save(bio); bio.seek(0); return bio

    # --- UI ---
    with st.sidebar:
        with st.expander("👤 Edit Profil", expanded=False):
            with st.form("profil_form"):
                nama = st.text_input("Nama", u_nama); nip = st.text_input("NIP", u_nip)
                if st.form_submit_button("Simpan"):
                    if save_user_settings_sheet(nama, nip, u_kpm, u_prov, u_kab, u_kec, u_kel):
                        st.success("Tersimpan!"); st.rerun()
                    else: st.error("Gagal simpan (Cek koneksi Sheet)")
        
        st.markdown("---")
        st.selectbox("Bulan", ["JANUARI", "FEBRUARI"], key="bln_val")
        st.text_input("Tahun", "2026", key="th_val")
        st.text_input("Tanggal Surat", "30 Januari 2026", key="tgl_val")

    def show_dashboard():
        st.title("📂 Aplikasi RHK PKH Pro"); cols = st.columns(3)
        for i, rhk in enumerate(CONFIG_LAPORAN.keys()):
            with cols[i % 3]:
                if st.button(f"{rhk.split('–')[0]}", key=f"nav_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'; st.rerun()

    def show_detail():
        rhk = st.session_state.get('selected_rhk')
        if not rhk: st.session_state['page'] = 'home'; st.rerun()
        
        st.button("⬅️ Kembali", on_click=lambda: st.session_state.update({'page': 'home'}))
        st.subheader(f"📝 {rhk}")
        
        meta = {'bulan': f"{st.session_state.bln_val} {st.session_state.th_val}", 
                'nama': u_nama, 'kab': u_kab, 'tgl': st.session_state.tgl_val, 'judul': rhk.split('–')[-1].upper()}

        with st.form("gen_form"):
            kegiatan = st.selectbox("Kegiatan", CONFIG_LAPORAN[rhk])
            ket = st.text_area("Detail Kegiatan")
            fotos = st.file_uploader("Foto", accept_multiple_files=True)
            
            if st.form_submit_button("🚀 Generate Laporan"):
                if not fotos: st.error("Foto wajib diupload!")
                else:
                    with st.spinner("Sedang membuat laporan..."):
                        jd = generate_isi_laporan(rhk, kegiatan, u_kpm, "Peserta", meta['bulan'], u_kec, ket)
                        if jd:
                            docx = create_word_doc(jd, meta, [io.BytesIO(f.getvalue()) for f in fotos])
                            
                            # Coba Upload Drive
                            fname = f"Laporan_{kegiatan}_{meta['bulan']}.docx"
                            link, err = upload_to_drive(docx, fname, st.secrets["general"]["DRIVE_FOLDER_ID"])
                            
                            st.success("✅ Laporan Berhasil Dibuat!")
                            
                            # Logika Tampilan Hasil
                            if link:
                                st.success(f"Tersimpan di Google Drive! [Klik untuk buka]({link})")
                            else:
                                st.warning(f"⚠️ Gagal simpan ke Drive (Mungkin folder belum dishare/penuh). Error: {err}")
                                st.info("Silakan download manual di bawah ini:")
                            
                            docx.seek(0)
                            st.download_button("⬇️ Download File Word", docx, fname, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                        else: st.error("AI sibuk, coba lagi.")

    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail()
