"""
Genel/keşfedici parser.
Bilinmeyen PDF formatları için heuristic yaklaşım kullanır.
Sütun yapısını otomatik algılamaya çalışır.
"""
import re
from typing import Optional
import pandas as pd

from .base_parser import BaseParser
from models.exam_result import ExamResult, StudentResult, SubjectScore
from utils.pdf_utils import parse_turkish_number


class GenericParser(BaseParser):
    """Bilinmeyen formatlar için genel amaçlı parser."""

    # Yaygın ders isimleri ve varyasyonları
    SUBJECT_KEYWORDS = {
        'turkce': ['türkçe', 'turkce', 'türk dili', 'trk'],
        'ink_tar': ['ink. tar', 'inkılap', 'sosyal', 'sos.', 'ink.tar', 't.c. inkılap'],
        'din_kul': ['din kült', 'din kül', 'dkab', 'din kültürü'],
        'ingilizce': ['ingilizce', 'yabancı dil', 'ing.', 'İngilizce'],
        'matematik': ['matematik', 'mat.'],
        'fen_bil': ['fen bilim', 'fen bil', 'fen.'],
    }

    def __init__(self):
        super().__init__()
        self.name = "generic"

    def can_parse(self, page_texts: list, tables: list) -> bool:
        """Her zaman True döndür - son çare parserı."""
        return True

    def parse(self, page_texts: list, tables: list, metadata: dict) -> ExamResult:
        """Genel amaçlı parse işlemi."""
        result = ExamResult(
            exam_name=metadata.get('exam_name', 'Bilinmeyen Sinav'),
            exam_date=metadata.get('exam_date', ''),
            institution=metadata.get('institution', ''),
            detected_format='generic'
        )

        students = []
        seen_names = set()

        # Tabloları tara
        for table_df in tables:
            if isinstance(table_df, pd.DataFrame):
                rows = table_df.values.tolist()
            else:
                rows = table_df

            # Sütun yapısını algıla
            column_map = self._detect_columns(rows)
            if not column_map:
                continue

            for row in rows:
                str_row = [str(c).strip() if c else "" for c in row]

                if self._is_header_row(str_row) or self._is_empty_or_summary_row(str_row):
                    continue

                student = self._parse_row_with_mapping(str_row, column_map)
                if student and student.full_name not in seen_names:
                    seen_names.add(student.full_name)
                    students.append(student)

        result.students = students
        return result

    def _detect_columns(self, rows: list) -> dict:
        """
        Tablo satırlarından sütun yapısını algıla.
        
        Returns:
            dict: Sütun indeksi -> alan adı eşlemesi
                  Örn: {'name': 2, 'class': 4, 'turkce_net': 7, ...}
        """
        if not rows:
            return {}

        # İlk birkaç satırı kontrol et - başlık satırları genellikle üstte
        header_text = ""
        for row in rows[:5]:
            row_text = " ".join(str(c) for c in row if c)
            header_text += " " + row_text.lower()

        column_map = {}

        # Ders sütunlarını bul
        for subject_key, keywords in self.SUBJECT_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in header_text:
                    # Bu dersin sütun indekslerini bul
                    for row_idx, row in enumerate(rows[:5]):
                        for col_idx, cell in enumerate(row):
                            if cell and keyword.lower() in str(cell).lower():
                                # Net sütunu genellikle 2 sütun sonra (D, C, Net)
                                if col_idx + 2 < len(row):
                                    column_map[f'{subject_key}_net'] = col_idx + 2
                                if col_idx < len(row):
                                    column_map[f'{subject_key}_d'] = col_idx
                                if col_idx + 1 < len(row):
                                    column_map[f'{subject_key}_c'] = col_idx + 1
                    break

        # İsim sütununu bul
        name_keywords = ['adı', 'ad', 'isim', 'öğrenci', 'numara']
        for row in rows[:5]:
            for col_idx, cell in enumerate(row):
                if cell:
                    cell_lower = str(cell).lower().strip()
                    if cell_lower in name_keywords:
                        column_map['name'] = col_idx
                        # Soyad genellikle bir sonraki sütun
                        column_map['surname'] = col_idx + 1
                        break
            if 'name' in column_map:
                break

        # Sınıf sütununu bul
        for row in rows[:5]:
            for col_idx, cell in enumerate(row):
                if cell:
                    cell_lower = str(cell).lower().strip()
                    if cell_lower in ['sınıf', 'sinif', 'şube']:
                        column_map['class'] = col_idx
                        break
            if 'class' in column_map:
                break

        # Toplam net ve puan sütunlarını bul
        for row in rows[:5]:
            for col_idx, cell in enumerate(row):
                if cell:
                    cell_lower = str(cell).lower().strip()
                    if 'toplam' in cell_lower and 'net' in cell_lower:
                        column_map['total_net'] = col_idx
                    elif cell_lower in ['puan', 'lgs puan', 'lgs']:
                        column_map['lgs_puan'] = col_idx

        return column_map if 'name' in column_map else {}

    def _parse_row_with_mapping(self, row: list, column_map: dict) -> Optional[StudentResult]:
        """Sütun eşlemesini kullanarak satırı parse et."""
        student = StudentResult()

        # İsim
        name_idx = column_map.get('name', -1)
        if 0 <= name_idx < len(row):
            student.adi = self._clean_name(str(row[name_idx]))

        # Soyad
        surname_idx = column_map.get('surname', -1)
        if 0 <= surname_idx < len(row):
            student.soyadi = self._clean_name(str(row[surname_idx]))

        # Sınıf
        class_idx = column_map.get('class', -1)
        if 0 <= class_idx < len(row):
            student.sinif = str(row[class_idx]).strip().upper()

        if not student.adi:
            return None

        # Ders skorları
        subjects = ['turkce', 'ink_tar', 'din_kul', 'ingilizce', 'matematik', 'fen_bil']
        for subject in subjects:
            net_idx = column_map.get(f'{subject}_net', -1)
            d_idx = column_map.get(f'{subject}_d', -1)
            c_idx = column_map.get(f'{subject}_c', -1)

            if 0 <= net_idx < len(row):
                net_val = parse_turkish_number(str(row[net_idx]))
                dogru_val = parse_turkish_number(str(row[d_idx])) if 0 <= d_idx < len(row) else 0
                yanlis_val = parse_turkish_number(str(row[c_idx])) if 0 <= c_idx < len(row) else 0

                score = SubjectScore(dogru=dogru_val, yanlis=yanlis_val, net=net_val)
                setattr(student, subject, score)

        # Toplam net
        total_net_idx = column_map.get('total_net', -1)
        if 0 <= total_net_idx < len(row):
            student.toplam_net = parse_turkish_number(str(row[total_net_idx]))
        else:
            student.toplam_net = student.hesaplanan_toplam_net

        # LGS Puan
        lgs_idx = column_map.get('lgs_puan', -1)
        if 0 <= lgs_idx < len(row):
            student.lgs_puan = parse_turkish_number(str(row[lgs_idx]))

        return student if student.full_name.strip() else None
