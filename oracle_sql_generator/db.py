"""
Veritabanı bağlantı ve işlemleri için modül.
"""
import os
import oracledb
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL
from typing import Dict, Any, List, Optional
import pandas as pd

from .config import ORACLE_CONFIG

# Oracle Instant Client yolunu ayarla
ORACLE_CLIENT_DIR = r"C:\oracle\instantclient_19_19"  # Kendi kurulum yolunuza göre güncelleyin
os.environ["PATH"] = ORACLE_CLIENT_DIR + os.pathsep + os.environ["PATH"]

# Oracle Client'ı başlat
try:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_DIR)
except Exception as e:
    print(f"Oracle Client başlatılırken hata: {e}")
    print("Oracle Instant Client kurulu değil veya yolu yanlış olabilir.")

def get_oracle_url() -> URL:
    """Oracle veritabanı için bağlantı URL'si oluşturur."""
    return URL.create(
        "oracle+oracledb",
        username=ORACLE_CONFIG["username"],
        password=ORACLE_CONFIG["password"],
        host=ORACLE_CONFIG["host"],
        port=ORACLE_CONFIG["port"],
        service_name=ORACLE_CONFIG["service_name"]
    )

def get_db_engine():
    """Veritabanı bağlantısı için SQLAlchemy engine'ini döndürür."""
    return create_engine(
        get_oracle_url(),
        thick_mode={
            'lib_dir': ORACLE_CLIENT_DIR
        },
        max_identifier_length=128  # Oracle'ın maksimum tanımlayıcı uzunluğu
    )

def execute_query(sql: str):
    """SQL sorgusunu çalıştır ve sonuçları döndür.
    
    Args:
        sql: Çalıştırılacak SQL sorgusu
        
    Returns:
        SELECT sorguları için DataFrame, diğerleri için etkilenen satır sayısı
    """
    engine = get_db_engine()
    with engine.connect() as conn:
        # Sadece SELECT sorguları için pandas kullan
        if sql.strip().upper().startswith('SELECT'):
            return pd.read_sql_query(text(sql), conn)
        else:
            # DML işlemleri için
            result = conn.execute(text(sql))
            conn.commit()
            return f"İşlem başarılı. Etkilenen satır sayısı: {result.rowcount}"

def test_connection() -> bool:
    """Veritabanı bağlantısını test eder."""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 FROM DUAL")).scalar()
            if result == 1:
                print("Oracle veritabanına başarıyla bağlanıldı.")
                return True
            return False
    except Exception as e:
        print(f"Veritabanı bağlantı hatası: {e}")
        print("Lütfen aşağıdakileri kontrol edin:")
        print(f"1. Oracle Instant Client yolu doğru mu? ({ORACLE_CLIENT_DIR})")
        print("2. Veritabanı bilgileri doğru mu?")
        print("3. Ağ bağlantısı var mı?")
        print(f"Hata detayı: {str(e)}")
        return False
