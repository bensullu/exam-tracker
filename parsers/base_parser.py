"""
Abstract base parser sınıfı.
Tüm format-specific parserlar bu sınıftan türetilir.
"""
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

from models.exam_result import ExamResult, StudentResult, SubjectScore
from utils.pdf_utils import parse_turkish_number


class BaseParser(ABC):
    """Sınav PDF parserı için abstract base sınıfı."""

    def __init__(self):
        self.name = "base"

    @abstractmethod
    def can_parse(self, page_texts: list, tables: list) -> bool:
        """
        Bu parserın verilen PDF'i parse edip edemeyeceğini belirle.
        
        Args:
            page_texts: Her sayfanın ham metni
            tables: Çıkarılmış tablo DataFrames
        
        Returns:
            bool: Bu format ile parse edilebilirse True
        """
        pass

    @abstractmethod
    def parse(self, page_texts: list, tables: list, metadata: dict) -> ExamResult:
        """
        PDF'i parse et ve ExamResult döndür.
        
        Args:
            page_texts: Her sayfanın ham metni
            tables: Çıkarılmış tablo DataFrames
            metadata: Sınav bilgileri (exam_name, date, institution)
        
        Returns:
            ExamResult: Parse edilmiş sınav sonuçları
        """
        pass

    def _clean_name(self, name: str) -> str:
        """Öğrenci adını temizle."""
        if not name:
            return ""
        name = name.strip()
        # Gereksiz karakterleri temizle
        name = name.replace('\n', ' ').replace('\r', '')
        # Çoklu boşlukları tek boşluğa çevir
        while '  ' in name:
            name = name.replace('  ', ' ')
        return name.strip()

    def _split_name(self, full_name: str) -> tuple:
        """
        Tam adı ad ve soyad olarak böl.
        'MİRAÇ AKYÜZ' -> ('MİRAÇ', 'AKYÜZ')
        'ECRİN ZÜMRA ÇİÇEK' -> ('ECRİN ZÜMRA', 'ÇİÇEK')
        """
        full_name = self._clean_name(full_name)
        if not full_name:
            return ("", "")

        parts = full_name.split()
        if len(parts) <= 1:
            return (full_name, "")
        elif len(parts) == 2:
            return (parts[0], parts[1])
        else:
            # Son kelime soyad, geri kalanı ad
            return (" ".join(parts[:-1]), parts[-1])

    def _parse_score_row(self, values: list, expected_cols: int) -> Optional[StudentResult]:
        """
        Bir skor satırını StudentResult'a dönüştür.
        Alt sınıflar tarafından override edilebilir.
        """
        pass

    def _create_subject_score(self, dogru: str, yanlis: str, net: str) -> SubjectScore:
        """D/C/Net değerlerinden SubjectScore oluştur."""
        return SubjectScore(
            dogru=parse_turkish_number(str(dogru)),
            yanlis=parse_turkish_number(str(yanlis)),
            net=parse_turkish_number(str(net))
        )

    def _is_header_row(self, row: list) -> bool:
        """Satırın başlık satırı olup olmadığını kontrol et."""
        row_text = " ".join(str(c) for c in row).lower()
        header_keywords = ['numara', 'adı', 'soyadı', 'sınıf', 'türkçe', 'matematik',
                          'fen bil', 'ders', 'toplam', 'puan', 'sıra', 'net',
                          'doğru', 'yanlış', 'kurum', 'katılım']
        match_count = sum(1 for kw in header_keywords if kw in row_text)
        return match_count >= 3

    def _is_empty_or_summary_row(self, row: list) -> bool:
        """Satırın boş veya özet satırı olup olmadığını kontrol et."""
        row_text = " ".join(str(c) for c in row).strip()
        if not row_text:
            return True
        # Ortalama satırları
        summary_keywords = ['ortalama', 'genel', 'kurum', 'toplam öğrenci']
        return any(kw in row_text.lower() for kw in summary_keywords)

    def _is_student_row(self, row: list) -> bool:
        """
        Satırın öğrenci verisi satırı olup olmadığını kontrol et.
        Öğrenci satırları genellikle sayısal değerler ve isim içerir.
        """
        if not row or len(row) < 5:
            return False
        
        row_text = " ".join(str(c) for c in row).strip()
        if not row_text:
            return False
        
        # Başlık satırı ise öğrenci satırı değil
        if self._is_header_row(row):
            return False
        
        # Boş/özet satırı ise öğrenci satırı değil
        if self._is_empty_or_summary_row(row):
            return False
        
        # En az birkaç sayısal değer olmalı (skorlar)
        numeric_count = 0
        for cell in row:
            cell_str = str(cell).strip()
            if cell_str:
                try:
                    parse_turkish_number(cell_str)
                    numeric_count += 1
                except (ValueError, TypeError):
                    pass
        
        return numeric_count >= 3
