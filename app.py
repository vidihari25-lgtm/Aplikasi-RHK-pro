import streamlit as st
import google.generativeai as genai
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
import io
import pandas as pd
# import sqlite3  <-- DIHAPUS (Diganti Google Sheets)
from datetime import datetime
import time
import os
from PIL import Image
import tempfile
import json
import re

# LIBRARY BARU UNTUK GOOGLE CLOUD
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

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

DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# ==========================================
# 3. KONEKSI CLOUD (DRIVE & SHEETS)
# ==========================================
def init_google_services():
    """Inisialisasi koneksi ke Google Cloud dengan Error Handling"""
    try:
        # Cek apakah secrets ada
        if "gcp_service_account" not in st.secrets:
            return None, None
            
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
        # Client Sheets
        client_sheets = gspread.authorize(creds)
        # Client Drive
        service_drive = build('drive', 'v3', credentials=creds)
        
        return client_sheets, service_drive
    except Exception as e:
        # Silent error agar app tidak crash saat init
        print(f"Error Init Google: {e}")
        return None, None

# --- FUNGSI UPLOAD KE DRIVE ---
def upload_to_drive(file_obj, filename, folder_id):
    """Mengupload file ke Google Drive dan mengembalikan Link"""
    try:
        _, drive_service = init_google_services()
        if not drive_service:
            return None, "Gagal koneksi Service Account"

        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        # Tentukan Mime Type
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        if filename.endswith('.pdf'): mime = 'application/pdf'
        elif filename.endswith('.jpg'): mime = 'image/jpeg'
        
        media = MediaIoBaseUpload(file_obj, mimetype=mime, resumable=True)
        
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink'), None # Sukses, Error=None
    except Exception as e:
        # Menangkap error quota/permission agar app tidak crash
        return None, str(e)

# --- FUNGSI DATABASE USER (GOOGLE SHEETS) ---
def get_user_settings_sheet():
    """Mengambil data user dari Sheets dengan Safety Net"""
    # Data Default (Cadangan jika database error/belum dishare)
    default_data = ("Pendamping PKH", "19xxxx", 100, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan")
    
    try:
        client, _ = init_google_services()
        if client is None: return default_data

        if "general" not in st.secrets or "SHEET_NAME" not in st.secrets["general"]:
            return default_data

        sheet_name = st.secrets["general"]["SHEET_NAME"]
        try:
            sh = client.open(sheet_name)
            wks = sh.sheet1
        except:
            # Jika sheet tidak ketemu (belum dishare), pakai default tanpa error merah
            st.toast(f"⚠️ Database '{sheet_name}' belum bisa diakses. Menggunakan profil default.")
            return default_data
        
        records = wks.get_all_records()
        if not records: return default_data
        
        u = records[0]
        # Pastikan key ada dengan .get() untuk menghindari KeyError
        return (
            u.get('nama', default_data[0]), 
            str(u.get('nip', default_data[1])), 
            u.get('kpm', default_data[2]), 
            u.get('prov', default_data[3]), 
            u.get('kab', default_data[4]), 
            u.get('kec', default_data[5]), 
            u.get('kel', default_data[6])
        )
    except:
        return default_data

def save_user_settings_sheet(nama, nip, kpm, prov, kab, kec, kel):
    """Menyimpan data user ke Sheets"""
    try:
        client, _ = init_google_services()
        if not client: 
            st.error("Koneksi Google gagal.")
            return False
        
        sheet_name = st.secrets["general"]["SHEET_NAME"]
        sh = client.open(sheet_name)
        wks = sh.sheet1
        
        # Format Data: ID, Nama, NIP (kasih kutip biar string), KPM, Prov, Kab, Kec, Kel
        row_data = [1, nama, "'" + str(nip), kpm, prov, kab, kec, kel]
        
        # Jika sheet kosong (cuma header), append. Jika ada isi, update baris 2.
        if len(wks.get_all_values()) < 2: 
            wks.append_row(row_data)
        else:
            # Update range A2:H2
            cell_list = wks.range('A2:H2')
            for i, cell in enumerate(cell_list): 
                if i < len(row_data):
                    cell.value = row_data[i]
            wks.update_cells(cell_list)
        return True
    except Exception as e:
        st.error(f"Gagal simpan ke database: {e}")
        return False

# ==========================================
# 4. SISTEM LOGIN & AI
# ==========================================
try:
    if "general" in st.secrets and "GOOGLE_API_KEY" in st.secrets["general"]:
        GOOGLE_API_KEY = st.secrets["general"]["GOOGLE_API_KEY"]
    else:
        GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"] # Fallback format lama
        
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"Gagal konfigurasi AI: {e}")
    st.stop()

