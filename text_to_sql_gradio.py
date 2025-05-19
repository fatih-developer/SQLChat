import re
import gradio as gr
from sqlalchemy import create_engine, inspect
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

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

def get_db_engine():
    return create_engine(db_url)

def extract_schema(db_url):
    """Veritabanı şemasını detaylı bir şekilde çıkarır."""
    engine = get_db_engine()
    inspector = inspect(engine)
    schema = {'tables': {}, 'foreign_keys': []}

    with engine.connect() as conn:
        from sqlalchemy import text
        tables = inspector.get_table_names()
        
        for table_name in tables:
            # Sütun bilgilerini al
            columns = []
            primary_keys = []
            
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
        for fk in table_info['foreign_keys']:
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
        import pandas as pd
        engine = create_engine(db_url)
        with engine.connect() as conn:
            df = pd.read_sql_query(sql, conn)
            return df
    except Exception as e:
        return f"Sorgu çalıştırılırken hata oluştu: {str(e)}"

# Arayüz fonksiyonları
def save_temp_csv(result):
    """Sonuçları geçici bir CSV dosyasına kaydeder"""
    import tempfile
    import os
    
    # Önceki geçici dosyaları temizle
    for f in os.listdir(tempfile.gettempdir()):
        if f.startswith('sql_query_result_') and f.endswith('.csv'):
            try:
                os.remove(os.path.join(tempfile.gettempdir(), f))
            except:
                pass
    
    # Yeni bir geçici dosya oluştur
    temp_file = tempfile.NamedTemporaryFile(
        mode='w', 
        suffix='.csv', 
        prefix='sql_query_result_',
        delete=False,
        encoding='utf-8-sig'
    )
    
    # Sonuçları CSV olarak yaz
    result.to_csv(temp_file, index=False, encoding='utf-8-sig')
    temp_file.close()
    
    return temp_file.name

def generate_sql(query, show_schema):
    """Kullanıcı sorusundan SQL oluştur"""
    try:
        sql = to_sql_query(query, schema)
        result = execute_query(sql)
        
        output = f"**Oluşturulan SQL Sorgusu:**\n```sql\n{sql}\n```\n\n"
        
        if isinstance(result, str):  # Hata durumu
            output += f"**Hata:** {result}"
            return output, None
        else:
            output += f"**Sorgu Sonucu (Toplam {len(result)} kayıt):**\n"
            output += result.to_markdown(index=False)
            
            # CSV olarak kaydet
            try:
                csv_path = save_temp_csv(result)
                return output, csv_path
            except Exception as e:
                output += f"\n\n**Uyarı:** Sonuçlar kaydedilemedi: {str(e)}"
                return output, None
        
    except Exception as e:
        return f"Bir hata oluştu: {str(e)}", None

# Gradio arayüzünü oluştur
with gr.Blocks(title="Metinden SQL Sorgu Oluşturucu") as demo:
    gr.Markdown("# Metinden SQL Sorgu Oluşturucu")
    
    with gr.Row():
        query = gr.Textbox(
            label="SQL sorgusuna dönüştürmek istediğiniz metni girin:",
            placeholder="Örnek: Müşteri tablosundaki tüm kayıtları getir",
            lines=3
        )
    
    with gr.Row():
        show_schema = gr.Checkbox(label="Veritabanı şemasını göster", value=False)
        submit_btn = gr.Button("Sorguyu Oluştur", variant="primary")
    
    # Durum göstergesi
    status = gr.Textbox(
        label="Durum",
        value="Hazır",
        interactive=False,
        show_label=True
    )
    
    output = gr.Markdown()
    download_btn = gr.File(visible=False, label="Sonuçları İndir (CSV)")
    
    def update_ui(query, show_schema, status_text):
        try:
            # Sorguyu çalıştır
            output_text, file_path = generate_sql(query, show_schema)
            
            if show_schema and file_path is not None:
                schema_text = format_schema_for_prompt(schema)
                output_text += f"\n\n**Veritabanı Şeması:**\n```\n{schema_text}\n```"
            
            # Durum mesajını belirle
            if "Hata:" in output_text or "hata" in output_text.lower():
                status_msg = "❌ Hata oluştu!"
            else:
                status_msg = "✅ Sorgu başarıyla oluşturuldu!"
            
            if file_path:
                return output_text, file_path, status_msg
            return output_text, None, status_msg
            
        except Exception as e:
            error_msg = f"❌ Hata: {str(e)}"
            return f"Bir hata oluştu: {str(e)}", None, error_msg
    
    # Buton tıklandığında çalışacak fonksiyon
    def on_click(query, show_schema):
        # İşlem başladığında butonu devre dışı bırak
        submit_btn = gr.update(interactive=False, variant="secondary")
        status_msg = "⏳ Sorgu oluşturuluyor..."
        return submit_btn, status_msg
    
    # Buton tıklandığında
    submit_event = submit_btn.click(
        fn=on_click,
        inputs=[query, show_schema],
        outputs=[submit_btn, status],
        queue=False
    ).then(
        fn=update_ui,
        inputs=[query, show_schema, status],
        outputs=[output, download_btn, status],
        queue=True
    )
    
    # Butonu tekrar etkinleştir
    submit_event.then(
        lambda: gr.update(interactive=True, variant="primary"),
        outputs=[submit_btn],
        queue=False
    )
    
    # Enter tuşu ile de göndermeyi etkinleştir
    query.submit(
        fn=on_click,
        inputs=[query, show_schema],
        outputs=[submit_btn, status],
        queue=False
    ).then(
        fn=update_ui,
        inputs=[query, show_schema, status],
        outputs=[output, download_btn, status],
        queue=True
    ).then(
        lambda: gr.update(interactive=True, variant="primary"),
        outputs=[submit_btn],
        queue=False
    )

# Veritabanı şemasını yükle
print("Veritabanı şeması yükleniyor...")
schema = extract_schema(db_url)
print("Veritabanı şeması yüklendi. Tablolar:", list(schema['tables'].keys()))

# Uygulamayı başlat
if __name__ == "__main__":
    demo.launch(share=False, server_name="0.0.0.0")
