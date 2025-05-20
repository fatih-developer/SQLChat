"""
Yardımcı fonksiyonlar için modül.
"""
import tempfile
import os
from typing import Optional, Union
import pandas as pd

def save_temp_csv(result: Union[pd.DataFrame, str]) -> Optional[str]:
    """Sonuçları geçici bir CSV dosyasına kaydeder.
    
    Args:
        result: Kaydedilecek veri (DataFrame veya metin)
        
    Returns:
        Oluşturulan dosyanın yolu veya None
    """
    if isinstance(result, pd.DataFrame) and not result.empty:
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "oracle_query_result.csv")
        result.to_csv(temp_file, index=False, encoding='utf-8-sig')
        return temp_file
    return None

def clear_temp_files():
    """Geçici dosyaları temizler."""
    temp_dir = tempfile.gettempdir()
    for filename in os.listdir(temp_dir):
        if filename.startswith("oracle_query_result") and filename.endswith(".csv"):
            try:
                os.remove(os.path.join(temp_dir, filename))
            except Exception as e:
                print(f"Dosya silinirken hata oluştu {filename}: {e}")

def format_error_message(error: Exception) -> str:
    """Hata mesajını kullanıcı dostu bir formata dönüştürür."""
    error_msg = str(error)
    
    # Oracle hata mesajlarını daha anlaşılır hale getir
    if "ORA-" in error_msg:
        # Oracle hata kodu ve mesajını ayır
        import re
        match = re.search(r'ORA-\d+: (.+)', error_msg)
        if match:
            error_msg = f"Oracle Hatası: {match.group(1)}"
    
    return error_msg
