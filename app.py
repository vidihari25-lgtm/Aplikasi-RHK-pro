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

# --- LIBRARY GOOGLE DRIVE ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# 1. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="Aplikasi RHK PKH Pro Cloud", layout="wide")

# ==========================================
# 2. DEFINISI CONFIG RHK
# ==========================================
CONFIG_LAPORAN = {
    "RHK 1 – Laporan Penyaluran bansos": ["Laporan Penyaluran Bantuan Sosial"],
    "RHK 2 – Laporan pertemuan P2K2": ["Modul Ekonomi", "Modul Kesehatan", "Modul Pengasuhan", "Modul Perlindungan"],
    "RHK 3 – Laporan Verifikasi Komitmen": ["Verifikasi Pendidikan", "Verifikasi Kesehatan", "Verifikasi Kesos"],
    "RHK 4 – Rekapitulasi Data KPM graduasi": ["Laporan Graduasi Mandiri"], 
    "RHK 5 – Laporan Pemutakhiran Data": ["Laporan Pemutakhiran Data KPM"],
    "RHK 6 – Laporan Kasus Adaptif": ["Laporan Penanganan Kasus"],
    "RHK 7 – Laporan Bulanan ASN PPPK": ["Laporan Kinerja Bulanan"],
    "RHK 8 – Laporan Tugas Direktif": ["Tugas Direktif Pimpinan"],
    "RHK 9 – Evaluasi Tugas Direktif": ["Evaluasi Penyelesaian Tugas"]
}

# --- SELF HEALING SESSION (Anti KeyError) ---
if 'selected_rhk' in st.session_state and st.session_state['selected_rhk']:
    if st.session_state['selected_rhk'] not in CONFIG_LAPORAN:
        st.session_state.clear(); st.rerun()

# --- SECURITY ---
DAFTAR_USER = {"admin": "admin123", "pendamping": "pkh2026", "user": "user"}

try: GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except: st.error("Setting Secrets GOOGLE_API_KEY belum ada!"); st.stop()

# --- SETUP AI (Gemini 2.0 Flash) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash', generation_config={"response_mime_type": "application/json"})
except Exception as e: st.error(f"Error AI: {e}")

# ==========================================
# 3. FUNGSI GOOGLE DRIVE (CLOUD STORAGE)
# ==========================================
def get_drive_service():
    """Koneksi aman ke Google Drive via Streamlit Secrets"""
    try:
        # Cek apakah secrets gcp ada
        if "gcp_service_account" not in st.secrets:
            return None
        
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        return None

def upload_to_drive(file_obj, filename, mime_type='application/octet-stream'):
    """Upload file BytesIO ke Google Drive Folder"""
    service = get_drive_service()
    if not service: return None # Skip jika belum disetting
    
    try:
        folder_id = st.secrets["drive"]["folder_id"]
        file_metadata = {'name': filename, 'parents': [folder_id]}
        
        file_obj.seek(0) # Reset pointer
        media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        st.error(f"Gagal Upload Cloud: {e}")
        return None

# ==========================================
# 4. LOGIN & DATABASE LOKAL
# ==========================================
def check_password():
    if st.session_state.get("password_correct", False): return True
    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"]=True; st.session_state["username"]=qp.get("user"); return True

    st.markdown("<br><h1 style='text-align: center;'>🔐 LOGIN PRO 2.0</h1>", unsafe_allow_html=True)
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        with st.form("lgn"):
            u = st.text_input("User"); p = st.text_input("Pass", type="password")
            if st.form_submit_button("MASUK", type="primary", use_container_width=True):
                if u in DAFTAR_USER and DAFTAR_USER[u] == p:
                    st.session_state["password_correct"]=True; st.session_state["username"]=u
                    st.query_params["auth"]="valid"; st.query_params["user"]=u; st.rerun()
                else: st.error("Salah!")
    return False

