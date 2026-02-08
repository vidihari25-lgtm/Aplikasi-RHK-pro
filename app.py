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

# --- DAFTAR USER & PASSWORD ---
DAFTAR_USER = {
    "admin": "admin123",
    "pendamping": "pkh2026",
    "user": "user"
}

# ==========================================
# 2. SISTEM KEAMANAN & LOGIN
# ==========================================

# --- API KEY DARI SECRETS ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except FileNotFoundError:
    st.error("🚨 File .streamlit/secrets.toml tidak ditemukan!")
    st.stop()
except KeyError:
    st.error("🚨 Key 'GOOGLE_API_KEY' tidak ditemukan di secrets.toml.")
    st.stop()

# --- KONFIGURASI AI TERBARU (GEMINI 2.0 FLASH) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json",
    }
    # Update Model ke 2.0 Flash
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash", 
        generation_config=generation_config,
    )
except Exception as e:
    st.error(f"Gagal konfigurasi AI: {e}")

# --- FUNGSI LOGIN ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    qp = st.query_params
    if qp.get("auth") == "valid" and qp.get("user") in DAFTAR_USER:
        st.session_state["password_correct"] = True
        st.session_state["username"] = qp.get("user")
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🔐 LOGIN APP RHK</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            input_user = st.text_input("Username")
            input_pass = st.text_input("Password", type="password")
            submitted = st.form_submit_button("MASUK / LOGIN", type="primary", use_container_width=True)
            
            if submitted:
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
        st.write(f"👤 User: **{st.session_state.get('username', 'User')}**")
        if st.button("🔒 Logout", type="primary"):
            st.session_state["password_correct"] = False
            st.query_params.clear()
            st.rerun()

    # Init Session State
    keys = ['page', 'selected_rhk', 'kop_bytes', 'ttd_bytes', 
            'graduasi_raw', 'graduasi_fix', 'generated_file_data', 
            'rhk2_queue', 'rhk2_results', 
            'rhk3_queue', 'rhk3_results', 
            'rhk4_graduasi_results',
            'rhk8_queue', 'rhk8_results', 
            'tgl_val', 'bln_val', 'th_val'] 

    for k in keys:
        if k not in st.session_state: st.session_state[k] = None

    # Lists Initialization
    if st.session_state['rhk2_queue'] is None: st.session_state['rhk2_queue'] = []
    if st.session_state['rhk3_queue'] is None: st.session_state['rhk3_queue'] = []
    if st.session_state['rhk8_queue'] is None: st.session_state['rhk8_queue'] = []
    
    if st.session_state['page'] is None: st.session_state['page'] = 'home'
    if not st.session_state['bln_val']: st.session_state['bln_val'] = "JANUARI"
    if not st.session_state['th_val']: st.session_state['th_val'] = "2026"
    if not st.session_state['tgl_val']: st.session_state['tgl_val'] = "30 Januari 2026"

    # ==========================================
    # 4. DATABASE & DEFINISI RHK
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

    # --- Database Sederhana ---
    def init_db():
        conn = sqlite3.connect('rhk_pro_2.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS user_settings (id INTEGER PRIMARY KEY, nama TEXT, nip TEXT, kpm INTEGER, prov TEXT, kab TEXT, kec TEXT, kel TEXT)''')
        c.execute('SELECT count(*) FROM user_settings')
        if c.fetchone()[0] == 0:
            c.execute('INSERT INTO user_settings (id, nama, nip, kpm, prov, kab, kec, kel) VALUES (1, ?, ?, ?, ?, ?, ?, ?)', ("Pendamping PKH", "19xxxx", 100, "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan"))
        conn.commit(); conn.close()

    def get_user_settings():
        conn = sqlite3.connect('rhk_pro_2.db'); c = conn.cursor()
        c.execute('SELECT nama, nip, kpm, prov, kab, kec, kel FROM user_settings WHERE id=1')
        data = c.fetchone(); conn.close(); return data

    def save_user_settings(nama, nip, kpm, prov, kab, kec, kel):
        conn = sqlite3.connect('rhk_pro_2.db'); c = conn.cursor()
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
            
            with open(os.path.join(target_folder, final_name), "wb") as f:
                f.write(uploaded_file_obj.getvalue())
            return True
        except: return False

    # --- TEXT & PDF TOOLS ---
    def clean_text_for_pdf(text):
        if not text: return "-"
        text = str(text).replace('\u2013', '-').replace('\u201c', '"').replace('\u201d', '"')
        return text.encode('latin-1', 'replace').decode('latin-1')

    # ==========================================
    # 5. GENERATOR AI (GEMINI 2.0 FLASH)
    # ==========================================
    def generate_isi_laporan(topik, detail, kpm_total, kpm_fokus, bulan, lokasi_lengkap, ket_info=""):
        prompt = f"""
        Bertindaklah sebagai Pendamping Sosial PKH Profesional. 
        Buatlah JSON Laporan Kegiatan yang *Sangat Detail* dan *Manusiawi*.
        
        DATA:
        - RHK: {topik}
        - Kegiatan: {detail}
        - Lokasi: {lokasi_lengkap}
        - Periode: {bulan}
        - KETERANGAN KHUSUS (Wajib masuk narasi): {ket_info}

        Output JSON format (wajib JSON valid):
        {{
            "gambaran_umum": "Jelaskan situasi wilayah dan urgensi kegiatan ini...",
            "maksud_tujuan": "Jelaskan tujuan strategis dan operasional...",
            "ruang_lingkup": "Jelaskan siapa sasarannya dan metodenya...",
            "dasar_hukum": ["Permensos No 1 Tahun 2018", "Juknis PKH Tahun Berjalan"],
            "kegiatan": ["Deskripsi detail proses pelaksanaan...", "Interaksi yang terjadi...", "{ket_info}"],
            "hasil": ["Indikator keberhasilan 1...", "Output yang dicapai..."],
            "kesimpulan": "Analisis singkat keberhasilan kegiatan...",
            "saran": ["Rekomendasi tindak lanjut 1...", "Rekomendasi 2..."],
            "penutup": "Demikian laporan ini dibuat sebagai pertanggungjawaban..."
        }}
        """
        try:
            response = model.generate_content(prompt)
            return json.loads(response.text)
        except Exception as e:
            # Mengembalikan None jika terjadi error, akan ditangani di create_word_doc
            return None

    # ==========================================
    # 6. PEMBUAT DOKUMEN (Word & PDF)
    # ==========================================
    def create_word_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        # --- FIX ERROR ATTRIBUTE ERROR ---
        # Jika 'data' kosong (AI gagal generate), hentikan proses agar tidak error
        if not data:
            return None

        doc = Document()
        # Setup Margin
        for s in doc.sections: 
            s.top_margin=Cm(2); s.bottom_margin=Cm(2); s.left_margin=Cm(2.5); s.right_margin=Cm(2.5)
        
        # KOP SURAT
        if kop: 
            try:
                p = doc.add_paragraph(); p.alignment = 1
                p.add_run().add_picture(io.BytesIO(kop), width=Inches(6.2))
            except: pass
        
        # JUDUL
        p = doc.add_paragraph(f"\nLAPORAN\nTENTANG\n{meta['judul'].upper()}\n{meta['bulan'].upper()}"); p.alignment = 1; p.runs[0].bold = True
        
        # ISI (Defined Inside to access 'doc')
        def add_section(title, content, is_list=False):
            doc.add_paragraph(title, style='Heading 1')
            if not content: content = "-"
            if is_list:
                if isinstance(content, list):
                    for item in content:
                        p = doc.add_paragraph(str(item), style='List Bullet')
                else:
                    doc.add_paragraph(str(content), style='List Bullet')
            else:
                doc.add_paragraph(str(content)).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        add_section("A. Pendahuluan", data.get('gambaran_umum', '-'))
        add_section("B. Maksud & Tujuan", data.get('maksud_tujuan', '-'))
        
        doc.add_paragraph("C. Pelaksanaan Kegiatan", style='Heading 1')
        if extra_info: doc.add_paragraph(f"Catatan: {extra_info}", style='Quote')
        
        keg = data.get('kegiatan', [])
        if keg:
            for k in keg: doc.add_paragraph(str(k), style='List Bullet')

        # TABEL DATA KPM (Jika ada)
        if kpm_data:
            doc.add_paragraph("Data KPM Terkait:", style='Heading 2')
            table = doc.add_table(rows=1, cols=2)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'Atribut'; hdr_cells[1].text = 'Keterangan'
            for k, v in kpm_data.items():
                row = table.add_row().cells
                row[0].text = str(k); row[1].text = str(v)
            doc.add_paragraph("\n")

        add_section("D. Hasil", data.get('hasil', []), True)
        add_section("E. Penutup", data.get('penutup', '-'))

        # TANDA TANGAN
        doc.add_paragraph("\n\n")
        table = doc.add_table(rows=1, cols=2); table.autofit = False
        table.columns[0].width = Inches(3); table.columns[1].width = Inches(3)
        c2 = table.cell(0, 1).paragraphs[0]
        c2.alignment = 1
        c2.add_run(f"{meta['kab']}, {meta['tgl']}\nPendamping PKH\n\n")
        if ttd: 
            try:
                c2.add_run().add_picture(io.BytesIO(ttd), height=Inches(0.8))
            except: pass
        c2.add_run(f"\n{meta['nama']}\nNIP. {meta['nip']}")

        # FOTO
        if imgs:
            doc.add_page_break()
            doc.add_paragraph("DOKUMENTASI", style='Heading 1').alignment = 1
            for img in imgs:
                try:
                    doc.add_paragraph().alignment = 1
                    doc.add_picture(compress_image(img), width=Inches(3.5))
                except: pass
        
        bio = io.BytesIO(); doc.save(bio); return bio

    # ==========================================
    # 7. LOGIKA UI (DASHBOARD & DETAIL)
    # ==========================================
    def update_tanggal():
        st.session_state.tgl_val = f"30 {st.session_state.bln_val.title()} {st.session_state.th_val}"

    # --- SIDEBAR ---
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
                    st.success("Tersimpan!")
                    st.rerun()

        st.markdown("---")
        st.selectbox("Bulan", ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], key="bln_val", on_change=update_tanggal)
        st.selectbox("Tahun", ["2026", "2027"], key="th_val", on_change=update_tanggal)
        st.text_input("Tanggal Surat", key="tgl_val")
        
        st.markdown("---")
        kop = st.file_uploader("Kop Surat", type=['png','jpg'], key="kop_up")
        if kop: st.session_state['kop_bytes'] = kop.getvalue()
        ttd = st.file_uploader("Tanda Tangan", type=['png','jpg'], key="ttd_up")
        if ttd: st.session_state['ttd_bytes'] = ttd.getvalue()

    # --- DASHBOARD UTAMA ---
    def show_dashboard():
        st.title("📂 Aplikasi RHK PKH Pro (Gemini 2.0 Flash)")
        
        cols = st.columns(3)
        rhk_list = list(CONFIG_LAPORAN.keys())
        
        for i, rhk in enumerate(rhk_list):
            with cols[i % 3]:
                # Card Styling
                st.markdown(f"""
                <div style="background-color:#f0f2f6; padding:15px; border-radius:10px; margin-bottom:10px; border:1px solid #d1d5db;">
                    <h5 style="color:#1f2937; margin:0;">{rhk.split('–')[0]}</h5>
                    <p style="font-size:12px; color:#4b5563;">{rhk.split('–')[-1]}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # UNIQUE KEY is Vital for Buttons to work
                if st.button(f"Buka {rhk.split('–')[0]}", key=f"nav_home_{i}", use_container_width=True):
                    st.session_state['selected_rhk'] = rhk
                    st.session_state['page'] = 'detail'
                    st.rerun()

    # --- HALAMAN DETAIL (DENGAN FIX KEYERROR) ---
    def show_detail():
        rhk = st.session_state.get('selected_rhk')
        
        # --- FIX KEYERROR: RESET OTOMATIS JIKA SESI KEDALUWARSA ---
        # Ini mencegah aplikasi crash karena nama menu berubah
        if rhk is None or rhk not in CONFIG_LAPORAN:
            st.warning("⚠️ Data sesi kedaluwarsa. Me-refresh halaman secara otomatis...")
            time.sleep(1)
            st.session_state['selected_rhk'] = None
            st.session_state['page'] = 'home'
            st.rerun()
            return

        # Header Navigasi
        c1, c2 = st.columns([1, 6])
        if c1.button("⬅️ Kembali", use_container_width=True):
            st.session_state['page'] = 'home'
            st.rerun()
        c2.markdown(f"### 📝 {rhk}")
        
        # Meta Data untuk Generator
        meta = {
            'bulan': f"{st.session_state.bln_val} {st.session_state.th_val}",
            'nama': u_nama, 'nip': u_nip, 'kab': u_kab, 'kec': u_kec, 'kel': u_kel,
            'tgl': st.session_state.tgl_val, 'judul': rhk.split('–')[-1].upper()
        }
        lokasi = f"{u_kel}, {u_kec}, {u_kab}"
        
        # --- LOGIC PER RHK ---
        
        # 1. Tipe Antrian (RHK 2, 3, 8)
        if "RHK 2" in rhk or "RHK 3" in rhk or "RHK 8" in rhk:
            q_key = 'rhk2_queue' if "RHK 2" in rhk else ('rhk3_queue' if "RHK 3" in rhk else 'rhk8_queue')
            r_key = q_key.replace('queue', 'results')
            
            st.info(f"💡 **Mode Antrian:** Masukkan semua kegiatan dalam sebulan satu per satu, lalu klik 'Generate Semua' di bawah.")
            
            # FORM INPUT ANTRIAN
            with st.form("queue_form", clear_on_submit=True):
                col_a, col_b = st.columns(2)
                with col_a:
                    kegiatan = st.selectbox("Pilih Sub-Kegiatan", CONFIG_LAPORAN[rhk])
                with col_b:
                    ket_q = st.text_input("Keterangan Spesifik", placeholder="Lokasi spesifik / detail peserta...")
                
                fotos = st.file_uploader("Upload Foto Bukti", accept_multiple_files=True, type=['jpg','png'])
                add_btn = st.form_submit_button("➕ Tambahkan ke Antrian")
                
                if add_btn:
                    if not fotos:
                        st.error("❌ Foto wajib ada!")
                    else:
                        foto_data = [io.BytesIO(f.getvalue()) for f in fotos]
                        [auto_save_photo_local(f, rhk, meta['bulan']) for f in fotos]
                        
                        st.session_state[q_key].append({
                            "kegiatan": kegiatan,
                            "ket": ket_q,
                            "fotos": foto_data
                        })
                        st.success("✅ Berhasil masuk antrian")
                        st.rerun()
            
            # TAMPILAN ANTRIAN
            queue = st.session_state[q_key]
            if queue:
                st.write(f"**📋 Daftar Antrian ({len(queue)} Item):**")
                for i, q in enumerate(queue):
                    st.text(f"{i+1}. {q['kegiatan']} ({len(q['fotos'])} Foto) - {q['ket']}")
                
                col_gen, col_clr = st.columns([3, 1])
                if col_clr.button("🗑️ Hapus Semua", key="clr_q"):
                    st.session_state[q_key] = []
                    st.rerun()
                
                if col_gen.button("🚀 GENERATE SEMUA LAPORAN", type="primary", key="gen_q", use_container_width=True):
                    results = []
                    bar = st.progress(0)
                    status = st.empty()
                    
                    for i, item in enumerate(queue):
                        status.write(f"⏳ Memproses ({i+1}/{len(queue)}): {item['kegiatan']}...")
                        
                        # GENERATE AI
                        json_data = generate_isi_laporan(rhk, item['kegiatan'], u_kpm, "Peserta", meta['bulan'], lokasi, item['ket'])
                        
                        # CEK DATA SEBELUM MEMBUAT DOC
                        if json_data:
                            word = create_word_doc(json_data, meta, item['fotos'], st.session_state['kop_bytes'], st.session_state['ttd_bytes'], item['ket'])
                            if word:
                                results.append({"judul": item['kegiatan'], "file": word})
                        else:
                            st.warning(f"⚠️ Gagal generate: {item['kegiatan']} (AI Sibuk)")
                        
                        bar.progress((i + 1) / len(queue))
                    
                    st.session_state[r_key] = results
                    status.success("✅ Semua Laporan Selesai!")
                    st.rerun()
            
            # HASIL
            res = st.session_state.get(r_key)
            if res:
                st.write("---")
                st.write("### 📥 Download Hasil")
                for i, r in enumerate(res):
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"📄 {r['judul']}")
                    c2.download_button(f"Download", r['file'], file_name=f"{r['judul']}.docx", key=f"dl_{r_key}_{i}")

        # 2. Tipe Graduasi (RHK 4 - Excel)
        elif "RHK 4" in rhk:
            st.info("ℹ️ **Mode Graduasi:** Upload Excel Data KPM untuk membuat banyak laporan sekaligus.")
            
            # --- FITUR TEMPLATE EXCEL ---
            df_template = pd.DataFrame({
                "Nama": ["Budi Santoso", "Siti Aminah"],
                "NIK": ["1234567890", "0987654321"],
                "Alamat": ["Desa A, RT 01", "Desa B, RT 02"],
                "Kategori": ["PKH Murni", "BPNT + PKH"],
                "Status": ["Graduasi Mandiri", "Graduasi Sejahtera"],
                "Alasan": ["Sudah Mampu", "Memiliki Usaha"]
            })
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer) as writer:
                df_template.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Download Template Excel Graduasi",
                data=buffer.getvalue(),
                file_name="Template_Graduasi.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            upl = st.file_uploader("Upload Excel (.xlsx)", type=['xlsx'])
            
            if upl:
                try:
                    df = pd.read_excel(upl)
                    if "Nama" not in df.columns:
                        st.error("⚠️ Excel harus punya kolom bernama 'Nama'")
                    else:
                        selected_kpms = st.multiselect("Pilih KPM yang Graduasi:", df['Nama'].tolist())
                        
                        if selected_kpms:
                            st.write("Upload 1 set foto untuk semua laporan ini:")
                            photos = st.file_uploader("Foto Dokumentasi", accept_multiple_files=True, key="grad_foto")
                            if st.button("🚀 Generate Laporan Graduasi", type="primary"):
                                if not photos: st.error("Foto wajib!"); st.stop()
                                
                                res = []
                                p_data = [io.BytesIO(f.getvalue()) for f in photos]
                                bar = st.progress(0)
                                
                                for i, nama_kpm in enumerate(selected_kpms):
                                    try:
                                        row = df[df['Nama'] == nama_kpm].iloc[0].to_dict()
                                        json_data = generate_isi_laporan(rhk, f"Graduasi KPM {nama_kpm}", 1, nama_kpm, meta['bulan'], lokasi, f"Graduasi Mandiri a.n {nama_kpm}")
                                        
                                        if json_data:
                                            word = create_word_doc(json_data, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], f"Graduasi {nama_kpm}", kpm_data=row)
                                            res.append({"judul": nama_kpm, "file": word})
                                    except: pass
                                    bar.progress((i+1)/len(selected_kpms))
                                
                                st.session_state['rhk4_graduasi_results'] = res
                                st.rerun()
                except Exception as e:
                    st.error(f"Gagal baca file: {e}")

            res = st.session_state.get('rhk4_graduasi_results')
            if res:
                st.write("---")
                st.write("### Hasil Graduasi")
                for i, r in enumerate(res):
                    st.download_button(f"📥 {r['judul']}", r['file'], f"Graduasi_{r['judul']}.docx", key=f"dl_g_{i}")

        # 3. Tipe Standar (RHK 1, 5, 6, 7, 9)
        else:
            with st.form("std_form"):
                judul_keg = st.selectbox("Pilih Kegiatan", CONFIG_LAPORAN[rhk])
                ket_add = st.text_area("Keterangan Tambahan", height=100, placeholder="Ceritakan sedikit tentang kegiatan ini...")
                fotos = st.file_uploader("Upload Foto", accept_multiple_files=True)
                
                generate_btn = st.form_submit_button("🚀 BUAT LAPORAN SEKARANG", type="primary", use_container_width=True)
            
            if generate_btn:
                if not fotos:
                    st.error("❌ Mohon upload foto dokumentasi.")
                else:
                    with st.status("🤖 AI sedang bekerja...", expanded=True) as status:
                        st.write("Menganalisis data...")
                        json_data = generate_isi_laporan(rhk, judul_keg, u_kpm, "Peserta", meta['bulan'], lokasi, ket_add)
                        
                        if json_data:
                            st.write("Menyusun dokumen...")
                            p_data = [io.BytesIO(f.getvalue()) for f in fotos]
                            [auto_save_photo_local(f, rhk, meta['bulan']) for f in fotos]
                            
                            word_file = create_word_doc(json_data, meta, p_data, st.session_state['kop_bytes'], st.session_state['ttd_bytes'], ket_add)
                            
                            st.session_state['generated_file_data'] = {
                                "name": f"Laporan_{rhk[:5]}_{meta['bulan']}",
                                "file": word_file
                            }
                            status.update(label="✅ Selesai!", state="complete", expanded=False)
                            st.rerun()
                        else:
                            status.update(label="❌ Gagal menghubungi AI (Traffic Tinggi). Coba lagi!", state="error")
            
            if st.session_state.get('generated_file_data'):
                f = st.session_state['generated_file_data']
                st.success("✅ Laporan Siap Unduh!")
                st.download_button("📥 Download Word (.docx)", f['file'], f"{f['name']}.docx", type="primary", use_container_width=True)

    # ==========================================
    # 8. ROUTING UTAMA
    # ==========================================
    if st.session_state['page'] == 'home':
        show_dashboard()
    else:
        show_detail()
