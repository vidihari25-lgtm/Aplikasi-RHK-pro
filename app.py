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
    if st.session_state.get("password_correct", False):
        return True

    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True
        st.session_state["username"] = qp.get("user")
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APLIKASI</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_user = st.text_input("Username", key="login_user")
        input_pass = st.text_input("Password", type="password", key="login_pass")
        
        if st.button("MASUK / LOGIN", type="primary", use_container_width=True):
            if input_user in DAFTAR_USER and DAFTAR_USER[input_user] == input_pass:
                st.session_state["password_correct"] = True
                st.session_state["username"] = input_user
                st.query_params["auth"] = "valid"
                st.query_params["user"] = input_user
                st.rerun()
            else:
                st.error("😕 Username atau Password Salah!")
    return False

if check_password():

    # ==========================================
    # 3. SETUP & INIT STATE
    # ==========================================
    with st.sidebar:
        st.write(f"👤 Login: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout", type="secondary"):
            st.session_state["password_correct"] = False
            st.query_params.clear()
            st.rerun()

    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 
            'graduasi_raw', 'graduasi_fix', 'generated_file_data', 
            'rhk3_results', 'rhk2_queue', 'rhk2_results', 
            'rhk4_queue', 'rhk4_results', 'rhk7_queue', 'rhk7_results',
            'rhk8_queue', 'rhk9_queue', 'rhk9_results',
            'tgl_val', 'bln_val', 'th_val'] 

    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    if "page" in st.query_params: st.session_state['page'] = st.query_params["page"]
    if "rhk" in st.query_params: st.session_state['selected_rhk'] = st.query_params["rhk"]

    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk4_queue'] is None: st.session_state['rhk4_queue'] = []
    if st.session_state['rhk7_queue'] is None: st.session_state['rhk7_queue'] = []
    if st.session_state['rhk8_queue'] is None: st.session_state['rhk8_queue'] = []
    if st.session_state['rhk9_queue'] is None: st.session_state['rhk9_queue'] = []
    if st.session_state['page'] is None: st.session_state['page'] = 'home'

    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    if not st.session_state['tgl_val']: st.session_state['tgl_val'] = "30 Januari 2026"

    # ==========================================
    # 4. DATABASE & TOOLS (UPDATE 9 RHK)
    # ==========================================
    CONFIG_LAPORAN = {
        "RHK 1 – LAPORAN PENYALURAN BANSOS": ["Laporan Penyaluran Bantuan Sosial"],
        "RHK 2 – LAPORAN PERTEMUAN P2K2": [
            "Modul Ekonomi 1: Mengelola Keuangan Keluarga", "Modul Ekonomi 2: Cermat Meminjam Dan Menabung", "Modul Ekonomi 3: Memulai Usaha",
            "Modul Kesehatan 1: Pentingnya Gizi Ibu Hamil", "Modul Kesehatan 2: Pentingnya Gizi Ibu Menyusui & Balita", "Modul Kesehatan 3: Kesakitan Anak & Kesling",
            "Modul Kesehatan 4: Permainan Anak", "Modul Kesejahteraan 1: Disabilitas Berat", "Modul Kesejahteraan 2: Kesejahteraan Lanjut Usia",
            "Modul Pengasuhan 1: Menjadi Orangtua Lebih Baik", "Modul Pengasuhan 2: Perilaku Anak", "Modul Pengasuhan 3: Cara Anak Usia Dini Belajar",
            "Modul Pengasuhan 4: Membantu Anak Sukses Sekolah", "Modul Perlindungan 1: Pencegahan Kekerasan Anak", "Modul Perlindungan 2: Penelantaran & Eksploitasi Anak"
        ],
        "RHK 3 – LAPORAN VERIFIKASI KOMITMEN DATA KPM": ["Verifikasi Fasilitas Pendidikan", "Verifikasi Fasilitas Kesehatan", "Verifikasi Kesejahteraan Sosial"],
        "RHK 4 – REKAPITULASI DATA KPM GRADUASI": ["Laporan Graduasi Mandiri"], 
        "RHK 5 – LAPORAN DATA VERIFIKASI, VALIDASI DAN PEMUTAKHIRAN DATA KPM": ["Laporan Hasil Pemutakhiran Data KPM"],
        "RHK 6 – PERSENTASE PENYELESAIAN LAPORAN KASUS ADAPTIF": ["Laporan Penanganan Kasus (Respon Kasus/Bencana/Kerentanan)"],
        "RHK 7 – LAPORAN BULANAN ASN PPPK": ["Laporan Kinerja Bulanan ASN PPPK"],
        "RHK 8 – LAPORAN PELAKSANA TUGAS DIREKTIF": ["Laporan Pelaksanaan Tugas"],
        "RHK 9 – PRESENTASE PENYELESAIAN PENUGASAN DIREKTIF PIMPINAN": ["Tugas Direktif Pimpinan (A)", "Tugas Direktif Pimpinan (B)"]
    }

    def init_db():
        conn = sqlite3.connect('riwayat_v40_finalbtn.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS riwayat (id INTEGER PRIMARY KEY, tgl TEXT, rhk TEXT, judul TEXT, lokasi TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_settings (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
        c.execute('SELECT count(*) FROM user_settings')
        if c.fetchone()[0] == 0:
            c.execute('INSERT INTO user_settings (id, nama, nip, kpm, prov, kab, kec, kel) VALUES (1, ?, ?, ?, ?, ?, ?, ?)', ("User", "123456", 120, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan"))
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
        for k in ['rhk2_queue', 'rhk4_queue', 'rhk7_queue', 'rhk8_queue', 'rhk9_queue', 'generated_file_data', 'rhk3_results']:
            st.session_state[k] = [] if 'queue' in k else None

    # ==========================================
    # 5. ENGINE AI
    # ==========================================
    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, analisis="", app_info="", ket_info=""):
        max_retries = 3
        prompt = f"""
        Role: Pendamping PKH Profesional.
        Buat JSON Laporan Kegiatan.
        KONTEKS:
        - RHK: {topik} | Nama Kegiatan: {detail} 
        - Lokasi: {lokasi_lengkap} | Periode: {bulan}
        - CATATAN USER: {ket_info}
        Output JSON Wajib (lowercase key):
        {{
            "gambaran_umum": "...", "maksud_tujuan": "...", "ruang_lingkup": "...",
            "dasar_hukum": ["..."], "kegiatan": ["..."], "hasil": ["..."],
            "kesimpulan": "...", "saran": ["..."], "penutup": "..."
        }}
        """
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                clean_text = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_text)
            except:
                if attempt < max_retries - 1: time.sleep(2); continue
        return None

    # ==========================================
    # 6. DOCUMENT GENERATORS
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

        def add_p_indent(text, bold=False):
            safe_text = safe_str(text)
            for p_text in safe_text.split('\n'):
                if p_text.strip():
                    p = doc.add_paragraph()
                    p.paragraph_format.first_line_indent = Cm(1.27) 
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
        doc.add_paragraph("2. Maksud dan Tujuan", style='Heading 2'); add_p_indent(data.get('maksud_tujuan'))
        doc.add_paragraph("3. Ruang Lingkup", style='Heading 2'); add_p_indent(data.get('ruang_lingkup'))
        doc.add_paragraph("4. Dasar", style='Heading 2')
        for i, item in enumerate(data.get('dasar_hukum', []), 1): add_numbered_item(i, item)

        doc.add_paragraph("B. Kegiatan yang dilaksanakan", style='Heading 1')
        for item in data.get('kegiatan', []): add_p_indent(item)

        doc.add_paragraph("C. Hasil yang dicapai", style='Heading 1')
        if kpm_data:
            table = doc.add_table(rows=0, cols=3)
            for label, val in kpm_data.items():
                row = table.add_row().cells
                row[0].text = label; row[1].text = ":"; row[2].text = str(val)
        for i, item in enumerate(data.get('hasil', []), 1): add_numbered_item(i, item)

        doc.add_paragraph("D. Kesimpulan dan Saran", style='Heading 1')
        add_p_indent(data.get('kesimpulan'))
        for item in data.get('saran', []): doc.add_paragraph(f"- {item}").paragraph_format.left_indent = Cm(1.0)

        doc.add_paragraph("E. Penutup", style='Heading 1'); add_p_indent(data.get('penutup'))

        table = doc.add_table(rows=1, cols=2)
        cell = table.cell(0, 1)
        p_ttd = cell.paragraphs[0]; p_ttd.alignment = 1
        p_ttd.add_run(f"Dibuat di {meta['kab']}\nPada Tanggal {meta['tgl']}\nPendamping PKH\n")
        if ttd: p_ttd.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
        p_ttd.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}").bold = True

        if imgs:
            doc.add_page_break()
            doc.add_paragraph("LAMPIRAN DOKUMENTASI").alignment = 1
            for img_data in imgs:
                img_data.seek(0)
                doc.add_picture(compress_image(img_data), width=Inches(4))

        bio = io.BytesIO(); doc.save(bio); return bio

    def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        pdf = FPDF(); pdf.set_margins(25, 20, 25); pdf.add_page(); pdf.set_font("Times", size=12)
        def TXT(s): return clean_text_for_pdf(s)

        if kop:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(kop); pth=tmp.name
            pdf.image(pth, x=10, y=10, w=190); os.unlink(pth); pdf.ln(35)
        
        pdf.set_font("Times", "B", 14); pdf.cell(0, 6, "LAPORAN TENTANG", ln=True, align='C')
        pdf.cell(0, 6, TXT(meta['judul'].upper()), ln=True, align='C'); pdf.ln(10)

        pdf.set_font("Times", "B", 12); pdf.cell(0, 8, "A. Pendahuluan", ln=True)
        pdf.set_font("Times", "", 12); pdf.multi_cell(0, 6, TXT(data.get('gambaran_umum')), align='J')
        
        pdf.ln(10); pdf.set_font("Times", "B", 12); pdf.cell(0, 5, TXT(meta['nama']), ln=True, align='R')
        
        if ttd:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(ttd); pth=tmp.name
            pdf.image(pth, x=140, y=pdf.get_y(), h=20); os.unlink(pth)
            
        return pdf.output(dest='S').encode('latin-1')

    # ==========================================
    # 7. UI PAGES
    # ==========================================
    def update_tanggal_surat():
        bln = st.session_state.get('bln_val', 'JANUARI')
        th = st.session_state.get('th_val', '2026')
        st.session_state.tgl_val = f"30 {bln.title()} {th}"

    def render_sidebar():
        u_nama, u_nip, u_kpm, u_prov, u_kab, u_kec, u_kel = get_user_settings()
        with st.sidebar.expander("👤 Profil Pendamping", expanded=True):
            nama = st.text_input("Nama Lengkap", u_nama)
            nip = st.text_input("NIP", u_nip)
            kpm = st.number_input("KPM Dampingan", value=u_kpm)
        with st.sidebar.expander("🌍 Wilayah", expanded=False):
            prov = st.text_input("Provinsi", u_prov); kab = st.text_input("Kabupaten", u_kab)
            kec = st.text_input("Kecamatan", u_kec); kel = st.text_input("Kelurahan", u_kel)
        with st.sidebar.expander("📅 Periode", expanded=False):
            st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal_surat)
            st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], key="bln_val", on_change=update_tanggal_surat)
            st.text_input("Tanggal Surat", key="tgl_val")
        with st.sidebar.expander("🖼️ Atribut", expanded=False):
            k = st.file_uploader("Kop Surat", type=['png','jpg'])
            t = st.file_uploader("Tanda Tangan", type=['png','jpg'])

        if st.sidebar.button("💾 SIMPAN PROFIL"):
            save_user_settings(nama, nip, kpm, prov, kab, kec, kel)
            if k: st.session_state['kop_bytes'] = k.getvalue()
            if t: st.session_state['ttd_bytes'] = t.getvalue()
            st.sidebar.success("Tersimpan!")

    def show_dashboard():
        st.markdown("""
        <style>
        div.stButton > button {
            width: 100%; height: 140px; font-size: 14px; font-weight: bold; border-radius: 12px;
            background: linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%); color: #0277bd; border: 1px solid #b3e5fc;
        }
        div.stButton > button:hover { transform: translateY(-3px); border-color: #0277bd; }
        </style>
        """, unsafe_allow_html=True)

        st.title("📂 Aplikasi RHK PKH Pro"); st.markdown("### Menu Utama (9 RHK)")
        rhk_keys = list(CONFIG_LAPORAN.keys()); cols = st.columns(3)
        for i, rhk in enumerate(rhk_keys):
            icon = "💰" if "RHK 1" in rhk else "👨‍👩‍👧" if "RHK 2" in rhk else "✅" if "RHK 3" in rhk else "🎓" if "RHK 4" in rhk else "📋" if "RHK 5" in rhk else "⚠️" if "RHK 6" in rhk else "👔" if "RHK 7" in rhk else "📜" if "RHK 8" in rhk else "📢"
            label = f"{icon}\n{rhk.split('–')[0].strip()}\n{rhk.split('–')[-1].strip()}"
            with cols[i % 3]:
                if st.button(label, key=f"btn_{i}"):
                    st.session_state['selected_rhk'] = rhk; st.session_state['page'] = 'detail'
                    st.query_params["page"] = "detail"; st.query_params["rhk"] = rhk
                    reset_states(); st.rerun()

    def show_detail_page():
        current_rhk = st.session_state['selected_rhk']
        if st.button("🏠 KEMBALI KE MENU UTAMA"):
            st.session_state['page'] = 'home'; reset_states(); st.rerun()
        
        st.divider(); st.subheader(f"{current_rhk}")
        judul_kop = st.text_input("Judul Kop Laporan:", value=current_rhk.split("–")[-1].strip())
        
        meta = {
            'bulan': f"{st.session_state.get('bln_val')} {st.session_state.get('th_val')}",
            'nama': st.session_state.get('nama_val', 'User'), 'nip': st.session_state.get('nip_val', '-'),
            'prov': st.session_state.get('prov_val', '-'), 'kab': st.session_state.get('kab_val', '-'),
            'kec': st.session_state.get('kec_val', '-'), 'kel': st.session_state.get('kel_val', '-'),
            'tgl': st.session_state.get('tgl_val', '-'), 'judul': judul_kop
        }

        # Handle Photo Upload
        ups = st.file_uploader("Upload Foto Kegiatan", type=['jpg','png','jpeg'], accept_multiple_files=True)
        photos = [io.BytesIO(f.getvalue()) for f in ups] if ups else []

        if st.button("🚀 GENERATE LAPORAN", type="primary"):
            if not photos: st.warning("Unggah foto terlebih dahulu."); return
            
            with st.spinner("AI sedang menyusun laporan..."):
                data = generate_isi_laporan(current_rhk, judul_kop, 120, "KPM", meta['bulan'], f"{meta['kel']}, {meta['kec']}")
                if data:
                    w = create_word_doc(data, meta, photos, st.session_state['kop_bytes'], st.session_state['ttd_bytes']).getvalue()
                    st.session_state['generated_file_data'] = {'word': w}
                    st.success("Laporan Berhasil Dibuat!")
                    st.rerun()

        f = st.session_state.get('generated_file_data')
        if f:
            st.download_button("📥 Download Word (.docx)", f['word'], f"{current_rhk}.docx")

    # ==========================================
    # 8. ROUTING
    # ==========================================
    render_sidebar()
    if st.session_state['page'] == 'home': show_dashboard()
    else: show_detail_page()