if check_password():
    # --- INIT SESSION ---
    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 'rhk2_queue', 'rhk2_results', 
            'rhk4_graduasi_results', 'generated_file_data', 'tgl_val', 'bln_val', 'th_val']
    for k in keys: 
        if k not in st.session_state: st.session_state[k] = None
    
    if not st.session_state['rhk2_queue']: st.session_state['rhk2_queue'] = []
    if not st.session_state['page']: st.session_state['page'] = 'home'
    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    
    # --- DB LOKAL (User Settings) ---
    def init_db():
        conn = sqlite3.connect('rhk_settings.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS user (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
        c.execute('SELECT count(*) FROM user'); 
        if c.fetchone()[0]==0: c.execute('INSERT INTO user VALUES (1, ?, ?, ?, ?, ?, ?, ?)', ("Pendamping", "19xx", 100, "Prov", "Kab", "Kec", "Kel"))
        conn.commit(); conn.close()
    
    def get_set(): 
        conn = sqlite3.connect('rhk_settings.db'); c=conn.cursor(); c.execute('SELECT * FROM user WHERE id=1'); d=c.fetchone(); conn.close(); return d
    def save_set(n,i,k,p,kb,kc,kl):
        conn = sqlite3.connect('rhk_settings.db'); c=conn.cursor(); c.execute('UPDATE user SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1', (n,i,k,p,kb,kc,kl)); conn.commit(); conn.close()
    
    init_db()

    # --- TOOLS DOKUMEN ---
    def compress_image(uploaded_file):
        try:
            uploaded_file.seek(0); image = Image.open(uploaded_file)
            if image.mode in ("RGBA", "P"): image = image.convert("RGB")
            output = io.BytesIO(); image.save(output, format="JPEG", quality=60); output.seek(0)
            return output
        except: uploaded_file.seek(0); return uploaded_file

    def generate_ai(topik, detail, lokasi, bulan, info):
        prompt = f"Role: Pendamping PKH. JSON Laporan.\nTopik: {topik}\nKegiatan: {detail}\nLokasi: {lokasi}\nBulan: {bulan}\nInfo: {info}\nOutput JSON: {{'gambaran_umum':'...','maksud_tujuan':'...','kegiatan':['...'],'hasil':['...'],'penutup':'...'}}"
        try:
            res = model.generate_content(prompt)
            return json.loads(res.text.replace("```json","").replace("```","").strip())
        except: return None

    def create_doc(data, meta, imgs, kop, ttd, extra_info=None):
        if not data: return None
        doc = Document()
        for s in doc.sections: s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
        
        if kop: 
            try: p=doc.add_paragraph(); p.alignment=1; p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
            except: pass
        
        p = doc.add_paragraph(f"\nLAPORAN\nTENTANG\n{meta['judul']}\n{meta['bulan']}"); p.alignment=1; p.runs[0].bold=True
        
        doc.add_paragraph("A. Pendahuluan", style='Heading 1'); doc.add_paragraph(str(data.get('gambaran_umum','-')), style='Body Text')
        doc.add_paragraph("B. Pelaksanaan", style='Heading 1')
        if extra_info: doc.add_paragraph(f"Info: {extra_info}", style='Quote')
        for k in data.get('kegiatan', []): doc.add_paragraph(str(k), style='List Bullet')
        doc.add_paragraph("C. Hasil", style='Heading 1')
        for h in data.get('hasil', []): doc.add_paragraph(str(h), style='List Bullet')
        doc.add_paragraph("D. Penutup", style='Heading 1'); doc.add_paragraph(str(data.get('penutup','-')), style='Body Text')
        
        doc.add_paragraph("\n\n")
        t = doc.add_table(1,2); t.autofit=False; t.columns[0].width=Inches(3); t.columns[1].width=Inches(3)
        c2 = t.cell(0,1).paragraphs[0]; c2.alignment=1; c2.add_run(f"{meta['kab']}, {meta['tgl']}\nPendamping PKH\n\n")
        if ttd: 
            try: c2.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
            except: pass
        c2.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}")
        
        if imgs:
            doc.add_page_break(); doc.add_paragraph("DOKUMENTASI", style='Heading 1').alignment=1
            for img in imgs:
                try: doc.add_paragraph().alignment=1; doc.add_picture(compress_image(img), width=Inches(3.5))
                except: pass
        
        bio = io.BytesIO(); doc.save(bio); return bio

    # ==========================================
    # 5. UI UTAMA & LOGIKA TANGGAL
    # ==========================================
    
    # --- LOGIKA TANGGAL OTOMATIS (Update Sesuai Permintaan) ---
    def update_tanggal():
        # Februari = 28, Lainnya = 30
        bulan = st.session_state.bln_val
        tahun = st.session_state.th_val
        hari = "28" if bulan == "FEBRUARI" else "30"
        st.session_state.tgl_val = f"{hari} {bulan.title()} {tahun}"

    # --- SIDEBAR ---
    u_data = get_set() # id, nama, nip, kpm, prov, kab, kec, kel
    with st.sidebar:
        st.write("☁️ **Status: Terhubung Cloud**" if "gcp_service_account" in st.secrets else "⚠️ **Offline / Lokal**")
        
        with st.expander("👤 Profil Pendamping"):
            with st.form("prof"):
                n=st.text_input("Nama", u_data[1]); i=st.text_input("NIP", u_data[2])
                k=st.number_input("KPM", value=u_data[3]); p=st.text_input("Prov", u_data[4])
                kb=st.text_input("Kab", u_data[5]); kc=st.text_input("Kec", u_data[6]); kl=st.text_input("Kel", u_data[7])
                if st.form_submit_button("Simpan"): save_set(n,i,k,p,kb,kc,kl); st.rerun()
        
        st.divider()
        st.selectbox("Bulan", ["JANUARI","FEBRUARI","MARET","APRIL","MEI","JUNI","JULI","AGUSTUS","SEPTEMBER","OKTOBER","NOVEMBER","DESEMBER"], key="bln_val", on_change=update_tanggal)
        st.selectbox("Tahun", ["2026","2027"], key="th_val", on_change=update_tanggal)
        # Jika session tgl_val belum ada, inisialisasi default
        if not st.session_state.tgl_val: update_tanggal()
        
        st.text_input("Tgl Surat", key="tgl_val")
        
        st.divider()
        kop = st.file_uploader("Kop Surat", type=['jpg','png']); ttd = st.file_uploader("TTD", type=['jpg','png'])
        if kop: st.session_state['kop_bytes'] = kop.getvalue()
        if ttd: st.session_state['ttd_bytes'] = ttd.getvalue()

    # --- PAGE LOGIC ---
    def show_dashboard():
        st.title("📂 Menu Laporan PKH"); cols = st.columns(3)
        for i, (k,v) in enumerate(CONFIG_LAPORAN.items()):
            with cols[i%3]:
                if st.button(f"{k.split('–')[0]}\n{k.split('–')[-1]}", key=f"btn_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = k; st.session_state['page'] = 'detail'; st.rerun()

    def show_detail():
        rhk = st.session_state.get('selected_rhk')
        if rhk not in CONFIG_LAPORAN: st.session_state['page']='home'; st.rerun(); return

        c1,c2 = st.columns([1,5])
        if c1.button("⬅️ Home"): st.session_state['page']='home'; st.rerun()
        c2.subheader(f"{rhk}")
        
        meta = {'nama':u_data[1], 'nip':u_data[2], 'kab':u_data[5], 'tgl':st.session_state.tgl_val, 'judul':rhk.split('–')[-1].upper(), 'bulan':f"{st.session_state.bln_val} {st.session_state.th_val}"}
        lokasi = f"{u_data[7]}, {u_data[6]}, {u_data[5]}"

        # --- LOGIKA RHK ---
        if "RHK 4" in rhk: # Graduasi
            st.info("🎓 Mode Graduasi: Upload Excel Data KPM.")
            # Template Button
            df_tmpl = pd.DataFrame({"Nama": ["Budi"], "NIK": ["123"], "Alamat": ["Desa A"], "Kategori": ["PKH"], "Status": ["Graduasi"], "Alasan": ["Mampu"]})
            buf = io.BytesIO(); df_tmpl.to_excel(buf, index=False); buf.seek(0)
            st.download_button("📥 Template Excel", buf, "Template.xlsx")
            
            upl = st.file_uploader("Excel KPM (.xlsx)", type=['xlsx'])
            if upl:
                try:
                    df = pd.read_excel(upl); names = df['Nama'].tolist() if 'Nama' in df.columns else []
                    sel = st.multiselect("Pilih KPM", names)
                    ft = st.file_uploader("Foto Dokumentasi", accept_multiple_files=True)
                    if st.button("🚀 Generate & Upload Cloud") and sel and ft:
                        res = []; p_data = [io.BytesIO(f.getvalue()) for f in ft]; bar = st.progress(0)
                        for idx, nm in enumerate(sel):
                            jd = generate_ai(rhk, f"Graduasi {nm}", lokasi, meta['bulan'], f"Graduasi {nm}")
                            if jd:
                                w = create_doc(jd, meta, p_data, st.session_state.get('kop_bytes'), st.session_state.get('ttd_bytes'), f"KPM: {nm}")
                                if w:
                                    # AUTO UPLOAD
                                    file_id = upload_to_drive(w, f"GRADUASI_{nm}_{meta['bulan']}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                                    res.append({'judul': nm, 'file': w, 'drive_id': file_id})
                            bar.progress((idx+1)/len(sel))
                        st.session_state['rhk4_graduasi_results'] = res; st.success("Selesai! File tersimpan di Google Drive.")
                except: st.error("Format Excel salah (harus ada kolom 'Nama')")
            
            if st.session_state.get('rhk4_graduasi_results'):
                for r in st.session_state['rhk4_graduasi_results']:
                    c1,c2 = st.columns([4,1])
                    c1.write(f"📄 {r['judul']} " + ("(✅ Cloud)" if r.get('drive_id') else ""))
                    c2.download_button("⬇️", r['file'], f"{r['judul']}.docx", key=f"dl_{r['judul']}")

        elif "RHK 2" in rhk or "RHK 3" in rhk or "RHK 8" in rhk: # Antrian
            st.info("📋 Mode Antrian: Tambah kegiatan, lalu Generate sekaligus.")
            with st.form("q"):
                try: keg = st.selectbox("Kegiatan", CONFIG_LAPORAN[rhk])
                except: keg = "Kegiatan Umum"
                ket = st.text_input("Ket")
                ft = st.file_uploader("Foto", accept_multiple_files=True)
                if st.form_submit_button("Tambah"):
                    st.session_state['rhk2_queue'].append({'keg':keg, 'ket':ket, 'ft':[io.BytesIO(f.getvalue()) for f in ft]})
                    st.success("Ditambahkan!"); st.rerun()
            
            q = st.session_state['rhk2_queue']
            if q:
                st.write(f"Antrian: {len(q)} item"); 
                if st.button("Hapus Semua"): st.session_state['rhk2_queue']=[]; st.rerun()
                if st.button("🚀 Generate & Upload All"):
                    res=[]; bar=st.progress(0)
                    for i, x in enumerate(q):
                        jd = generate_ai(rhk, x['keg'], lokasi, meta['bulan'], x['ket'])
                        if jd:
                            w = create_doc(jd, meta, x['ft'], st.session_state.get('kop_bytes'), st.session_state.get('ttd_bytes'), x['ket'])
                            if w:
                                fid = upload_to_drive(w, f"{rhk[:5]}_{x['keg']}_{meta['bulan']}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                                res.append({'judul':x['keg'], 'file':w, 'drive_id':fid})
                        bar.progress((i+1)/len(q))
                    st.session_state['rhk2_results'] = res; st.success("Semua terupload ke Drive!"); st.rerun()
            
            if st.session_state.get('rhk2_results'):
                for i, r in enumerate(st.session_state['rhk2_results']):
                    st.download_button(f"⬇️ {r['judul']}", r['file'], f"{r['judul']}.docx", key=f"dlq_{i}")

        else: # Standar
            with st.form("std"):
                try: keg = st.selectbox("Kegiatan", CONFIG_LAPORAN[rhk])
                except: keg = "Kegiatan Umum"
                ket = st.text_area("Ket")
                ft = st.file_uploader("Foto", accept_multiple_files=True)
                if st.form_submit_button("🚀 Buat Laporan"):
                    if not ft: st.error("Foto wajib!")
                    else:
                        with st.status("Memproses AI & Cloud Upload..."):
                            jd = generate_ai(rhk, keg, lokasi, meta['bulan'], ket)
                            if jd:
                                w = create_doc(jd, meta, [io.BytesIO(f.getvalue()) for f in ft], st.session_state.get('kop_bytes'), st.session_state.get('ttd_bytes'), ket)
                                if w:
                                    fid = upload_to_drive(w, f"LAPORAN_{rhk[:5]}_{meta['bulan']}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                                    st.session_state['generated_file_data'] = {'name':keg, 'file':w, 'drive_id':fid}
                                    st.rerun()
            
            if st.session_state.get('generated_file_data'):
                d = st.session_state['generated_file_data']
                st.success(f"✅ Selesai! ID Drive: {d.get('drive_id','Offline')}")
                st.download_button("📥 Download Word", d['file'], f"{d['name']}.docx")

    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail()
