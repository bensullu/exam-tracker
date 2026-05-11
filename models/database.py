"""
SQLite veritabanı bağlantı ve tablo yönetimi.
Fuzzy student matching ile farklı formatlardaki aynı öğrencileri eşleştirir.
"""
import sqlite3
import os
import re
from typing import Optional
from .exam_result import ExamResult, StudentResult, SubjectScore


def make_canonical_name(full_name: str) -> str:
    """
    İsim parçalarını alfabetik sıralayarak canonical name oluşturur.
    Bu sayede "MİRAÇ AKYÜZ" ve "AKYÜZ MİRAÇ" aynı öğrenci olarak eşleşir.

    "MİRAÇ AKYÜZ"       → parts=["MİRAÇ","AKYÜZ"]   → "AKYÜZ MİRAÇ"
    "AKYÜZ MİRAÇ"       → parts=["AKYÜZ","MİRAÇ"]   → "AKYÜZ MİRAÇ"  ✓
    "ECRİN ZÜMRA ÇİÇEK" → parts=["ÇİÇEK","ECRİN","ZÜMRA"] → "ÇİÇEK ECRİN ZÜMRA"
    "ÇİÇEK ECRİN ZÜMRA" → parts=["ÇİÇEK","ECRİN","ZÜMRA"] → "ÇİÇEK ECRİN ZÜMRA"  ✓
    """
    if not full_name:
        return ""
    # Büyük harfe çevir ve temizle
    name = full_name.strip().upper()
    # Türkçe karakter dönüşümü: i→İ, ı→I (Python .upper() bunu doğru yapar mı?)
    # Standartlaştır
    name = name.replace("\u0130", "I").replace("\u0131", "I")  # İ→I, ı→I
    parts = name.split()
    if not parts:
        return ""
    parts.sort()
    return " ".join(parts)


