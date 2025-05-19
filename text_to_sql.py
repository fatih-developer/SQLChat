import json
import re
import warnings

# LangChain uyarılarını filtrele
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")

import streamlit as st
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from sqlalchemy import create_engine, inspect

db_url = "sqlite:///Northwind_small.sqlite"

template = """
Sen bir SQL sorgu oluşturucususun. Veritabanı şeması ve kullanıcının Türkçe sorusu verildiğinde, SQLite uyumlu bir SQL sorgusu oluştur. 
SADECE SQL ifadesini döndür, başka hiçbir şey yazma. Açıklama gerekmez.

VERİTABANI ŞEMASI:
{schema}

ÖNEMLİ NOTLAR:
1. Tablo isimlerini doğru yazmaya dikkat edin (büyük/küçük harf duyarlı olabilir).
2. Alan isimlerini tam olarak verildiği gibi kullanın.
3. Tablolar arası ilişkileri doğru kurun (foreign key'leri kullanın).
4. Sorgunun sonunda noktalı virgül (;) kullanmayın.
5. SQLite sözdizimine uygun yazın.
6. Sütun isimlerinde boşluk veya özel karakter varsa köşeli parantez içinde yazın (örneğin: [Unit Price]).

Kullanici sorusu: {query}

SQL Sorgusu:
"""

try:
    # Gemma3 4B modelini kullanıyoruz
    model = OllamaLLM(
        model="gemma3:4b",
        base_url="http://127.0.0.1:11434",
        temperature=0.1,     # Düşük sıcaklık daha tutarlı yanıtlar için
        top_p=0.9,          # Daha hızlı yanıt için
        top_k=40,           # Daha iyi çeşitlilik için
        num_ctx=2048,       # Bağlam penceresi
        num_thread=4,       # CPU thread sayısı
        request_timeout=30.0 # Zaman aşımı
    )
    # Bağlantıyı test et
    model.invoke("test")
except Exception as e:
    print(f"Ollama bağlantı hatası: {e}")
    print("Lütfen Ollama'nın çalıştığından emin olun: 'ollama serve'")
    import sys
    sys.exit(1)

# Veritabanı bağlantısını önbelleğe al
@st.cache_resource
def get_db_engine():
    return create_engine(db_url)

@st.cache_data(ttl=3600)  # 1 saat süreyle önbellekte tut
def extract_schema(db_url):
    """Veritabanı şemasını detaylı bir şekilde çıkarır.
    
    Returns:
        dict: Tablo isimlerini anahtar, sütun bilgilerini değer olarak içeren sözlük.
        Her sütun bilgisi, sütun adı, veri tipi ve nullable bilgisini içerir.
    """
    engine = get_db_engine()
    inspector = inspect(engine)
    schema = {
        'tables': {},
        'foreign_keys': []
    }

    # SQLite için özel sorgu ile tablo bilgilerini al
    with engine.connect() as conn:
        from sqlalchemy import text
        
        # Tabloları al
        tables = inspector.get_table_names()
        
        for table_name in tables:
            # Sütun bilgilerini al
            columns = []
            primary_keys = []
            
            # SQLite'da sütun bilgilerini al
            cursor = conn.execute(text(f'PRAGMA table_info("{table_name}")'))
            for col in cursor.mappings().all():
                is_primary = bool(col['pk'])
                columns.append({
                    'name': col['name'],
                    'type': col['type'],
                    'nullable': not bool(col['notnull']),
                    'default': col['dflt_value'],
                    'primary_key': is_primary
                })
                if is_primary:
                    primary_keys.append(col['name'])
            
            # Foreign key bilgilerini al
            fks = []
            cursor = conn.execute(text(f'PRAGMA foreign_key_list("{table_name}")'))
            for fk in cursor.mappings().all():
                fk_info = {
                    'constrained_columns': [fk['from']],
                    'referred_table': fk['table'],
                    'referred_columns': [fk['to']]
                }
                fks.append(fk_info)
                
                # Genel foreign key listesine ekle
                schema['foreign_keys'].append({
                    'table': table_name,
                    'columns': [fk['from']],
                    'foreign_table': fk['table'],
                    'foreign_columns': [fk['to']]
                })
            
            # Tablo DDL'sini al
            cursor = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
                {'name': table_name}
            )
            ddl = cursor.first()
            
            schema['tables'][table_name] = {
                'columns': columns,
                'primary_key': primary_keys,
                'foreign_keys': fks,
                'ddl': ddl[0] if ddl else None
            }
    
    return schema

