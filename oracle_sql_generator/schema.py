"""
Veritabanı şema işlemleri için modül.
"""
from typing import Dict, Any, List
from sqlalchemy import inspect
from .db import get_db_engine
from .config import ORACLE_CONFIG

def extract_schema() -> Dict[str, Any]:
    """Oracle veritabanı şemasını çıkarır."""
    engine = get_db_engine()
    inspector = inspect(engine)
    schema = {'tables': {}, 'foreign_keys': []}
    
    with engine.connect() as conn:
        # Kullanıcının erişebildiği tabloları al
        tables = inspector.get_table_names(schema=ORACLE_CONFIG["username"].upper())
        
        for table_name in tables:
            try:
                # Sütun bilgilerini al
                columns = []
                primary_keys = inspector.get_pk_constraint(table_name, schema=ORACLE_CONFIG["username"].upper())
                pk_columns = primary_keys.get('constrained_columns', [])
                
                # Sütun detaylarını al
                columns_info = inspector.get_columns(table_name, schema=ORACLE_CONFIG["username"].upper())
                for col in columns_info:
                    columns.append({
                        'name': col['name'],
                        'type': str(col['type']),
                        'nullable': col['nullable'],
                        'default': col.get('default'),
                        'primary_key': col['name'] in pk_columns
                    })
                
                # Foreign key bilgilerini al
                fks = inspector.get_foreign_keys(table_name, schema=ORACLE_CONFIG["username"].upper())
                
                schema['tables'][table_name] = {
                    'columns': columns,
                    'primary_key': pk_columns,
                    'foreign_keys': fks
                }
                
                # Global foreign key listesine ekle
                for fk in fks:
                    schema['foreign_keys'].append({
                        'table': table_name,
                        'columns': fk['constrained_columns'],
                        'foreign_table': fk['referred_table'],
                        'foreign_columns': fk['referred_columns']
                    })
                    
            except Exception as e:
                print(f"Tablo {table_name} işlenirken hata: {str(e)}")
                continue
    
    return schema

def format_schema_for_prompt(schema: Dict[str, Any]) -> str:
    """Şema bilgisini prompt için düzenlenmiş bir metne dönüştürür.
    
    Args:
        schema: extract_schema() fonksiyonundan dönen şema sözlüğü
        
    Returns:
        İnsan tarafından okunabilir şema metni
    """
    schema_text = []
    
    for table_name, table_info in schema['tables'].items():
        table_header = f"\n### {table_name} Tablosu"
        
        # Sütun bilgileri
        columns_info = []
        for col in table_info['columns']:
            col_info = f"- {col['name']}: {col['type']}"
            if col['primary_key']:
                col_info += " (PRIMARY KEY)"
            if not col['nullable']:
                col_info += " NOT NULL"
            if col['default'] is not None:
                col_info += f" DEFAULT {col['default']}"
            columns_info.append(col_info)
        
        # Foreign key ilişkileri
        fk_info = []
        for fk in table_info.get('foreign_keys', []):
            fk_info.append(
                f"- {', '.join(fk['constrained_columns'])} → "
                f"{fk['referred_table']}({', '.join(fk['referred_columns'])})"
            )
        
        # Tüm bilgileri birleştir
        table_info_text = [table_header]
        table_info_text.extend(columns_info)
        if fk_info:
            table_info_text.append("\n  İlişkiler:")
            table_info_text.extend(fk_info)
        
        schema_text.append("\n".join(table_info_text))
    
    return "\n\n".join(schema_text)
