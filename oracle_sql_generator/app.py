"""
Ana uygulama modülü - Gradio arayüzü.
"""
import gradio as gr
from typing import Tuple, Optional
import pandas as pd

from .db import execute_query, test_connection
from .schema import extract_schema, format_schema_for_prompt
from .llm import LLMHandler
from .utils import save_temp_csv, clear_temp_files

class OracleSQLApp:
    """Oracle SQL oluşturucu uygulama sınıfı."""
    
    def __init__(self):
        """Uygulamayı başlat."""
        self.llm_handler = LLMHandler()
        self.schema = None
        self.schema_text = ""
        
        # Uygulama başlatıldığında şemayı yükle
        self.load_schema()
    
    def load_schema(self):
        """Veritabanı şemasını yükler."""
        try:
            self.schema = extract_schema()
            self.schema_text = format_schema_for_prompt(self.schema)
            print("Veritabanı şeması başarıyla yüklendi.")
        except Exception as e:
            print(f"Şema yüklenirken hata oluştu: {e}")
            self.schema = None
            self.schema_text = "Şema yüklenemedi."
    
    def generate_sql(self, query: str, show_schema: bool) -> Tuple[str, str, str]:
        """Kullanıcı sorusundan SQL oluşturur.
        
        Args:
            query: Kullanıcı sorusu
            show_schema: Şemayı gösterip göstermeme durumu
            
        Returns:
            (sql_query, schema_text, status_message)
        """
        if not query.strip():
            return "", self.schema_text if show_schema else "Şema gösterilmiyor.", ""
        
        try:
            # SQL oluştur
            sql_query = self.llm_handler.generate_sql(query, self.schema_text)
            
            # Şema metnini hazırla
            schema_display = self.schema_text if show_schema else "Şema gösterilmiyor."
            
            return sql_query, schema_display, "SQL sorgusu başarıyla oluşturuldu."
        except Exception as e:
            return "", "", f"Hata oluştu: {str(e)}"
    
    def execute_and_display(self, query: str, show_schema: bool):
        """SQL oluştur, çalıştır ve sonuçları göster."""
        if not query.strip():
            return "", "", "", None, False, ""
        
        try:
            # SQL oluştur
            sql, schema_text, status_msg = self.generate_sql(query, show_schema)
            
            if not sql:
                return "", schema_text, "", None, False, status_msg
            
            # Sorguyu çalıştır
            result = execute_query(sql)
            
            # Sonuçları işle
            download_file = None
            show_download = False
            
            if isinstance(result, pd.DataFrame) and not result.empty:
                download_file = save_temp_csv(result)
                show_download = True
            
            return sql, schema_text, result, download_file, show_download, status_msg
            
        except Exception as e:
            return sql, schema_text, f"Sorgu çalıştırılırken hata: {str(e)}", None, False, status_msg
    
    def create_ui(self):
        """Gradio kullanıcı arayüzünü oluşturur."""
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
            
            # Buton tıklandığında
            submit_event = submit_btn.click(
                fn=self.execute_and_display,
                inputs=[query, show_schema],
                outputs=[sql_output, schema_output, results, download_btn, gr.update(visible=True), status]
            )
            
            # Temizle butonu
            def clear_all():
                clear_temp_files()
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
            
            # Sayfa yüklendiğinde şemayı göster
            demo.load(
                fn=lambda: (self.schema_text, ""),
                outputs=[schema_output, status]
            )
            
        return demo

def main():
    """Uygulamayı başlat."""
    # Oracle bağlantısını test et
    if not test_connection():
        print("Oracle veritabanına bağlanılamadı. Lütfen bağlantı ayarlarını kontrol edin.")
        return
    
    try:
        # Uygulamayı başlat
        app = OracleSQLApp()
        demo = app.create_ui()
        
        print("Uygulama başlatılıyor...")
        print("Tarayıcıda http://localhost:7860 adresini açabilirsiniz.")
        
        demo.launch()
    except Exception as e:
        print(f"Uygulama başlatılırken hata oluştu: {e}")
    finally:
        # Temizlik işlemleri
        clear_temp_files()

if __name__ == "__main__":
    main()