def check_password():
    if st.session_state.get("password_correct", False): return True
    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True; st.session_state["username"] = qp.get("user"); return True

    st.markdown("<br><br><h1 style='text-align: center;'>🔐 LOGIN APP RHK (CLOUD)</h1>", unsafe_allow_html=True)
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
    # 5. SETUP & INIT STATE
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

    # --- IMAGE TOOLS ---
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

    # --- GENERATOR AI ---
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
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            return None

    # --- DOC CREATOR ---
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
        
        bio = io.BytesIO(); doc.save(bio); bio.seek(0); return bio

    # ==========================================
    # 6. LOGIKA UI (MAIN)
    # ==========================================
    def update_tanggal():
        st.session_state.tgl_val = f"30 {st.session_state.bln_val.title()} {st.session_state.th_val}"

    # Load Data dari Google Sheet (Safe Mode)
    u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings_sheet()

    with st.sidebar:
        with st.expander("👤 Profil (Cloud Database)", expanded=False):
            with st.form("profil_form"):
                nama = st.text_input("Nama", u_nama)
                nip = st.text_input("NIP", u_nip)
                kpm = st.number_input("Jml KPM", value=int(u_kpm))
                prov = st.text_input("Provinsi", u_prov)
                kab = st.text_input("Kabupaten", u_kab)
                kec = st.text_input("Kecamatan", u_kec)
                kel = st.text_input("Kelurahan", u_kel)
                if st.form_submit_button("Simpan ke Cloud"):
                    if save_user_settings_sheet(nama, nip, kpm, prov, kab, kec, kel):
                        st.success("Tersimpan di Google Sheets!"); st.rerun()
                    else:
                        st.error("Gagal simpan. Cek koneksi internet/izin akses.")

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
        st.title("📂 Aplikasi RHK PKH Pro (Cloud)"); cols = st.columns(3)
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
        
        # --- LOGIKA TAMPILAN BERDASARKAN JENIS RHK ---
        
        # TYPE 1: ANTRIAN (RHK 2, 3, 8)
        if "RHK 2" in rhk or "RHK 3" in rhk or "RHK 8" in rhk:
            q_key = 'rhk2_queue' if "RHK 2" in rhk else ('rhk3_queue' if "RHK 3" in rhk else 'rhk8_queue')
            r_key = q_key.replace('queue', 'results')
            st.info("💡 **Mode Antrian:** Masukkan kegiatan satu per satu, lalu klik 'Generate Semua'.")
            
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
            
            queue = st.session_state[q_key]
            if queue:
                st.write(f"**Antrian ({len(queue)} Item):**")
                for i, q in enumerate(queue): st.text(f"{i+1}. {q['kegiatan']} - {q['ket']}")
                
                if st.button("🚀 GENERATE SEMUA KE DRIVE", type="primary"):
                    results = []; bar = st.progress(0)
                    folder_id = st.secrets["general"].get("DRIVE_FOLDER_ID", "") if "general" in st.secrets else ""
                    
                    for i, item in enumerate(queue):
                        jd = generate_isi_laporan(rhk, item['kegiatan'], u_kpm, "Peserta", meta['bulan'], lokasi, item['ket'])
                        if jd: 
                            w = create_word_doc(jd, meta, item['fotos'], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], item['ket'])
                            if w: 
                                # Upload to Drive
                                fname = f"{item['kegiatan']}_{meta['bulan']}_{i}.docx"
                                link, err = upload_to_drive(w, fname, folder_id)
                                w.seek(0) # Reset pointer for download button
                                results.append({"judul": item['kegiatan'], "file": w, "link": link, "err": err})
                        bar.progress((i + 1) / len(queue))
                    st.session_state[r_key] = results; st.success("Selesai!"); st.rerun()
            
            if st.session_state.get(r_key):
                st.write("### 📥 Hasil Laporan")
                for i, r in enumerate(st.session_state[r_key]):
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        if r['link']: st.markdown(f"✅ **{r['judul']}** -> [Buka di Drive]({r['link']})")
                        else: st.markdown(f"⚠️ **{r['judul']}** (Gagal Upload: {r['err']})")
                    with col_b:
                        # Fix Tombol Download
                        st.download_button(
                            label="⬇️ Local",
                            data=r['file'],
                            file_name=f"{r['judul']}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_{i}"
                        )

        # TYPE 2: GRADUASI (RHK 4)
        elif "RHK 4" in rhk:
            st.info("ℹ️ **Mode Graduasi:** Upload Excel KPM.")
            df_tmpl = pd.DataFrame({"Nama": ["Budi"], "NIK": ["123"], "Alamat": ["Desa A"], "Kategori": ["PKH"], "Status": ["Graduasi"], "Alasan": ["Mampu"]})
            buf = io.BytesIO(); df_tmpl.to_excel(buf, index=False); buf.seek(0)
            
            st.download_button(
                label="📥 Template Excel",
                data=buf,
                file_name="Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            upl = st.file_uploader("Upload Excel", type=['xlsx'])
            if upl:
                try:
                    df = pd.read_excel(upl)
                    sel_kpm = st.multiselect("Pilih KPM", df['Nama'].tolist()) if 'Nama' in df.columns else []
                    if sel_kpm:
                        photos = st.file_uploader("Foto", accept_multiple_files=True)
                        if st.button("🚀 Generate") and photos:
                            res = []; p_data = [io.BytesIO(f.getvalue()) for f in photos]; bar = st.progress(0)
                            folder_id = st.secrets["general"].get("DRIVE_FOLDER_ID", "")
                            
                            for i, nm in enumerate(sel_kpm):
                                row = df[df['Nama'] == nm].iloc[0].to_dict()
                                jd = generate_isi_laporan(rhk, f"Graduasi {nm}", 1, nm, meta['bulan'], lokasi, f"Graduasi {nm}")
                                if jd:
                                    w = create_word_doc(jd, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], f"Graduasi {nm}", row)
                                    if w: 
                                        fname = f"Graduasi_{nm}.docx"
                                        link, err = upload_to_drive(w, fname, folder_id)
                                        w.seek(0)
                                        res.append({"judul": nm, "file": w, "link": link})
                                bar.progress((i+1)/len(sel_kpm))
                            st.session_state['rhk4_graduasi_results'] = res; st.rerun()
                except: st.error("Format Excel Salah")
            
            if st.session_state.get('rhk4_graduasi_results'):
                for i, r in enumerate(st.session_state['rhk4_graduasi_results']):
                    # Fix Download Button
                    if r['link']: st.write(f"✅ Tersimpan di Drive: [Link]({r['link']})")
                    st.download_button(
                        label=f"📥 Download {r['judul']}",
                        data=r['file'],
                        file_name=f"Graduasi_{r['judul']}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dlg_{i}"
                    )

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
                                w = create_word_doc(jd, meta, [io.BytesIO(f.getvalue()) for f in ft], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], ka)
                                if w:
                                    # Upload Drive Logic
                                    folder_id = st.secrets["general"].get("DRIVE_FOLDER_ID", "")
                                    fname = f"Laporan_{jk}_{meta['bulan']}.docx"
                                    link, err = upload_to_drive(w, fname, folder_id)
                                    w.seek(0) # Reset
                                    
                                    st.session_state['generated_file_data'] = {"name": fname, "file": w, "link": link, "err": err}
                                    st.rerun()
                            else: st.error("Gagal koneksi AI, coba lagi.")
            
            if st.session_state.get('generated_file_data'):
                f = st.session_state['generated_file_data']
                if f['link']:
                    st.success(f"✅ Berhasil upload ke Drive! [Klik untuk buka]({f['link']})")
                elif f['err']:
                    st.warning(f"⚠️ File jadi tapi gagal upload ke Drive: {f['err']}")
                
                # Fix Download Button
                st.download_button(
                    label="📥 Download File Word (Backup)",
                    data=f['file'],
                    file_name=f['name'],
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary"
                )

    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail()
