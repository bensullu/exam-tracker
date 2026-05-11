"""
MOBESE format parseri.
MOBESE sinav sonuc PDF'lerini parse eder.

MOBESE PDF yapisi:
- Ana sonuc tablosu: Her ogrenci icin 6 ders x (D, C, Net) + Toplam Net + LGS Puan + Siralamalar
- Dersler: Turkce, Ink.Tar./Sos, Din Kulturu, Ingilizce, Matematik, Fen Bilimleri
- Her ogrenci icin ayrintili SINAV SONUC BELGESI sayfalari
"""
import re
from typing import Optional
import pandas as pd

from .base_parser import BaseParser
from models.exam_result import ExamResult, StudentResult, SubjectScore
from utils.pdf_utils import parse_turkish_number


class MobeseParser(BaseParser):
    """MOBESE sinavi formati parseri."""

    def __init__(self):
        super().__init__()
        self.name = "mobese"

    def can_parse(self, page_texts: list, tables: list) -> bool:
        """MOBESE formatini algila."""
        combined_text = " ".join(page_texts[:5]).lower()
        mobese_patterns = [
            r'mobese.*s.n.f.*de.erlendirme',
            r'mobese.*s.re.*geli.im',
            r'mobese',
        ]
        for pattern in mobese_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return True
        return False

    def parse(self, page_texts: list, tables: list, metadata: dict) -> ExamResult:
        """MOBESE PDF'ini parse et."""
        result = ExamResult(
            exam_name=metadata.get('exam_name', 'MOBESE Sinav'),
            exam_date=metadata.get('exam_date', ''),
            institution=metadata.get('institution', ''),
            detected_format='mobese'
        )

        # Strateji 1: Tablolari header-aware sekilde parse et
        students_from_tables = self._parse_tables_header_aware(tables)

        # Strateji 2: Eger tablolar basarisiz olursa sertifika sayfalarini parse et
        if len(students_from_tables) < 10:
            students_from_certs = self._parse_certificate_pages(page_texts)
            if len(students_from_certs) > len(students_from_tables):
                students_from_tables = students_from_certs

        result.students = students_from_tables

        # Eksik toplam net'leri tamamla
        for s in result.students:
            if s.toplam_net == 0:
                s.toplam_net = s.hesaplanan_toplam_net

        return result

    # ─── Header-Aware Tablo Parsing ────────────────────────────────────

    def _parse_tables_header_aware(self, tables: list) -> list:
        """
        Tablolari header satirindan ogrenilen sütun yapisiyla parse et.
        Her tablonun basinda tekrarlanan header satirlari kullanilir.
        """
        students = []
        seen_names = set()

        for table_df in tables:
            if isinstance(table_df, pd.DataFrame):
                rows = table_df.values.tolist()
            else:
                rows = table_df

            if not rows or len(rows) < 3:
                continue

            # Header satirini bul ve sütun haritasini cikar
            col_map = self._detect_column_map_from_header(rows)
            if not col_map:
                continue

            # Veri satirlarini parse et
            for row in rows:
                str_row = [str(c).strip() if c else "" for c in row]

                # Header/bos/ozet satirlari atla
                if self._is_header_row(str_row) or self._is_empty_or_summary_row(str_row):
                    continue

                student = self._parse_row_with_col_map(str_row, col_map)
                if student:
                    name_key = student.full_name.strip().upper()
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        students.append(student)

        return students

    def _detect_column_map_from_header(self, rows: list) -> dict:
        """
        Tablodaki header satirindan sütun indeks haritasini cikar.

        Returns:
            dict: Alan adi -> sütun indeksi
                  Orn: {'adi': 3, 'soyadi': 4, 'sinif': 5,
                        'turkce_d': 6, 'turkce_c': 7, 'turkce_net': 8, ...}
        """
        # Ilk 5 satir icinde header'i bul
        # Header: ['Sira', 'Numara', '', 'Adi', 'Soyadi', 'Sinif', 'DC', 'YC', ...]
        # veya: ['Ogrenci Bilgileri', '', '', '', '', '', 'Turkce', '']
        #        ['Sira', 'Numara', '', 'Adi', 'Soyadi', 'Sinif', 'DC', 'YC', ...]

        col_map = {}
        header_row_idx = -1

        # Header satirini bul: "Sira" veya "Numara" iceren satir
        for idx, row in enumerate(rows[:8]):
            row_text = " ".join(str(c).lower().strip() for c in row if c)
            if 's\ufeffra' in row_text or 'sira' in row_text or 'numara' in row_text:
                header_row_idx = idx
                break

        if header_row_idx < 0:
            return {}

        header = rows[header_row_idx]
        header_lower = [str(c).lower().strip() if c else "" for c in header]

        # Sütun indekslerini bul
        # Ogrenci bilgileri
        for i, h in enumerate(header_lower):
            if h in ('s\ufeffra', 's\ufeffra', 's\U0000feffra'):
                h = 'sira'
            if h == 'sira' and 'sira' not in col_map:
                col_map['sira'] = i
            elif h == 'numara' and 'numara' not in col_map:
                col_map['numara'] = i
            elif h in ('adi', 'ad\u0131', '\u00e7\u0131') and 'adi' not in col_map:
                col_map['adi'] = i
            elif h in ('soyadi', 'soyad\u0131') and 'soyadi' not in col_map:
                col_map['soyadi'] = i
            elif h in ('sinif', 's\u0131n\u0131f', '\u00e7\u0131') and 'sinif' not in col_map:
                # Check if it looks like a class column
                col_map['sinif'] = i

        # Eger hala adi bulamadiysak, "Ogrenci Bilgileri" satirindan tahmin et
        if 'adi' not in col_map:
            # Ilk satirda "Ogrenci Bilgileri" varsa, header satirindaki bos olmayan
            # harf degerleri ad/soyad olabilir
            for i, h in enumerate(header_lower):
                if h and h not in ('sira', 'numara', 'dc', 'yc', 'net', 'puan', 'toplam',
                                   'sinif', 'kurum', 'sira', 'katilim'):
                    if len(h) > 1 and not h.isdigit():
                        if 'adi' not in col_map:
                            col_map['adi'] = i
                        elif 'soyadi' not in col_map:
                            col_map['soyadi'] = i

        # Ders sütunlarını bul - "DC"/"YC"/"Net" pattern'ini takip et
        # Header yapisi: ... DC YC [Net] DC YC [Net] ...
        # Her ders icin 3 sutun (D, C, Net) veya 2 sutun (D, C) + Net sonraki dersin basinda

        # Once ders basliklarini bul - ust satirda ders isimleri olabilir
        subject_row = None
        if header_row_idx > 0:
            subject_row = rows[header_row_idx - 1]
        elif header_row_idx + 1 < len(rows):
            # Bazen ders isimleri header'in altinda da olabilir
            pass

        # "DC" pattern'lerini bul - her DC bir dersin baslangici
        dc_positions = []
        for i, h in enumerate(header_lower):
            if h in ('dc', 'd'):
                # Onceki sutun "YC" degilse (yani bu yeni bir dersin basi)
                dc_positions.append(i)

        # Dersleri ata: her DC-YC-Net grubu bir ders
        subject_names = ['turkce', 'ink_tar', 'din_kul', 'ingilizce', 'matematik', 'fen_bil']

        # Ders isimlerini ust satirdan tespit et
        detected_subjects = {}
        if subject_row:
            subject_texts = [str(c).lower().strip() if c else "" for c in subject_row]
            for i, txt in enumerate(subject_texts):
                if 'türk' in txt or 'turk' in txt:
                    detected_subjects[i] = 'turkce'
                elif 'ink' in txt or 'sos' in txt:
                    detected_subjects[i] = 'ink_tar'
                elif 'din' in txt:
                    detected_subjects[i] = 'din_kul'
                elif 'ing' in txt:
                    detected_subjects[i] = 'ingilizce'
                elif 'mat' in txt:
                    detected_subjects[i] = 'matematik'
                elif 'fen' in txt:
                    detected_subjects[i] = 'fen_bil'

        # DC pozisyonlarini ders isimleriyle eslestir
        subject_idx = 0
        for dc_pos in dc_positions:
            if dc_pos + 2 >= len(header):
                # Sadece DC ve YC var (Net yok)
                if subject_idx < len(subject_names):
                    subject = subject_names[subject_idx]
                    col_map[f'{subject}_d'] = dc_pos
                    col_map[f'{subject}_c'] = dc_pos + 1
                    subject_idx += 1
                continue

            # Net sutununun pozisyonunu kontrol et
            # Eger dc_pos + 2'de "net" yaziyorsa, 3'lü grup
            # Yoksa dc_pos + 1'den sonraki sutuna bak
            net_pos = dc_pos + 2

            # Ders ismini ust satirdan veya pozisyondan belirle
            subject = None
            # En yakin tespit edilen dersi bul
            for detected_pos, detected_name in sorted(detected_subjects.items()):
                if abs(detected_pos - dc_pos) <= 2:
                    subject = detected_name
                    break

            if subject is None and subject_idx < len(subject_names):
                subject = subject_names[subject_idx]

            if subject:
                col_map[f'{subject}_d'] = dc_pos
                col_map[f'{subject}_c'] = dc_pos + 1
                col_map[f'{subject}_net'] = net_pos
                subject_idx += 1

        # Toplam Net ve Puan sutunlarini bul
        # Toplam Net genellikle son ders net'inden sonra
        if subject_idx > 0:
            last_subject = subject_names[subject_idx - 1] if subject_idx <= len(subject_names) else subject_names[-1]
            last_net_pos = col_map.get(f'{last_subject}_net', -1)
            if last_net_pos >= 0 and last_net_pos + 1 < len(header):
                col_map['toplam_net'] = last_net_pos + 1
                col_map['lgs_puan'] = last_net_pos + 2

        return col_map if col_map.get('adi') is not None else {}

    def _parse_row_with_col_map(self, row: list, col_map: dict) -> Optional[StudentResult]:
        """Sütun haritasini kullanarak satiri parse et."""
        if len(row) < 6:
            return None

        student = StudentResult()

        # Isim
        adi_idx = col_map.get('adi', -1)
        if 0 <= adi_idx < len(row):
            student.adi = self._clean_name(str(row[adi_idx]))

        # Soyad
        soyadi_idx = col_map.get('soyadi', -1)
        if 0 <= soyadi_idx < len(row):
            student.soyadi = self._clean_name(str(row[soyadi_idx]))

        # Sinif
        sinif_idx = col_map.get('sinif', -1)
        if 0 <= sinif_idx < len(row):
            sinif_val = str(row[sinif_idx]).strip()
            if re.match(r'^\d+[A-Ea-e]?$', sinif_val):
                student.sinif = sinif_val.upper()

        if not student.adi:
            return None

        # Ders skorlari
        subjects = ['turkce', 'ink_tar', 'din_kul', 'ingilizce', 'matematik', 'fen_bil']
        for subject in subjects:
            d_idx = col_map.get(f'{subject}_d', -1)
            c_idx = col_map.get(f'{subject}_c', -1)
            net_idx = col_map.get(f'{subject}_net', -1)

            dogru = parse_turkish_number(str(row[d_idx])) if 0 <= d_idx < len(row) else 0
            yanlis = parse_turkish_number(str(row[c_idx])) if 0 <= c_idx < len(row) else 0
            net = parse_turkish_number(str(row[net_idx])) if 0 <= net_idx < len(row) else 0

            setattr(student, subject, SubjectScore(dogru=dogru, yanlis=yanlis, net=net))

        # Toplam net
        toplam_idx = col_map.get('toplam_net', -1)
        if 0 <= toplam_idx < len(row):
            student.toplam_net = parse_turkish_number(str(row[toplam_idx]))

        # LGS Puan
        lgs_idx = col_map.get('lgs_puan', -1)
        if 0 <= lgs_idx < len(row):
            student.lgs_puan = parse_turkish_number(str(row[lgs_idx]))

        # En az bir dersin net'i sifirdan farkli olmali
        if student.toplam_net == 0 and student.hesaplanan_toplam_net == 0:
            return None

        return student

    # ─── Sertifika Sayfa Parsing ───────────────────────────────────────

    def _parse_certificate_pages(self, page_texts: list) -> list:
        """SINAV SONUC BELGESI sayfalarini parse et."""
        students = []
        seen_names = set()

        for text in page_texts:
            if "SINAV" in text and ("SONUC" in text.upper() or "SONUÇ" in text):
                student = self._parse_single_certificate(text)
                if student:
                    name_key = student.full_name.strip().upper()
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        students.append(student)

        return students

    def _parse_single_certificate(self, text: str) -> Optional[StudentResult]:
        """Tek bir SINAV SONUC BELGESI sayfasini parse et."""
        student = StudentResult()
        lines = text.split('\n')

        # LGS Puani
        for line in lines[:5]:
            match = re.search(r'(\d{2,3}[,\.]\d{3})', line.strip())
            if match:
                student.lgs_puan = parse_turkish_number(match.group(1))
                break

        # Ogrenci adi - genellikle LGS puanindan sonra
        found_lgs = False
        for i, line in enumerate(lines):
            line_s = line.strip()
            if not line_s:
                continue

            # LGS satirini bul
            if re.match(r'^\d{2,3}[,\.]\d{3}$', line_s):
                found_lgs = True
                continue

            if found_lgs:
                # Kurum satirini atla
                if 'Egitim' in line_s or 'Kurum' in line_s or 'Sorunet' in line_s:
                    continue
                # Isim satiri - buyuk harfle baslayan kisa metin
                if re.match(r'^[A-ZCĞIİÖŞÜ][a-zçğıiöşü]+', line_s) and len(line_s) < 20:
                    student.adi = line_s.strip()
                    found_lgs = False  # Adi buldu, devam et
                    continue

            # Soyadi - "Mobese..." satirindan sonra
            if student.adi and not student.soyadi:
                if "Mobese" in line_s or "MOBESE" in line_s:
                    # Sonraki satir soyadi
                    for j in range(i + 1, min(i + 4, len(lines))):
                        soyad_line = lines[j].strip()
                        if re.match(r'^[A-ZCĞIİÖŞÜ]', soyad_line) and len(soyad_line) < 25:
                            if 'Kitap' not in soyad_line and 'AA' not in soyad_line:
                                student.soyadi = soyad_line.strip()
                                break
                    break

        # Sinif
        class_match = re.search(r'(\d[A-Ea-e])', text)
        if class_match:
            student.sinif = class_match.group(1).upper()

        # Ders bazli skorlari parse et
        self._parse_certificate_scores_v2(text, student)

        # Toplam net hesapla
        if student.toplam_net == 0:
            student.toplam_net = student.hesaplanan_toplam_net

        return student if student.adi else None

    def _parse_certificate_scores_v2(self, text: str, student: StudentResult):
        """
        Sertifika sayfasindan ders bazli skorlari cikar.
        
        Format: "20200020.0017,35912,69210,885Turkce"
        Bu: SoruSayisi=20, Dogru=20, Yanlis=0, Bos=0, Net=20.00, SinifOrt=17.359, ...
        """
        lines = text.split('\n')

        subject_keywords = {
            'turkce': ['türkçe', 'turkce', 'türk dili'],
            'ink_tar': ['ink. tar', 'inkılap', 'sosyal', 'sos.', 't.c.'],
            'din_kul': ['din kült', 'din kül', 'dkab'],
            'ingilizce': ['ingilizce', 'yabancı dil'],
            'matematik': ['matematik'],
            'fen_bil': ['fen bilim', 'fen bil'],
        }

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            for subject_key, keywords in subject_keywords.items():
                matched = False
                for keyword in keywords:
                    if keyword.lower() in line_stripped.lower():
                        # Ders adindan onceki sayisal kismi al
                        keyword_pos = line_stripped.lower().find(keyword.lower())
                        numeric_part = line_stripped[:keyword_pos].strip()

                        if numeric_part:
                            values = self._extract_numbers_from_line(numeric_part)
                            # Format: SoruSayisi, Dogru, Yanlis, Bos, Net, ...
                            if len(values) >= 5:
                                # values[0]=Soru, [1]=Dogru, [2]=Yanlis, [3]=Bos, [4]=Net
                                score = SubjectScore(
                                    dogru=values[1],
                                    yanlis=values[2],
                                    net=values[4]
                                )
                                setattr(student, subject_key, score)
                            elif len(values) >= 4:
                                # values[0]=Dogru, [1]=Yanlis, [2]=Bos, [3]=Net
                                score = SubjectScore(
                                    dogru=values[0],
                                    yanlis=values[1],
                                    net=values[3]
                                )
                                setattr(student, subject_key, score)
                        matched = True
                        break
                if matched:
                    break

    def _extract_numbers_from_line(self, text: str) -> list:
        """Satirdaki sayisal degerleri cikar."""
        values = []
        # Nokta ve virgul ile ayrılmis sayilari bul
        pattern = r'-?\d+[.,]?\d*'
        matches = re.findall(pattern, text)
        for m in matches:
            values.append(parse_turkish_number(m))
        return values
