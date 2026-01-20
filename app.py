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
st.set_page_config(page_title="Aplikasi RHK PKH Pro", layout="wide", page_icon="📊")

# --- DAFTAR USER & PASSWORD ---
DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# ==========================================
# 2. SISTEM KEAMANAN & LOGIN
# ==========================================

try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except FileNotFoundError:
    st.error("🚨 File .streamlit/secrets.toml tidak ditemukan!")
    st.stop()
except KeyError:
    st.error("🚨 Key 'GOOGLE_API_KEY' tidak ditemukan di secrets.toml.")
    st.stop()

try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-flash-latest')
except Exception as e:
    st.error(f"Gagal konfigurasi AI: {e}")

def check_password():
    if st.session_state.get("password_correct", False): return True
    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True
        st.session_state["username"] = qp.get("user")
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        u = st.text_input("Username", key="login_user")
        p = st.text_input("Password", type="password", key="login_pass")
        if st.button("MASUK / LOGIN", type="primary", use_container_width=True):
            if u in DAFTAR_USER and DAFTAR_USER[u] == p:
                st.session_state["password_correct"] = True
                st.session_state["username"] = u
                st.query_params["auth"] = "valid"; st.query_params["user"] = u
                st.rerun()
            else: st.error("Username/Password Salah!")
    return False

