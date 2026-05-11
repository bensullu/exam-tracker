"""
SORUNET/LGS Deneme formati parseri.
METIN YAYINLARI gibi yayinevlerinin LGS deneme sinav sonuc PDF'lerini parse eder.

SORUNET PDF yapisi (33 sutun):
- Row 0: Subject headers: Turkce(col4), Matematik(col7), Fen(col10), Sosyal(col13), Y.Dil(col19), Din Klt.(col22), TOPLAM(col25), Puanlar(col28)
- Row 1: Inkilap(col16) - alone on a row
- Row 2: D/Y/N headers for each subject group + Ogrenci info headers

Column mapping (from actual PDF):
- Col 0:    Sira
- Col 1:    Soyad/Ad (ters sirayla!)
- Col 2:    T.C. / Ogrenci No
- Col 3:    Sinif
- Col 4-6:  Turkce D, Y, N
- Col 7-9:  Matematik D, Y, N
- Col 10-12: Fen D, Y, N
- Col 13-15: Sosyal D, Y, N  (bazen "-" = soru yok)
- Col 16-18: Inkilap D, Y, N  (bazen "-" = soru yok)
- Col 19-21: Y. Dil (Ingilizce) D, Y, N
- Col 22-24: Din Klt. D, Y, N
- Col 25-27: TOPLAM D, Y, N
- Col 28:   Puan (LGS)
- Col 29:   Krm (Kurum sirasi)
- Col 30:   Ilce sirasi
- Col 31:   Il sirasi
- Col 32:   Gnl (Genel sirasi)
"""
import re
from typing import Optional
import pandas as pd

from .base_parser import BaseParser
from models.exam_result import ExamResult, StudentResult, SubjectScore
from utils.pdf_utils import parse_turkish_number


