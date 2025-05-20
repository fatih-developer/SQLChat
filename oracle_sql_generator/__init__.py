"""
Oracle SQL Oluşturucu Uygulaması

Bu modül, doğal dildeki soruları Oracle SQL sorgularına dönüştüren bir araç sağlar.
Kullanıcılar basit Türkçe cümlelerle veritabanı sorguları oluşturabilir.
"""

__version__ = "0.1.0"

from .app import OracleSQLApp, main
from .db import get_db_engine, execute_query, test_connection
from .schema import extract_schema, format_schema_for_prompt
from .llm import LLMHandler
from .utils import save_temp_csv, clear_temp_files

__all__ = [
    'OracleSQLApp',
    'main',
    'get_db_engine',
    'execute_query',
    'test_connection',
    'extract_schema',
    'format_schema_for_prompt',
    'LLMHandler',
    'save_temp_csv',
    'clear_temp_files'
]
