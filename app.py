"""
Dershane Sınav Sonuç Takip Sistemi - Streamlit Dashboard
=========================================================
Bu uygulama sınav sonuç PDF'lerini parse eder, veritabanında saklar
ve öğrencilere yönelik grafik raporlar oluşturur.

Kullanım:
    cd exam-tracker
    streamlit run app.py
"""
import os
import sys
import tempfile

import streamlit as st
import pandas as pd

# Proje kök dizinini PYTHONPATH'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.database import Database
from models.exam_result import ExamResult
from parsers.format_detector import FormatDetector
from parsers.mobese_parser import MobeseParser
from parsers.sorunet_parser import SorunetParser
from parsers.generic_parser import GenericParser
from utils.pdf_utils import extract_tables_from_pdf
from utils.chart_utils import (
    create_student_trend_chart,
    create_student_subject_chart,
    create_class_comparison_chart,
    create_exam_distribution_chart,
    create_rank_progress_chart,
)

# ─── Sayfa yapılandırması ────────────────────────────────────────────
st.set_page_config(
    page_title="Sinav Sonuc Takip Sistemi",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Veritabanı bağlantısı (session state) ───────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exam_tracker.db")

if "db" not in st.session_state:
    st.session_state.db = Database(DB_PATH)


def get_db() -> Database:
    return st.session_state.db


# ─── Sidebar ─────────────────────────────────────────────────────────
st.sidebar.title("📊 Sinav Takip")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Sayfa Sec",
    [
        "🏠 Ana Sayfa",
        "📄 PDF Yukle",
        "👤 Ogrenci Takibi",
        "🏫 Sinif Analizi",
        "📈 Grafik Raporlar",
        "📥 Disa Aktar",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("v1.0 — Dershane Sinav Sonuc Takip Sistemi")

# ═══════════════════════════════════════════════════════════════════════
#  ANA SAYFA
# ═══════════════════════════════════════════════════════════════════════
if page == "🏠 Ana Sayfa":
    st.title("🏠 Sinav Sonuc Takip Sistemi — Genel Bakis")

    db = get_db()
    exam_count = db.get_exam_count()
    student_count = db.get_student_count()

    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam Sinav", exam_count)
    col2.metric("Toplam Ogrenci", student_count)
    col3.metric("Veritabani", os.path.basename(DB_PATH))

    st.markdown("---")

    if exam_count == 0:
        st.info("Henuz hicbir sinav yuklenmedi. Sol menuden **📄 PDF Yukle** sayfasini kullanarak baslayin.")
    else:
        exams = db.get_all_exams()
        st.subheader("Son Yuklenen Sinavlar")
        df_exams = pd.DataFrame(exams)
        if not df_exams.empty:
            display_cols = [c for c in ["exam_name", "exam_date", "institution", "detected_format", "created_at"] if c in df_exams.columns]
            st.dataframe(df_exams[display_cols], use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════════
#  PDF YUKLE
# ═══════════════════════════════════════════════════════════════════════
elif page == "📄 PDF Yukle":
    st.title("📄 Sinav Sonuc PDF Yukle")

    # Database durumu
    db = get_db()
    st.caption(f"📦 Veritabani: {db.get_exam_count()} sinav, {db.get_student_count()} ogrenci kayitli")

    # Parser secimi - ONCELIKLE secilir
    st.markdown("---")
    parser_options = {
        "Otomatik Algila": None,
        "MOBESE Parser": MobeseParser(),
        "SORUNET/LGS Deneme Parser": SorunetParser(),
        "Genel Parser (Fallback)": GenericParser(),
    }
    selected_parser_label = st.selectbox(
        "⚙️ Parser Secimi",
        list(parser_options.keys()),
        help="PDF formatina uygun parseri secin. 'Otomatik Algila' genellikle yeterlidir."
    )

    st.markdown("---")

    uploaded_file = st.file_uploader("PDF dosyasini secin", type=["pdf"])

    if uploaded_file is not None:
        st.info(f"Yuklenen dosya: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")

        if st.button("🔍 PDF'i Analiz Et ve Parse Et", type="primary"):
            # Geçici dosyaya yaz ve parse et
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name

            with st.spinner("PDF okunuyor ve tablolar cikariliyor..."):
                extraction = extract_tables_from_pdf(tmp_path)

            # Geçici dosyayı temizle
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

            if "error" in extraction:
                st.error(f"PDF okuma hatasi: {extraction['error']}")
            elif not extraction["text_tables"]:
                st.warning("PDF'den hicbir tablo cikarilamadi.")
                st.session_state.pop("parsed_exam", None)
            else:
                # Parse
                metadata = extraction["metadata"]
                with st.spinner(f"'{selected_parser_label}' ile parse ediliyor..."):
                    if selected_parser_label == "Otomatik Algila":
                        detector = FormatDetector()
                        parser_name, exam_result = detector.detect_and_parse(
                            extraction["page_texts"],
                            extraction["text_tables"],
                            metadata,
                        )
                    else:
                        manual_parser = parser_options[selected_parser_label]
                        if manual_parser:
                            result = manual_parser.parse(extraction["page_texts"], extraction["text_tables"], metadata)
                            result.detected_format = manual_parser.name
                            parser_name, exam_result = manual_parser.name, result
                        else:
                            parser_name, exam_result = "none", None

                if exam_result and exam_result.students:
                    exam_result.source_file = uploaded_file.name
                    # Session state'e kaydet (rerun'larda korunur)
                    st.session_state["parsed_exam"] = exam_result
                    st.session_state["parsed_parser"] = parser_name
                    st.session_state["parsed_metadata"] = metadata
                    st.success(
                        f"**{parser_name}** parseri ile **{len(exam_result.students)}** ogrenci basariyla parse edildi!"
                    )
                else:
                    st.session_state.pop("parsed_exam", None)
                    st.warning("Ogrenci verisi parse edilemedi. Lutfen farkli bir parser secmeyi deneyin.")
                    with st.expander("Cikarilan tablolar (ham)"):
                        for i, tbl in enumerate(extraction["text_tables"][:5]):
                            st.write(f"Tablo {i + 1} ({tbl.shape[0]} satir x {tbl.shape[1]} sutun):")
                            st.dataframe(tbl.head(10))

        # Session state'de parse edilmis sonuc varsa goster
        if "parsed_exam" in st.session_state and st.session_state["parsed_exam"]:
            exam_result = st.session_state["parsed_exam"]
            parser_name = st.session_state.get("parsed_parser", "unknown")
            metadata = st.session_state.get("parsed_metadata", {})

            # Metadata duzenleme
            st.markdown("---")
            st.subheader("📝 Sinav Bilgileri (duzenleyebilirsiniz)")
            col_a, col_b = st.columns(2)
            new_name = col_a.text_input("Sinav Adi", value=exam_result.exam_name, key="meta_name")
            new_date = col_b.text_input("Tarih", value=exam_result.exam_date, key="meta_date")
            new_inst = st.text_input("Kurum", value=exam_result.institution, key="meta_inst")

            # Onizleme tablosu
            st.subheader("📋 Onizleme (Dogru / Yanlis / Net)")
            preview_data = []
            for s in exam_result.students:
                preview_data.append({
                    "Adi": s.adi,
                    "Soyadi": s.soyadi,
                    "Sinif": s.sinif,
                    "TRK_D": s.turkce.dogru, "TRK_Y": s.turkce.yanlis, "TRK_N": s.turkce.net,
                    "INK_D": s.ink_tar.dogru, "INK_Y": s.ink_tar.yanlis, "INK_N": s.ink_tar.net,
                    "DIN_D": s.din_kul.dogru, "DIN_Y": s.din_kul.yanlis, "DIN_N": s.din_kul.net,
                    "ING_D": s.ingilizce.dogru, "ING_Y": s.ingilizce.yanlis, "ING_N": s.ingilizce.net,
                    "MAT_D": s.matematik.dogru, "MAT_Y": s.matematik.yanlis, "MAT_N": s.matematik.net,
                    "FEN_D": s.fen_bil.dogru, "FEN_Y": s.fen_bil.yanlis, "FEN_N": s.fen_bil.net,
                    "Toplam Net": s.toplam_net,
                    "LGS Puan": s.lgs_puan,
                })
            df_preview = pd.DataFrame(preview_data)
            st.dataframe(df_preview, use_container_width=True, hide_index=True)

            # Veritabanına kaydet
            st.markdown("---")
            if st.button("💾 Veritabanina Kaydet", type="primary"):
                exam_result.exam_name = new_name
                exam_result.exam_date = new_date
                exam_result.institution = new_inst

                db = get_db()
                exam_id = db.insert_exam(exam_result)
                st.success(f"Sinav basariyla kaydedildi! (ID: {exam_id}, {len(exam_result.students)} ogrenci)")
                st.balloons()
                # Temizle
                st.session_state.pop("parsed_exam", None)
                st.session_state.pop("parsed_parser", None)
                st.session_state.pop("parsed_metadata", None)

            # Sifirla butonu
            if st.button("🗑️ Onizlemeyi Temizle"):
                st.session_state.pop("parsed_exam", None)
                st.session_state.pop("parsed_parser", None)
                st.session_state.pop("parsed_metadata", None)

# ═══════════════════════════════════════════════════════════════════════
#  OGRENCI TAKIBI
# ═══════════════════════════════════════════════════════════════════════
elif page == "👤 Ogrenci Takibi":
    st.title("👤 Ogrenci Takibi")

    db = get_db()
    students = db.get_all_students()

    if not students:
        st.info("Henuz ogrenci yok. Once PDF yukleyin.")
    else:
        # Ogrenci secimi
        student_names = [f"{s['full_name']} ({s['class_name']})" for s in students]
        selected_idx = st.selectbox("Ogrenci secin", range(len(student_names)), format_func=lambda i: student_names[i])

        if selected_idx is not None:
            student = students[selected_idx]
            student_scores = db.get_student_scores(student["id"])

            if not student_scores:
                st.warning("Bu ogrencinin henuz sinav kaydi yok.")
            else:
                st.subheader(f"📊 {student['full_name']} — Sinav Gecmisi")

                # Genel bakış metrikleri
                latest = student_scores[-1]
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Toplam Sinav", len(student_scores))
                col2.metric("Son Toplam Net", f"{latest['toplam_net']:.2f}")
                col3.metric("Son LGS Puani", f"{latest['lgs_puan']:.0f}")
                if len(student_scores) > 1:
                    first_net = student_scores[0]["toplam_net"]
                    col4.metric("Ilk Sinav Net", f"{first_net:.2f}", delta=f"{latest['toplam_net'] - first_net:+.2f}")
                else:
                    col4.metric("Ilk Sinav Net", f"{latest['toplam_net']:.2f}")

                # Tablo
                st.markdown("---")
                st.subheader("📋 Tum Sinav Sonuclari")
                table_data = []
                for sc in student_scores:
                    table_data.append({
                        "Sinav": sc["exam_name"],
                        "Tarih": sc["exam_date"],
                        "Turkce": sc["turkce_net"],
                        "Ink.Tar": sc["ink_tar_net"],
                        "Din Kul": sc["din_kul_net"],
                        "Ingilizce": sc["ingilizce_net"],
                        "Matematik": sc["matematik_net"],
                        "Fen Bil": sc["fen_bil_net"],
                        "Toplam Net": sc["toplam_net"],
                        "LGS Puan": sc["lgs_puan"],
                    })
                st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

                # Grafikler
                st.markdown("---")
                st.subheader("📈 Trend Grafigi")

                exam_names = [sc["exam_name"] for sc in student_scores]
                total_nets = [sc["toplam_net"] for sc in student_scores]
                lgs_scores = [sc["lgs_puan"] for sc in student_scores]

                fig_trend = create_student_trend_chart(student["full_name"], exam_names, total_nets, lgs_scores)
                st.plotly_chart(fig_trend, use_container_width=True)

                # Ders bazlı grafik
                st.subheader("📚 Ders Bazli Gelisim")
                subject_scores = {
                    "turkce": [sc["turkce_net"] for sc in student_scores],
                    "ink_tar": [sc["ink_tar_net"] for sc in student_scores],
                    "din_kul": [sc["din_kul_net"] for sc in student_scores],
                    "ingilizce": [sc["ingilizce_net"] for sc in student_scores],
                    "matematik": [sc["matematik_net"] for sc in student_scores],
                    "fen_bil": [sc["fen_bil_net"] for sc in student_scores],
                }
                fig_subjects = create_student_subject_chart(student["full_name"], exam_names, subject_scores)
                st.plotly_chart(fig_subjects, use_container_width=True)

                # Sıralama grafiği
                if any(sc.get("general_rank", 0) > 0 for sc in student_scores):
                    st.subheader("🏆 Siralama Degisimi")
                    ranks = [sc.get("general_rank", 0) or 0 for sc in student_scores]
                    fig_rank = create_rank_progress_chart(student["full_name"], exam_names, ranks)
                    st.plotly_chart(fig_rank, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
#  SINIF ANALIZI
# ═══════════════════════════════════════════════════════════════════════
elif page == "🏫 Sinif Analizi":
    st.title("🏫 Sinif Analizi")

    db = get_db()
    exams = db.get_all_exams()

    if not exams:
        st.info("Henuz sinav yok. Once PDF yukleyin.")
    else:
        # Sınav seçimi
        exam_options = {f"{e['exam_name']} ({e['exam_date']})": e['id'] for e in exams}
        selected_exam_label = st.selectbox("Sinav secin", list(exam_options.keys()))
        selected_exam_id = exam_options[selected_exam_label]

        scores = db.get_exam_scores(selected_exam_id)

        if not scores:
            st.warning("Bu sinavda kayit bulunamadi.")
        else:
            df_scores = pd.DataFrame(scores)

            # Genel istatistikler
            st.subheader("📊 Genel Istatistikler")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Ogrenci Sayisi", len(df_scores))
            col2.metric("Ort. Toplam Net", f"{df_scores['toplam_net'].mean():.2f}")
            col3.metric("En Yuksek Net", f"{df_scores['toplam_net'].max():.2f}")
            col4.metric("En Dusuk Net", f"{df_scores['toplam_net'].min():.2f}")

            # Sınıf bazlı analiz
            st.markdown("---")
            st.subheader("🎓 Sinif Bazli Analiz")

            if "class_name" in df_scores.columns:
                class_groups = df_scores.groupby("class_name")
                class_summary = class_groups.agg({
                    "toplam_net": ["mean", "max", "min", "count"],
                    "turkce_net": "mean",
                    "matematik_net": "mean",
                    "fen_bil_net": "mean",
                }).round(2)

                st.dataframe(class_summary, use_container_width=True)

                # Sınıf karşılaştırma grafiği
                st.subheader("📊 Sinif Karsilastirmasi")
                class_names = sorted(df_scores["class_name"].unique())
                averages = {}
                for cls in class_names:
                    cls_data = df_scores[df_scores["class_name"] == cls]
                    averages[cls] = {
                        "turkce": cls_data["turkce_net"].mean(),
                        "ink_tar": cls_data["ink_tar_net"].mean(),
                        "din_kul": cls_data["din_kul_net"].mean(),
                        "ingilizce": cls_data["ingilizce_net"].mean(),
                        "matematik": cls_data["matematik_net"].mean(),
                        "fen_bil": cls_data["fen_bil_net"].mean(),
                    }

                fig_class = create_class_comparison_chart(class_names, averages)
                st.plotly_chart(fig_class, use_container_width=True)

            # Net dağılımı
            st.markdown("---")
            st.subheader("📉 Net Dagilimi")
            exam_name = [e for e in exams if e["id"] == selected_exam_id][0]["exam_name"]
            fig_dist = create_exam_distribution_chart(exam_name, df_scores["toplam_net"].tolist())
            st.plotly_chart(fig_dist, use_container_width=True)

            # Tüm öğrencilerin listesi
            st.markdown("---")
            st.subheader("📋 Tum Ogrenciler (Sirali)")
            display_df = df_scores[["full_name", "class_name", "turkce_net", "ink_tar_net",
                                     "din_kul_net", "ingilizce_net", "matematik_net",
                                     "fen_bil_net", "toplam_net", "lgs_puan"]].copy()
            display_df.columns = ["Ad Soyad", "Sinif", "Turkce", "Ink.Tar", "Din Kul",
                                   "Ingilizce", "Matematik", "Fen Bil", "Toplam Net", "LGS Puan"]
            display_df = display_df.sort_values("Toplam Net", ascending=False).reset_index(drop=True)
            display_df.index += 1
            st.dataframe(display_df, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
#  GRAFIK RAPORLAR
# ═══════════════════════════════════════════════════════════════════════
elif page == "📈 Grafik Raporlar":
    st.title("📈 Grafik Raporlar")

    db = get_db()
    exams = db.get_all_exams()

    if not exams:
        st.info("Henuz sinav yok. Once PDF yukleyin.")
    else:
        st.subheader("🔄 Sinavlar Arasi Karsilastirma")

        exam_labels = [f"{e['exam_name']} ({e['exam_date']})" for e in exams]
        selected_exams = st.multiselect("Karsilastirmak istediginiz sinavlari secin", exam_labels, default=exam_labels[:2])

        if selected_exams:
            # Her sınav için ortalama netleri hesapla
            exam_averages = {}
            for label in selected_exams:
                exam_id = [e["id"] for e in exams if f"{e['exam_name']} ({e['exam_date']})" == label][0]
                scores = db.get_exam_scores(exam_id)
                if scores:
                    df = pd.DataFrame(scores)
                    exam_averages[label] = {
                        "Turkce": df["turkce_net"].mean(),
                        "Ink.Tar": df["ink_tar_net"].mean(),
                        "Din Kul": df["din_kul_net"].mean(),
                        "Ingilizce": df["ingilizce_net"].mean(),
                        "Matematik": df["matematik_net"].mean(),
                        "Fen Bil": df["fen_bil_net"].mean(),
                        "Toplam Net": df["toplam_net"].mean(),
                    }

            if exam_averages:
                import plotly.graph_objects as go

                subjects = ["Turkce", "Ink.Tar", "Din Kul", "Ingilizce", "Matematik", "Fen Bil"]
                fig = go.Figure()
                for exam_label, avgs in exam_averages.items():
                    fig.add_trace(go.Bar(
                        name=exam_label,
                        x=subjects,
                        y=[avgs.get(s, 0) for s in subjects],
                    ))

                fig.update_layout(
                    title="Sinavlar Arasi Ders Bazli Ortalama Karsilastirma",
                    barmode="group",
                    yaxis_title="Ortalama Net",
                    height=500,
                    template="plotly_white",
                )
                st.plotly_chart(fig, use_container_width=True)

        # Ogrenci bazlı çoklu sınav trendi
        st.markdown("---")
        st.subheader("👤 Ogrenci Bazli Coklu Sinav Trendi")

        students = db.get_all_students()
        if students:
            student_names = [f"{s['full_name']} ({s['class_name']})" for s in students]
            sel_idx = st.selectbox("Ogrenci secin", range(len(student_names)),
                                    format_func=lambda i: student_names[i], key="trend_student")
            student = students[sel_idx]
            student_scores = db.get_student_scores(student["id"])

            if student_scores:
                exam_names = [sc["exam_name"] for sc in student_scores]
                total_nets = [sc["toplam_net"] for sc in student_scores]
                lgs_scores = [sc["lgs_puan"] for sc in student_scores]

                fig = create_student_trend_chart(student["full_name"], exam_names, total_nets, lgs_scores)
                st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
#  DISA AKTAR
# ═══════════════════════════════════════════════════════════════════════
elif page == "📥 Disa Aktar":
    st.title("📥 Disa Aktar")

    db = get_db()
    exams = db.get_all_exams()

    if not exams:
        st.info("Henuz sinav yok. Once PDF yukleyin.")
    else:
        export_type = st.radio("Aktarma turu", ["Tek Sinav", "Tum Sinavlar (Birlesik)"])

        if export_type == "Tek Sinav":
            exam_options = {f"{e['exam_name']} ({e['exam_date']})": e['id'] for e in exams}
            selected_label = st.selectbox("Sinav secin", list(exam_options.keys()))
            selected_id = exam_options[selected_label]

            scores = db.get_exam_scores(selected_id)
            if scores:
                df = pd.DataFrame(scores)

                col1, col2 = st.columns(2)

                with col1:
                    csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        "📄 CSV olarak indir",
                        csv_data,
                        file_name=f"sinav_sonuc_{selected_label.replace(' ', '_')}.csv",
                        mime="text/csv",
                    )

                with col2:
                    import io
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="Sonuclar")
                    st.download_button(
                        "📊 Excel olarak indir",
                        buffer.getvalue(),
                        file_name=f"sinav_sonuc_{selected_label.replace(' ', '_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                st.markdown("---")
                st.subheader("📋 Onizleme")
                st.dataframe(df, use_container_width=True, hide_index=True)

        else:  # Tum sinavlar
            all_data = []
            for exam in exams:
                scores = db.get_exam_scores(exam["id"])
                for sc in scores:
                    sc["sinav_adi"] = exam["exam_name"]
                    sc["sinav_tarihi"] = exam["exam_date"]
                    all_data.append(sc)

            if all_data:
                df_all = pd.DataFrame(all_data)

                col1, col2 = st.columns(2)

                with col1:
                    csv_data = df_all.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        "📄 Tum Sinavlar CSV",
                        csv_data,
                        file_name="tum_sinav_sonuclari.csv",
                        mime="text/csv",
                    )

                with col2:
                    import io
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                        df_all.to_excel(writer, index=False, sheet_name="Tum Sonuclar")
                    st.download_button(
                        "📊 Tum Sinavlar Excel",
                        buffer.getvalue(),
                        file_name="tum_sinav_sonuclari.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                st.markdown("---")
                st.subheader("📋 Onizleme")
                st.dataframe(df_all, use_container_width=True, hide_index=True)
