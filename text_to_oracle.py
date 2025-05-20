import re
import gradio as gr
import cx_Oracle
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

# Oracle bağlantı bilgileri
ORACLE_CONFIG = {
    "username": "kullanici_adi",
    "password": "sifre",
    "host": "localhost",
    "port": "1521",
    "service_name": "ORCL"
}

# SQLAlchemy bağlantı URL'si oluştur
def get_oracle_url():
    return URL.create(
        "oracle+cx_oracle",
        username=ORACLE_CONFIG["username"],
        password=ORACLE_CONFIG["password"],
        host=ORACLE_CONFIG["host"],
        port=ORACLE_CONFIG["port"],
        database=ORACLE_CONFIG["service_name"]
    )

# Oracle bağlantısı için engine oluştur
def get_db_engine():
    return create_engine(get_oracle_url())

# Prompt şablonu
template = """
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

# Modeli başlat
try:
    model = OllamaLLM(
        model="gemma3:4b",
        base_url="http://127.0.0.1:11434",
        temperature=0.1,
        top_p=0.9,
        top_k=40,
        num_ctx=2048,
        num_thread=4,
        request_timeout=30.0
    )
    model.invoke("test")  # Bağlantı testi
except Exception as e:
    print(f"Ollama bağlantı hatası: {e}")
    print("Lütfen Ollama'nın çalıştığından emin olun: 'ollama serve'")
    import sys
    sys.exit(1)

def extract_schema():
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

def format_schema_for_prompt(schema):
    """Şema bilgisini prompt için düzenlenmiş bir metne dönüştürür"""
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

def clean_text(text: str):
    # Markdown kod bloklarını temizle
    text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    
    # Eğer hala SQL ifadesi içeriyorsa sadece SQL kısmını al
    sql_match = re.search(r'(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE).*', 
                         text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        text = sql_match.group(0)
    
    return text.strip()

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
    
    return clean_text(response)

def execute_query(sql):
    """SQL sorgusunu çalıştır ve sonuçları döndür"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Sadece SELECT sorguları için pandas kullan
            if sql.strip().upper().startswith('SELECT'):
                df = pd.read_sql_query(text(sql), conn)
                return df
            else:
                # DML işlemleri için
                result = conn.execute(text(sql))
                conn.commit()
                return f"İşlem başarılı. Etkilenen satır sayısı: {result.rowcount}"
    except Exception as e:
        return f"Sorgu çalıştırılırken hata oluştu: {str(e)}"

# Arayüz fonksiyonları
def save_temp_csv(result):
    """Sonuçları geçici bir CSV dosyasına kaydeder"""
    import tempfile
    import os
    import pandas as pd
    
    if isinstance(result, pd.DataFrame):
        # Pandas DataFrame ise doğrudan CSV'ye kaydet
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "oracle_query_result.csv")
        result.to_csv(temp_file, index=False, encoding='utf-8-sig')
        return temp_file
    return None

def generate_sql(query, show_schema):
    """Kullanıcı sorusundan SQL oluştur"""
    try:
        # Veritabanı şemasını al
        schema = extract_schema()
        
        # Şemayı göster
        schema_text = format_schema_for_prompt(schema) if show_schema else "Şema gösterilmiyor"
        
        # SQL sorgusunu oluştur
        sql_query = to_sql_query(query, schema)
        
        return sql_query, schema_text, "SQL sorgusu başarıyla oluşturuldu."
    except Exception as e:
        return "", f"Hata oluştu: {str(e)}", ""

# Gradio arayüzünü oluştur
with gr.Blocks(title="Metinden Oracle SQL Sorgu Oluşturucu") as demo:
    gr.Markdown("# Metinden Oracle SQL Sorgu Oluşturucu")
    
    with gr.Row():
        with gr.Column(scale=2):
            query = gr.Textbox(
                label="Soru",
                placeholder="Örnek: Maaşı 5000'den yüksek olan çalışanları listele",
                lines=3
            )
            
            with gr.Row():
                submit_btn = gr.Button("Sorguyu Oluştur", variant="primary")
                clear_btn = gr.Button("Temizle")
            
            sql_output = gr.Code(
                label="Oluşturulan SQL",
                language="sql",
                interactive=True,
                lines=5
            )
            
            status = gr.Textbox(label="Durum", interactive=False)
        
        with gr.Column(scale=1):
            show_schema = gr.Checkbox(label="Şemayı Göster", value=True)
            schema_output = gr.Textbox(
                label="Veritabanı Şeması",
                lines=20,
                max_lines=20,
                interactive=False
            )
    
    # Sonuçlar bölümü
    with gr.Row():
        results = gr.Dataframe(
            label="Sorgu Sonuçları",
            headers=[],
            datatype=["str"]*10,
            max_rows=50,
            wrap=True
        )
    
    # Dosya indirme bağlantısı
    download_btn = gr.File(label="Sonuçları İndir", visible=False)
    
    def update_ui(query, show_schema, status_text):
        """Arayüzü günceller"""
        if not query.strip():
            return "", "", "", None, False, status_text
        
        sql, schema_text, status_msg = generate_sql(query, show_schema)
        
        # Sonuçları göster
        if sql:
            try:
                result = execute_query(sql)
                if isinstance(result, pd.DataFrame) and not result.empty:
                    download_file = save_temp_csv(result)
                    return sql, schema_text, result, download_file, True, status_msg
                else:
                    return sql, schema_text, result, None, False, status_msg
            except Exception as e:
                return sql, schema_text, f"Sorgu çalıştırılırken hata: {str(e)}", None, False, status_msg
        else:
            return sql, schema_text, "", None, False, status_msg
    
    # Buton tıklandığında çalışacak fonksiyon
    def on_click(query, show_schema):
        return update_ui(query, show_schema, "Sorgu oluşturuluyor...")
    
    # Buton tıklandığında
    submit_event = submit_btn.click(
        fn=on_click,
        inputs=[query, show_schema],
        outputs=[sql_output, schema_output, results, download_btn, gr.update(visible=True), status]
    )
    
    # Temizle butonu
    def clear_all():
        return "", "", "", None, False, ""
    
    clear_btn.click(
        fn=clear_all,
        outputs=[query, sql_output, results, download_btn, gr.update(visible=False), status]
    )
    
    # Şema göster/gizle değiştiğinde
    show_schema.change(
        fn=lambda x, y: (y, x, "", None, False, ""),
        inputs=[query, show_schema],
        outputs=[query, show_schema, schema_output, download_btn, gr.update(visible=False), status]
    )

# Uygulamayı başlat
if __name__ == "__main__":
    # Oracle Instant Client yolu (gerekirse)
    # cx_Oracle.init_oracle_client(lib_dir="path_to_oracle_instant_client")
    
    try:
        # Bağlantı testi
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM DUAL"))
        print("Oracle veritabanına başarıyla bağlanıldı.")
        
        # Uygulamayı başlat
        demo.launch()
    except Exception as e:
        print(f"Oracle veritabanına bağlanılamadı: {str(e)}")
        print("Lütfen bağlantı bilgilerini kontrol edin ve Oracle Instant Client'ın kurulu olduğundan emin olun.")
