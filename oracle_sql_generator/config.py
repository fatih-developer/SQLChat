"""
Oracle veritabanı bağlantı ayarları ve yapılandırma.
"""

# Oracle bağlantı bilgileri
ORACLE_CONFIG = {
    "username": "kullanici_adi",
    "password": "sifre",
    "host": "localhost",
    "port": "1521",
    "service_name": "ORCL"
}

# Model ayarları
MODEL_CONFIG = {
    "model_name": "gemma3:4b",
    "base_url": "http://127.0.0.1:11434",
    "temperature": 0.1,
    "top_p": 0.9,
    "top_k": 40,
    "num_ctx": 2048,
    "num_thread": 4,
    "request_timeout": 30.0
}

# Prompt şablonu
SQL_PROMPT_TEMPLATE = """
Sen bir Oracle SQL sorgu oluşturucususun. Veritabanı şeması ve kullanıcının Türkçe sorusu verildiğinde, Oracle uyumlu bir SQL sorgusu oluştur. 
SADECE SQL ifadesini döndür, başka hiçbir şey yazma. Açıklama gerekmez.

VERİTABANI ŞEMASI:
{schema}

ÖNEMLİ NOTLAR:
1. Tablo isimlerini büyük harfle yazın (Oracle case-sensitive'dir).
2. Alan isimlerini büyük harfle yazın.
3. Tablolar arası ilişkileri doğru kurun (foreign key'leri kullanın).
4. Sorgunun sonunda noktalı virgül (;) kullanmayın.
5. Oracle SQL sözdizimine uygun yazın.
6. Sütun isimlerinde özel karakter varsa çift tırnak içinde yazın.

Kullanici sorusu: {query}

SQL Sorgusu:
"""
