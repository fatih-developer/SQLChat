"""
Dil modeli işlemleri için modül.
"""
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from .config import MODEL_CONFIG, SQL_PROMPT_TEMPLATE

class LLMHandler:
    """Dil modeli işlemlerini yöneten sınıf."""
    
    def __init__(self):
        """Modeli başlat."""
        try:
            self.model = OllamaLLM(**MODEL_CONFIG)
            # Bağlantı testi
            self.model.invoke("test")
        except Exception as e:
            print(f"Ollama bağlantı hatası: {e}")
            print("Lütfen Ollama'nın çalıştığından emin olun: 'ollama serve'")
            raise
    
    def clean_sql_output(self, text: str) -> str:
        """Model çıktısından SQL ifadesini temizler.
        
        Args:
            text: Modelin ham çıktısı
            
        Returns:
            Temizlenmiş SQL ifadesi
        """
        # Markdown kod bloklarını temizle
        text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = text.strip()
        
        # Eğer hala SQL ifadesi içeriyorsa sadece SQL kısmını al
        sql_match = re.search(
            r'(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE).*', 
            text, re.DOTALL | re.IGNORECASE
        )
        if sql_match:
            text = sql_match.group(0)
        
        return text.strip()
    
    def generate_sql(self, query: str, schema_text: str) -> str:
        """Doğal dil sorusundan SQL sorgusu oluşturur.
        
        Args:
            query: Kullanıcının doğal dil sorusu
            schema_text: Veritabanı şema metni
            
        Returns:
            Oluşturulan SQL sorgusu
        """
        # Prompt'u oluştur
        prompt = ChatPromptTemplate.from_template(SQL_PROMPT_TEMPLATE)
        chain = prompt | self.model
        
        # Sorguyu çalıştır
        response = chain.invoke(
            {"query": query, "schema": schema_text},
            config={"max_tokens": 500}
        )
        
        # Çıktıyı temizle ve döndür
        return self.clean_sql_output(response)