class Database:
    """SQLite veritabanı yöneticisi."""

    def __init__(self, db_path: str = "data/exam_tracker.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate()

    def _create_tables(self):
        """Veritabanı tablolarını oluştur."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_name TEXT NOT NULL,
                exam_date TEXT DEFAULT '',
                institution TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                detected_format TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                canonical_name TEXT NOT NULL DEFAULT '',
                class_name TEXT DEFAULT '',
                student_number TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(full_name, class_name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                turkce_dogru REAL DEFAULT 0,
                turkce_yanlis REAL DEFAULT 0,
                turkce_net REAL DEFAULT 0,
                ink_tar_dogru REAL DEFAULT 0,
                ink_tar_yanlis REAL DEFAULT 0,
                ink_tar_net REAL DEFAULT 0,
                din_kul_dogru REAL DEFAULT 0,
                din_kul_yanlis REAL DEFAULT 0,
                din_kul_net REAL DEFAULT 0,
                ingilizce_dogru REAL DEFAULT 0,
                ingilizce_yanlis REAL DEFAULT 0,
                ingilizce_net REAL DEFAULT 0,
                matematik_dogru REAL DEFAULT 0,
                matematik_yanlis REAL DEFAULT 0,
                matematik_net REAL DEFAULT 0,
                fen_bil_dogru REAL DEFAULT 0,
                fen_bil_yanlis REAL DEFAULT 0,
                fen_bil_net REAL DEFAULT 0,
                toplam_net REAL DEFAULT 0,
                lgs_puan REAL DEFAULT 0,
                class_rank INTEGER DEFAULT 0,
                school_rank INTEGER DEFAULT 0,
                district_rank INTEGER DEFAULT 0,
                city_rank INTEGER DEFAULT 0,
                general_rank INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exam_id) REFERENCES exams(id),
                FOREIGN KEY (student_id) REFERENCES students(id),
                UNIQUE(exam_id, student_id)
            )
        """)

        self.conn.commit()

    def _migrate(self):
        """Veritabanı şemasını güncelle (eski versiyonlardan)."""
        cursor = self.conn.cursor()

        # canonical_name sütunu var mı kontrol et
        cursor.execute("PRAGMA table_info(students)")
        columns = [row['name'] for row in cursor.fetchall()]

        if 'canonical_name' not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN canonical_name TEXT NOT NULL DEFAULT ''")
            # Mevcut öğrenciler için canonical_name doldur
            cursor.execute("SELECT id, full_name FROM students")
            for row in cursor.fetchall():
                canon = make_canonical_name(row['full_name'])
                cursor.execute("UPDATE students SET canonical_name = ? WHERE id = ?", (canon, row['id']))

        # canonical_name indeksi oluştur
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_students_canonical
            ON students(canonical_name)
        """)

        self.conn.commit()

    def get_or_create_student(self, full_name: str, class_name: str, student_number: str = "") -> int:
        """
        Öğrenciyi bul veya oluştur, ID döndür.

        Eşleme stratejisi (öncelik sırasıyla):
        1. Tam eşleşme: full_name + class_name
        2. Canonical name eşleme: parçaları sıralayarak eşleştir
        3. Bulunamazsa yeni öğrenci oluştur
        """
        cursor = self.conn.cursor()

        # 1. Tam eşleşme ara
        cursor.execute(
            "SELECT id FROM students WHERE full_name = ? AND class_name = ?",
            (full_name, class_name)
        )
        row = cursor.fetchone()
        if row:
            return row['id']

        # 2. Canonical name ile eşleştir
        canonical = make_canonical_name(full_name)
        if canonical:
            cursor.execute(
                "SELECT id, full_name FROM students WHERE canonical_name = ?",
                (canonical,)
            )
            matches = cursor.fetchall()

            if len(matches) == 1:
                # Tek eşleşme bulundu - sınıf bilgisini güncelle (eğer boşsa)
                student_id = matches[0]['id']
                if class_name:
                    cursor.execute(
                        "UPDATE students SET class_name = ? WHERE id = ? AND class_name = ''",
                        (class_name, student_id)
                    )
                self.conn.commit()
                return student_id

            elif len(matches) > 1:
                # Birden fazla eşleşme - sınıf ile daralt
                for m in matches:
                    cursor.execute(
                        "SELECT id FROM students WHERE id = ? AND class_name = ?",
                        (m['id'], class_name)
                    )
                    class_match = cursor.fetchone()
                    if class_match:
                        return class_match['id']

                # Sınıf ile de eşleşmediyse, ilk eşleşmeyi döndür
                return matches[0]['id']

        # 3. Yeni öğrenci oluştur
        cursor.execute(
            "INSERT INTO students (full_name, canonical_name, class_name, student_number) VALUES (?, ?, ?, ?)",
            (full_name, canonical, class_name, student_number)
        )
        self.conn.commit()
        return cursor.lastrowid

    def insert_exam(self, exam: ExamResult) -> int:
        """Sınav ve tüm öğrenci sonuçlarını kaydet."""
        cursor = self.conn.cursor()

        # Sınavı kaydet
        cursor.execute(
            """INSERT INTO exams (exam_name, exam_date, institution, source_file, detected_format)
               VALUES (?, ?, ?, ?, ?)""",
            (exam.exam_name, exam.exam_date, exam.institution, exam.source_file, exam.detected_format)
        )
        exam_id = cursor.lastrowid

        # Her öğrenci için skorları kaydet
        for student in exam.students:
            full_name = student.full_name.strip()
            if not full_name:
                continue

            student_id = self.get_or_create_student(full_name, student.sinif, student.numara)

            try:
                cursor.execute(
                    """INSERT OR REPLACE INTO exam_scores
                       (exam_id, student_id,
                        turkce_dogru, turkce_yanlis, turkce_net,
                        ink_tar_dogru, ink_tar_yanlis, ink_tar_net,
                        din_kul_dogru, din_kul_yanlis, din_kul_net,
                        ingilizce_dogru, ingilizce_yanlis, ingilizce_net,
                        matematik_dogru, matematik_yanlis, matematik_net,
                        fen_bil_dogru, fen_bil_yanlis, fen_bil_net,
                        toplam_net, lgs_puan,
                        class_rank, school_rank, district_rank, city_rank, general_rank)
                       VALUES (?, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               ?, ?, ?, ?, ?)""",
                    (exam_id, student_id,
                     student.turkce.dogru, student.turkce.yanlis, student.turkce.net,
                     student.ink_tar.dogru, student.ink_tar.yanlis, student.ink_tar.net,
                     student.din_kul.dogru, student.din_kul.yanlis, student.din_kul.net,
                     student.ingilizce.dogru, student.ingilizce.yanlis, student.ingilizce.net,
                     student.matematik.dogru, student.matematik.yanlis, student.matematik.net,
                     student.fen_bil.dogru, student.fen_bil.yanlis, student.fen_bil.net,
                     student.toplam_net, student.lgs_puan,
                     student.class_rank or 0, student.school_rank or 0,
                     student.district_rank or 0, student.city_rank or 0,
                     student.general_rank or 0)
                )
            except sqlite3.IntegrityError:
                cursor.execute(
                    """UPDATE exam_scores SET
                        turkce_dogru=?, turkce_yanlis=?, turkce_net=?,
                        ink_tar_dogru=?, ink_tar_yanlis=?, ink_tar_net=?,
                        din_kul_dogru=?, din_kul_yanlis=?, din_kul_net=?,
                        ingilizce_dogru=?, ingilizce_yanlis=?, ingilizce_net=?,
                        matematik_dogru=?, matematik_yanlis=?, matematik_net=?,
                        fen_bil_dogru=?, fen_bil_yanlis=?, fen_bil_net=?,
                        toplam_net=?, lgs_puan=?,
                        class_rank=?, school_rank=?, district_rank=?, city_rank=?, general_rank=?
                       WHERE exam_id=? AND student_id=?""",
                    (student.turkce.dogru, student.turkce.yanlis, student.turkce.net,
                     student.ink_tar.dogru, student.ink_tar.yanlis, student.ink_tar.net,
                     student.din_kul.dogru, student.din_kul.yanlis, student.din_kul.net,
                     student.ingilizce.dogru, student.ingilizce.yanlis, student.ingilizce.net,
                     student.matematik.dogru, student.matematik.yanlis, student.matematik.net,
                     student.fen_bil.dogru, student.fen_bil.yanlis, student.fen_bil.net,
                     student.toplam_net, student.lgs_puan,
                     student.class_rank or 0, student.school_rank or 0,
                     student.district_rank or 0, student.city_rank or 0,
                     student.general_rank or 0,
                     exam_id, student_id)
                )

        self.conn.commit()
        return exam_id

    def get_all_exams(self) -> list:
        """Tüm sınavları listele."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM exams ORDER BY exam_date DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_all_students(self) -> list:
        """Tüm öğrencileri listele."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM students ORDER BY class_name, full_name")
        return [dict(row) for row in cursor.fetchall()]

    def get_student_scores(self, student_id: int) -> list:
        """Bir öğrencinin tüm sınav skorlarını getir."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT es.*, e.exam_name, e.exam_date
            FROM exam_scores es
            JOIN exams e ON es.exam_id = e.id
            WHERE es.student_id = ?
            ORDER BY e.exam_date
        """, (student_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_exam_scores(self, exam_id: int) -> list:
        """Bir sınavın tüm öğrenci skorlarını getir."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT es.*, s.full_name, s.class_name
            FROM exam_scores es
            JOIN students s ON es.student_id = s.id
            WHERE es.exam_id = ?
            ORDER BY es.toplam_net DESC
        """, (exam_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_student_by_name(self, full_name: str) -> Optional[dict]:
        """İsme göre öğrenci ara (canonical matching)."""
        cursor = self.conn.cursor()
        canonical = make_canonical_name(full_name)

        # Önce canonical name ile
        cursor.execute("SELECT * FROM students WHERE canonical_name = ?", (canonical,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        # Sonra tam isimle
        cursor.execute("SELECT * FROM students WHERE full_name = ?", (full_name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_exam_count(self) -> int:
        """Toplam sınav sayısı."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM exams")
        return cursor.fetchone()['cnt']

    def get_student_count(self) -> int:
        """Toplam öğrenci sayısı."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM students")
        return cursor.fetchone()['cnt']

    def get_canonical_duplicates(self) -> list:
        """Aynı canonical_name'e sahip farklı öğrencileri bul (debug amaçlı)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT canonical_name, COUNT(*) as cnt, GROUP_CONCAT(full_name, ' | ') as names
            FROM students
            WHERE canonical_name != ''
            GROUP BY canonical_name
            HAVING cnt > 1
        """)
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Bağlantıyı kapat."""
        self.conn.close()
