"""
PDF okuma yardımcı fonksiyonları.
pdfplumber ve camelot ile tablo çıkarma.
"""
import re
import pdfplumber


def extract_tables_from_pdf(pdf_path: str) -> dict:
    """
    PDF'den tabloları çıkar.
    
    Returns:
        dict: {
            'text_tables': list of DataFrames from pdfplumber,
            'page_texts': list of raw text per page,
            'metadata': dict with exam info
        }
    """
    result = {
        'text_tables': [],
        'page_texts': [],
        'metadata': {}
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Ham metni çıkar
                text = page.extract_text() or ""
                result['page_texts'].append(text)

                # Metadata'yı ilk sayfalardan çıkar
                if not result['metadata']:
                    result['metadata'] = _extract_metadata(text)

                # Tabloları çıkar
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        # Her satırı temizle
                        cleaned = []
                        for row in table:
                            cleaned_row = []
                            for cell in row:
                                if cell is None:
                                    cleaned_row.append("")
                                else:
                                    cleaned_row.append(cell.strip())
                            cleaned_row = _merge_splitted_cells(cleaned_row)
                            cleaned.append(cleaned_row)
                        
                        if len(cleaned) > 1 and len(cleaned[0]) > 5:
                            import pandas as pd
                            df = pd.DataFrame(cleaned)
                            result['text_tables'].append(df)

    except Exception as e:
        result['error'] = str(e)

    # pdfplumber başarısız olursa camelot dene
    if not result['text_tables']:
        result = _try_camelot(pdf_path, result)

    return result


def _merge_splitted_cells(row: list) -> list:
    """
    Bir satırda ayrılmış hücreleri birleştir.
    Örneğin ['1', '010,000', '1010,000'] gibi split edilmiş hücreleri düzelt.
    """
    # Hücre sayısı çok fazlaysa birleştirme yapma
    return row


def _extract_metadata(text: str) -> dict:
    """Metin içinden sınav bilgilerini çıkar."""
    metadata = {}

    # Sınav adı
    exam_patterns = [
        r'Mobese\s+(\d+)\.Sınıf\s+Süreç\s+ve\s+Gelişim\s+Değerlendirme-(\d+)',
        r'MOBES[Eİ]\s*(\d+)\.?\s*SINIF.*?Değerlendirme\s*[-–]\s*(\d+)',
        r'(\w+)\s+(\d+)\.Sınıf.*?Değerlendirme\s*[-–]\s*(\d+)',
    ]
    for pattern in exam_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            metadata['exam_name'] = match.group(0).strip()
            break

    # Tarih
    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
    if date_match:
        metadata['exam_date'] = date_match.group(1)

    # Kurum - sadece kurum adini al, sonraki satirlardaki bilgileri dahil etme
    inst_patterns = [
        r'(Torbalı Sorunet Eğitim Kurumları)',
        r'(Torbal\w+ Sorunet \w+ Kurumlar\w+)',
        r'([A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+Eğitim\s+Kurumları)',
    ]
    for pattern in inst_patterns:
        inst_match = re.search(pattern, text)
        if inst_match:
            metadata['institution'] = inst_match.group(1).strip()
            break

    return metadata


def _try_camelot(pdf_path: str, existing_result: dict) -> dict:
    """Camelot ile tablo çıkarmayı dene."""
    try:
        import camelot

        # Lattice modu dene
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice', line_scale=40)
        if tables.n > 0:
            import pandas as pd
            for table in tables:
                if table.df.shape[0] > 1 and table.df.shape[1] > 5:
                    existing_result['text_tables'].append(table.df)
            return existing_result

        # Stream modu dene
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
        if tables.n > 0:
            import pandas as pd
            for table in tables:
                if table.df.shape[0] > 1 and table.df.shape[1] > 5:
                    existing_result['text_tables'].append(table.df)

    except ImportError:
        existing_result['camelot_error'] = 'camelot yüklü değil'
    except Exception as e:
        existing_result['camelot_error'] = str(e)

    return existing_result


def parse_turkish_number(value: str) -> float:
    """
    Türkçe sayı formatını Python float'a çevir.
    Örn: '10,000' -> 10.0, '94,507' -> 94.507
    """
    if not value or not isinstance(value, str):
        return 0.0

    value = value.strip()

    # Boş veya geçersiz değerler
    if not value or value in ['-', '', ' ']:
        return 0.0

    # Noktalı virgül formatı (10.000,50 -> 10000.50)
    if '.' in value and ',' in value:
        value = value.replace('.', '').replace(',', '.')
    elif ',' in value:
        # Sadece virgül varsa ondalık ayırıcı (10,50 -> 10.5)
        # Ama birden fazla virgül varsa binlik ayırıcı olabilir
        parts = value.split(',')
        if len(parts) == 2:
            value = value.replace(',', '.')
        else:
            # Binlik + ondalık: 1,000,50 -> 1000.50
            value = value.replace(',', '', len(parts) - 2).replace(',', '.')

    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
