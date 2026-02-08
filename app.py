# --- FUNGSI PDF (PERBAIKAN LAYOUT, KOP, & TTD) ---
    def create_pdf_doc(data, meta, imgs, kop, ttd, extra_info=None, kpm_data=None):
        if data is None: return None
        
        # Setup A4 Page (210mm x 297mm)
        pdf = FPDF('P', 'mm', 'A4')
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        pdf.set_margins(20, 20, 20) # Margin kiri, atas, kanan 20mm

        # --- 1. KOP SURAT ---
        if kop:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(kop)
                tmp.flush()
                tmp_path = tmp.name
            try:
                # Koordinat 0,0 (Pojok kiri atas), Lebar 210mm (Full A4)
                # Tinggi (h) diset 0 agar proporsional otomatis
                pdf.image(tmp_path, x=0, y=0, w=210)
                
                # Kita perlu 'menebak' tinggi kop untuk memindahkan kursor ke bawah
                # Asumsi standar kop surat tingginya sekitar 35-40mm dari atas
                pdf.set_y(38) 
            except: 
                pdf.ln(10)
            finally:
                if os.path.exists(tmp_path): os.remove(tmp_path)
        else:
            pdf.ln(10) # Jika tidak ada kop, beri jarak dari atas

        # --- 2. JUDUL LAPORAN ---
        pdf.set_font("Arial", "B", 12)
        # Gunakan Multi Cell agar kalau judul kepanjangan dia turun ke bawah (wrapping)
        title_text = f"LAPORAN\nTENTANG\n{clean_text_for_pdf(meta['judul'].upper())}\n{clean_text_for_pdf(meta['bulan'].upper())}"
        pdf.multi_cell(0, 6, title_text, align='C')
        pdf.ln(8) # Jarak setelah judul

        # Helper untuk Section
        def add_section_pdf(title, content, is_list=False):
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 7, clean_text_for_pdf(title), ln=True) # Judul section
            pdf.set_font("Arial", "", 11)
            
            if content is None: content = "-"
            
            if is_list and isinstance(content, list):
                for item in content:
                    # Bullet point manual
                    current_y = pdf.get_y()
                    pdf.set_x(25) # Indentasi bullet
                    # Gunakan karakter bullet atau dash
                    pdf.multi_cell(0, 6, f"- {clean_text_for_pdf(item)}")
            else:
                pdf.multi_cell(0, 6, clean_text_for_pdf(str(content)))
            pdf.ln(3)

        # --- 3. ISI LAPORAN ---
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

        # Data KPM (Tabel Sederhana)
        if kpm_data:
            pdf.set_font("Arial", "B", 10)
            pdf.cell(0, 7, "Data KPM Terkait:", ln=True)
            pdf.set_font("Arial", "", 10)
            col_width = 85 # Lebar kolom
            for k, v in kpm_data.items():
                pdf.cell(col_width, 6, clean_text_for_pdf(str(k)), border=1)
                pdf.cell(col_width, 6, clean_text_for_pdf(str(v)), border=1, ln=True)
            pdf.ln(5)

        add_section_pdf("D. Hasil", data.get('hasil'), True)
        add_section_pdf("E. Penutup", data.get('penutup'))

        # --- 4. TANDA TANGAN (FIX POSISI) ---
        # Cek sisa halaman, jika tinggal sedikit, pindah halaman baru untuk TTD
        if pdf.get_y() > 220: 
            pdf.add_page()
        else:
            pdf.ln(10)

        pdf.set_font("Arial", "", 11)
        
        # Koordinat Blok TTD (Kanan)
        # Margin kanan 20mm, Lebar kertas 210. Titik tengah blok kanan kira2 di X=140
        x_block = 130 
        w_block = 60 # Lebar area tanda tangan
        
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
                ttd_path = tmp_ttd.name
            try:
                # Simpan posisi Y sekarang
                y_before_img = pdf.get_y()
                
                # Taruh gambar. X disesuaikan agar di tengah blok (x_block + offset)
                # Tinggi (h) dipaksa 25mm agar tidak kegedean/kekecilan
                pdf.image(ttd_path, x=x_block + 5, y=y_before_img, h=25)
                
                # Pindahkan kursor ke bawah gambar manual
                pdf.set_y(y_before_img + 27) 
            except: 
                pdf.ln(25) # Jika error gambar, kasih spasi kosong
            finally:
                if os.path.exists(ttd_path): os.remove(ttd_path)
        else:
            pdf.ln(25) # Spasi untuk TTD basah
        
        # Nama & NIP
        pdf.set_x(x_block)
        # Nama dibold dan digarisbawah
        pdf.set_font("Arial", "BU", 11) 
        pdf.cell(w_block, 6, clean_text_for_pdf(meta['nama']), ln=True, align='C')
        
        # NIP normal
        pdf.set_font("Arial", "", 11)
        pdf.set_x(x_block)
        pdf.cell(w_block, 6, f"NIP. {clean_text_for_pdf(meta['nip'])}", ln=True, align='C')

        # --- 5. DOKUMENTASI ---
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
                    # Gambar ditengah, lebar 120mm
                    x_img = (210 - 120) / 2
                    pdf.image(img_path, x=x_img, w=120) 
                    pdf.ln(5) # Spasi antar foto
                except: pass
                finally:
                    if os.path.exists(img_path): os.remove(img_path)

        return pdf.output(dest='S').encode('latin-1')