if check_password():

    # ==========================================
    # 3. CSS KHUSUS UNTUK TOMBOL KOTAK
    # ==========================================
    st.markdown("""
        <style>
        /* 1. MEMBUAT TOMBOL MENU UTAMA MENJADI KOTAK (PERSEGI) */
        /* Target tombol di dalam kolom layout utama */
        div[data-testid="column"] button {
            width: 100% !important;
            aspect-ratio: 1 / 1 !important; /* Kunci rasio lebar:tinggi = 1:1 */
            height: auto !important;
            padding: 10px !important;
            white-space: pre-wrap !important; /* Izinkan text turun baris */
            
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            align-items: center !important;
            
            border-radius: 15px !important;
            border: 1px solid #e0e0e0 !important;
            background-color: #ffffff !important;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
            transition: transform 0.2s, box-shadow 0.2s !important;
        }

        /* Efek Hover: Sedikit membesar */
        div[data-testid="column"] button:hover {
            transform: scale(1.03) !important;
            border-color: #ff4b4b !important;
            box-shadow: 0 8px 15px rgba(0,0,0,0.1) !important;
            z-index: 2;
        }

        /* 2. MENGATUR UKURAN FONT DI DALAM TOMBOL */
        /* Semua teks di dalam tombol */
        div[data-testid="column"] button p {
            text-align: center !important;
            line-height: 1.4 !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Trik CSS: Baris Pertama (Judul RHK) Besar & Tebal */
        div[data-testid="column"] button p::first-line {
            font-size: 1.4rem !important; /* Ukuran Besar */
            font-weight: 800 !important;
            color: #31333F !important;
        }

        /* Sisa Teks (Keterangan) Lebih Kecil */
        div[data-testid="column"] button p {
            font-size: 0.9rem !important; /* Ukuran Kecil */
            font-weight: 400 !important;
            color: #555 !important;
        }

        /* 3. TOMBOL LOGOUT (SIDEBAR) - RAPI & TIDAK TERLALU BESAR */
        section[data-testid="stSidebar"] button {
            width: 100% !important;
            height: auto !important;
            padding: 8px 16px !important;
            border-radius: 8px !important;
            border: 1px solid #ccc !important;
            background-color: #f0f2f6 !important;
            font-weight: 600 !important;
        }
        section[data-testid="stSidebar"] button:hover {
            border-color: #ff4b4b !important;
            color: #ff4b4b !important;
            background-color: #fff !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # ==========================================
    # 4. SETUP STATE & DB
    # ==========================================
    with st.sidebar:
        st.write(f"👤 Login: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout"):
            st.session_state["password_correct"] = False
            st.query_params.clear()
            st.rerun()

    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 'graduasi_raw', 'graduasi_fix', 
            'generated_file_data', 'rhk3_results', 'rhk2_queue', 'rhk2_results', 
            'rhk4_queue', 'rhk4_results', 'rhk7_queue', 'rhk7_results', 'tgl_val', 'bln_val', 'th_val'] 
    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    if "page" in st.query_params: st.session_state['page'] = st.query_params["page"]
    if "rhk" in st.query_params: st.session_state['selected_rhk'] = st.query_params["rhk"]

    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk4_queue'] is None: st.session_state['rhk4_queue'] = []
    if st.session_state['rhk7_queue'] is None: st.session_state['rhk7_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'
    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    if not st.session_state['tgl_val']: st.session_state['tgl_val'] = "30 Januari 2026"

    CONFIG_LAPORAN = {
        "RHK 1 – LAPORAN PENYALURAN": ["Laporan Penyaluran Bantuan Sosial"],
        "RHK 2 – LAPORAN P2K2 (FDS)": ["Modul Ekonomi 1", "Modul Ekonomi 2", "Modul Kesehatan 1", "Modul Kesehatan 2", "Modul Pengasuhan 1", "Modul Perlindungan 1"],
        "RHK 3 – TARGET GRADUASI MANDIRI": ["Laporan Graduasi Mandiri"], 
        "RHK 4 – KEGIATAN PEMUTAKHIRAN": ["Verifikasi Pendidikan", "Verifikasi Kesehatan", "Verifikasi Kesos"],
        "RHK 5 – KPM YANG DIMUTAKHIRKAN": ["Laporan Pemutakhiran Data"],
        "RHK 6 – LAPORAN KASUS ADAPTIF": ["Case Management"],
        "RHK 7 – LAPORAN DIREKTIF": ["Tugas Direktif"]
    }

    def init_db():
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS riwayat (id INTEGER PRIMARY KEY, tgl TEXT, rhk TEXT, judul TEXT, lokasi TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_settings (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
        c.execute('SELECT count(*) FROM user_settings')
        if c.fetchone()[0] == 0:
            c.execute('INSERT INTO user_settings VALUES (1, "Vidi Hari Suci", "123456", 250, "Lampung", "Lampung Tengah", "Punggur", "Mojopahit")')
        conn.commit(); conn.close()

    def get_user_settings():
        conn = sqlite3.connect('riwayat_v40_finalbtn.db'); c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone(); conn.close(); return data

    def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
        conn = sqlite3.connect('riwayat_v40_finalbtn.db'); c = conn.cursor()
        c.execute('''UPDATE user_settings SET nama=?, nip=?, kpm=?, prov=?, kab=?, kec=?, kel=? WHERE id=1''', (nama, nip, kpm, prov, kab, kec, kel))
        conn.commit(); conn.close()

    def simpan_riwayat(rhk, judul, lokasi):
        try:
            conn = sqlite3.connect('riwayat_v40_finalbtn.db'); c = conn.cursor()
            tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute('INSERT INTO riwayat (tgl, rhk, judul, lokasi) VALUES (?, ?, ?, ?)', (tgl, rhk, judul, lokasi))
            conn.commit(); conn.close()
        except: pass

    init_db()
    BASE_ARSIP = "Arsip_Foto_Kegiatan"

    def compress_image(uploaded_file, quality=70, max_width=800):
        try:
            uploaded_file.seek(0); image = Image.open(uploaded_file)
            if image.mode in ("RGBA", "P"): image = image.convert("RGB")
            if image.width > max_width:
                ratio = max_width / float(image.width); new_height = int((float(image.height) * float(ratio)))
                image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
            output = io.BytesIO(); image.save(output, format="JPEG", quality=quality, optimize=True)
            output.seek(0); uploaded_file.seek(0); return output
        except: uploaded_file.seek(0); return uploaded_file 

    def get_folder_path(rhk, per):
        try: parts=per.split(" "); b=parts[0]; t=parts[1]
        except: b="UMUM"; t="2026"
        return os.path.join(BASE_ARSIP, t, b, rhk.replace("–", "-").strip())

    def count_archived_photos():
        t = 0
        if os.path.exists(BASE_ARSIP):
            for r, d, f in os.walk(BASE_ARSIP): t += len([x for x in f if x.endswith(('jpg','png','jpeg'))])
        return t

    def auto_save_photo_local(f_obj, rhk, per):
        try:
            tf = get_folder_path(rhk, per); 
            if not os.path.exists(tf): os.makedirs(tf)
            cb = compress_image(f_obj); ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fn = f"{ts}_{f_obj.name.replace(' ', '_')}"
            with open(os.path.join(tf, fn), "wb") as f: f.write(cb.getvalue())
            return True
        except: return False

    def get_archived_photos(rhk, per):
        tf = get_folder_path(rhk, per)
        if os.path.exists(tf): 
            fl = [f for f in os.listdir(tf) if f.lower().endswith(('jpg','png','jpeg'))]
            fl.sort(reverse=True); return fl
        return []

    def load_photo_from_disk(rhk, per, fn):
        path = os.path.join(get_folder_path(rhk, per), fn)
        with open(path, "rb") as f: return io.BytesIO(f.read())

    def safe_str(d): return str(list(d.values())[0]) if isinstance(d, dict) else "-" if d is None else str(d)
    def clean_text_for_pdf(t): return safe_str(t).encode('latin-1', 'replace').decode('latin-1')
    def reset_states():
        st.session_state['rhk2_queue'] = []; st.session_state['rhk4_queue'] = []
        st.session_state['rhk7_queue'] = []; st.session_state['generated_file_data'] = None
        st.session_state['rhk3_results'] = None

    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, analisis="", app_info="", ket_info=""):
        max_retries = 3
        prompt = f"""Role: Pendamping PKH. Buat JSON Laporan. KONTEKS: RHK: {topik}, Kegiatan: {detail}, Lokasi: {lokasi_lengkap}, Periode: {bulan}, Catatan: {ket_info}.
        Output JSON Wajib (lowercase key): {{ "gambaran_umum": "...", "maksud_tujuan": "...", "ruang_lingkup": "...", "dasar_hukum": ["..."], "kegiatan": ["..."], "hasil": ["..."], "kesimpulan": "...", "saran": ["..."], "penutup": "..." }}"""
        for i in range(max_retries):
            try:
                res = model.generate_content(prompt); txt = res.text
                cln = txt.replace("```json", "").replace("```", "").strip()
                try: return json.loads(cln)
                except:
                    m = re.search(r'\{.*\}', txt, re.DOTALL)
                    if m: return json.loads(m.group())
            except: 
                if i < max_retries - 1: time.sleep(2); continue
                return None
        return None

    def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        doc = Document(); 
        for s in doc.sections: s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
        style = doc.styles['Normal']; style.font.name = 'Times New Roman'; style.font.size = Pt(12)
        if kop: p=doc.add_paragraph(); p.alignment=1; p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
        
        doc.add_paragraph(" "); p=doc.add_paragraph(); p.alignment=1
        run=p.add_run(f"LAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}"); run.bold=True; run.font.size=Pt(14)
        doc.add_paragraph(" ")

        def add_p(t):
            for x in safe_str(t).split('\n'):
                if x.strip(): p=doc.add_paragraph(); p.paragraph_format.first_line_indent=Cm(1.27); p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY; p.add_run(x.strip())

        doc.add_paragraph("A. Pendahuluan", style='Heading 1')
        doc.add_paragraph("1. Gambaran Umum", style='Heading 2'); add_p(f"Lokasi: {meta['kel']}, {meta['kec']}, {meta['kab']}."); add_p(data.get('gambaran_umum'))
        doc.add_paragraph("2. Maksud dan Tujuan", style='Heading 2'); add_p(data.get('maksud_tujuan'))
        doc.add_paragraph("3. Ruang Lingkup", style='Heading 2'); add_p(data.get('ruang_lingkup'))
        doc.add_paragraph("4. Dasar", style='Heading 2')
        for i,x in enumerate(data.get('dasar_hukum', []),1): p=doc.add_paragraph(); p.paragraph_format.left_indent=Cm(0.75); p.paragraph_format.first_line_indent=Cm(-0.75); p.add_run(f"{i}.\t{safe_str(x)}")

        doc.add_paragraph("B. Kegiatan", style='Heading 1')
        if extra_info and extra_info.get('desc'): p=doc.add_paragraph(f"Fokus: {extra_info['desc']}"); p.runs[0].italic=True
        for x in data.get('kegiatan', []): add_p(safe_str(x).replace('\n', ' '))

        doc.add_paragraph("C. Hasil", style='Heading 1')
        if kpm_data and isinstance(kpm_data, dict):
            p=doc.add_paragraph(); p.add_run("Profil KPM:").bold=True
            tbl=doc.add_table(rows=0, cols=3); tbl.autofit=False; tbl.columns[0].width=Cm(5.5); tbl.columns[1].width=Cm(0.5); tbl.columns[2].width=Cm(10.0)
            for k,v in kpm_data.items(): 
                if k != 'Pilih': r=tbl.add_row().cells; r[0].text=k; r[1].text=":"; r[2].text=str(v)
            doc.add_paragraph(" ")
        for i,x in enumerate(data.get('hasil', []),1): p=doc.add_paragraph(); p.paragraph_format.left_indent=Cm(0.75); p.paragraph_format.first_line_indent=Cm(-0.75); p.add_run(f"{i}.\t{safe_str(x)}")

        doc.add_paragraph("D. Penutup", style='Heading 1'); add_p(data.get('kesimpulan')); add_p(data.get('penutup'))
        doc.add_paragraph(" "); doc.add_paragraph(" ")
        
        tbl=doc.add_table(rows=1, cols=2); tbl.autofit=False; tbl.columns[0].width=Inches(3.5); tbl.columns[1].width=Inches(3.0)
        c=tbl.cell(0,1); p=c.paragraphs[0]; p.alignment=1
        p.add_run(f"Dibuat di {meta['kab']}\nPada Tanggal {meta['tgl']}\nPendamping PKH\n")
        if ttd: p.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8)); p.add_run("\n")
        else: p.add_run("\n\n\n")
        p.add_run(f"\n{meta['nama']}\n").bold=True; p.add_run(f"NIP. {meta['nip']}")

        doc.add_page_break(); p=doc.add_paragraph("DOKUMENTASI"); p.alignment=1; p.runs[0].bold=True; doc.add_paragraph(" ")
        if imgs:
            rt=doc.add_table(rows=(len(imgs)+1)//2, cols=2); rt.autofit=True
            for i,im in enumerate(imgs):
                try: 
                    cl=rt.cell(i//2, i%2); p=cl.paragraphs[0]; p.alignment=1
                    im.seek(0); p.add_run().add_picture(compress_image(im), width=Inches(2.8)); p.add_run(f"\nFoto {i+1}")
                except: pass
        
        bio=io.BytesIO(); doc.save(bio); return bio

    def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        pdf = FPDF(); pdf.set_margins(25, 20, 25); pdf.add_page(); pdf.set_font("Times", size=12)
        def J(t): pdf.multi_cell(0, 6, clean_text_for_pdf(t), align='J')
        def JI(t): pdf.multi_cell(0, 6, "        "+clean_text_for_pdf(t), align='J')
        
        if kop:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pdf.image(tmp.name, 10, 10, 190); os.unlink(tmp.name); pdf.ln(35)
        else: pdf.ln(10)

        pdf.set_font("Times", "B", 14); pdf.cell(0,6,"LAPORAN",0,1,'C'); pdf.cell(0,6,"TENTANG",0,1,'C')
        pdf.cell(0,6, clean_text_for_pdf(meta['judul'].upper()),0,1,'C'); pdf.cell(0,6, clean_text_for_pdf(meta['bulan'].upper()),0,1,'C'); pdf.ln(10)

        pdf.set_font("Times", "B", 12); pdf.cell(0,8,"A. Pendahuluan",0,1)
        pdf.cell(0,6,"1. Gambaran Umum",0,1); pdf.set_font("Times","",12); JI(f"Lokasi: {meta['kel']}, {meta['kec']}, {meta['kab']}."); JI(data.get('gambaran_umum'))
        
        pdf.set_font("Times", "B", 12); pdf.cell(0,6,"2. Maksud Tujuan",0,1); pdf.set_font("Times","",12); JI(data.get('maksud_tujuan'))
        pdf.set_font("Times", "B", 12); pdf.cell(0,6,"3. Dasar",0,1); pdf.set_font("Times","",12)
        for i,x in enumerate(data.get('dasar_hukum', []),1): pdf.cell(10,6,f"{i}.",0,0); pdf.multi_cell(0,6,clean_text_for_pdf(x))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0,8,"B. Kegiatan",0,1); pdf.set_font("Times","",12)
        if extra_info: pdf.set_font("Times","I",12); J(f"Fokus: {extra_info.get('desc')}"); pdf.set_font("Times","",12)
        for x in data.get('kegiatan', []): JI(x)

        pdf.ln(2); pdf.set_font("Times", "B", 12); pdf.cell(0,8,"C. Hasil",0,1); pdf.set_font("Times","",12)
        if kpm_data and isinstance(kpm_data, dict):
            for k,v in kpm_data.items():
                if k!='Pilih': pdf.cell(50,6,clean_text_for_pdf(k),0,0); pdf.cell(5,6,":",0,0); pdf.multi_cell(0,6,clean_text_for_pdf(str(v)),0,1)
            pdf.ln(2)
        for i,x in enumerate(data.get('hasil', []),1): pdf.cell(10,6,f"{i}.",0,0); pdf.multi_cell(0,6,clean_text_for_pdf(x))

        pdf.ln(4); pdf.set_font("Times", "B", 12); pdf.cell(0,8,"D. Penutup",0,1); pdf.set_font("Times","",12); JI(data.get('penutup'))
        
        pdf.ln(10); x=110; pdf.set_x(x); pdf.cell(80,5,f"Dibuat di {meta['kab']}",0,1,'C')
        pdf.set_x(x); pdf.cell(80,5,f"Pada {meta['tgl']}",0,1,'C'); pdf.set_x(x); pdf.cell(80,5,"Pendamping PKH",0,1,'C')
        if ttd:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(ttd); pdf.image(tmp.name, x+25, pdf.get_y(), h=25); os.unlink(tmp.name); pdf.ln(25)
        else: pdf.ln(25)
        pdf.set_x(x); pdf.set_font("Times","B",12); pdf.cell(80,5,clean_text_for_pdf(meta['nama']),0,1,'C')
        pdf.set_x(x); pdf.set_font("Times","",12); pdf.cell(80,5,f"NIP. {meta['nip']}",0,1,'C')

        if imgs:
            pdf.add_page(); pdf.set_font("Times","B",12); pdf.cell(0,10,"DOKUMENTASI",0,1,'C'); pdf.ln(5)
            for i,im in enumerate(imgs):
                if i>0 and i%2==0:
                    pdf.ln(60)
                    if pdf.get_y()>250: pdf.add_page(); pdf.ln(10)
                xp=30 if i%2==0 else 120; yp=pdf.get_y()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    im.seek(0); tmp.write(im.read()); tp=tmp.name
                try: pdf.image(tp, xp, yp, w=70, h=50); pdf.set_xy(xp, yp+52); pdf.set_font("Times","",9); pdf.multi_cell(70,4,f"Foto {i+1}",0,'C'); pdf.set_xy(25, yp)
                except: pass
                finally: os.unlink(tp)
        return pdf.output(dest='S').encode('latin-1')

    # ==========================================
    # 8. UI HANDLER
    # ==========================================
    def update_tgl():
        d="28" if st.session_state.bln_val=="FEBRUARI" else "30"
        st.session_state.tgl_val = f"{d} {st.session_state.bln_val.title()} {st.session_state.th_val}"

    def render_sidebar():
        set_data = get_user_settings()
        st.sidebar.header("👤 Profil Pendamping")
        nm = st.sidebar.text_input("Nama", set_data[0], key="nama_val")
        nip = st.sidebar.text_input("NIP", set_data[1], key="nip_val")
        kpm = st.sidebar.number_input("Jml KPM", value=set_data[2], key="kpm_global_val")
        st.sidebar.markdown("### 🌍 Wilayah")
        prov = st.sidebar.text_input("Provinsi", set_data[3], key="prov_val")
        kab = st.sidebar.text_input("Kabupaten", set_data[4], key="kab_val")
        kec = st.sidebar.text_input("Kecamatan", set_data[5], key="kec_val")
        kel = st.sidebar.text_input("Kelurahan", set_data[6], key="kel_val")
        
        st.sidebar.markdown("### 📅 Periode")
        c1, c2 = st.sidebar.columns([1, 1.5])
        with c1: st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tgl)
        with c2: st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], key="bln_val", on_change=update_tgl)
        st.sidebar.text_input("Tanggal Surat", key="tgl_val")
        
        st.sidebar.markdown("---"); st.sidebar.info(f"📂 Arsip: {count_archived_photos()} Foto")
        k = st.sidebar.file_uploader("Kop", type=['png','jpg'])
        t = st.sidebar.file_uploader("TTD", type=['png','jpg'])
        if st.sidebar.button("💾 SIMPAN PROFIL"):
            save_user_settings(nm, nip, kpm, prov, kab, kec, kel)
            if k: st.session_state['kop_bytes'] = k.getvalue()
            if t: st.session_state['ttd_bytes'] = t.getvalue()
            st.sidebar.success("Disimpan!")

    def show_dashboard():
        st.title("📂 Aplikasi RHK PKH Pro"); st.markdown("### Menu Utama")
        ks = list(CONFIG_LAPORAN.keys()); cols = st.columns(4)
        for i, k in enumerate(ks):
            ic = "💸" if "RHK 1" in k else "📚" if "RHK 2" in k else "🎓" if "RHK 3" in k else "📝" if "RHK 4" in k else "👥" if "RHK 5" in k else "🆘" if "RHK 6" in k else "📢"
            # Format Label: Judul (RHK X) di atas, Keterangan di bawah (dipisah 2 enter)
            lbl = f"{ic} {k.split('–')[0].strip()}\n\n{k.split('–')[-1].strip()}"
            with cols[i % 4]:
                if st.button(lbl, key=f"b_{i}"):
                    st.session_state['selected_rhk']=k; st.session_state['page']='detail'
                    st.query_params["page"]="detail"; st.query_params["rhk"]=k; reset_states(); st.rerun()

    def show_detail():
        cr = st.session_state['selected_rhk']
        with st.container():
            nc = st.columns(8)
            if nc[0].button("🏠 HOME"):
                st.session_state['page']='home'; st.query_params["page"]="home"
                if "rhk" in st.query_params: del st.query_params["rhk"]
                reset_states(); st.rerun()
            for i, k in enumerate(CONFIG_LAPORAN.keys()):
                if k!=cr and i+1<8:
                    if nc[i+1].button(k.split('–')[0].strip(), key=f"n_{k}"):
                        st.session_state['selected_rhk']=k; st.query_params["rhk"]=k; reset_states(); st.rerun()

        st.divider(); st.subheader(cr)
        def_jud = "KEGIATAN PENYALURAN" if "RHK 1" in cr else "P2K2 (FDS)" if "RHK 2" in cr else "GRADUASI MANDIRI" if "RHK 3" in cr else "PEMUTAKHIRAN DATA" if "RHK 4" in cr else "PEMUTAKHIRAN DATA KPM" if "RHK 5" in cr else "PENANGANAN KASUS" if "RHK 6" in cr else "TUGAS DIREKTIF"
        jk = st.text_input("Judul Kop (Edit):", value=def_jud); st.divider()
        
        meta = {
            'bulan': f"{st.session_state.bln_val} {st.session_state.th_val}",
            'kpm': st.session_state.kpm_global_val, 'nama': st.session_state.nama_val, 'nip': st.session_state.nip_val,
            'prov': st.session_state.prov_val, 'kab': st.session_state.kab_val, 'kec': st.session_state.kec_val, 'kel': st.session_state.kel_val,
            'tgl': st.session_state.tgl_val, 'judul': jk
        }
        loc = f"Desa {meta['kel']}, Kec. {meta['kec']}, {meta['kab']}"
        kop = st.session_state.kop_bytes; ttd = st.session_state.ttd_bytes

        def phot_man(suf):
            st.write("#### 📸 Dokumentasi")
            t1, t2 = st.tabs(["📤 Upload", "🗂️ Arsip"]); sel=[]
            with t1: 
                up = st.file_uploader("File Foto", type=['jpg','png'], accept_multiple_files=True, key=f"u_{suf}")
                if up: sel=[io.BytesIO(f.getvalue()) for f in up]
            with t2:
                sv = get_archived_photos(cr, meta['bulan'])
                if sv: 
                    for x in st.multiselect("Pilih Arsip:", sv, key=f"m_{suf}"): sel.append(load_photo_from_disk(cr, meta['bulan'], x))
                else: st.info("Kosong")
            return sel, up

        if "RHK 3" in cr:
            st.info("ℹ️ RHK 3: Pakai Excel.")
            td = pd.DataFrame({"Nama":["A"], "NIK":["123"], "Alamat":["B"], "Kategori":["S"], "Status":["L"], "Jenis Graduasi":["S"], "Tahun Bergabung":["2018"], "Jumlah Anggota":["4"], "Alasan":["M"]})
            b=io.BytesIO(); td.to_excel(b, index=False); b.seek(0)
            st.download_button("📥 Template XLSX", b, "template.xlsx")
            
            up = st.file_uploader("Upload Excel", type=['xlsx'])
            if up: st.session_state['graduasi_raw'] = pd.read_excel(up)
            
            if st.session_state['graduasi_raw'] is not None:
                df = st.session_state['graduasi_raw']; 
                if 'Pilih' not in df.columns: df.insert(0, "Pilih", False)
                ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                if st.button("💾 Simpan Pilihan"): st.session_state['graduasi_fix'] = ed[ed['Pilih']==True].to_dict('records'); st.success("Disimpan")

            ket = st.text_area("Keterangan:", height=80); ph, nu = phot_man("3")
            if st.button("🚀 Generate RHK 3", type="primary"):
                if nu: [auto_save_photo_local(f, cr, meta['bulan']) for f in nu]
                kp = st.session_state.get('graduasi_fix', []); res=[]
                pr = st.progress(0); stt = st.empty()
                for i, k in enumerate(kp):
                    nm = str(k.get('Nama', 'KPM')); stt.info(f"Proses: {nm}..."); time.sleep(3)
                    dt = generate_isi_laporan(cr, f"Graduasi: {nm}", meta['kpm'], nm, meta['bulan'], loc, ket_info=ket)
                    if dt:
                        [p.seek(0) for p in ph]
                        res.append({'nama': nm, 'word': create_word_doc(dt, meta, ph, kop, ttd, {'desc':ket}, k).getvalue(), 'pdf': create_pdf_doc(dt, meta, ph, kop, ttd, {'desc':ket}, k)})
                    pr.progress((i+1)/len(kp))
                st.session_state['rhk3_results'] = res; st.success("Selesai!"); st.rerun()
            
            if st.session_state.get('rhk3_results'):
                for i, r in enumerate(st.session_state['rhk3_results']):
                    c1,c2,c3=st.columns([3,1,1]); c1.write(f"📄 **{r['nama']}**")
                    c2.download_button("Word", r['word'], f"{r['nama']}.docx", key=f"w{i}")
                    c3.download_button("PDF", r['pdf'], f"{r['nama']}.pdf", key=f"p{i}")

        elif cr in ["RHK 2 – LAPORAN P2K2 (FDS)", "RHK 4 – KEGIATAN PEMUTAKHIRAN", "RHK 7 – LAPORAN DIREKTIF"]:
            qk = 'rhk2_queue' if "RHK 2" in cr else 'rhk4_queue' if "RHK 4" in cr else 'rhk7_queue'
            rk = 'rhk2_results' if "RHK 2" in cr else 'rhk4_results' if "RHK 4" in cr else 'rhk7_results'
            
            with st.container(border=True):
                st.write("#### ➕ Antrian")
                md = st.text_input("Kegiatan:") if "RHK 7" in cr else st.selectbox("Modul:", CONFIG_LAPORAN[cr])
                ap = st.selectbox("App:", ["SIKS-NG", "ESDM", "SIKMA"]) if "RHK 4" in cr else ""
                kt = st.text_area("Ket:", height=80); ph, nu = phot_man("q")
                if st.button("Masuk Antrian"):
                    if not ph: st.error("Foto Wajib!")
                    else:
                        if nu: [auto_save_photo_local(f, cr, meta['bulan']) for f in nu]
                        st.session_state[qk].append({"modul": md, "foto": ph, "foto_count": len(ph), "app": ap, "desc": kt})
                        st.success("Masuk!"); time.sleep(0.5); st.rerun()
            
            q = st.session_state[qk]
            if q:
                st.write(f"### 📋 List ({len(q)})"); 
                for i,x in enumerate(q): st.write(f"{i+1}. {x['modul']} ({x['foto_count']} Foto)")
                if st.button("Hapus Semua"): st.session_state[qk]=[]; st.rerun()
                if st.button("🚀 Generate Semua", type="primary"):
                    res=[]; pr=st.progress(0); stt=st.empty()
                    for i, it in enumerate(q):
                        nm=it['modul']; stt.info(f"Proses: {nm}..."); time.sleep(3)
                        d = generate_isi_laporan(cr, nm, meta['kpm'], "Peserta", meta['bulan'], loc, "", it.get('app'), it.get('desc'))
                        if d:
                            [p.seek(0) for p in it['foto']]
                            res.append({'nama': nm, 'word': create_word_doc(d, meta, it['foto'], kop, ttd, {'desc':it.get('desc')}).getvalue(), 'pdf': create_pdf_doc(d, meta, it['foto'], kop, ttd, {'desc':it.get('desc')})})
                        pr.progress((i+1)/len(q))
                    st.session_state[rk]=res; st.success("Selesai!"); st.rerun()
            
            rs = st.session_state.get(rk)
            if rs:
                for i, r in enumerate(rs):
                    c1,c2,c3=st.columns([3,1,1]); c1.write(f"📘 **{r['nama']}**")
                    c2.download_button("Word", r['word'], f"{r['nama']}.docx", key=f"wq{i}")
                    c3.download_button("PDF", r['pdf'], f"{r['nama']}.pdf", key=f"pq{i}")

        else: # RHK 1, 5, 6
            sub = CONFIG_LAPORAN[cr]
            jk = sub[0] if len(sub)==1 else st.text_input("Kegiatan:", value=sub[0])
            kt = st.text_area("Ket:", height=80); ph, nu = phot_man("s")
            
            if st.button("🚀 Generate Laporan", type="primary"):
                if nu: [auto_save_photo_local(f, cr, meta['bulan']) for f in nu]
                with st.status("Proses...", expanded=True) as s:
                    st.write("Analisis..."); time.sleep(2); st.write("AI Generating...")
                    d = generate_isi_laporan(cr, jk, meta['kpm'], "Peserta", meta['bulan'], loc, ket_info=kt)
                    if d:
                        st.write("Menyusun...")
                        [p.seek(0) for p in ph]; w=create_word_doc(d, meta, ph, kop, ttd, {'desc':kt}).getvalue()
                        [p.seek(0) for p in ph]; p=create_pdf_doc(d, meta, ph, kop, ttd, {'desc':kt})
                        st.session_state['generated_file_data']={'name':cr, 'word':w, 'pdf':p}
                        simpan_riwayat(cr, "Gen", meta['kel']); s.update(label="Selesai!", state="complete", expanded=False)
                    else: s.update(label="Gagal", state="error")

            f = st.session_state.get('generated_file_data')
            if f:
                c1,c2=st.columns(2)
                c1.download_button("Word", f['word'], f"{f['name']}.docx")
                c2.download_button("PDF", f['pdf'], f"{f['name']}.pdf")

    render_sidebar()
    if st.session_state['page'] == 'home': show_dashboard()
    elif st.session_state['page'] == 'detail': show_detail()
