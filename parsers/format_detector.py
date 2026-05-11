"""
Format dedektörü.
PDF'in hangi parser ile parse edileceğini belirler.
"""
from typing import Optional

from .base_parser import BaseParser
from .mobese_parser import MobeseParser
from .sorunet_parser import SorunetParser
from .generic_parser import GenericParser


class FormatDetector:
    """PDF formatını algılayıp uygun parserı seçen sınıf."""

    def __init__(self):
        # Bilinen parserlar (öncelik sırasına göre)
        self.parsers: list[BaseParser] = [
            MobeseParser(),
            SorunetParser(),
            GenericParser(),  # Son çare - her zaman eşleşir
        ]

    def detect_and_parse(self, page_texts: list, tables: list, metadata: dict):
        """
        Formatı algıla ve uygun parser ile parse et.
        
        Args:
            page_texts: Her sayfanın ham metni
            tables: Çıkarılmış tablo DataFrames
            metadata: Sınav bilgileri
        
        Returns:
            tuple: (parser_name, ExamResult)
        """
        for parser in self.parsers:
            if parser.can_parse(page_texts, tables):
                result = parser.parse(page_texts, tables, metadata)
                result.detected_format = parser.name
                return parser.name, result

        # Bu noktaya ulaşılmaması gerekir (GenericParser her zaman eşleşir)
        return "none", None

    def get_available_parsers(self) -> list:
        """Mevcut parserların listesini döndür."""
        return [(p.name, p.__class__.__name__) for p in self.parsers]