class SorunetParser(BaseParser):
    """SORUNET/LGS Deneme sinav formati parseri."""

    # Sabit sutun pozisyonlari (SORUNET standart format: 33 sutun)
    COLUMN_MAP_33 = {
        'sira': 0,
        'name': 1,
        'numara': 2,
        'class': 3,
        'turkce_d': 4, 'turkce_c': 5, 'turkce_net': 6,
        'matematik_d': 7, 'matematik_c': 8, 'matematik_net': 9,
        'fen_bil_d': 10, 'fen_bil_c': 11, 'fen_bil_net': 12,
        'sosyal_d': 13, 'sosyal_c': 14, 'sosyal_net': 15,
        'inkilap_d': 16, 'inkilap_c': 17, 'inkilap_net': 18,
        'ingilizce_d': 19, 'ingilizce_c': 20, 'ingilizce_net': 21,
        'din_kul_d': 22, 'din_kul_c': 23, 'din_kul_net': 24,
        'toplam_d': 25, 'toplam_c': 26, 'toplam_net': 27,
        'lgs_puan': 28,
        'rank_kurum': 29,
        'rank_ilce': 30,
        'rank_il': 31,
        'rank_genel': 32,
    }

    def __init__(self):
        super().__init__()
        self.name = "sorunet"

    def can_parse(self, page_texts: list, tables: list) -> bool:
        """SORUNET formatini algila."""
        combined_text = " ".join(page_texts[:3]).lower()

        # SORUNET/METIN yayinlari deseni
        sorunet_patterns = [
            r'sorunet\s+e\u011fitim',
            r'sorunet\s+e.i.im',
            r'met.n\s+yayinlari',
            r'lgs.*deneme.*s.nav.',
            r'puan.*s.ral..*liste',
        ]
        for pattern in sorunet_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return True

        # Tablo yapisindan algila: 33 sutun ve "Soyad/Ad" header'i
        for table_df in tables[:3]:
            if isinstance(table_df, pd.DataFrame):
                if table_df.shape[1] >= 30 and table_df.shape[1] <= 35:
                    # "Soyad/Ad" header'ini ara
                    for idx in range(min(5, len(table_df))):
                        row_text = " ".join(str(c) for c in table_df.iloc[idx].values if c)
                        if 'soyad' in row_text.lower() or 'ad' in row_text.lower():
                            return True

        return False

    def parse(self, page_texts: list, tables: list, metadata: dict) -> ExamResult:
        """SORUNET PDF'ini parse et."""
        enhanced_metadata = self._enhance_metadata(page_texts, metadata)

        result = ExamResult(
            exam_name=enhanced_metadata.get('exam_name', 'LGS Deneme Sinavi'),
            exam_date=enhanced_metadata.get('exam_date', ''),
            institution=enhanced_metadata.get('institution', ''),
            detected_format='sorunet'
        )

        students = []
        seen_names = set()

        for table_df in tables:
            if isinstance(table_df, pd.DataFrame):
                rows = table_df.values.tolist()
            else:
                rows = table_df

            if not rows or len(rows) < 5:
                continue

            # Sutun sayisina gore harita sec
            num_cols = len(rows[0]) if rows else 0
            if num_cols >= 30 and num_cols <= 35:
                col_map = self.COLUMN_MAP_33.copy()
            else:
                col_map = self._detect_column_map_dynamic(rows)

            if not col_map or 'name' not in col_map:
                continue

            for row in rows:
                str_row = [str(c).strip() if c else "" for c in row]

                if self._is_header_or_summary(str_row):
                    continue

                student = self._parse_student_row(str_row, col_map)
                if student:
                    name_key = student.full_name.strip().upper()
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        students.append(student)

        result.students = students
        return result

    def _enhance_metadata(self, page_texts: list, metadata: dict) -> dict:
        """Sayfa metinlerinden metadata'yi gelistir."""
        combined = " ".join(page_texts[:2])

        if not metadata.get('exam_name'):
            name_patterns = [
                r'(\d+\.\s*\d{4}\s+\w+\s+\d+\s+Lgs\s+Deneme\s+S.nav.)',
                r'(LGS\s*-\s*\d+\.\s*\d{4}.*?S.nav.)',
                r'(\d+\.\s*\d{4}.*?Deneme\s*S.nav.)',
            ]
            for pattern in name_patterns:
                match = re.search(pattern, combined, re.IGNORECASE)
                if match:
                    metadata['exam_name'] = match.group(1).strip()
                    break

        if not metadata.get('institution'):
            inst_patterns = [
                r'(SORUNET\s+E\u011fitim\s+KURUMLARI)',
                r'(SORUNET\s+\w+\s+\w+)',
            ]
            for pattern in inst_patterns:
                inst_match = re.search(pattern, combined, re.IGNORECASE)
                if inst_match:
                    metadata['institution'] = inst_match.group(1).strip()
                    break

        return metadata

    def _detect_column_map_dynamic(self, rows: list) -> dict:
        """Header satirlarindan sutun haritasini dinamik olarak cikar (standart olmayan formatlar icin)."""
        col_map = {}

        # Header satirini bul
        header_idx = -1
        for idx, row in enumerate(rows[:5]):
            row_text = " ".join(str(c).lower().strip() for c in row if c)
            if 'soyad' in row_text:
                header_idx = idx
                break

        if header_idx < 0:
            for idx, row in enumerate(rows[:5]):
                vals = [str(c).strip().lower() for c in row if c]
                d_count = sum(1 for v in vals if v == 'd')
                if d_count >= 3:
                    header_idx = idx
                    break

        if header_idx < 0:
            return {}

        header = rows[header_idx]
        header_lower = [str(c).lower().strip() if c else "" for c in header]

        # Ogrenci bilgileri
        for i, h in enumerate(header_lower):
            if 'soyad' in h:
                col_map['name'] = i
            elif 'sinif' in h:
                col_map['class'] = i
            elif 't.c' in h:
                col_map['numara'] = i

        if 'name' not in col_map:
            col_map['name'] = 1
        if 'class' not in col_map:
            col_map['class'] = 3

        # D pozisyonlarini bul
        d_positions = [i for i, h in enumerate(header_lower) if h == 'd' and i > 2]

        # Ust satirlardan ders isimlerini tespit et
        detected_subjects = {}
        for row_offset in range(1, 4):
            if header_idx - row_offset >= 0:
                subj_row = rows[header_idx - row_offset]
                for i, cell in enumerate(subj_row):
                    cell_str = str(cell).lower().strip() if cell else ""
                    if not cell_str or len(cell_str) < 2:
                        continue
                    # Unicode-normalize
                    cn = cell_str.replace('\u0307', '').replace('\u0131', 'i').replace('\u00fc', 'u').replace('\u00f6', 'o').replace('\u015f', 's').replace('\u00e7', 'c').replace('\u011f', 'g')
                    if 'turk' in cn:
                        detected_subjects[i] = 'turkce'
                    elif 'matematik' in cn:
                        detected_subjects[i] = 'matematik'
                    elif 'fen' in cn:
                        detected_subjects[i] = 'fen_bil'
                    elif 'sosyal' in cn:
                        detected_subjects[i] = 'sosyal'
                    elif 'dil' in cn or 'ingilizce' in cn:
                        detected_subjects[i] = 'ingilizce'
                    elif 'din' in cn:
                        detected_subjects[i] = 'din_kul'
                    elif 'ink' in cn or 'inkilap' in cn:
                        detected_subjects[i] = 'inkilap'

        # Eslestir
        used = set()
        for dc_pos in d_positions:
            subject = None
            for det_pos, det_name in sorted(detected_subjects.items()):
                if abs(det_pos - dc_pos) <= 2 and det_name not in used:
                    subject = det_name
                    used.add(det_name)
                    break
            if subject:
                col_map[f'{subject}_d'] = dc_pos
                col_map[f'{subject}_c'] = dc_pos + 1
                col_map[f'{subject}_net'] = dc_pos + 2

        # Fallback: pozisyondan tahmin
        if len(d_positions) >= 6 and 'turkce_d' not in col_map:
            names = ['turkce', 'matematik', 'fen_bil', 'sosyal', 'ingilizce', 'din_kul']
            for i, dc_pos in enumerate(d_positions[:6]):
                col_map[f'{names[i]}_d'] = dc_pos
                col_map[f'{names[i]}_c'] = dc_pos + 1
                col_map[f'{names[i]}_net'] = dc_pos + 2
            if len(d_positions) >= 7:
                col_map['inkilap_d'] = d_positions[6]
                col_map['inkilap_c'] = d_positions[6] + 1
                col_map['inkilap_net'] = d_positions[6] + 2

        # Toplam ve Puan
        if d_positions:
            last_d = d_positions[-1]
            for offset, key in [(3, 'toplam_d'), (4, 'toplam_c'), (5, 'toplam_net'), (6, 'lgs_puan')]:
                if last_d + offset < len(header):
                    col_map[key] = last_d + offset
            if 'lgs_puan' in col_map:
                puan_idx = col_map['lgs_puan']
                for offset, key in [(1, 'rank_kurum'), (2, 'rank_ilce'), (3, 'rank_il'), (4, 'rank_genel')]:
                    if puan_idx + offset < len(header):
                        col_map[key] = puan_idx + offset

        return col_map if 'name' in col_map else {}

    def _is_header_or_summary(self, row: list) -> bool:
        """Header veya ozet satiri mi kontrol et."""
        row_text = " ".join(str(c) for c in row).lower()
        if 'ortalama' in row_text:
            return True
        if 'soyad' in row_text:
            return True
        if 'sirasi' in row_text or 'liste' in row_text:
            return True
        non_empty = [str(c).strip() for c in row if str(c).strip()]
        if all(v.lower() in ('d', 'y', 'n') for v in non_empty) and len(non_empty) >= 3:
            return True
        return False

    def _parse_student_row(self, row: list, col_map: dict) -> Optional[StudentResult]:
        """Sutun haritasini kullanarak ogrenci satirini parse et."""
        if len(row) < 10:
            return None

        student = StudentResult()

        # Isim - "SOYAD AD" formatinda (ters!)
        name_idx = col_map.get('name', 1)
        if 0 <= name_idx < len(row):
            raw_name = self._clean_name(str(row[name_idx]))
            if not raw_name:
                return None
            parts = raw_name.split()
            if len(parts) >= 2:
                student.soyadi = parts[0]
                student.adi = " ".join(parts[1:])
            else:
                student.adi = raw_name

        # Sinif
        class_idx = col_map.get('class', 3)
        if 0 <= class_idx < len(row):
            sinif_val = str(row[class_idx]).strip()
            if re.match(r'^\d+[A-Ea-e]?$', sinif_val):
                student.sinif = sinif_val.upper()

        # Numara
        numara_idx = col_map.get('numara', 2)
        if 0 <= numara_idx < len(row):
            student.numara = str(row[numara_idx]).strip()

        if not student.adi:
            return None

        # Ana dersler
        main_subjects = ['turkce', 'matematik', 'fen_bil', 'ingilizce', 'din_kul']
        for subject in main_subjects:
            dogru = self._parse_cell(row, col_map.get(f'{subject}_d', -1))
            yanlis = self._parse_cell(row, col_map.get(f'{subject}_c', -1))
            net = self._parse_cell(row, col_map.get(f'{subject}_net', -1))
            setattr(student, subject, SubjectScore(dogru=dogru, yanlis=yanlis, net=net))

        # Sosyal ve Inkilap'i birlestir -> ink_tar
        sosyal_d = self._parse_cell(row, col_map.get('sosyal_d', -1))
        sosyal_c = self._parse_cell(row, col_map.get('sosyal_c', -1))
        sosyal_net = self._parse_cell(row, col_map.get('sosyal_net', -1))

        inkilap_d = self._parse_cell(row, col_map.get('inkilap_d', -1))
        inkilap_c = self._parse_cell(row, col_map.get('inkilap_c', -1))
        inkilap_net = self._parse_cell(row, col_map.get('inkilap_net', -1))

        if sosyal_net != 0 and inkilap_net != 0:
            combined_d = sosyal_d + inkilap_d
            combined_c = sosyal_c + inkilap_c
            combined_net = sosyal_net + inkilap_net
        elif sosyal_net != 0:
            combined_d, combined_c, combined_net = sosyal_d, sosyal_c, sosyal_net
        else:
            combined_d, combined_c, combined_net = inkilap_d, inkilap_c, inkilap_net

        student.ink_tar = SubjectScore(dogru=combined_d, yanlis=combined_c, net=combined_net)

        # Toplam net
        toplam_net_idx = col_map.get('toplam_net', -1)
        if 0 <= toplam_net_idx < len(row):
            student.toplam_net = self._parse_cell(row, toplam_net_idx)
        else:
            student.toplam_net = student.hesaplanan_toplam_net

        # LGS Puan
        lgs_idx = col_map.get('lgs_puan', -1)
        if 0 <= lgs_idx < len(row):
            student.lgs_puan = self._parse_cell(row, lgs_idx)

        # Siralamalar
        for rank_key, attr_name in [('rank_kurum', 'school_rank'), ('rank_ilce', 'district_rank'),
                                      ('rank_il', 'city_rank'), ('rank_genel', 'general_rank')]:
            rank_idx = col_map.get(rank_key, -1)
            if 0 <= rank_idx < len(row):
                val = self._parse_cell(row, rank_idx)
                setattr(student, attr_name, int(val) if val > 0 else None)

        if student.toplam_net == 0 and student.hesaplanan_toplam_net == 0:
            return None

        return student

    def _parse_cell(self, row: list, idx: int) -> float:
        """Hucre degerini float'a cevir."""
        if idx < 0 or idx >= len(row):
            return 0.0
        val = str(row[idx]).strip()
        if val in ('-', '', ' ', '--'):
            return 0.0
        return parse_turkish_number(val)