def format_schema_for_prompt(schema):
    """Şema bilgisini prompt için düzenlenmiş bir metne dönüştürür"""
    schema_text = []
    
    # Her tablo için bilgileri topla
    for table_name, table_info in schema['tables'].items():
        # Tablo başlığı
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
        for fk in table_info['foreign_keys']:
            fk_info.append(
                f"- {', '.join(fk['constrained_columns'])} → "
                f"{fk['referred_table']}({', '.join(fk['referred_columns'])})"
            )
        
        # Tüm bilgileri birleştir
        table_info = [table_header]
        table_info.extend(columns_info)
        if fk_info:
            table_info.append("\n  İlişkiler:")
            table_info.extend(fk_info)
        
        schema_text.append("\n".join(table_info))
    
    return "\n\n".join(schema_text)

@st.cache_data(ttl=300)  # 5 dakika süreyle önbellekte tut
def to_sql_query(query, schema):
    # Şema bilgisini formatla
    formatted_schema = format_schema_for_prompt(schema)
    
    # Prompt'u oluştur
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    
    # Sorguyu çalıştır
    response = chain.invoke({
        "query": query, 
        "schema": formatted_schema
    }, config={"max_tokens": 500})
    
    # Sonucu temizle ve döndür
    return clean_text(response)

def clean_text(text: str):
    # Markdown kod bloklarını temizle
    text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
    
    # Diğer temizlik işlemleri
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    
    # Eğer hala SQL ifadesi içeriyorsa sadece SQL kısmını al
    sql_match = re.search(r'(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE).*', text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        text = sql_match.group(0)
    
    return text.strip()

# Veritabanı şemasını al ve önbelleğe al
schema = extract_schema(db_url)

# Şema bilgilerini yazdır (debug için)
print("Veritabanı şeması yüklendi. Tablolar:", list(schema['tables'].keys()))

# Şema özetini göster (isteğe bağlı)
if 'show_schema_summary' not in st.session_state:
    st.session_state.show_schema_summary = False

if st.sidebar.button("Veritabanı Şemasını Göster"):
    st.session_state.show_schema_summary = not st.session_state.show_schema_summary

if st.session_state.show_schema_summary:
    with st.sidebar.expander("📊 Veritabanı Şema Özeti", expanded=True):
        for table_name, table_info in schema['tables'].items():
            st.subheader(f"📌 {table_name}")
            st.write("**Sütunlar:**")
            for col in table_info['columns']:
                pk = "🔑" if col['primary_key'] else ""
                nullable = "NULL" if col['nullable'] else "NOT NULL"
                st.write(f"- {pk} `{col['name']}`: {col['type']} {nullable}")
            
            if table_info['foreign_keys']:
                st.write("\n**İlişkiler:**")
                for fk in table_info['foreign_keys']:
                    st.write(f"- {' + '.join(fk['constrained_columns'])} → {fk['referred_table']}({', '.join(fk['referred_columns'])})")
            
            if 'ddl' in table_info and table_info['ddl']:
                if st.button(f"📝 {table_name} Tablo Tanımını Göster"):
                    st.session_state[f'show_ddl_{table_name}'] = not st.session_state.get(f'show_ddl_{table_name}', False)
                
                if st.session_state.get(f'show_ddl_{table_name}', False):
                    st.code(table_info['ddl'])
            
            st.markdown("---")

st.title("Metinden SQL Sorgu Oluşturucu")

# Metin alanı ve gönder butonu
query = st.text_area(
    "Veritabanından çekmek istediğiniz veriyi Türkçe olarak yazın:",
    help="Sorgunuzu yazdıktan sonra göndermek için 'Sorguyu Çalıştır' butonuna tıklayın. Alt satıra geçmek için Ctrl+Enter kullanın.",
    key="query_input"
)

# Sorguyu göndermek için buton
submit_button = st.button("Sorguyu Çalıştır")

if query and (submit_button or st.session_state.get('auto_submit', False)):
    with st.spinner('SQL sorgusu oluşturuluyor...'):
        sql = to_sql_query(query, schema)
    
    st.subheader("Oluşturulan SQL Sorgusu:")
    st.code(sql, language="sql")
    
    # SQL sorgusunu çalıştır ve sonuçları göster
    try:
        import pandas as pd
        from sqlalchemy import text
        
        engine = create_engine(db_url)
        try:
            # SQLAlchemy bağlantısını kullanarak sorguyu çalıştır
            with engine.connect() as conn:
                # Sorguyu çalıştır ve sonuçları DataFrame'e aktar
                df = pd.read_sql_query(sql, conn)
                
                st.subheader("Sorgu Sonuçları:")
                st.dataframe(df)
                
                # Sonuçları indirme bağlantısı ekle
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="Sonuçları İndir (CSV)",
                    data=csv,
                    file_name='sorgu_sonuclari.csv',
                    mime='text/csv',
                )
                
        except Exception as e:
            st.error(f"Sorgu çalıştırılırken hata oluştu: {str(e)}")
            # Hata ayıklama için SQL sorgusunu da göster
            st.text("SQL Sorgusu:")
            st.code(sql, language="sql")
            
    except Exception as e:
        st.error(f"Sorgu çalıştırılırken hata oluştu: {str(e)}")



